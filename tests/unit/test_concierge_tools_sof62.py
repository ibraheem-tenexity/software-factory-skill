"""SOF-62: the four new/changed Concierge tools (search_document_summaries,
fetch_document_markdown, flag_for_verification, finalize_product_brief). Written fresh against the
CURRENT chat_agent/concierge_tools APIs — not mirrored off test_concierge_agent.py's imports,
which fail at import time post-c97c7eb (filed separately as SOF-67; not this ticket's scope).

No DB, no network: `console` and `MemoryStore` are mocked/patched throughout. Each `@tool`-wrapped
function is invoked via `.func(...)` (langchain_core.tools.tool's underlying callable) so these
tests call the real closures, not LangChain's tool-calling machinery.
"""
from unittest.mock import MagicMock, patch

import pytest

from software_factory.concierge_tools import build_project_tools


def _tools(console, store_patch_target="software_factory.concierge_tools.MemoryStore"):
    with patch(store_patch_target) as MS:
        tools = build_project_tools(console, "proj-1")
        by_name = {t.name: t for t in tools}
        return by_name, MS.return_value


class TestFetchDocumentMarkdown:
    def test_returns_content_under_the_token_ceiling(self):
        console = MagicMock()
        by_name, store = _tools(console)
        store.get_document_markdown.return_value = "short document text"
        result = by_name["fetch_document_markdown"].func(blob_id=7)
        assert result == "short document text"
        store.get_document_markdown.assert_called_once_with(7)

    def test_missing_document_says_so(self):
        console = MagicMock()
        by_name, store = _tools(console)
        store.get_document_markdown.return_value = None
        result = by_name["fetch_document_markdown"].func(blob_id=7)
        assert "no readable markdown" in result

    def test_oversized_document_is_gated_not_dumped(self):
        console = MagicMock()
        by_name, store = _tools(console)
        # 4 chars/token heuristic (memory.ingest.estimate_tokens) — comfortably over 500k tokens.
        store.get_document_markdown.return_value = "x" * (500_001 * 4)
        result = by_name["fetch_document_markdown"].func(blob_id=7)
        assert "too large to read whole" in result
        assert "search_document_summaries" in result


class TestFlagForVerification:
    def test_appends_a_new_open_question_with_the_expected_shape(self):
        console = MagicMock()
        state = MagicMock(reflection_questions=[])
        console._load_state.return_value = state
        by_name, _store = _tools(console)

        result = by_name["flag_for_verification"].func(
            question="Is this really the bottleneck?", related_document_blob_id=42)

        assert result == "flagged"
        state.save.assert_called_once()
        assert len(state.reflection_questions) == 1
        q = state.reflection_questions[0]
        assert q["fact"] == "Is this really the bottleneck?"
        assert q["document_blob_id"] == 42
        assert q["section_path_claimed"] is None
        assert q["status"] == "open"
        assert q["answer"] is None
        assert isinstance(q["created_at"], float)
        assert len(q["id"]) == 12

    def test_reraising_the_identical_question_is_idempotent(self):
        console = MagicMock()
        state = MagicMock(reflection_questions=[])
        console._load_state.return_value = state
        by_name, _store = _tools(console)

        by_name["flag_for_verification"].func(question="same question", related_document_blob_id=1)
        first_count = len(state.reflection_questions)
        result = by_name["flag_for_verification"].func(question="same question", related_document_blob_id=1)

        assert result == "already flagged"
        assert len(state.reflection_questions) == first_count == 1

    def test_no_document_uses_the_concierge_seed(self):
        console = MagicMock()
        state = MagicMock(reflection_questions=[])
        console._load_state.return_value = state
        by_name, _store = _tools(console)

        by_name["flag_for_verification"].func(question="general question")
        assert state.reflection_questions[0]["document_blob_id"] is None

    def test_empty_question_flags_nothing(self):
        console = MagicMock()
        state = MagicMock(reflection_questions=[])
        console._load_state.return_value = state
        by_name, _store = _tools(console)

        result = by_name["flag_for_verification"].func(question="   ")
        assert result == "question is empty — nothing flagged"
        state.save.assert_not_called()


class TestFinalizeProductBrief:
    def test_records_a_product_brief_artifact_via_projectstore(self):
        console = MagicMock()
        console._paths.return_value = {"db": "/fake/db/path"}
        by_name, _store = _tools(console)

        with patch("software_factory.concierge_tools.ProjectStore") as PS:
            result = by_name["finalize_product_brief"].func(markdown="# Brief\n\ndetails")

        assert result == "saved"
        console._paths.assert_called_once_with("proj-1")
        PS.assert_called_once_with("/fake/db/path")
        PS.return_value.record_artifact.assert_called_once_with(
            "Product Brief", "", kind="product_brief", agent="concierge", content="# Brief\n\ndetails")

    def test_empty_markdown_saves_nothing(self):
        console = MagicMock()
        by_name, _store = _tools(console)
        with patch("software_factory.concierge_tools.ProjectStore") as PS:
            result = by_name["finalize_product_brief"].func(markdown="   ")
        assert result == "markdown is empty — nothing saved"
        PS.assert_not_called()


class TestSearchDocumentSummaries:
    def test_delegates_to_memory_search_documents(self):
        console = MagicMock()
        by_name, _store = _tools(console)
        hits = [{"blob_id": 1, "document": "a.pdf", "summary_excerpt": "...", "score": 0.9}]
        with patch("software_factory.concierge_tools.memory_search.search_documents", return_value=hits) as search:
            result = by_name["search_document_summaries"].func(query="pricing")
        search.assert_called_once_with("project", "proj-1", "pricing")
        assert "a.pdf" in result

    def test_empty_query_error_is_surfaced_not_raised(self):
        console = MagicMock()
        by_name, _store = _tools(console)
        with patch("software_factory.concierge_tools.memory_search.search_documents",
                   side_effect=ValueError("query is empty")):
            result = by_name["search_document_summaries"].func(query="")
        assert "search failed" in result
