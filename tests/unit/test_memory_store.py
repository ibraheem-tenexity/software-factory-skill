"""SOF-29: MemoryStore — CRUD over dbshim for doc_summary/chunk.

NOT EXECUTED IN THIS SANDBOX, including the fake-connection tests at the bottom of this file:
conftest.py bootstraps a real Postgres connection via create_all at COLLECTION time for every
test file in this repo, unconditionally, regardless of what an individual test's body touches
— once pgvector columns exist in models.py that alone puts this whole file out of reach here,
not just the round-trip tests above that genuinely need a live DB.

The round-trip tests (add_chunk/chunks_for/replace_chunks/upsert_doc_summary) use
MemoryStore's real default connect() (dbshim.connect -> DATABASE_URL) and were reasoned
through against dbshim's real API (PgConn.execute(...).fetchone()/.fetchall(), the `?`
placeholder translation, the auto-RETURNING-id convenience for tables in _ID_TABLES — chunk is
NOT in that set, hence the explicit `RETURNING id` in MemoryStore.add_chunk). The overview()
tests at the bottom inject a fake in-memory connection (MemoryStore's own injectable `connect`
param) and were actually run standalone via a `python -c` script bypassing pytest/conftest
entirely — see the PR description for that transcript. The integrator validates the round-trip
tests off-box (scratch DB) before merge, same posture as PR #237/#238.
"""
from software_factory import dbshim
from software_factory.memory.embed import DIMENSIONS
from software_factory.memory.store import MemoryStore


def _make_blob(scope="project", scope_id="project-store-test", storage_key="input/doc.md") -> int:
    """chunk.blob_id and doc_summary.blob_id both FK -> blobs.id — every test here needs a
    real blobs row first, not a bare integer."""
    conn = dbshim.connect(".")
    try:
        row = conn.execute(
            "INSERT INTO blobs (scope, scope_id, storage_key) VALUES (?, ?, ?) RETURNING id",
            (scope, scope_id, storage_key),
        ).fetchone()
        return row["id"]
    finally:
        conn.close()


def test_add_chunk_and_chunks_for_round_trips_by_blob_id():
    blob_id = _make_blob()
    store = MemoryStore()
    store.add_chunk(blob_id, "project", "project-store-test", 0, "1 Intro",
                    "hello world", dense=[0.0] * DIMENSIONS)
    store.add_chunk(blob_id, "project", "project-store-test", 1, "2 Details",
                    "more content here", dense=[0.1] * DIMENSIONS)
    chunks = store.chunks_for(blob_id)
    assert [c["ordinal"] for c in chunks] == [0, 1]
    assert chunks[0]["content"] == "hello world"
    # pgvector.psycopg decodes a halfvec column to a HalfVector, not a plain list — .to_list()
    # first (this assertion was never actually executed before SOF-84; a bare len() on the
    # wrapper object raises TypeError, since HalfVector has no __len__).
    assert len(chunks[0]["dense"].to_list()) == DIMENSIONS


def test_replace_chunks_deletes_old_rows_before_inserting_new_ones():
    blob_id = _make_blob()
    store = MemoryStore()
    store.add_chunk(blob_id, "project", "project-store-test", 0, None, "old content")
    store.replace_chunks(blob_id, [(0, "1 New", "new content")],
                         scope="project", scope_id="project-store-test")
    chunks = store.chunks_for(blob_id)
    assert len(chunks) == 1
    assert chunks[0]["content"] == "new content"


def test_upsert_doc_summary_is_idempotent_on_conflict():
    blob_id = _make_blob()
    store = MemoryStore()
    store.upsert_doc_summary(blob_id, "project", "project-store-test",
                             summary_md="v1", status="pending")
    store.upsert_doc_summary(blob_id, "project", "project-store-test",
                             summary_md="v2", status="ready")
    row = store.get_doc_summary(blob_id)
    assert row["summary_md"] == "v2"
    assert row["status"] == "ready"


def test_list_doc_summaries_returns_blob_id_keyed_map_for_the_scope():
    """SOF-36: the Documents-tab enrichment reads this in bulk (one query per project view load,
    not one per blob) — must be keyed by blob_id and scoped like everything else here."""
    blob_id_a = _make_blob(storage_key="input/a.md")
    blob_id_b = _make_blob(storage_key="input/b.md")
    other_scope_blob = _make_blob(scope="project", scope_id="project-store-test-OTHER",
                                  storage_key="input/c.md")
    store = MemoryStore()
    store.upsert_doc_summary(blob_id_a, "project", "project-store-test",
                             summary_md="Summary A", status="ready")
    store.upsert_doc_summary(blob_id_b, "project", "project-store-test",
                             summary_md="Summary B", status="pending")
    store.upsert_doc_summary(other_scope_blob, "project", "project-store-test-OTHER",
                             summary_md="Not this scope", status="ready")

    result = store.list_doc_summaries("project", "project-store-test")
    assert set(result.keys()) == {blob_id_a, blob_id_b}
    assert result[blob_id_a]["summary_md"] == "Summary A" and result[blob_id_a]["status"] == "ready"
    assert result[blob_id_b]["summary_md"] == "Summary B" and result[blob_id_b]["status"] == "pending"


def test_list_doc_summaries_empty_scope_returns_empty_dict():
    store = MemoryStore()
    assert store.list_doc_summaries("project", "project-store-test-NEVER-USED") == {}


def test_overview_counts_doc_summaries_by_status_for_the_scope():
    blob_a = _make_blob(scope_id="project-overview-test")
    blob_b = _make_blob(scope_id="project-overview-test")
    store = MemoryStore()
    store.upsert_doc_summary(blob_a, "project", "project-overview-test", status="ready")
    store.upsert_doc_summary(blob_b, "project", "project-overview-test", status="pending")
    out = store.overview("project", "project-overview-test")
    assert out["doc_counts"] == {"ready": 1, "pending": 1}


# ---- overview() branch logic against a FAKE in-memory connection (genuinely DB-free; only
# unreachable via pytest here because of conftest's unconditional collection-time bootstrap —
# see the module docstring). Actually executed via a standalone `python -c` script; transcript
# in the PR description. ------------------------------------------------------------------

class _FakeCursor:
    def __init__(self, rows):
        self._rows = rows

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return self._rows


class _FakeConn:
    """script: [(SQL_PREFIX_UPPER, rows)] — the first matching prefix wins."""
    def __init__(self, script):
        self.script = script
        self.calls = []

    def execute(self, sql, params=()):
        self.calls.append((sql, params))
        for prefix, rows in self.script:
            if sql.strip().upper().startswith(prefix):
                return _FakeCursor(rows)
        return _FakeCursor([])

    def close(self):
        pass


def test_overview_reads_no_rollup_before_t3_2_writes_one():
    # T3.1 is store-only; nothing computes/writes projectstate.data['memory_overview'] yet
    # (that's T3.2). A fresh project's overview must not fabricate a rollup.
    fake = _FakeConn([("SELECT STATUS", []), ("SELECT DATA", [])])
    store = MemoryStore(connect=lambda: fake)
    out = store.overview("project", "project-with-no-rollup-yet")
    assert out["rollup"] is None


def test_overview_project_scope_reads_the_cached_rollup_when_present():
    import json
    fake = _FakeConn([
        ("SELECT STATUS", []),
        ("SELECT DATA", [{"data": json.dumps({"memory_overview": "a rollup blurb"})}]),
    ])
    store = MemoryStore(connect=lambda: fake)
    out = store.overview("project", "p2")
    assert out["rollup"] == "a rollup blurb"


def test_overview_malformed_projectstate_json_does_not_raise():
    fake = _FakeConn([("SELECT STATUS", []), ("SELECT DATA", [{"data": "not json"}])])
    store = MemoryStore(connect=lambda: fake)
    out = store.overview("project", "p3")
    assert out["rollup"] is None


def test_overview_org_scope_has_no_persisted_rollup_cache_yet():
    # organizations.context_rollup does not exist (not added by T0.1) — flagged, not faked.
    # Also: org scope must not even ATTEMPT a projectstate lookup (scope_id is an org id there).
    fake = _FakeConn([("SELECT STATUS", [])])
    store = MemoryStore(connect=lambda: fake)
    out = store.overview("org", "org-test")
    assert out["rollup"] is None
    assert len(fake.calls) == 1
