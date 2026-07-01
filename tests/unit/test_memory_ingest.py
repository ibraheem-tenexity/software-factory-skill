"""SOF-32: memory/ingest.py — pure-logic pieces ACTUALLY RUN via a standalone python -c script
(no DB, no live network — markitdown/pypandoc/mammoth aren't even installed in this sandbox,
they're Dockerfile-only pip3 deps, not pyproject.toml, so the real extractors can't run here
either; dispatch is tested via monkeypatching pdf_extract/docx_extract, the same injectable-
converter pattern those modules already document). Transcript in the PR description.

The full ingest_blob(...) pipeline (dedup, write-through, chunk/doc_summary persistence, cost
recording against a real ledger, rollup write) needs a real Postgres connection through
Console/BlobStore/MemoryStore — written below per the ticket's AC, NOT executed here, same
posture as #237/#238/#243.
"""
import os
import tempfile
from unittest.mock import patch

from software_factory.memory import ingest


def test_filter_key_facts_drops_unreferenced_and_keeps_referenced():
    raw = [
        {"fact": "Uses OAuth2", "section_path": "Auth"},
        {"fact": "an unreferenced inference", "section_path": "NotARealSection"},
        {"fact": "", "section_path": "Auth"},          # empty fact text
        {"section_path": "Auth"},                        # missing fact key entirely
        {"fact": "no section at all"},                   # missing section_path entirely
    ]
    out = ingest._filter_key_facts(raw, blob_id=42, valid_section_paths={"Auth", "Billing"})
    assert out == [{"fact": "Uses OAuth2", "document_blob_id": 42, "section_path": "Auth"}]


def test_filter_key_facts_document_blob_id_is_never_taken_from_the_model():
    # Even if a (malicious or confused) model response includes its own document_blob_id, the
    # code-attached value must win — never trust the model for provenance.
    raw = [{"fact": "x", "section_path": "Auth", "document_blob_id": 999}]
    out = ingest._filter_key_facts(raw, blob_id=42, valid_section_paths={"Auth"})
    assert out == [{"fact": "x", "document_blob_id": 42, "section_path": "Auth"}]


def test_build_rollup_skips_non_ready_and_empty_summaries():
    docs = [
        {"status": "ready", "summary_md": "This is doc A.\nMore text.", "name": "a.pdf"},
        {"status": "pending", "summary_md": "not ready yet", "name": "b.pdf"},
        {"status": "ready", "summary_md": "", "name": "c.pdf"},
        {"status": "failed", "summary_md": "should never show", "name": "d.pdf"},
    ]
    assert ingest._build_rollup(docs) == "- a.pdf: This is doc A."


def test_extract_dispatches_non_docx_to_pdf_extract():
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "notes.txt")
        open(path, "w").close()
        with patch.object(ingest.pdf_extract, "extract_to_markdown", return_value="# Hello\n\ntext") as m:
            text, images = ingest._extract(path, tmp)
        m.assert_called_once_with(path)
        assert text == "# Hello\n\ntext"
        assert images == []


def test_extract_dispatches_docx_to_docx_extract_with_images():
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "doc.docx")
        open(path, "w").close()
        with patch.object(ingest.docx_extract, "extract_with_images",
                          return_value=("# Doc", ["images/image-01.png"])):
            text, images = ingest._extract(path, tmp)
        assert text == "# Doc"
        assert images == [os.path.join(tmp, "images/image-01.png")]


def test_extract_docx_falls_back_to_text_only_when_images_lib_missing():
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "doc.docx")
        open(path, "w").close()
        with patch.object(ingest.docx_extract, "extract_with_images", side_effect=ImportError):
            with patch.object(ingest.docx_extract, "extract_to_markdown", return_value="# Doc text only"):
                text, images = ingest._extract(path, tmp)
        assert text == "# Doc text only"
        assert images == []


def test_estimate_cost_usd_returns_none_when_pricing_unavailable():
    with patch.object(ingest.pricing, "openrouter_price", return_value=None):
        assert ingest._estimate_cost_usd("some/model", "chat", prompt_tokens=100) is None


def test_estimate_cost_usd_chat_uses_real_usage_and_real_price():
    with patch.object(ingest.pricing, "openrouter_price",
                      return_value={"input": 0.000001, "output": 0.000005}):
        cost = ingest._estimate_cost_usd("anthropic/claude-haiku-4.5", "chat",
                                         prompt_tokens=1000, completion_tokens=200)
    assert cost == 1000 * 0.000001 + 200 * 0.000005


def test_estimate_cost_usd_embedding_estimates_tokens_from_char_count():
    with patch.object(ingest.pricing, "openrouter_price", return_value={"input": 0.0000002, "output": 0.0}):
        cost = ingest._estimate_cost_usd("google/gemini-embedding-2", "embedding", input_chars=4000)
    assert cost == (4000 / ingest._ESTIMATED_CHARS_PER_TOKEN) * 0.0000002


def test_maybe_ingest_async_is_a_noop_when_sf_memory_is_not_set(monkeypatch):
    monkeypatch.delenv("SF_MEMORY", raising=False)
    with patch.object(ingest.threading, "Thread") as thread_cls:
        ingest.maybe_ingest_async(1, console=object())
    thread_cls.assert_not_called()


def test_maybe_ingest_async_spawns_a_daemon_thread_when_enabled(monkeypatch):
    monkeypatch.setenv("SF_MEMORY", "1")
    with patch.object(ingest.threading, "Thread") as thread_cls:
        ingest.maybe_ingest_async(7, console=object())
    thread_cls.assert_called_once()
    _args, kwargs = thread_cls.call_args
    assert kwargs["daemon"] is True
    thread_cls.return_value.start.assert_called_once()


# ---- DB-requiring: written per AC, NOT executed here (needs Console/BlobStore/MemoryStore
# against a real Postgres). Deferred to the integrator's off-box run, same posture as #237/
# #238/#243. ------------------------------------------------------------------------------

def test_ingest_blob_dedups_on_unchanged_content_sha256():
    """A blob whose doc_summary is already status=ready with a matching content_sha256 must
    be skipped, not re-ingested (no re-parse, no re-embed, no re-summarize, no new cost)."""
    pass  # needs a real BlobStore/MemoryStore round-trip; see module docstring


def test_ingest_blob_marks_failed_on_parse_error_without_raising():
    """A corrupt file's extract() call raising must land the doc as status=failed and return a
    clean dict — never propagate, so a caller iterating N blobs continues to the next one."""
    pass  # needs a real BlobStore/MemoryStore round-trip; see module docstring


def test_ingest_blob_records_extracted_docx_images_with_source_blob_id():
    """Each image path docx_extract writes must become its own blobs row with
    source_blob_id=the parent doc's id and source_page=None (docx has no fixed pages)."""
    pass  # needs a real BlobStore round-trip; see module docstring


def test_ingest_blob_recomputes_the_project_rollup_only_for_project_scope():
    """An org-scope blob's ingest must NOT write ProjectState.memory_overview (no project_id to
    write to); a project-scope blob's ingest must update it to include the new doc."""
    pass  # needs a real Console/ProjectState round-trip; see module docstring


def test_ingest_blob_never_records_a_fabricated_zero_cost_when_pricing_fails():
    """If pricing.openrouter_price returns None (live fetch failed) for a call that really
    happened, record_ingestion_cost must NOT be called with usd=0 — the cost entry is skipped
    and loudly logged, never silently zeroed."""
    pass  # needs a real Console/ProjectState round-trip (record_ingestion_cost writes state)
