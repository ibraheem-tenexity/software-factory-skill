"""Manifest of stored blobs — the durable index of what `storage` wrote, for both run-scoped and
org-scoped files. One Postgres table (`public.blobs`); schema owned by the SQLAlchemy models.

A row is metadata only (scope, scope_id, kind, storage_key, content_type, size, sha256); the bytes
live in Supabase Storage (or the local fallback) addressed by `storage_key`.
"""
from __future__ import annotations

import os

from . import dbshim


class BlobStore:
    def __init__(self):
        pass

    def record(self, scope: str, scope_id: str, storage_key: str, *, kind: str | None = None,
               name: str | None = None, tag: str | None = None,
               content_type: str | None = None, size_bytes: int | None = None,
               sha256: str | None = None) -> int:
        """Record one stored blob and return its id. `scope` is 'project' or 'org'; `name`/`tag` are
        the display filename + category shown in the org knowledge base."""
        if scope not in ("project", "org"):
            raise ValueError(f"blob scope must be 'project' or 'org', got {scope!r}")
        conn = dbshim._pg_connect(os.environ["DATABASE_URL"])
        try:
            with conn.transaction():
                cur = conn.cursor()
                cur.execute(
                    "INSERT INTO public.blobs (scope, scope_id, kind, name, tag, storage_key, "
                    "content_type, size_bytes, sha256) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) "
                    "RETURNING id",
                    (scope, scope_id, kind, name, tag, storage_key, content_type, size_bytes,
                     sha256))
                return cur.fetchone()["id"]
        finally:
            conn.close()

    def list_for(self, scope: str, scope_id: str) -> list[dict]:
        conn = dbshim._pg_connect(os.environ["DATABASE_URL"])
        try:
            with conn.transaction():
                cur = conn.cursor()
                cur.execute(
                    "SELECT scope, scope_id, kind, name, tag, storage_key, content_type, "
                    "size_bytes, sha256 FROM public.blobs WHERE scope=%s AND scope_id=%s "
                    "ORDER BY id", (scope, scope_id))
                return [dict(r) for r in cur.fetchall()]
        finally:
            conn.close()

    # -- org knowledge base (org-scoped docs + reuse count) -----------------------------
    def list_org_docs(self, org_id: str) -> list[dict]:
        """The org's knowledge-base docs, each with `used_count` = distinct projects that have
        imported it and `updated` (epoch seconds). Newest first."""
        conn = dbshim._pg_connect(os.environ["DATABASE_URL"])
        try:
            with conn.transaction():
                cur = conn.cursor()
                cur.execute(
                    "SELECT b.id, b.name, b.tag, b.kind, b.content_type, b.size_bytes, "
                    "extract(epoch from b.created_at) AS updated, "
                    "count(DISTINCT u.project_id) AS used_count "
                    "FROM public.blobs b "
                    "LEFT JOIN public.blob_uses u ON u.blob_id = b.id "
                    "WHERE b.scope='org' AND b.scope_id=%s "
                    "GROUP BY b.id ORDER BY b.id DESC", (org_id,))
                return [dict(r) for r in cur.fetchall()]
        finally:
            conn.close()

    def get_blob(self, blob_id: int) -> dict | None:
        conn = dbshim._pg_connect(os.environ["DATABASE_URL"])
        try:
            with conn.transaction():
                cur = conn.cursor()
                cur.execute(
                    "SELECT id, scope, scope_id, kind, name, tag, storage_key, content_type, "
                    "size_bytes, sha256 FROM public.blobs WHERE id=%s", (blob_id,))
                row = cur.fetchone()
                return dict(row) if row else None
        finally:
            conn.close()

    def record_use(self, blob_id: int, project_id: str) -> int:
        """Note that a project (`project_id`) imported this org doc; return the new distinct-project
        count. Re-recording the same project is a no-op for the count."""
        conn = dbshim._pg_connect(os.environ["DATABASE_URL"])
        try:
            with conn.transaction():
                cur = conn.cursor()
                cur.execute(
                    "INSERT INTO public.blob_uses (blob_id, project_id) VALUES (%s,%s)",
                    (blob_id, project_id))
                cur.execute(
                    "SELECT count(DISTINCT project_id) AS n FROM public.blob_uses WHERE blob_id=%s",
                    (blob_id,))
                return cur.fetchone()["n"]
        finally:
            conn.close()

    def update(self, blob_id: int, *, name: str | None = None, tag: str | None = None) -> None:
        """Rename / retag a doc (only the provided fields)."""
        sets, vals = [], []
        for col, val in (("name", name), ("tag", tag)):
            if val is not None:
                sets.append(f"{col}=%s")
                vals.append(val)
        if not sets:
            return
        vals.append(blob_id)
        conn = dbshim._pg_connect(os.environ["DATABASE_URL"])
        try:
            with conn.transaction():
                conn.cursor().execute(
                    f"UPDATE public.blobs SET {', '.join(sets)} WHERE id=%s", tuple(vals))
        finally:
            conn.close()

    def delete(self, blob_id: int) -> None:
        conn = dbshim._pg_connect(os.environ["DATABASE_URL"])
        try:
            with conn.transaction():
                cur = conn.cursor()
                cur.execute("DELETE FROM public.blob_uses WHERE blob_id=%s", (blob_id,))
                cur.execute("DELETE FROM public.blobs WHERE id=%s", (blob_id,))
        finally:
            conn.close()
