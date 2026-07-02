"""SOF-38 (T4.1): hybrid dense + tsvector search over `chunk`, fused with Reciprocal Rank Fusion —
project-memory-integration.md §2. Dense (pgvector cosine `<=>`) and keyword (Postgres native
`tsvector`/`ts_rank_cd`) channels are each capped at `_CHANNEL_LIMIT`, then combined by RRF
(`1/(_RRF_K + rank)` per channel, summed) so a passage strong in either channel — not just both —
surfaces. No reranker/contextual-retrieval prepend/learned-sparse here; those are deferred per the
ticket's own scope.

Written as a single SELECT with subqueries in FROM, not a `WITH` CTE: `PgConn.execute()`
(dbshim.py) decides whether to fetch rows by checking `head.startswith("SELECT")` — a
`WITH ...` CTE query fails that check and silently returns zero rows every time (confirmed by
reading dbshim.py; no existing caller uses a CTE, so this never surfaced before). Subqueries in
FROM are equivalent for a query with no recursion, and this avoids touching dbshim.py at all.

`dense <=> ?::vector` — the explicit cast is required (found against a real seeded DB, review
by y96ilz0o): a bare `?` binds the query vector as a generic param with no column-type context,
and Postgres has no `vector <=> double precision[]` operator, so the comparison raises
`UndefinedFunction` at runtime. An INSERT into a `vector` column gets pgvector's assignment cast
automatically; a raw operator comparison like this one does not — first time this codebase has
done the latter.
"""
from __future__ import annotations

from .. import dbshim
from .embed import embed_texts

_RRF_K = 60           # RRF's own smoothing constant (not the caller's k) — standard value
_CHANNEL_LIMIT = 50    # top-N per channel before fusion, per the design doc


def _scope_where(scope: str, scope_id: str) -> tuple[str, list]:
    """SQL fragment (no leading AND/WHERE) + its positional params, in the same order the '?'
    placeholders appear in the fragment. Project scope also pulls in org docs imported into the
    project via `blob_uses` (this ticket's own scope note) — org scope has no such expansion
    (nothing imports FROM a project INTO an org)."""
    if scope == "project":
        return (
            "(scope = ? AND scope_id = ?) OR blob_id IN "
            "(SELECT blob_id FROM blob_uses WHERE project_id = ?)",
            [scope, scope_id, scope_id],
        )
    return "scope = ? AND scope_id = ?", [scope, scope_id]


def search(scope: str, scope_id: str, query: str, k: int = 8, *, connect=None, embed=None) -> list[dict]:
    """Top-`k` passages for `query`, scoped to `scope`/`scope_id`, fused from the dense and
    keyword channels. Each hit: `{"content", "document" (blob name), "section_path", "score"}`,
    highest score first.

    `connect`/`embed` are injectable — mirrors `MemoryStore`'s `connect` param and `embed_texts`'
    own `client` param — so the SQL-building/fusion logic is testable without a live DB or a
    network call to the embedding provider."""
    if scope not in ("project", "org"):
        raise ValueError(f"unsupported scope {scope!r} — must be 'project' or 'org'")
    text = (query or "").strip()
    if not text:
        raise ValueError("query is empty")

    connect = connect or (lambda: dbshim.connect("."))
    embed = embed or embed_texts
    qvec = embed([text])[0]

    scope_sql, scope_params = _scope_where(scope, scope_id)
    sql = f"""
    SELECT c.content, c.section_path, b.name AS document,
           coalesce(1.0/({_RRF_K}+dense.rnk), 0) + coalesce(1.0/({_RRF_K}+kw.rnk), 0) AS score
    FROM chunk c
    JOIN blobs b ON b.id = c.blob_id
    LEFT JOIN (
      SELECT id, row_number() OVER (ORDER BY dense <=> ?::vector) AS rnk
      FROM chunk
      WHERE {scope_sql}
      ORDER BY dense <=> ?::vector LIMIT {_CHANNEL_LIMIT}
    ) AS dense ON dense.id = c.id
    LEFT JOIN (
      SELECT id, row_number() OVER (
               ORDER BY ts_rank_cd(fts, plainto_tsquery('english', ?)) DESC) AS rnk
      FROM chunk
      WHERE ({scope_sql}) AND fts @@ plainto_tsquery('english', ?)
      ORDER BY ts_rank_cd(fts, plainto_tsquery('english', ?)) DESC LIMIT {_CHANNEL_LIMIT}
    ) AS kw ON kw.id = c.id
    WHERE dense.id IS NOT NULL OR kw.id IS NOT NULL
    ORDER BY score DESC LIMIT ?
    """
    params = [qvec, *scope_params, qvec, text, *scope_params, text, text, k]

    conn = connect()
    try:
        rows = conn.execute(sql, params).fetchall()
    finally:
        conn.close()
    return [{"content": r["content"], "document": r["document"],
             "section_path": r["section_path"], "score": float(r["score"])} for r in rows]


def search_documents(scope: str, scope_id: str, query: str, k: int = 8, *,
                     connect=None, embed=None) -> list[dict]:
    """SOF-60: coarse, whole-document search — which documents are relevant to `query`, ranked
    by cosine similarity over `doc_summary.embedding` (written at ingest, previously never
    queried). The document-level tier of coarse-to-fine retrieval: call this to pick the 2-3
    relevant documents, then `search()` for exact passages. Dense-only by design — summaries
    have no single canonical text column to generate a tsvector from the way `chunk.content`
    does, and keyword precision is already covered by `search()`. No vector index needed:
    one row per document is a few hundred rows at most, an exact sequential scan.

    Each hit: `{"blob_id", "document", "summary_excerpt", "score"}` — blob_id is the pointer
    for the follow-up call (get_document_summary / full-document read), unlike search()'s
    chunk hits which carry their content directly. Same no-CTE + `?::vector` cast constraints
    as search() (see module docstring)."""
    if scope not in ("project", "org"):
        raise ValueError(f"unsupported scope {scope!r} — must be 'project' or 'org'")
    text = (query or "").strip()
    if not text:
        raise ValueError("query is empty")

    connect = connect or (lambda: dbshim.connect("."))
    embed = embed or embed_texts
    qvec = embed([text])[0]

    scope_sql, scope_params = _scope_where(scope, scope_id)
    sql = f"""
    SELECT ds.blob_id, b.name AS document,
           coalesce(left(ds.summary_md, 300), '') AS summary_excerpt,
           1 - (ds.embedding <=> ?::vector) AS score
    FROM doc_summary ds
    JOIN blobs b ON b.id = ds.blob_id
    WHERE ({scope_sql}) AND ds.status = 'ready' AND ds.embedding IS NOT NULL
    ORDER BY ds.embedding <=> ?::vector LIMIT ?
    """
    params = [qvec, *scope_params, qvec, k]

    conn = connect()
    try:
        rows = conn.execute(sql, params).fetchall()
    finally:
        conn.close()
    return [{"blob_id": r["blob_id"], "document": r["document"],
             "summary_excerpt": r["summary_excerpt"], "score": float(r["score"])} for r in rows]
