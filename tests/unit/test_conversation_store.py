"""Tests for ConversationStore (SOF-28/T1.1).

Split deliberately in two:
- The seq-retry-on-conflict tests inject a FAKE ConversationRepository — no DB touched, safe to
  run anywhere, and they exercise the concurrency AC directly (a real UniqueViolation is simulated,
  not just asserted-by-reading-the-code).
- The round-trip/ordering/image-reference/tool-turn tests use the real ConversationStore against
  the actual `conversation` table (same convention as every other tests/unit/*.py in this repo —
  Postgres via conftest.py). NOT executed in this session: the box this was built on has a standing
  constraint that ANY pytest invocation triggers conftest.py's collection-time create_all against a
  live Postgres and OOMs once the pgvector-era models.py landed (SOF-26/T0.1) — left for CI/staging/
  the integrator to run.
"""
import psycopg
import pytest

from software_factory.conversation_store import ConversationStore
from software_factory.repositories.conversation_repo import ConversationRepository
from software_factory.repositories._exec import GlobalExec


# ── Concurrency (no DB — fake repo) ─────────────────────────────────────────────────────────

class _FakeRepo:
    """Fails the first N inserts with UniqueViolation (simulating a losing writer under a real
    (session_id, seq) race), then succeeds. Records every insert() call for assertions."""

    def __init__(self, fail_times: int):
        self.fail_times = fail_times
        self.next_seq_calls = 0
        self.insert_calls: list[dict] = []

    def next_seq(self, session_id):
        self.next_seq_calls += 1
        return self.next_seq_calls - 1

    def insert(self, **kwargs):
        self.insert_calls.append(kwargs)
        if len(self.insert_calls) <= self.fail_times:
            raise psycopg.errors.UniqueViolation("duplicate key value violates unique constraint")
        return "msg-fake-id"


def test_append_retries_on_seq_conflict_and_succeeds():
    repo = _FakeRepo(fail_times=1)
    store = ConversationStore(repo=repo)
    mid = store.append("sess-1", "user", [{"type": "text", "text": "hi"}])
    assert mid == "msg-fake-id"
    assert len(repo.insert_calls) == 2                       # one conflict, one success
    assert repo.insert_calls[0]["seq"] != repo.insert_calls[1]["seq"]   # retry used a fresh seq


def test_append_exhausts_retries_and_reraises():
    repo = _FakeRepo(fail_times=99)   # always conflicts
    store = ConversationStore(repo=repo)
    with pytest.raises(psycopg.errors.UniqueViolation):
        store.append("sess-1", "user", [{"type": "text", "text": "hi"}])
    from software_factory.conversation_store import _MAX_SEQ_RETRIES
    assert len(repo.insert_calls) == _MAX_SEQ_RETRIES


def test_append_validates_blocks_before_ever_calling_the_repo():
    """A malformed block must never reach the DB layer — confirmed by a repo that would raise
    AssertionError if it were ever called."""
    class _ExplodesIfCalled:
        def next_seq(self, session_id): raise AssertionError("must not be called")
        def insert(self, **kwargs): raise AssertionError("must not be called")
    store = ConversationStore(repo=_ExplodesIfCalled())
    with pytest.raises(ValueError):
        store.append("sess-1", "user", [{"type": "not-a-real-type"}])
    with pytest.raises(ValueError):
        store.append("sess-1", "user", [])


# ── Persistence + ordering (real DB — NOT run in this session, see module docstring) ────────

def test_append_then_history_round_trips_in_seq_order(tmp_path):
    store = ConversationStore()
    session_id = "11111111-1111-1111-1111-111111111111"
    store.append(session_id, "user", [{"type": "text", "text": "first"}], project_id="project-abc")
    store.append(session_id, "agent", [{"type": "text", "text": "second"}], project_id="project-abc")
    store.append(session_id, "user", [{"type": "text", "text": "third"}], project_id="project-abc")
    rows = store.history(session_id)
    assert [r["input"] for r in rows] == ["first", "second", "third"]
    assert [r["seq"] for r in rows] == sorted(r["seq"] for r in rows)
    assert [r["role"] for r in rows] == ["user", "agent", "user"]


def test_image_block_references_a_real_blob_id_never_inline_bytes(tmp_path):
    from software_factory.blobs import BlobStore
    store = ConversationStore()
    blob_id = BlobStore().record("project", "project-abc", "diagram-key.png",
                                 kind="image", name="diagram.png", content_type="image/png")
    session_id = "22222222-2222-2222-2222-222222222222"
    store.append(session_id, "agent",
                [{"type": "image", "blob_id": blob_id, "media_type": "image/png"}],
                project_id="project-abc")
    row = store.history(session_id)[0]
    assert row["json_blob"][0]["blob_id"] == blob_id
    assert "bytes" not in row["json_blob"][0] and "data" not in row["json_blob"][0]


def test_tool_use_then_tool_result_reconstructs_losslessly(tmp_path):
    store = ConversationStore()
    session_id = "33333333-3333-3333-3333-333333333333"
    store.append(session_id, "agent",
                [{"type": "tool_use", "id": "call_1", "name": "search_memory",
                  "input": {"query": "pricing"}}],
                project_id="project-abc", tool_name="search_memory", tool_call_id="call_1")
    store.append(session_id, "tool",
                [{"type": "tool_result", "tool_use_id": "call_1", "is_error": False,
                  "content": [{"type": "text", "text": "found 3 pricing tiers"}]}],
                project_id="project-abc", tool_call_id="call_1")
    rows = store.history(session_id)
    assert rows[0]["role"] == "agent" and rows[0]["json_blob"][0]["type"] == "tool_use"
    assert rows[1]["role"] == "tool" and rows[1]["tool_result"]["tool_use_id"] == "call_1"
    assert rows[1]["json_blob"][0]["content"][0]["text"] == "found 3 pricing tiers"
