"""Golden-file tests for to_provider (SOF-30/T1.2) — no DB, no live model calls, no real Storage.
`resolve_image` is always injected with a fake for the role-mapping/shape tests; the two tests that
exercise the REAL default resolver mock its dependencies (BlobRepository.by_id, storage.enabled/
storage.get/storage.url) rather than hitting Postgres or a network. Safe to run anywhere — but per
the standing constraint on the box this was built on (conftest.py's collection-time create_all
against live Postgres once T0.1's pgvector columns landed), no pytest invocation was run in this
session at all; verified via direct python3 -c imports instead (see PR notes)."""
import base64
from unittest.mock import patch

import pytest

from software_factory.conversation_provider import to_provider, _default_resolve_image


def _fake_resolve_image(block, provider):
    if provider == "openai":
        return {"type": "image_url", "image_url": {"url": "https://signed.example/img.png"}}
    return {"type": "image", "source": {"type": "url", "url": "https://signed.example/img.png"}}


# ── The golden transcript: text turn + image turn + tool_use/tool_result pair ───────────────

_TRANSCRIPT = [
    {"role": "system", "json_blob": [{"type": "text", "text": "You are the Concierge."}]},
    {"role": "user", "json_blob": [{"type": "text", "text": "Show me the wiring diagram"}]},
    {"role": "agent", "json_blob": [
        {"type": "text", "text": "Here it is:"},
        {"type": "image", "blob_id": 8130, "media_type": "image/png",
         "origin": {"kind": "doc_extract", "document_blob_id": 8100, "page": 4}},
    ]},
    {"role": "agent", "json_blob": [
        {"type": "tool_use", "id": "call_ab12", "name": "search_memory",
         "input": {"query": "pricing tiers", "k": 8}},
    ]},
    {"role": "tool", "json_blob": [
        {"type": "tool_result", "tool_use_id": "call_ab12", "is_error": False,
         "content": [{"type": "text", "text": "Found 3 pricing tiers."}]},
    ]},
]


def test_golden_transcript_renders_valid_openai_payload():
    msgs = to_provider(_TRANSCRIPT, "openai", resolve_image=_fake_resolve_image)
    assert msgs == [
        {"role": "system", "content": [{"type": "text", "text": "You are the Concierge."}]},
        {"role": "user", "content": [{"type": "text", "text": "Show me the wiring diagram"}]},
        {"role": "assistant", "content": [
            {"type": "text", "text": "Here it is:"},
            {"type": "image_url", "image_url": {"url": "https://signed.example/img.png"}},
        ]},
        {"role": "assistant", "tool_calls": [
            {"id": "call_ab12", "type": "function",
             "function": {"name": "search_memory", "arguments": '{"query": "pricing tiers", "k": 8}'}},
        ]},
        {"role": "tool", "tool_call_id": "call_ab12", "content": "Found 3 pricing tiers."},
    ]


def test_golden_transcript_renders_valid_anthropic_payload():
    msgs = to_provider(_TRANSCRIPT, "anthropic", resolve_image=_fake_resolve_image)
    assert msgs == [
        {"role": "system", "content": [{"type": "text", "text": "You are the Concierge."}]},
        {"role": "user", "content": [{"type": "text", "text": "Show me the wiring diagram"}]},
        {"role": "assistant", "content": [
            {"type": "text", "text": "Here it is:"},
            {"type": "image", "source": {"type": "url", "url": "https://signed.example/img.png"}},
        ]},
        {"role": "assistant", "content": [
            {"type": "tool_use", "id": "call_ab12", "name": "search_memory",
             "input": {"query": "pricing tiers", "k": 8}},
        ]},
        {"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": "call_ab12", "is_error": False,
             "content": [{"type": "text", "text": "Found 3 pricing tiers."}]},
        ]},
    ]


# ── Role mapping, all four roles, both providers ────────────────────────────────────────────

@pytest.mark.parametrize("role,expected_openai,expected_anthropic", [
    ("user", "user", "user"),
    ("agent", "assistant", "assistant"),
    ("system", "system", "system"),
])
def test_role_maps_to_the_right_provider_role(role, expected_openai, expected_anthropic):
    row = [{"role": role, "json_blob": [{"type": "text", "text": "x"}]}]
    assert to_provider(row, "openai")[0]["role"] == expected_openai
    assert to_provider(row, "anthropic")[0]["role"] == expected_anthropic


def test_tool_role_diverges_openai_separate_message_vs_anthropic_inline_user():
    row = [{"role": "tool", "json_blob": [
        {"type": "tool_result", "tool_use_id": "c1", "is_error": False, "content": []}]}]
    openai_msg = to_provider(row, "openai")[0]
    anthropic_msg = to_provider(row, "anthropic")[0]
    assert openai_msg["role"] == "tool" and openai_msg["tool_call_id"] == "c1"
    assert anthropic_msg["role"] == "user"       # Anthropic has no "tool" role
    assert anthropic_msg["content"][0]["type"] == "tool_result"


def test_tool_row_without_a_tool_result_block_raises_clear_error_not_stopiteration():
    row = [{"role": "tool", "json_blob": [{"type": "text", "text": "malformed row"}]}]
    with pytest.raises(ValueError, match="tool_result"):
        to_provider(row, "openai")
    with pytest.raises(ValueError, match="tool_result"):
        to_provider(row, "anthropic")


# ── Image resolution ─────────────────────────────────────────────────────────────────────────

def test_unsupported_provider_rejected():
    with pytest.raises(ValueError, match="openai.*anthropic|anthropic.*openai"):
        to_provider([], "bogus-provider")


def test_default_image_resolver_prefers_signed_url_when_storage_enabled():
    from software_factory.repositories.blobs_repo import BlobRepository
    from software_factory import storage
    with patch.object(BlobRepository, "by_id",
                      return_value={"scope_id": "project-abc", "storage_key": "diagram.png"}), \
         patch.object(storage, "enabled", return_value=True), \
         patch.object(storage, "url", return_value="https://signed.example/diagram.png"):
        block = {"type": "image", "blob_id": 42, "media_type": "image/png"}
        assert _default_resolve_image(block, "openai") == {
            "type": "image_url", "image_url": {"url": "https://signed.example/diagram.png"}}
        assert _default_resolve_image(block, "anthropic") == {
            "type": "image", "source": {"type": "url", "url": "https://signed.example/diagram.png"}}


def test_default_image_resolver_falls_back_to_base64_when_storage_disabled():
    """No raw bytes leak into a row — this only touches the OUTBOUND provider payload, never
    conversation.json_blob, which continues to hold only {type, blob_id, media_type, origin}."""
    from software_factory.repositories.blobs_repo import BlobRepository
    from software_factory import storage
    raw = b"\x89PNG\r\n\x1a\nfakepngbytes"
    with patch.object(BlobRepository, "by_id",
                      return_value={"scope_id": "project-abc", "storage_key": "diagram.png"}), \
         patch.object(storage, "enabled", return_value=False), \
         patch.object(storage, "get", return_value=raw):
        block = {"type": "image", "blob_id": 42, "media_type": "image/png"}
        openai_part = _default_resolve_image(block, "openai")
        anthropic_part = _default_resolve_image(block, "anthropic")
        assert openai_part["image_url"]["url"] == f"data:image/png;base64,{base64.b64encode(raw).decode()}"
        assert anthropic_part["source"]["type"] == "base64"
        assert base64.b64decode(anthropic_part["source"]["data"]) == raw


def test_default_image_resolver_raises_on_unknown_blob_id():
    from software_factory.repositories.blobs_repo import BlobRepository
    with patch.object(BlobRepository, "by_id", return_value=None):
        with pytest.raises(ValueError, match="unknown blob_id"):
            _default_resolve_image({"type": "image", "blob_id": 999, "media_type": "image/png"}, "openai")


def test_origin_metadata_is_dropped_from_the_provider_payload():
    row = [{"role": "agent", "json_blob": [
        {"type": "image", "blob_id": 1, "media_type": "image/png",
         "origin": {"kind": "doc_extract", "document_blob_id": 100, "page": 4}},
    ]}]
    msg = to_provider(row, "openai", resolve_image=_fake_resolve_image)[0]
    assert "origin" not in msg["content"][0]
