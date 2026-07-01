"""SOF-29: MemoryStore — thin CRUD over dbshim for doc_summary/chunk (T3.1's store layer).

No business logic (ingestion orchestration is T3.2; search/RRF is T4.1) — just persistence for
what embed.py/chunker.py produce, plus the read side of the coarse-to-fine "project overview"
tier. Everything is scope/scope_id-filtered, mirroring blobs, so project- and org-scoped memory
share one app-layer filter shape (isolation is app-layer + credential-scoped MCP, not RLS).
"""
from __future__ import annotations

from .. import dbshim


class MemoryStore:
    def __init__(self, connect=None):
        # dbshim.connect(path)'s `path` argument is unused for the actual connection target
        # (a legacy artifact of the old per-project-sqlite convention) — the real target is
        # DATABASE_URL. `connect` is injectable for tests. pgvector's register_vector() is
        # registered centrally in dbshim._StatePool._configure (see that module) — every
        # connection this returns already has it, so dense/embedding reads come back as real
        # arrays, not strings.
        self._connect = connect or (lambda: dbshim.connect("."))

    # ---- doc_summary --------------------------------------------------------------------
    def upsert_doc_summary(
        self, blob_id: int, scope: str, scope_id: str, *,
        summary_md: str | None = None, key_facts: list | None = None,
        outline: list | None = None, embedding: list[float] | None = None,
        token_count: int | None = None, content_sha256: str | None = None,
        status: str = "pending",
    ) -> None:
        import json
        conn = self._connect()
        try:
            conn.execute(
                "INSERT INTO doc_summary "
                "(blob_id, scope, scope_id, summary_md, key_facts, outline, embedding, "
                " token_count, content_sha256, status) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT (blob_id) DO UPDATE SET "
                "summary_md=excluded.summary_md, key_facts=excluded.key_facts, "
                "outline=excluded.outline, embedding=excluded.embedding, "
                "token_count=excluded.token_count, content_sha256=excluded.content_sha256, "
                "status=excluded.status, updated_at=now()",
                (blob_id, scope, scope_id, summary_md, json.dumps(key_facts or []),
                 json.dumps(outline or []), embedding, token_count, content_sha256, status),
            )
        finally:
            conn.close()

    def get_doc_summary(self, blob_id: int) -> dict | None:
        conn = self._connect()
        try:
            return conn.execute(
                "SELECT * FROM doc_summary WHERE blob_id = ?", (blob_id,)
            ).fetchone()
        finally:
            conn.close()

    def list_doc_summaries(self, scope: str, scope_id: str) -> dict[int, dict]:
        """blob_id -> {summary_md, status} for every doc_summary row in this scope — a bulk read
        for enriching a document listing (SOF-36) without an N+1 per-blob query."""
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT blob_id, summary_md, status FROM doc_summary WHERE scope = ? AND scope_id = ?",
                (scope, scope_id),
            ).fetchall()
        finally:
            conn.close()
        return {r["blob_id"]: r for r in rows}

    # ---- chunk ---------------------------------------------------------------------------
    def add_chunk(
        self, blob_id: int, scope: str, scope_id: str, ordinal: int,
        section_path: str | None, content: str, *,
        dense: list[float] | None = None, token_count: int | None = None,
    ) -> int:
        conn = self._connect()
        try:
            row = conn.execute(
                "INSERT INTO chunk (blob_id, scope, scope_id, ordinal, section_path, "
                "content, dense, token_count) VALUES (?, ?, ?, ?, ?, ?, ?, ?) RETURNING id",
                (blob_id, scope, scope_id, ordinal, section_path, content, dense, token_count),
            ).fetchone()
            return row["id"]
        finally:
            conn.close()

    def chunks_for(self, blob_id: int) -> list[dict]:
        conn = self._connect()
        try:
            return conn.execute(
                "SELECT * FROM chunk WHERE blob_id = ? ORDER BY ordinal", (blob_id,)
            ).fetchall()
        finally:
            conn.close()

    def replace_chunks(self, blob_id: int, chunks: list[tuple[int, str | None, str]], *,
                       scope: str, scope_id: str, dense: list[list[float]] | None = None) -> None:
        """Delete this document's existing chunks and insert the new set — a re-ingest (changed
        content_hash) replaces wholesale rather than trying to diff ordinals."""
        conn = self._connect()
        try:
            conn.execute("DELETE FROM chunk WHERE blob_id = ?", (blob_id,))
            for i, (ordinal, section_path, content) in enumerate(chunks):
                vec = dense[i] if dense else None
                conn.execute(
                    "INSERT INTO chunk (blob_id, scope, scope_id, ordinal, section_path, "
                    "content, dense) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (blob_id, scope, scope_id, ordinal, section_path, content, vec),
                )
        finally:
            conn.close()

    # ---- overview (read side of the "2,000-ft view" — the rollup itself is written by T3.2) --
    def overview(self, scope: str, scope_id: str) -> dict:
        """The coarse top tier an agent reads first: doc_summary counts by status for this
        scope, plus (project scope only) the cached rollup blurb from projectstate.data —
        None until T3.2's ingestion pipeline writes one. Org scope has no persisted rollup
        cache yet (no organizations.context_rollup column exists) — flagged, not fabricated."""
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT status, count(*) as n FROM doc_summary "
                "WHERE scope = ? AND scope_id = ? GROUP BY status",
                (scope, scope_id),
            ).fetchall()
        finally:
            conn.close()
        by_status = {r["status"]: r["n"] for r in rows}
        rollup = None
        if scope == "project":
            rollup = self._project_rollup(scope_id)
        return {"scope": scope, "scope_id": scope_id, "doc_counts": by_status, "rollup": rollup}

    def _project_rollup(self, project_id: str) -> str | None:
        import json
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT data FROM projectstate WHERE project_id = ?", (project_id,)
            ).fetchone()
        finally:
            conn.close()
        if not row or not row.get("data"):
            return None
        try:
            return json.loads(row["data"]).get("memory_overview")
        except (ValueError, TypeError):
            return None

    # ---- learned facts (SOF-37: the reflection step's "What I learned" surface) -----------
    def learned_facts(self, scope: str, scope_id: str) -> list[dict]:
        """Every key_fact from every READY doc_summary in this scope, each enriched with its
        source document's display name (via a blobs join) — the "links to a real source" AC.
        Only ever returns facts that were already filtered as referenced at ingest time
        (memory/ingest.py._filter_key_facts) — this method does no filtering of its own, it
        just flattens + joins what's already trustworthy."""
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT ds.key_facts, b.id AS blob_id, b.name AS document_name "
                "FROM doc_summary ds JOIN blobs b ON b.id = ds.blob_id "
                "WHERE ds.scope = ? AND ds.scope_id = ? AND ds.status = ?",
                (scope, scope_id, "ready"),
            ).fetchall()
        finally:
            conn.close()
        out = []
        for row in rows:
            facts = row["key_facts"] or []
            for f in facts:
                out.append({**f, "document_name": row["document_name"]})
        return out
