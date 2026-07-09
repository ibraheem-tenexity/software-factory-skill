"""SOF-62: the Concierge tools search_document_summaries and fetch_document_markdown. Written
fresh against the CURRENT chat_agent/concierge_tools APIs — not mirrored off
test_concierge_agent.py's imports, which fail at import time post-c97c7eb (filed separately as
SOF-67; not this ticket's scope). flag_for_verification and its tests were deleted with the
reflection-question machinery (SOF-137, Minimum Machinery); finalize_product_brief's coverage
here was deleted too since SOF-137 changed it to write through storage.py.

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
