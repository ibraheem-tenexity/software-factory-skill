"""Pure unit tests for search_documents (SOF-60) — the coarse, document-level tier of
coarse-to-fine retrieval, dense-only over doc_summary.embedding. Same no-DB/no-network posture
and fake connect/embed fixtures as test_memory_search.py."""
import pytest

from software_factory.memory.search import search_documents


class _FakeCursor:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return self._rows


class _FakeConn:
    def __init__(self, rows):
        self.rows = rows
        self.executed_sql = None
        self.executed_params = None
        self.closed = False

    def execute(self, sql, params):
        self.executed_sql = sql
        self.executed_params = list(params)
        return _FakeCursor(self.rows)

    def close(self):
        self.closed = True


def _fake_embed(texts):
    return [[0.1, 0.2, 0.3] for _ in texts]


def test_rejects_unsupported_scope():
    with pytest.raises(ValueError, match="project.*org|org.*project"):
        search_documents("bogus", "sid", "query", connect=lambda: _FakeConn([]), embed=_fake_embed)


def test_rejects_empty_query():
    with pytest.raises(ValueError, match="empty"):
        search_documents("project", "sid", "   ", connect=lambda: _FakeConn([]), embed=_fake_embed)


def test_placeholder_count_matches_param_count_project_scope():
    conn = _FakeConn([])
    search_documents("project", "proj-1", "pricing tiers", k=8, connect=lambda: conn, embed=_fake_embed)
    assert conn.executed_sql.count("?") == len(conn.executed_params)


def test_placeholder_count_matches_param_count_org_scope():
    conn = _FakeConn([])
    search_documents("org", "org-1", "pricing tiers", k=8, connect=lambda: conn, embed=_fake_embed)
    assert conn.executed_sql.count("?") == len(conn.executed_params)


def test_query_is_embedded_and_the_vector_used_as_the_dense_param():
    conn = _FakeConn([])
    calls = []

    def spy_embed(texts):
        calls.append(list(texts))
        return [[9.0, 9.0]]

    search_documents("project", "proj-1", "pricing tiers", connect=lambda: conn, embed=spy_embed)
    assert calls == [["pricing tiers"]]
    assert conn.executed_params[0] == [9.0, 9.0]     # dense param, first placeholder


def test_k_is_passed_through_as_the_final_limit_param():
    conn = _FakeConn([])
    search_documents("project", "proj-1", "pricing tiers", k=3, connect=lambda: conn, embed=_fake_embed)
    assert conn.executed_params[-1] == 3


def test_default_k_is_eight():
    conn = _FakeConn([])
    search_documents("project", "proj-1", "pricing tiers", connect=lambda: conn, embed=_fake_embed)
    assert conn.executed_params[-1] == 8


def test_dense_comparison_casts_the_param_to_halfvec():
    # Same UndefinedFunction trap search() documents: the SELECT-expression + ORDER BY each
    # bind the query vector, both need the ::halfvec cast (column is halfvec(3072), SOF-84).
    conn = _FakeConn([])
    search_documents("project", "proj-1", "pricing tiers", connect=lambda: conn, embed=_fake_embed)
    assert conn.executed_sql.count("<=> ?::halfvec") == 2


def test_scope_filter_is_qualified_against_ambiguous_column():
    # SOF-84: found live — `doc_summary ds JOIN blobs b` both have `scope`/`scope_id` columns,
    # so a bare `scope = ?` in the WHERE clause raises `AmbiguousColumn` at runtime (the fake
    # connection here can't catch that itself; this locks in that the fix — qualifying with
    # `ds.` — doesn't regress back to the bare, ambiguous form).
    conn = _FakeConn([])
    search_documents("project", "proj-1", "pricing tiers", connect=lambda: conn, embed=_fake_embed)
    assert "ds.scope = ?" in conn.executed_sql
    assert "ds.scope_id = ?" in conn.executed_sql
    assert " scope = ?" not in conn.executed_sql


def test_sql_is_a_plain_select_so_pgconn_still_detects_it():
    conn = _FakeConn([])
    search_documents("project", "proj-1", "pricing tiers", connect=lambda: conn, embed=_fake_embed)
    assert conn.executed_sql.strip().upper().startswith("SELECT")


def test_sql_filters_to_ready_status_and_non_null_embeddings():
    # New behaviors vs chunk search: a pending/failed doc_summary has no trustworthy embedding
    # (written together with status='ready'), and a NULL embedding must never rank.
    conn = _FakeConn([])
    search_documents("project", "proj-1", "pricing tiers", connect=lambda: conn, embed=_fake_embed)
    assert "status = 'ready'" in conn.executed_sql
    assert "embedding IS NOT NULL" in conn.executed_sql


def test_connection_is_always_closed():
    conn = _FakeConn([])
    search_documents("project", "proj-1", "pricing tiers", connect=lambda: conn, embed=_fake_embed)
    assert conn.closed is True


def test_maps_rows_to_the_documented_hit_shape():
    rows = [
        {"blob_id": 7, "document": "pricing.pdf", "summary_excerpt": "Standard price book…", "score": 0.91},
        {"blob_id": 3, "document": "sop.pdf", "summary_excerpt": "Quoting SOP…", "score": 0.42},
    ]
    conn = _FakeConn(rows)
    hits = search_documents("project", "proj-1", "pricing", connect=lambda: conn, embed=_fake_embed)
    assert hits == [
        {"blob_id": 7, "document": "pricing.pdf", "summary_excerpt": "Standard price book…", "score": 0.91},
        {"blob_id": 3, "document": "sop.pdf", "summary_excerpt": "Quoting SOP…", "score": 0.42},
    ]


def test_empty_results_return_an_empty_list_not_an_error():
    conn = _FakeConn([])
    assert search_documents("project", "proj-1", "nothing", connect=lambda: conn, embed=_fake_embed) == []
