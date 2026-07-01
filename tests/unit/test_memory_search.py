"""Pure unit tests for memory/search.py (SOF-38/T4.1) — no DB, no network. Injects a fake
`connect`/`embed` (mirrors MemoryStore's injectable connect and embed_texts' injectable client) so
the SQL-building, placeholder/param alignment, and RRF-fusion-result mapping are all verified
without a live Postgres or an embedding-provider call. Matches the standing no-DB-connection
constraint on this box — seed-and-query tests against a real corpus are deferred to the scratch DB
(see PR notes)."""
import pytest

from software_factory.memory.search import search, _scope_where


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


# ── Input validation ─────────────────────────────────────────────────────────────────────────

def test_rejects_unsupported_scope():
    with pytest.raises(ValueError, match="project.*org|org.*project"):
        search("bogus", "sid", "query", connect=lambda: _FakeConn([]), embed=_fake_embed)


def test_rejects_empty_query():
    with pytest.raises(ValueError, match="empty"):
        search("project", "sid", "   ", connect=lambda: _FakeConn([]), embed=_fake_embed)


# ── _scope_where ─────────────────────────────────────────────────────────────────────────────

def test_scope_where_project_expands_via_blob_uses():
    sql, params = _scope_where("project", "proj-1")
    assert "blob_uses" in sql
    assert params == ["project", "proj-1", "proj-1"]
    assert sql.count("?") == len(params)


def test_scope_where_org_has_no_blob_uses_expansion():
    sql, params = _scope_where("org", "org-1")
    assert "blob_uses" not in sql
    assert params == ["org", "org-1"]
    assert sql.count("?") == len(params)


# ── search() — SQL/param alignment + result mapping, via a fake connection ─────────────────────

def test_placeholder_count_matches_param_count_project_scope():
    conn = _FakeConn([])
    search("project", "proj-1", "pricing tiers", k=8, connect=lambda: conn, embed=_fake_embed)
    assert conn.executed_sql.count("?") == len(conn.executed_params)


def test_placeholder_count_matches_param_count_org_scope():
    conn = _FakeConn([])
    search("org", "org-1", "pricing tiers", k=8, connect=lambda: conn, embed=_fake_embed)
    assert conn.executed_sql.count("?") == len(conn.executed_params)


def test_query_is_embedded_and_the_vector_used_as_the_dense_param():
    conn = _FakeConn([])
    calls = []

    def spy_embed(texts):
        calls.append(list(texts))
        return [[9.0, 9.0]]

    search("project", "proj-1", "pricing tiers", connect=lambda: conn, embed=spy_embed)
    assert calls == [["pricing tiers"]]
    assert conn.executed_params[0] == [9.0, 9.0]     # dense param, first placeholder


def test_k_is_passed_through_as_the_final_limit_param():
    conn = _FakeConn([])
    search("project", "proj-1", "pricing tiers", k=3, connect=lambda: conn, embed=_fake_embed)
    assert conn.executed_params[-1] == 3


def test_default_k_is_eight():
    conn = _FakeConn([])
    search("project", "proj-1", "pricing tiers", connect=lambda: conn, embed=_fake_embed)
    assert conn.executed_params[-1] == 8


def test_dense_comparison_casts_the_param_to_vector():
    """A bare `?` binds the query vector with no column-type context — Postgres has no
    `vector <=> double precision[]` operator and raises UndefinedFunction at runtime (found
    against a real seeded DB in review). `?::vector` fixes it; lock the cast in."""
    conn = _FakeConn([])
    search("project", "proj-1", "pricing tiers", connect=lambda: conn, embed=_fake_embed)
    assert conn.executed_sql.count("<=> ?::vector") == 2


def test_sql_uses_subqueries_not_a_cte_so_pgconn_still_detects_a_select():
    """PgConn.execute() only fetches rows when the statement's head is 'SELECT' (or an INSERT
    RETURNING) — a `WITH ...` CTE query silently returns zero rows every time. Locks that in."""
    conn = _FakeConn([])
    search("project", "proj-1", "pricing tiers", connect=lambda: conn, embed=_fake_embed)
    assert conn.executed_sql.strip().upper().startswith("SELECT")


def test_connection_is_always_closed():
    conn = _FakeConn([])
    search("project", "proj-1", "pricing tiers", connect=lambda: conn, embed=_fake_embed)
    assert conn.closed is True


def test_maps_rows_to_the_documented_hit_shape():
    rows = [
        {"content": "Widget pricing is $10/unit.", "section_path": "2 / 2.3 Pricing",
         "document": "pricing.pdf", "score": 0.031},
        {"content": "SKU 4471-B is discontinued.", "section_path": None,
         "document": "catalog.pdf", "score": 0.016},
    ]
    conn = _FakeConn(rows)
    hits = search("project", "proj-1", "pricing", connect=lambda: conn, embed=_fake_embed)
    assert hits == [
        {"content": "Widget pricing is $10/unit.", "document": "pricing.pdf",
         "section_path": "2 / 2.3 Pricing", "score": 0.031},
        {"content": "SKU 4471-B is discontinued.", "document": "catalog.pdf",
         "section_path": None, "score": 0.016},
    ]


def test_empty_results_return_an_empty_list_not_an_error():
    conn = _FakeConn([])
    assert search("project", "proj-1", "nothing matches", connect=lambda: conn, embed=_fake_embed) == []
