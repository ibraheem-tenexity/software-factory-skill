"""Concierge chat: /api/chat (send), /api/chat/{pid}/history, /api/chat/{pid}/deps, SSE stream."""
import asyncio
import json
import os
import time

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from software_factory.chat_store import ChatStore, ChatMessage
from software_factory.deps import extract_env_creds
from software_factory.transcription import transcribe_audio, TranscriptionError

import console.state as state
from console.deps import require_authed, authorize_project, _can_see
from console.schemas import ChatIn, ConverseIn, ConverseOut, DepsIn, TranscribeIn

router = APIRouter()

# Server-side backstop: FE 90 s AbortController fires first on real stalls; this is the fallback.
_CHAT_TIMEOUT = 120


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
    project_id = body.project_id
    # Messaging an EXISTING run requires ownership; a new conversation mints a durable DRAFT
    # (canonical run-<8hex>) up front so the interview persists to chat.jsonl from turn one and
    # survives a refresh/restart. The draft is invisible to the pipeline poller until promotion.
    if project_id and not _can_see(v, project_id):
        raise HTTPException(status_code=403, detail="forbidden")
    if not project_id:
        project_id = console.create_draft(owner=v[0] or "", name=body.project_name or "",
                                      runtime=body.runtime, planning_model=body.planning_model,
                                      impl_model=body.impl_model, model=body.model)
    # Files/images attached during the interview persist into the draft now (wireframes survive),
    # so they're in input/ for Stage 1 regardless of which turn they arrived on. Drafts only.
    if (body.files or body.images) and console.is_draft(project_id):
        try:
            console.attach_to_draft(project_id, (body.files or []) + (body.images or []))
        except Exception:
            pass  # a bad attachment must not 500 the chat turn

    user_msg = ChatMessage(role="user", content=body.message, msg_type="text", ts=time.time())
    if body.files:
        user_msg.metadata["files"] = [f.get("name", "file") for f in body.files]
    if body.images:
        user_msg.metadata["images"] = [i.get("name", "image") for i in body.images]

    pid = project_id  # capture for closure

    async def generate():
        result: dict = {}
        try:
            async with asyncio.timeout(_CHAT_TIMEOUT):
                async for line in state._chat_runner.handle_message_streamed(
                    pid, body.message, body.files, body.images,
                    runtime=body.runtime, planning_model=body.planning_model,
                    impl_model=body.impl_model, project_name=body.project_name,
                    gated=body.gated, owner=v[0] or "", role=v[1] or "member",
                ):
                    yield line
                    try:
                        evt = json.loads(line)
                        if evt.get("type") == "done":
                            result.update(evt)
                    except Exception:
                        pass
        except asyncio.TimeoutError:
            yield json.dumps({"type": "error", "detail": "chat turn timed out — try again"}) + "\n"
        except Exception as e:
            yield json.dumps({"type": "error", "detail": str(e)}) + "\n"

        # Persist to ChatStore + push SSE after stream completes.
        final_pid = result.get("project_id") or pid
        if final_pid and result.get("type") == "done":
            store = ChatStore(state._chat_path(final_pid))
            store.append(user_msg)
            msgs = [ChatMessage.from_dict(m) for m in (result.get("messages") or [])]
            for m in msgs:
                store.append(m)
            state._push_sse(final_pid, msgs)

    return StreamingResponse(generate(), media_type="application/x-ndjson",
                             headers={"Cache-Control": "no-cache"})


@router.post("/api/projects/{pid}/converse", response_model=ConverseOut)
def converse(pid: str, body: ConverseIn, v: tuple = Depends(authorize_project)):
    """One onboarding-Concierge turn: record the user's message, return the (mock) agent's reply —
    plain text or up to 4 choices, plus `done` when it's inviting hand-off. Backed by the in-memory
    mock `conversation_svc` for now; swaps to the real agent + DB-backed history later with no route
    change. `authorize_project` gates cross-org access."""
    return state.conversation_svc.turn(pid, body.message)


@router.get("/api/chat/{pid}/history")
def chat_history(pid: str, v: tuple = Depends(authorize_project)):
    store = ChatStore(state._chat_path(pid))
    return {"messages": [m.to_dict() for m in store.history()]}


@router.post("/api/chat/{pid}/deps")
def chat_deps(pid: str, body: DepsIn, v: tuple = Depends(authorize_project)):
    console = state.console
    deps = body.deps
    result = console.submit_deps(pid, deps)
    dep_msg = ChatMessage(role="user", content=f"Provided: {', '.join(deps.keys())}",
                          msg_type="dep_submit", ts=time.time(),
                          metadata={"dep_names": list(deps.keys())})
    store = ChatStore(state._chat_path(pid))
    store.append(dep_msg)
    if result.get("satisfied"):
        console.start_stage3(pid, extra_creds=extract_env_creds(deps))
        launch_msg = ChatMessage(role="system", content="Dependencies received. Build stage launching.",
                                 msg_type="status_update", ts=time.time(),
                                 metadata={"project_id": pid, "stage": 3})
        store.append(launch_msg)
        state._push_sse(pid, [dep_msg, launch_msg])
    else:
        state._push_sse(pid, [dep_msg])
    return result


@router.get("/api/chat/{pid}/stream")
async def chat_stream(pid: str, v: tuple = Depends(authorize_project)):
    """SSE for real-time pipeline updates. Drains a per-client queue fed by _push_sse (from the
    poller thread + chat/deps handlers); keepalive every 2s."""
    q: list[str] = []
    with state._sse_lock:
        state._sse_clients.setdefault(pid, []).append(q)

    async def gen():
        try:
            while True:
                if q:
                    yield q.pop(0)
                else:
                    yield ": keepalive\n\n"
                    await asyncio.sleep(2)
        finally:
            with state._sse_lock:
                clients = state._sse_clients.get(pid, [])
                if q in clients:
                    clients.remove(q)

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "Connection": "keep-alive"})
