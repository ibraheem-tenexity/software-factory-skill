"""Chat-dock persistence on the `conversation` table (concierge-agent-spec.md §6).

Retires the legacy chat.jsonl / ChatStore: both /api/chat and the poller's deterministic
narration persist + read here instead. There is exactly one deterministic session_id per
project's dock conversation. Role vocabulary is mapped at this boundary — the FE/ChatMessage
use "assistant" for AI turns; the conversation table's convention is "agent".
"""
from __future__ import annotations

import uuid

from software_factory.conversation_store import ConversationStore
from software_factory.data_transfer_objects.chat_agent import ChatMessage


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


def chat_history(project_id: str) -> list[dict]:
    """Read a project's dock conversation back as chat-shaped dicts (newest last)."""
    rows = ConversationStore().history(chat_session_id(project_id))
    out = []
    for r in rows:
        block = next((b for b in (r["json_blob"] or []) if b.get("type") == "text"), {})
        out.append({
            "role": from_conversation_role(r["role"]),
            "content": r["input"] or block.get("text", ""),
            "msg_type": block.get("msg_type", "text"),
            "ts": r["created_at"],   # conversation_repo selects created_at as an epoch float
            "metadata": block.get("metadata", {}),
        })
    return out
