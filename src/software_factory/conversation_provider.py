"""to_provider (SOF-30/T1.2) — render ConversationStore.history() rows into a valid message array
for a specific model provider. Pure rendering: the DB always holds the canonical block form
(conversation_blocks.py); provider-specific shapes exist only at this boundary, so switching a
project's model never touches stored history. No live model calls, no agent logic — see
conversation_store.py for persistence.

Provider divergence this module has to account for (found while implementing, not just in the
design doc's role-map table):
- OpenAI tool-calling is NOT an inline content block like Anthropic's. An assistant's `tool_use`
  becomes an entry in that message's `tool_calls` array (function name + JSON-string arguments);
  the following `tool_result` becomes a SEPARATE message with role="tool" keyed by
  `tool_call_id`. Anthropic keeps both inline as content blocks — `tool_use` on the assistant
  message, `tool_result` on a user-role message (Anthropic's Messages API has no "tool" role).
- Anthropic's Messages API does not accept role="system" in the messages array at all (system
  prompts are a separate top-level parameter) — but the design doc's role map says system->system
  for the canonical mapping with no divergence called out. This module renders system rows as
  {"role":"system",...} for BOTH providers, matching the doc literally; hoisting it out into a
  separate `system` parameter for a real Anthropic SDK call is the caller's job (T2.1), not this
  adapter's — this module was never asked to guarantee live-API acceptance, only correct rendering
  of the documented canonical role map.
"""
from __future__ import annotations

import base64
import json

from . import storage
from .repositories._exec import GlobalExec
from .repositories.blobs_repo import BlobRepository
from .conversation_blocks import TEXT, IMAGE, TOOL_USE, TOOL_RESULT


def _default_resolve_image(block: dict, provider: str) -> dict:
    """Real image resolution: blob_id -> blobs row -> storage.url() (signed URL) or, when Storage
    isn't configured, storage.get()+base64 (the design doc's stated fallback)."""
    row = BlobRepository(GlobalExec()).by_id(block["blob_id"])
    if row is None:
        raise ValueError(f"image block references unknown blob_id {block['blob_id']!r}")
    media_type = block["media_type"]
    if storage.enabled():
        url = storage.url(row["scope_id"], row["storage_key"])
        if provider == "openai":
            return {"type": "image_url", "image_url": {"url": url}}
        return {"type": "image", "source": {"type": "url", "url": url}}
    b64 = base64.b64encode(storage.get(row["scope_id"], row["storage_key"])).decode()
    if provider == "openai":
        return {"type": "image_url", "image_url": {"url": f"data:{media_type};base64,{b64}"}}
    return {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": b64}}


def _render_content_block(block: dict, provider: str, resolve_image) -> dict:
    """Render one non-tool_use, non-tool_result block (text or image) to its provider part.
    `origin` is dropped — it's UI/context metadata, not part of the model-facing payload."""
    if block["type"] == TEXT:
        return {"type": "text", "text": block["text"]}
    if block["type"] == IMAGE:
        return resolve_image(block, provider)
    raise ValueError(f"_render_content_block does not handle {block['type']!r} directly")


def _tool_result_text(block: dict, provider: str, resolve_image) -> str:
    """OpenAI's tool-role message content is a plain string; join the tool_result's nested text
    blocks. Nested images aren't standard for an OpenAI tool result — dropped, not crashed."""
    parts = []
    for nested in block["content"]:
        if nested["type"] == TEXT:
            parts.append(nested["text"])
    return "\n".join(parts)


def _require_tool_result(blocks: list) -> dict:
    for b in blocks:
        if b["type"] == TOOL_RESULT:
            return b
    raise ValueError("a role='tool' row must contain a tool_result block")


def _openai_message(row: dict, resolve_image) -> list[dict]:
    """Returns ONE OR TWO OpenAI messages for this row (a tool_use row still emits exactly one
    assistant message; only role='tool' produces the separate keyed-by-tool_call_id message)."""
    role = row["role"]
    blocks = row["json_blob"]

    if role == "tool":
        tr = _require_tool_result(blocks)
        return [{"role": "tool", "tool_call_id": tr["tool_use_id"],
                "content": _tool_result_text(tr, "openai", resolve_image)}]

    content_parts = [_render_content_block(b, "openai", resolve_image)
                     for b in blocks if b["type"] in (TEXT, IMAGE)]
    tool_calls = [{"id": b["id"], "type": "function",
                  "function": {"name": b["name"], "arguments": json.dumps(b["input"])}}
                 for b in blocks if b["type"] == TOOL_USE]

    provider_role = {"user": "user", "agent": "assistant", "system": "system"}[role]
    msg: dict = {"role": provider_role}
    if content_parts or not tool_calls:
        msg["content"] = content_parts
    if tool_calls:
        msg["tool_calls"] = tool_calls
    return [msg]


def _anthropic_message(row: dict, resolve_image) -> list[dict]:
    role = row["role"]
    blocks = row["json_blob"]

    if role == "tool":
        tr = _require_tool_result(blocks)
        nested = [_render_content_block(b, "anthropic", resolve_image) for b in tr["content"]]
        return [{"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": tr["tool_use_id"], "is_error": tr["is_error"],
             "content": nested},
        ]}]

    content: list = []
    for b in blocks:
        if b["type"] in (TEXT, IMAGE):
            content.append(_render_content_block(b, "anthropic", resolve_image))
        elif b["type"] == TOOL_USE:
            content.append({"type": "tool_use", "id": b["id"], "name": b["name"], "input": b["input"]})

    provider_role = {"user": "user", "agent": "assistant", "system": "system"}[role]
    return [{"role": provider_role, "content": content}]


def to_provider(rows: list[dict], provider: str, *, resolve_image=None) -> list[dict]:
    """Render ConversationStore.history() rows to `provider`'s message shape.
    `provider`: 'openai' | 'anthropic' (OpenRouter uses the OpenAI shape — pass 'openai').
    `resolve_image`: optional (block, provider) -> provider image part, for tests to inject a fake
    that touches neither Storage nor the blobs table; defaults to the real resolver."""
    if provider not in ("openai", "anthropic"):
        raise ValueError(f"unsupported provider {provider!r} — must be 'openai' or 'anthropic'")
    resolve_image = resolve_image or _default_resolve_image
    render = _openai_message if provider == "openai" else _anthropic_message
    messages: list[dict] = []
    for row in rows:
        messages.extend(render(row, resolve_image))
    return messages
