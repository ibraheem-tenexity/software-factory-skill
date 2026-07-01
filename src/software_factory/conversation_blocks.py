"""The canonical content-block model stored in `conversation.json_blob` (SOF-28). One list of these
per row; provider-specific rendering happens only at the `to_provider` boundary (T1.2/SOF-30) — the
DB never holds a provider-shaped payload. Framework-free: light structural validation, no schema
library (matches the "no external markdown/schema deps" convention elsewhere in this codebase).

Exactly four block types are defined here — the ones `concierge-conversation-store.md` §3 gives a
concrete shape for. `suggested_responses` (mentioned in the design doc as something agent turns
"also carry... in json_blob") is a T2.2/Concierge-agent concern with no concrete shape yet; it is
NOT a block type and is deliberately not invented here — json_blob is a plain JSONB array, so
adding it later needs no migration and no change to this module's contract.
"""
from __future__ import annotations

TEXT = "text"
IMAGE = "image"
TOOL_USE = "tool_use"
TOOL_RESULT = "tool_result"
BLOCK_TYPES = (TEXT, IMAGE, TOOL_USE, TOOL_RESULT)

_ORIGIN_KINDS = ("upload", "generated", "doc_extract")


def validate_block(block: dict) -> None:
    """Raise ValueError if `block` isn't a well-formed canonical content block. Recurses into
    tool_result's nested `content` list (each element is itself a block)."""
    if not isinstance(block, dict):
        raise ValueError(f"block must be a dict, got {type(block).__name__}")
    btype = block.get("type")
    if btype not in BLOCK_TYPES:
        raise ValueError(f"unknown block type {btype!r} — must be one of {BLOCK_TYPES}")

    if btype == TEXT:
        if not isinstance(block.get("text"), str):
            raise ValueError("text block requires a string 'text' field")

    elif btype == IMAGE:
        if "blob_id" not in block or block["blob_id"] is None:
            raise ValueError("image block requires 'blob_id' (never inline bytes)")
        if not isinstance(block.get("media_type"), str):
            raise ValueError("image block requires a string 'media_type' field")
        origin = block.get("origin")
        if origin is not None:
            if not isinstance(origin, dict) or origin.get("kind") not in _ORIGIN_KINDS:
                raise ValueError(f"image block 'origin.kind' must be one of {_ORIGIN_KINDS}")
            if origin["kind"] == "doc_extract" and not origin.get("document_blob_id"):
                raise ValueError("origin.kind='doc_extract' requires 'document_blob_id'")

    elif btype == TOOL_USE:
        if not block.get("id") or not block.get("name"):
            raise ValueError("tool_use block requires 'id' and 'name'")
        if not isinstance(block.get("input"), dict):
            raise ValueError("tool_use block requires a dict 'input' field")

    elif btype == TOOL_RESULT:
        if not block.get("tool_use_id"):
            raise ValueError("tool_result block requires 'tool_use_id'")
        if "is_error" not in block:
            raise ValueError("tool_result block requires an 'is_error' field")
        content = block.get("content")
        if not isinstance(content, list):
            raise ValueError("tool_result block requires a list 'content' field")
        for nested in content:
            validate_block(nested)


def validate_blocks(blocks: list) -> None:
    if not isinstance(blocks, list) or not blocks:
        raise ValueError("blocks must be a non-empty list")
    for b in blocks:
        validate_block(b)


def first_text(blocks: list) -> str:
    """The first text block's content, or "" if none — used to denormalize `conversation.input`."""
    for b in blocks:
        if b.get("type") == TEXT:
            return b["text"]
    return ""


def first_tool_result(blocks: list) -> dict | None:
    """The first tool_result block, or None — used to denormalize `conversation.tool_result`."""
    for b in blocks:
        if b.get("type") == TOOL_RESULT:
            return b
    return None
