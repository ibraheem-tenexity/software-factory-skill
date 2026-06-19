"""Manifest of stored blobs — the durable index of what `storage` wrote, for both run-scoped and
org-scoped files. One Postgres table (`public.blobs`); schema owned by the SQLAlchemy models.

A row is metadata only (scope, scope_id, kind, storage_key, content_type, size, sha256); the bytes
live in Supabase Storage (or the local fallback) addressed by `storage_key`.
"""
from __future__ import annotations

import os

from . import dbshim


class BlobStore:
    def __init__(self, sqlite_path: str = ""):
        # `sqlite_path` is vestigial (Postgres everywhere); kept so existing call sites pass a path.
        pass

    def record(self, scope: str, scope_id: str, storage_key: str, *, kind: str | None = None,
               content_type: str | None = None, size_bytes: int | None = None,
               sha256: str | None = None) -> None:
        """Record one stored blob. `scope` is 'run' or 'org'."""
        if scope not in ("run", "org"):
            raise ValueError(f"blob scope must be 'run' or 'org', got {scope!r}")
        conn = dbshim._pg_connect(os.environ["DATABASE_URL"])
        try:
            with conn.transaction():
                conn.cursor().execute(
                    "INSERT INTO public.blobs (scope, scope_id, kind, storage_key, content_type, "
                    "size_bytes, sha256) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                    (scope, scope_id, kind, storage_key, content_type, size_bytes, sha256))
        finally:
            conn.close()

    def list_for(self, scope: str, scope_id: str) -> list[dict]:
        conn = dbshim._pg_connect(os.environ["DATABASE_URL"])
        try:
            with conn.transaction():
                cur = conn.cursor()
                cur.execute(
                    "SELECT scope, scope_id, kind, storage_key, content_type, size_bytes, sha256 "
                    "FROM public.blobs WHERE scope=%s AND scope_id=%s ORDER BY id", (scope, scope_id))
                return [dict(r) for r in cur.fetchall()]
        finally:
            conn.close()
