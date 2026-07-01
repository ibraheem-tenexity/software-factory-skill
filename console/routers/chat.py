"""Concierge chat: /api/chat (send), /api/chat/{pid}/history, /api/chat/{pid}/deps, SSE stream."""
import asyncio
import json
import os
import time
import uuid

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from software_factory.chat_store import ChatStore, ChatMessage
from software_factory.conversation_store import ConversationStore
from software_factory.deps import extract_env_creds
from software_factory.transcription import transcribe_audio, TranscriptionError

import console.state as state
from console.deps import require_authed, authorize_project, _can_see
from console.schemas import ChatIn, ConverseIn, ConverseOut, DepsIn, TranscribeIn

router = APIRouter()

# Server-side backstop: FE 90 s AbortController fires first on real stalls; this is the fallback.
_CHAT_TIMEOUT = 120


# ── T1.4: fold /api/chat's persistence off chat.jsonl onto the conversation table ──────────────
# Two independent flags — either, both, or neither can be on:
#   SF_CONVERSATION_DB     — write (and, once flipped, read) the durable conversation table.
#                            Same flag /converse's DbConversation swap already uses.
#   SF_CHAT_JSONL_MIRROR   — keep writing chat.jsonl too. Defaults ON: "chat.jsonl kept as a
#                            debug mirror during migration, then retired" (ticket's own words) —
#                            the safe initial rollout posture is BOTH paths active, flipped off
#                            later via config once the new path is trusted, not forced off here.
def _conversation_db_on() -> bool:
    return os.environ.get("SF_CONVERSATION_DB") == "1"


def _jsonl_mirror_on() -> bool:
    return (os.environ.get("SF_CHAT_JSONL_MIRROR") or "1") == "1"


def _chat_session_id(project_id: str) -> str:
    """Deterministic session_id for /api/chat's (exactly one) durable dock conversation per
    project. Deliberately DISTINCT from services/conversation.py's _onboarding_session_id —
    unifying the dock chat and the onboarding interview into one Concierge thread is Phase 2/
    T2.1's call, not this storage-layer swap's."""
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, f"chat:{project_id}"))


# chat.jsonl/ChatMessage/the FE use "assistant" for AI turns; the conversation table's
# established convention (services/conversation.py's DbConversation, T1.3) is "agent" — map at
# this boundary so neither side needs to change its own vocabulary.
def _to_conversation_role(role: str) -> str:
    return "agent" if role == "assistant" else role


def _from_conversation_role(role: str) -> str:
    return "assistant" if role == "agent" else role


def _persist_chat_turn(project_id: str, msg: ChatMessage, *, owner_email: str = "",
                       model: str | None = None, provider: str | None = None,
                       input_tokens: int = 0, output_tokens: int = 0,
                       cost_usd: float | None = 0.0) -> None:
    """Write one /api/chat turn to whichever store(s) are currently active."""
    if _jsonl_mirror_on():
        ChatStore(state._chat_path(project_id)).append(msg)
    if _conversation_db_on():
        # msg_type + the original metadata dict travel inside the block itself — the
        # conversation table has no column for either, and conversation_blocks.validate_block
        # only checks the fields IT requires, so extra keys pass through untouched.
        block = {"type": "text", "text": msg.content, "msg_type": msg.msg_type,
                "metadata": msg.metadata or {}}
        ConversationStore().append(
            _chat_session_id(project_id), _to_conversation_role(msg.role), [block],
            user_email=(owner_email or None) if msg.role == "user" else None,
            project_id=project_id, model=model, provider=provider,
            input_tokens=input_tokens, output_tokens=output_tokens, cost_usd=cost_usd,
        )


def _chat_history_from_conversation(project_id: str) -> list[dict]:
    rows = ConversationStore().history(_chat_session_id(project_id))
    out = []
    for r in rows:
        block = next((b for b in (r["json_blob"] or []) if b.get("type") == "text"), {})
        ts = r["created_at"]   # #267: conversation_repo.py now selects created_at as epoch float
        out.append({
            "role": _from_conversation_role(r["role"]),
            "content": r["input"] or block.get("text", ""),
            "msg_type": block.get("msg_type", "text"),
            "ts": ts,
            "metadata": block.get("metadata", {}),
        })
    return out


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

        # Persist (chat.jsonl and/or the conversation table, per the flags above) + push SSE
        # after stream completes.
        final_pid = result.get("project_id") or pid
        if final_pid and result.get("type") == "done":
            _persist_chat_turn(final_pid, user_msg, owner_email=v[0] or "")
            # SOF-57: ChatDockRunner's "done" event now carries the real LangChain usage
            # (model/provider/token counts/cost) for the assistant turn it just produced.
            usage = result.get("usage") or {}
            msgs = [ChatMessage.from_dict(m) for m in (result.get("messages") or [])]
            for m in msgs:
                _persist_chat_turn(final_pid, m, model=usage.get("model"), provider=usage.get("provider"),
                                   input_tokens=usage.get("input_tokens", 0),
                                   output_tokens=usage.get("output_tokens", 0),
                                   cost_usd=usage.get("cost_usd", 0.0))
            state._push_sse(final_pid, msgs)

    return StreamingResponse(generate(), media_type="application/x-ndjson",
                             headers={"Cache-Control": "no-cache"})


@router.post("/api/projects/{pid}/converse", response_model=ConverseOut)
def converse(pid: str, body: ConverseIn, v: tuple = Depends(authorize_project)):
    """One onboarding-Concierge turn: record the user's message, return the agent's reply as a
    ConciergeTurn — {response, suggested_responses[]} (T2.2; no `choices`/`done`). Backed by the
    in-memory mock `Conversation` or the DB-backed `DbConversation` (SF_CONVERSATION_DB) — the
    latter delegates to the real LangChain ConciergeAgent (T2.1); the mock stays scripted.
    `authorize_project` gates cross-org access."""
    result = state.conversation_svc.turn(pid, body.message)
    if "response" in result:
        return result   # DbConversation already returns the new ConciergeTurn shape
    # Conversation (the mock) still returns its ORIGINAL {message, choices, done} — untouched,
    # per T1.3's hermetic-mock contract (its own tests assert this shape directly). Translate at
    # the wire boundary so ConverseOut's new contract holds regardless of which service is active;
    # `choices` (single-select strings) map to single-select suggested_responses, `done` becomes a
    # hand-off invite suggested_response rather than a hidden boolean (spec §3).
    suggested = [{"response": c, "type": "single select"} for c in result.get("choices", [])]
    if result.get("done"):
        suggested = [{"response": "Hand off to the factory", "type": "single select"}]
    return {"response": result["message"], "suggested_responses": suggested}


@router.get("/api/chat/{pid}/history")
def chat_history(pid: str, v: tuple = Depends(authorize_project)):
    if _conversation_db_on():
        return {"messages": _chat_history_from_conversation(pid)}
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
    _persist_chat_turn(pid, dep_msg, owner_email=v[0] or "")
    if result.get("satisfied"):
        console.start_stage3(pid, extra_creds=extract_env_creds(deps))
        launch_msg = ChatMessage(role="system", content="Dependencies received. Build stage launching.",
                                 msg_type="status_update", ts=time.time(),
                                 metadata={"project_id": pid, "stage": 3})
        _persist_chat_turn(pid, launch_msg)
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
