"""Concierge chat: /api/chat (send), /api/chat/{pid}/history, /api/chat/{pid}/deps, SSE stream."""
import asyncio
import time

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from software_factory.chat_store import ChatStore, ChatMessage
from software_factory.deps import extract_env_creds

import console.state as state
from console.deps import require_authed, authorize_project, _can_see
from console.schemas import ChatIn, DepsIn

router = APIRouter()


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
                                      impl_model=body.impl_model)
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

    try:
        result_project_id, response_msgs = await state._chat_runner.handle_message(
            project_id, body.message, body.files, body.images, runtime=body.runtime,
            planning_model=body.planning_model, impl_model=body.impl_model,
            project_name=body.project_name, gated=body.gated,
            owner=v[0] or "", role=v[1] or "member")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    if not project_id:
        project_id = result_project_id
    if project_id:
        store = ChatStore(state._chat_path(project_id))
        store.append(user_msg)
        for m in response_msgs:
            store.append(m)
        state._push_sse(project_id, response_msgs)

    return {"project_id": project_id, "messages": [m.to_dict() for m in response_msgs]}


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
