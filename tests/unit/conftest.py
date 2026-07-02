"""tests/unit/conftest.py — layers on top of the repo-root conftest.py for this directory only
(pytest composes conftest.py files by directory; this adds one fixture, it doesn't replace
anything the root one does).

SOF-71: maybe_ingest_async no longer has an SF_MEMORY off-switch — every route/service call that
attaches real file content (materials upload, draft attach, org-doc-use) now genuinely spawns a
background ingest thread that makes real network calls (embeddings, summarization). Before SOF-71,
these tests were accidentally hermetic ONLY because SF_MEMORY was unset in the test env, so the
call silently no-op'd. Patched at the seam instead, per the ticket's explicit instruction not to
reintroduce an env opt-out.

Patches the two call sites' OWN bound names (`from ...ingest import maybe_ingest_async` binds a
local reference in each importing module — patching `memory.ingest.maybe_ingest_async` itself
would not affect either), not the source function. `test_memory_ingest.py`'s own tests call
`ingest.maybe_ingest_async` directly via the module reference, a third, untouched path, so they
keep exercising the real implementation without needing an explicit exemption.
"""
import pytest


@pytest.fixture(autouse=True)
def stub_maybe_ingest_async(monkeypatch):
    """Records calls instead of spawning real background ingestion. Fixture value is the list of
    recorded calls — request it by name in a test to assert whether/how ingestion was triggered."""
    calls: list[dict] = []

    def _record(blob_id, console, push_progress=None):
        calls.append({"blob_id": blob_id, "console": console, "push_progress": push_progress})

    monkeypatch.setattr("console.routers.projects.maybe_ingest_async", _record)
    monkeypatch.setattr("software_factory.services.org_service.maybe_ingest_async", _record)
    return calls
