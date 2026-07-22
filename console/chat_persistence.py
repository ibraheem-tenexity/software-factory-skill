"""Chat-dock persistence on the canonical `conversation` table.

Retires the legacy chat.jsonl / ChatStore: both /api/chat and the poller's deterministic
narration persist + read here instead. There is exactly one deterministic session_id per
project's dock conversation. Role vocabulary is mapped at this boundary — the FE/ChatMessage
use "assistant" for AI turns; the conversation table's convention is "agent".
"""
from __future__ import annotations

import uuid

from software_factory.conversation_store import ConversationStore
from software_factory.data_transfer_objects.chat_agent import ChatMessage, ConciergeTurn

# The concierge agent runs with response_format=ToolStrategy(ConciergeTurn): the model emits its
# final reply by calling an ARTIFICIAL structured-output tool named after the schema class. That
# call (and its synthetic tool result) shows up in the run's message trace exactly like a real
# tool call, but it is the response mechanism, not an action the concierge took — persisting it
# would clutter the concierge's own "what did I do" history with a bogus `[Called ConciergeTurn(…)]`.
# Derived from the class name so it tracks a rename of the schema.
_STRUCTURED_OUTPUT_TOOL = ConciergeTurn.__name__


def chat_session_id(project_id: str) -> str:
    """Deterministic session_id for a project's single durable dock conversation."""
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, f"chat:{project_id}"))


def to_conversation_role(role: str) -> str:
    return "agent" if role == "assistant" else role


def from_conversation_role(role: str) -> str:
    return "assistant" if role == "agent" else role


def persist_chat_turn(project_id: str, msg: ChatMessage, *, owner_email: str = "",
                      model: str | None = None, provider: str | None = None,
                      input_tokens: int = 0, output_tokens: int = 0,
                      cost_usd: float | None = 0.0) -> None:
    """Write one chat turn to the conversation table. msg_type + metadata ride inside the block
    (the table has no column for them; validate_block ignores extra keys)."""
    block = {"type": "text", "text": msg.content, "msg_type": msg.msg_type,
             "metadata": msg.metadata or {}}
    ConversationStore().append(
        chat_session_id(project_id), to_conversation_role(msg.role), [block],
        user_email=(owner_email or None) if msg.role == "user" else None,
        project_id=project_id, model=model, provider=provider,
        input_tokens=input_tokens, output_tokens=output_tokens, cost_usd=cost_usd,
    )


def persist_run_trace(project_id: str, result: dict, input_len: int) -> None:
    """Persist the REAL tool-call trace of one dock agent run (SOF-90): every tool_use the model
    emitted and every tool_result it got back, in order, on the project's dock session — using the
    canonical conversation_blocks shapes (tool_use / tool_result), the SAME format the onboarding
    /converse path already writes (services/conversation.py), and the table's existing
    tool_name/tool_call_id columns (previously 100% unused on this path).

    `result` is exactly what ChatAgent.run() returns; `input_len` is how many messages we fed it,
    so result["messages"][input_len:] is only what THIS run produced. The caller persists the user
    message BEFORE this and the final reply AFTER it, so table order (rows sort by `seq` /
    insertion) is user -> tool_use -> tool_result -> reply. Intermediate assistant *text* is
    intentionally dropped (the dock only ever surfaced the final reply); only the tool audit trail
    is newly captured.

    Without this the concierge had no durable record of its own actions and confabulated when asked
    what it did (confirmed live: a claimed tool call had zero matching evidence in this table, and a
    ~20 ms turnaround far too fast for any real call). chat_history() renders these rows back as
    plain bracketed text so a later turn is grounded in fact WITHOUT re-injecting raw tool-role
    dicts into the live LangChain invocation (some providers reject a tool-role message with no
    strictly-matching preceding tool_call in the same request)."""
    session_id = chat_session_id(project_id)
    store = ConversationStore()
    skip_call_ids: set[str] = set()   # tool_result rows whose tool_use we filtered out
    for m in (result.get("messages") or [])[input_len:]:
        mtype = getattr(m, "type", "")
        if mtype == "ai":
            tool_uses = []
            for tc in (getattr(m, "tool_calls", None) or []):
                if (tc.get("name") or "") == _STRUCTURED_OUTPUT_TOOL:
                    skip_call_ids.add(tc.get("id") or "")   # the ConciergeTurn reply mechanism, not an action
                    continue
                tool_uses.append({"type": "tool_use", "id": tc.get("id") or "",
                                  "name": tc.get("name") or "", "input": tc.get("args") or {}})
            if tool_uses:
                store.append(session_id, "agent", tool_uses, project_id=project_id)
        elif mtype == "tool":
            call_id = getattr(m, "tool_call_id", "") or ""
            if call_id in skip_call_ids or getattr(m, "name", None) == _STRUCTURED_OUTPUT_TOOL:
                continue
            content_text = m.content if isinstance(m.content, str) else str(m.content)
            store.append(
                session_id, "tool",
                [{"type": "tool_result", "tool_use_id": call_id,
                  "is_error": False, "content": [{"type": "text", "text": content_text}]}],
                project_id=project_id, tool_name=getattr(m, "name", None),
                tool_call_id=call_id or None,
            )


def chat_history(project_id: str) -> list[dict]:
    """Read a project's dock conversation back as chat-shaped dicts (newest last). Tool-call rows
    (SOF-90) render as compact bracketed text notes — real, persisted fact the model can read and
    ground its own self-reports in, not raw tool-role objects re-injected into the live agent.

    Those tool rows carry msg_type "tool_call" / "tool_result" (vs "text" for real utterances) so
    the two consumers can treat them differently: the model-grounding path (chat_dock rebuilds
    history as role+content, msg_type ignored) keeps them; the user-facing chat panel filters them
    out so end users don't see raw `[Called …]` plumbing in their conversation."""
    rows = ConversationStore().history(chat_session_id(project_id))
    out = []
    for r in rows:
        blocks = r["json_blob"] or []
        tool_uses = [b for b in blocks if b.get("type") == "tool_use"]
        if tool_uses:
            # One row can carry SEVERAL tool_use blocks (the model calling tools in parallel in a
            # single turn) — render EVERY one, so the concierge's self-report reflects all the
            # calls it actually made, not just the first (SOF-90's whole point is a truthful record).
            for tu in tool_uses:
                out.append({"role": "assistant", "content": f"[Called {tu['name']}({tu.get('input') or {}})]",
                            "msg_type": "tool_call", "ts": r["created_at"], "metadata": {}})
            continue
        tool_result = next((b for b in blocks if b.get("type") == "tool_result"), None)
        if tool_result:
            text = next((c.get("text", "") for c in (tool_result.get("content") or [])
                        if c.get("type") == "text"), "")
            out.append({"role": "assistant", "content": f"[{r.get('tool_name') or 'Tool'} returned: {text}]",
                        "msg_type": "tool_result", "ts": r["created_at"], "metadata": {}})
            continue
        block = next((b for b in blocks if b.get("type") == "text"), {})
        out.append({
            "role": from_conversation_role(r["role"]),
            "content": r["input"] or block.get("text", ""),
            "msg_type": block.get("msg_type", "text"),
            "ts": r["created_at"],   # conversation_repo selects created_at as an epoch float
            "metadata": block.get("metadata", {}),
        })
    return out
