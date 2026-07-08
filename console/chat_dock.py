"""The /api/chat dock — the persistent in-project concierge, served by ChatAgent.

Replaces the deleted ChatDockRunner (chat_agent.py stays tiny — agent + model chooser only).
History loads from the conversation table (console/chat_persistence.py), so a dock thread
survives restarts; the route persists the turn after the stream completes, unchanged contract.
"""
from __future__ import annotations

import json
import logging
import time

from software_factory.chat_agent import ChatAgent
from software_factory.concierge_tools import build_project_tools
from software_factory.data_transfer_objects.chat_agent import ChatMessage

from console import chat_persistence

logger = logging.getLogger(__name__)

# Phase -> context inference (no per-screen signal exists in ChatIn; coarsest reasonable proxy).
# "build" is the fallback for anything not explicitly mapped, drafts/unknown included.
_PHASE_CONTEXT = {"done": "overview"}


class ChatDock:
    """Serves `/api/chat` via ChatAgent. Only `handle_message_streamed` exists — the route never
    called a non-streaming variant. One agent per (project, context), tools bound per project."""

    def __init__(self, console, users=None, agent=None):
        self._console = console
        self._agent = agent          # injectable for tests; used for every project when set
        self._agents: dict = {}      # (project_id, context) -> ChatAgent

    def _context_for_project(self, project_id: str) -> str:
        try:
            phase = (self._console.status(project_id).get("phase") or "").lower()
        except Exception:
            return "build"
        return _PHASE_CONTEXT.get(phase, "build")

    def _get_agent(self, project_id: str | None, context: str) -> ChatAgent:
        if self._agent is not None:
            return self._agent
        key = (project_id, context)
        if key not in self._agents:
            tools = build_project_tools(self._console, project_id) if project_id else []
            self._agents[key] = ChatAgent(context=context, tools=tools)
        return self._agents[key]

    async def handle_message_streamed(
        self, project_id: str | None, user_msg: str,
        files: list, images: list,
        runtime: str = "", planning_model: str = "",
        impl_model: str = "", project_name: str = "",
        owner: str = "", role: str = "member",
    ):
        """Async generator yielding NDJSON lines. `ChatAgent.run()` is a single call (no real
        token-by-token stream), so this yields exactly one `done` event with the full reply —
        an honest simplification, not a pretense of streaming that isn't happening."""
        content = user_msg or ""
        if files:
            content += "\n" + "\n".join(f"[Attached file: {f.get('name', 'file')}]" for f in files)
        if images:
            content += "\n" + "\n".join(f"[Attached image: {i.get('name', 'image')}]" for i in images)

        # Durable history: the project's dock conversation from the conversation table.
        history: list[dict] = []
        if project_id:
            try:
                history = [{"role": m["role"], "content": m["content"]}
                           for m in chat_persistence.chat_history(project_id)]
            except Exception:
                history = []
        history.append({"role": "user", "content": content})

        input_len = len(history)
        context = self._context_for_project(project_id) if project_id else "build"
        agent = self._get_agent(project_id, context)
        try:
            result = await agent.run(history)
            turn = result["structured_response"]
        except Exception as e:
            yield json.dumps({"type": "error", "detail": str(e)}) + "\n"
            return

        # SOF-90: persist the WHOLE turn here, in chronological order, so the concierge's own claims
        # about what it did are grounded in fact rather than confabulated (confirmed live: a claimed
        # tool call had zero matching evidence in the conversation table, and a ~20 ms turnaround far
        # too fast for any real call). Previously the route persisted only the user message + a
        # flattened reply AFTER the stream, discarding the real tool-call trace; because conversation
        # rows sort by insertion `seq`, writing the trace mid-stream would also mis-order it before
        # the very user message that triggered it. Owning it here — user -> tool_use -> tool_result
        # -> reply — keeps the order correct and uses the same canonical block shapes as the
        # /converse path. Best-effort: an audit write must never break the turn the user is waiting on.
        if project_id:
            try:
                meta: dict = {}
                if files:
                    meta["files"] = [f.get("name", "file") for f in files]
                if images:
                    meta["images"] = [i.get("name", "image") for i in images]
                chat_persistence.persist_chat_turn(
                    project_id,
                    ChatMessage(role="user", content=user_msg or "", msg_type="text",
                                ts=time.time(), metadata=meta),
                    owner_email=owner)
                chat_persistence.persist_run_trace(project_id, result, input_len)
                usage = agent.last_usage or {}
                chat_persistence.persist_chat_turn(
                    project_id,
                    ChatMessage(role="assistant", content=turn.response, msg_type="text",
                                ts=time.time()),
                    model=usage.get("model"), provider=usage.get("provider"),
                    input_tokens=usage.get("input_tokens", 0),
                    output_tokens=usage.get("output_tokens", 0),
                    cost_usd=usage.get("cost_usd") or 0.0)
            except Exception:
                logger.exception("[chat_dock] SOF-90 turn persistence failed for %s", project_id)

        messages = [{"role": "assistant", "content": turn.response, "msg_type": "text",
                     "ts": time.time(), "metadata": {}}]
        yield json.dumps({"type": "done", "project_id": project_id, "messages": messages,
                          "usage": agent.last_usage}) + "\n"
