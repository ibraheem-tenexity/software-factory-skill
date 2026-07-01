"""Pure unit tests for memory/mcp_server.py (SOF-41/T4.2) — no DB, no network, no real MCP
transport. Injects fake connect/mem/blobs/embed (mirrors search.py/store.py's own injectable-
dependency convention). The load-bearing tests here are the scope-safety ones: an agent scoped to
project A must not be able to read project B's memory by passing another project's blob_id/
chunk_id — that's asserted directly against `_in_scope_blob_ids`/`_assert_in_scope` and every
ID-taking tool, not just implied by "the query filters by scope_id."""
import asyncio

import pytest

from software_factory.memory import mcp_server as m


class _FakeConn:
    def __init__(self, table):
        """`table`: {sql_substring_marker: rows_to_return} — matched by simple substring, since
        these tests care about WHICH query ran and what it returns, not exact SQL text (that's
        covered by test_conversation_repo_rollup.py-style compiled-SQL tests elsewhere; here the
        SQL is hand-written, not Core-compiled, so substring dispatch keeps the fakes simple)."""
        self.table = table
        self.calls = []
        self.closed = False

    def execute(self, sql, params=()):
        self.calls.append((sql, tuple(params)))
        for marker, rows in self.table.items():
            if marker in sql:
                return _FakeCursor(rows)
        raise AssertionError(f"unexpected query: {sql}")

    def close(self):
        self.closed = True


class _FakeCursor:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return list(self._rows)

    def fetchone(self):
        return self._rows[0] if self._rows else None


# ── _in_scope_blob_ids / _assert_in_scope — the actual security boundary ───────────────────────

def test_in_scope_blob_ids_includes_owned_and_imported_blobs():
    conn = _FakeConn({"UNION": [{"id": 1}, {"id": 2}]})
    ids = m._in_scope_blob_ids("project-a", connect=lambda: conn)
    assert ids == {1, 2}


def test_assert_in_scope_passes_for_an_owned_blob():
    conn = _FakeConn({"UNION": [{"id": 42}]})
    m._assert_in_scope(42, "project-a", connect=lambda: conn)   # must not raise


def test_assert_in_scope_rejects_a_blob_belonging_to_another_project():
    """The core security AC: project A's token must not unlock project B's blob_id."""
    conn = _FakeConn({"UNION": [{"id": 42}]})   # project-a's in-scope set does NOT include 999
    with pytest.raises(PermissionError):
        m._assert_in_scope(999, "project-a", connect=lambda: conn)


def test_get_document_summary_rejects_an_out_of_scope_blob_id():
    conn = _FakeConn({"UNION": []})   # nothing in scope for this project

    class _ExplodesIfCalled:
        def get_doc_summary(self, blob_id): raise AssertionError("must not be called")

    with pytest.raises(PermissionError):
        m.get_document_summary("project-a", 999, connect=lambda: conn, mem=_ExplodesIfCalled())


def test_get_document_summary_returns_the_row_for_an_in_scope_blob():
    conn = _FakeConn({"UNION": [{"id": 42}]})

    class _FakeMem:
        def get_doc_summary(self, blob_id):
            assert blob_id == 42
            return {"blob_id": 42, "summary_md": "It's a pricing sheet."}

    row = m.get_document_summary("project-a", 42, connect=lambda: conn, mem=_FakeMem())
    assert row["summary_md"] == "It's a pricing sheet."


def test_get_document_summary_raises_on_a_blob_with_no_summary_yet():
    conn = _FakeConn({"UNION": [{"id": 42}]})

    class _FakeMem:
        def get_doc_summary(self, blob_id): return None

    with pytest.raises(ValueError, match="no summary"):
        m.get_document_summary("project-a", 42, connect=lambda: conn, mem=_FakeMem())


def test_get_chunk_rejects_a_chunk_whose_blob_is_out_of_scope():
    """Even though chunk_id itself carries no project scoping, its BLOB does — and that's checked
    before any content is returned. This is the same AC as get_document_summary, for chunks."""
    conn = _FakeConn({
        "FROM chunk WHERE id": [{"id": 7, "blob_id": 999, "ordinal": 0,
                                 "section_path": None, "content": "victim's secret pricing"}],
        "UNION": [],   # project-a's scope does NOT include blob_id 999
    })
    with pytest.raises(PermissionError):
        m.get_chunk("project-a", 7, connect=lambda: conn)


def test_get_chunk_raises_on_unknown_chunk_id():
    conn = _FakeConn({"FROM chunk WHERE id": []})
    with pytest.raises(ValueError, match="unknown chunk_id"):
        m.get_chunk("project-a", 12345, connect=lambda: conn)


def test_get_chunk_returns_windowed_neighbors_in_ordinal_order():
    conn = _FakeConn({
        "FROM chunk WHERE id": [{"id": 3, "blob_id": 42, "ordinal": 2,
                                 "section_path": "2 / Pricing", "content": "middle"}],
        "UNION": [{"id": 42}],
    })

    class _FakeMem:
        def chunks_for(self, blob_id):
            assert blob_id == 42
            return [
                {"id": 1, "ordinal": 0, "content": "first"},
                {"id": 2, "ordinal": 1, "content": "second"},
                {"id": 3, "ordinal": 2, "content": "middle"},
                {"id": 4, "ordinal": 3, "content": "fourth"},
                {"id": 5, "ordinal": 4, "content": "fifth"},
            ]

    out = m.get_chunk("project-a", 3, window=1, connect=lambda: conn, mem=_FakeMem())
    assert out["chunk"]["id"] == 3
    assert [n["id"] for n in out["neighbors"]] == [2, 4]   # one each side, self excluded


def test_get_chunk_window_clamps_at_the_document_boundaries():
    conn = _FakeConn({
        "FROM chunk WHERE id": [{"id": 1, "blob_id": 42, "ordinal": 0,
                                 "section_path": None, "content": "first"}],
        "UNION": [{"id": 42}],
    })

    class _FakeMem:
        def chunks_for(self, blob_id):
            return [{"id": 1, "ordinal": 0, "content": "first"},
                    {"id": 2, "ordinal": 1, "content": "second"}]

    out = m.get_chunk("project-a", 1, window=5, connect=lambda: conn, mem=_FakeMem())
    assert [n["id"] for n in out["neighbors"]] == [2]   # no underflow before index 0


# ── search_memory — always scope='project', never any other scope reachable from this MCP ──────

def test_search_memory_always_scopes_to_project_never_org():
    calls = []

    def fake_search(scope, scope_id, query, k):
        calls.append((scope, scope_id, query, k))
        return [{"content": "hit"}]

    out = m.search_memory("project-a", "pricing tiers", k=5, search_fn=fake_search)
    assert calls == [("project", "project-a", "pricing tiers", 5)]
    assert out == [{"content": "hit"}]


# ── add_memory_note — the only writer; reuses an existing notes blob rather than duplicating ────

def test_add_memory_note_rejects_empty_body():
    with pytest.raises(ValueError, match="empty"):
        m.add_memory_note("project-a", "   ")


def test_add_memory_note_creates_a_notes_blob_on_first_use():
    created = []

    class _FakeBlobs:
        def list_for(self, scope, scope_id): return []
        def record(self, scope, scope_id, storage_key, **kw):
            created.append((scope, scope_id, storage_key, kw))
            return 99

    class _FakeMem:
        def chunks_for(self, blob_id): return []
        def add_chunk(self, blob_id, scope, scope_id, ordinal, section_path, content, **kw):
            assert blob_id == 99 and ordinal == 0
            return 1001

    out = m.add_memory_note("project-a", "learned something", blobs=_FakeBlobs(), mem=_FakeMem(),
                            embed=lambda texts: [[0.1] for _ in texts])
    assert out == {"note_id": 1001}
    assert created[0][3]["kind"] == "memory_note"


def test_add_memory_note_reuses_the_existing_notes_blob_and_appends_ordinal():
    class _FakeBlobs:
        def list_for(self, scope, scope_id):
            return [{"id": 55, "kind": "memory_note"}]
        def record(self, *a, **kw): raise AssertionError("must not create a second notes blob")

    class _FakeMem:
        def chunks_for(self, blob_id):
            assert blob_id == 55
            return [{"id": 1, "ordinal": 0}, {"id": 2, "ordinal": 1}]
        def add_chunk(self, blob_id, scope, scope_id, ordinal, section_path, content, **kw):
            assert blob_id == 55 and ordinal == 2   # next after 2 existing
            return 1002

    out = m.add_memory_note("project-a", "another note", blobs=_FakeBlobs(), mem=_FakeMem(),
                            embed=lambda texts: [[0.1] for _ in texts])
    assert out == {"note_id": 1002}


def test_add_memory_note_embeds_the_note_so_its_dense_retrievable():
    class _FakeBlobs:
        def list_for(self, scope, scope_id): return [{"id": 1, "kind": "memory_note"}]

    embed_calls = []

    def fake_embed(texts):
        embed_calls.append(list(texts))
        return [[9.0, 9.0]]

    class _FakeMem:
        def chunks_for(self, blob_id): return []
        def add_chunk(self, blob_id, scope, scope_id, ordinal, section_path, content, *, dense=None,
                     **kw):
            assert dense == [9.0, 9.0]
            return 1

    m.add_memory_note("project-a", "note text", blobs=_FakeBlobs(), mem=_FakeMem(), embed=fake_embed)
    assert embed_calls == [["note text"]]


# ── _current_project_id / contextvar boundary ───────────────────────────────────────────────────

def test_current_project_id_raises_without_a_verified_token():
    with pytest.raises(PermissionError):
        m._current_project_id()


def test_current_project_id_returns_whatever_the_contextvar_holds():
    token = m._project_ctx.set("project-a")
    try:
        assert m._current_project_id() == "project-a"
    finally:
        m._project_ctx.reset(token)


# ── _BearerScopeMiddleware — the actual HTTP-layer enforcement ─────────────────────────────────

class _RecordingApp:
    def __init__(self):
        self.called = False
        self.seen_project_id = None

    async def __call__(self, scope, receive, send):
        self.called = True
        self.seen_project_id = m._current_project_id()


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _http_scope(auth_header: str | None) -> dict:
    headers = [(b"authorization", auth_header.encode())] if auth_header else []
    return {"type": "http", "headers": headers}


def test_middleware_rejects_a_request_with_no_authorization_header():
    inner = _RecordingApp()
    mw = m._BearerScopeMiddleware(inner)
    sent = []

    async def send(msg): sent.append(msg)

    _run(mw(_http_scope(None), None, send))
    assert inner.called is False
    assert sent[0]["status"] == 401


def test_middleware_rejects_an_invalid_bearer_token():
    inner = _RecordingApp()
    mw = m._BearerScopeMiddleware(inner)
    sent = []

    async def send(msg): sent.append(msg)

    _run(mw(_http_scope("Bearer not-a-real-token"), None, send))
    assert inner.called is False
    assert sent[0]["status"] == 401


def test_middleware_admits_a_valid_token_and_exposes_the_project_id_to_the_app():
    from software_factory import auth as sf_auth
    token = sf_auth.sign_scope_token("project-a")
    inner = _RecordingApp()
    mw = m._BearerScopeMiddleware(inner)

    async def send(msg): pass

    _run(mw(_http_scope(f"Bearer {token}"), None, send))
    assert inner.called is True
    assert inner.seen_project_id == "project-a"


def test_middleware_never_leaks_project_id_across_requests():
    """Two sequential requests with different tokens must each see only their OWN project — the
    contextvar must not retain the previous request's scope."""
    from software_factory import auth as sf_auth
    mw = m._BearerScopeMiddleware(_RecordingApp())

    async def send(msg): pass

    inner_a = _RecordingApp()
    mw_a = m._BearerScopeMiddleware(inner_a)
    _run(mw_a(_http_scope(f"Bearer {sf_auth.sign_scope_token('project-a')}"), None, send))
    assert inner_a.seen_project_id == "project-a"

    inner_b = _RecordingApp()
    mw_b = m._BearerScopeMiddleware(inner_b)
    _run(mw_b(_http_scope(f"Bearer {sf_auth.sign_scope_token('project-b')}"), None, send))
    assert inner_b.seen_project_id == "project-b"

    with pytest.raises(PermissionError):
        m._current_project_id()   # context reset after each request — nothing leaks outside one
