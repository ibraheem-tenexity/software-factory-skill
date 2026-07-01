"""Pure unit tests for the canonical content-block model (SOF-28) — no DB, no app-load, no conftest
DB round-trips. Import-only module under test; safe to run even on a box where any pytest
invocation would otherwise trigger conftest.py's collection-time create_all against live Postgres,
PROVIDED it's invoked in isolation from the rest of the suite (see PR notes — not run in this
session regardless, per the standing no-DB-touch constraint)."""
import pytest

from software_factory.conversation_blocks import (
    validate_block, validate_blocks, first_text, first_tool_result,
)


def test_text_block_valid():
    validate_block({"type": "text", "text": "hello"})


def test_text_block_missing_text_field_raises():
    with pytest.raises(ValueError, match="text"):
        validate_block({"type": "text"})


def test_image_block_valid_without_origin():
    validate_block({"type": "image", "blob_id": 42, "media_type": "image/png"})


def test_image_block_valid_with_doc_extract_origin():
    validate_block({"type": "image", "blob_id": 42, "media_type": "image/png",
                    "origin": {"kind": "doc_extract", "document_blob_id": 7, "page": 3}})


def test_image_block_requires_blob_id_never_inline_bytes():
    with pytest.raises(ValueError, match="blob_id"):
        validate_block({"type": "image", "media_type": "image/png"})


def test_image_block_doc_extract_origin_requires_document_blob_id():
    with pytest.raises(ValueError, match="document_blob_id"):
        validate_block({"type": "image", "blob_id": 1, "media_type": "image/png",
                        "origin": {"kind": "doc_extract"}})


def test_image_block_rejects_unknown_origin_kind():
    with pytest.raises(ValueError, match="origin"):
        validate_block({"type": "image", "blob_id": 1, "media_type": "x",
                        "origin": {"kind": "bogus"}})


def test_tool_use_block_valid():
    validate_block({"type": "tool_use", "id": "call_1", "name": "search_memory",
                    "input": {"query": "pricing", "k": 8}})


def test_tool_use_block_requires_name_and_input():
    with pytest.raises(ValueError, match="tool_use"):
        validate_block({"type": "tool_use", "id": "call_1"})


def test_tool_result_block_valid_with_nested_text():
    validate_block({"type": "tool_result", "tool_use_id": "call_1", "is_error": False,
                    "content": [{"type": "text", "text": "the answer"}]})


def test_tool_result_block_validates_nested_blocks_recursively():
    with pytest.raises(ValueError, match="text"):
        validate_block({"type": "tool_result", "tool_use_id": "call_1", "is_error": False,
                        "content": [{"type": "text"}]})   # nested block missing 'text'


def test_tool_result_block_requires_content_list():
    with pytest.raises(ValueError, match="content"):
        validate_block({"type": "tool_result", "tool_use_id": "call_1", "is_error": False})


def test_unknown_block_type_rejected():
    with pytest.raises(ValueError, match="unknown block type"):
        validate_block({"type": "bogus"})


def test_non_dict_block_rejected():
    with pytest.raises(ValueError, match="dict"):
        validate_block("not a block")


def test_validate_blocks_rejects_empty_list():
    with pytest.raises(ValueError, match="non-empty"):
        validate_blocks([])


def test_validate_blocks_checks_every_block():
    with pytest.raises(ValueError):
        validate_blocks([{"type": "text", "text": "ok"}, {"type": "bogus"}])


def test_first_text_finds_the_first_text_block():
    blocks = [{"type": "tool_use", "id": "c1", "name": "x", "input": {}},
              {"type": "text", "text": "the reply"}]
    assert first_text(blocks) == "the reply"


def test_first_text_empty_string_when_no_text_block():
    assert first_text([{"type": "tool_use", "id": "c1", "name": "x", "input": {}}]) == ""
    assert first_text([]) == ""


def test_first_tool_result_finds_it():
    tr = {"type": "tool_result", "tool_use_id": "c1", "is_error": False, "content": []}
    assert first_tool_result([{"type": "text", "text": "x"}, tr]) is tr


def test_first_tool_result_none_when_absent():
    assert first_tool_result([{"type": "text", "text": "x"}]) is None
    assert first_tool_result([]) is None
