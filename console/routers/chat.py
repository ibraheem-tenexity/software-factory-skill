"""Concierge chat: /api/chat (send), /api/chat/{pid}/history, /api/chat/{pid}/deps."""
import asyncio
import json
import logging
import os
import time

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from software_factory.data_transfer_objects.chat_agent import ChatMessage
from software_factory.conversation.persistence import (
    chat_history as _chat_history,
    persist_chat_turn as _persist_chat_turn,
)
from software_factory.deps import extract_env_creds
from software_factory.transcription import transcribe_audio, TranscriptionError

import console.state as state
from console.deps import require_authed, authorize_project, _can_see
from console.schemas import ChatIn, ConverseIn, ConverseOut, DepsIn, TranscribeIn

logger = logging.getLogger(__name__)

router = APIRouter()

# Server-side backstop: FE 90 s AbortController fires first on real stalls; this is the fallback.
_CHAT_TIMEOUT = 120


# /api/chat persistence + history now live on the `conversation` table via conversation.persistence
# (imported above as _persist_chat_turn / _chat_history). The legacy chat.jsonl/ChatStore and its
# SF_CHAT_JSONL_MIRROR / SF_CONVERSATION_DB flags are retired — the table is the single store.


@router.post("/api/transcribe")
def transcribe(body: TranscribeIn, v: tuple = Depends(require_authed)):
    """Dictate mic button (SOF-14): proxy recorded audio to OpenRouter Whisper Large v3. The
    OPENROUTER_API_KEY never reaches the browser — the client only sends/receives audio + text."""
    if not os.environ.get("OPENROUTER_API_KEY"):
        raise HTTPException(status_code=503, detail="OPENROUTER_API_KEY not set — dictation unavailable")
    if not body.audio_base64:
        raise HTTPException(status_code=400, detail="audio_base64 is required")
    try:
        text = transcribe_audio(body.audio_base64, body.format, body.language)
    except TranscriptionError as e:
        raise HTTPException(status_code=502, detail=str(e))
    return {"text": text}


@router.post("/api/chat")
async def chat(body: ChatIn, v: tuple = Depends(require_authed)):
    if not state._chat_runner:
        raise HTTPException(status_code=503,
                            detail="no OPENAI_API_KEY or OPENROUTER_API_KEY — chat unavailable")
    console = state.console
    intake = console.intake
    project_id = body.project_id
    # Messaging an EXISTING run requires ownership; a new conversation mints a durable DRAFT
    # (canonical run-<8hex>) up front so the interview persists from turn one and survives a
    # refresh/restart. The draft is invisible to the pipeline poller until promotion.
    if project_id and not _can_see(v, project_id):
        raise HTTPException(status_code=403, detail="forbidden")
    if not project_id:
        project_id = intake.create_draft(owner=v[0] or "", name=body.project_name or "",
                                         runtime=body.runtime, planning_model=body.planning_model,
                                         impl_model=body.impl_model, model=body.model)
    # Files/images attached during the interview persist into the draft now (wireframes survive),
    # so they're in input/ for Stage 1 regardless of which turn they arrived on. Drafts only.
    if (body.files or body.images) and intake.is_draft(project_id):
        try:
            intake.attach_to_draft(project_id, (body.files or []) + (body.images or []))
        except Exception:
            logger.exception("[chat] failed to attach interview materials for %s", project_id)

    pid = project_id  # capture for closure

    async def generate():
        # SOF-90: the whole turn (user message, the REAL tool-call trace, and the reply) is now
        # persisted inside handle_message_streamed, in chronological order, so conversation rows
        # sort correctly by insertion `seq`. The route just streams — it no longer persists (which
        # previously discarded the tool-call trace and wrote the user message after the stream).
        try:
            async with asyncio.timeout(_CHAT_TIMEOUT):
                async for line in state._chat_runner.handle_message_streamed(
                    pid, body.message, body.files, body.images,
                    runtime=body.runtime, planning_model=body.planning_model,
                    impl_model=body.impl_model, project_name=body.project_name,
                    owner=v[0] or "", role=v[1] or "member",
                    display_context=body.display_context,
                ):
                    yield line
        except asyncio.TimeoutError:
            logger.exception("[chat] /api/chat turn timed out for %s", pid)
            yield json.dumps({"type": "error", "detail": "chat turn timed out — try again"}) + "\n"
        except Exception as e:
            logger.exception("[chat] /api/chat turn failed for %s", pid)
            yield json.dumps({"type": "error", "detail": str(e)}) + "\n"

    return StreamingResponse(generate(), media_type="application/x-ndjson",
                             headers={"Cache-Control": "no-cache"})


@router.post("/api/projects/{pid}/converse", response_model=ConverseOut)
async def converse(pid: str, body: ConverseIn, v: tuple = Depends(authorize_project)):
    """One onboarding-Concierge turn: record the user's message, return the agent's reply as a
    ConciergeTurn — {response, suggested_responses[], handed_off}. `handed_off` reflects the real
    project phase after any tool call, so the UI can navigate on agent-triggered promotion. Backed
    by the DB-backed `DbConversation`; `authorize_project` gates cross-org access."""
    return await state.conversation_svc.turn(pid, body.message)


@router.post("/api/projects/{pid}/converse/stream")
async def converse_stream(pid: str, body: ConverseIn, v: tuple = Depends(authorize_project)):
    """SOF-154: the streaming sibling of `/converse` — prose renders token-by-token, then
    suggested-response chips arrive one at a time. `/converse` itself is untouched (unchanged
    contract for OnboardingScreen.tsx's separate composer). NDJSON over StreamingResponse, same
    transport shape as `/api/chat`: event types `working` | `token` | `option` | `done` | `error`."""
    async def generate():
        try:
            async with asyncio.timeout(_CHAT_TIMEOUT):
                async for ev in state.conversation_svc.turn_stream(pid, body.message):
                    yield json.dumps(ev) + "\n"
        except asyncio.TimeoutError:
            logger.exception("[chat] /converse/stream turn timed out for %s", pid)
            yield json.dumps({"type": "error", "detail": "chat turn timed out — try again"}) + "\n"
        except Exception as e:
            logger.exception("[chat] /converse/stream turn failed for %s", pid)
            yield json.dumps({"type": "error", "detail": str(e)}) + "\n"

    return StreamingResponse(generate(), media_type="application/x-ndjson",
                             headers={"Cache-Control": "no-cache"})


@router.get("/api/chat/{pid}/history")
def chat_history(pid: str, v: tuple = Depends(authorize_project)):
    return {"messages": _chat_history(pid)}


@router.post("/api/chat/{pid}/deps")
def chat_deps(pid: str, body: DepsIn, v: tuple = Depends(authorize_project)):
    console = state.console
    deps = body.deps
    result = console.submit_deps(pid, deps)
    dep_msg = ChatMessage(role="user", content=f"Provided: {', '.join(deps.keys())}",
                          msg_type="dep_submit", ts=time.time(),
                          metadata={"dep_names": list(deps.keys())})
    _persist_chat_turn(pid, dep_msg, owner_email=v[0] or "")
    if result.get("satisfied"):
        console.start_stage3(pid, extra_creds=extract_env_creds(deps))
        launch_msg = ChatMessage(role="system", content="Dependencies received. Build stage launching.",
                                 msg_type="status_update", ts=time.time(),
                                 metadata={"project_id": pid, "stage": 3})
        _persist_chat_turn(pid, launch_msg)
    return result
