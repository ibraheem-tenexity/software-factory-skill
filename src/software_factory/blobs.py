"""Manifest of stored blobs — the durable index of what `storage` wrote, for both run-scoped and
org-scoped files. One Postgres table (`public.blobs`); schema owned by the SQLAlchemy models.

A row is metadata only (scope, scope_id, kind, storage_key, content_type, size, sha256); the bytes
live in Supabase Storage (or the local fallback) addressed by `storage_key`.

DATA ACCESS: all `blobs`/`blob_uses` SQL lives in `repositories.blobs.BlobRepository`
(SQLAlchemy Core); this store keeps only the scope validation.
"""
from __future__ import annotations

from .repositories._exec import GlobalExec
from .repositories.blobs import BlobRepository


class BlobStore:
    def __init__(self):
        self._repo = BlobRepository(GlobalExec())

    def record(self, scope: str, scope_id: str, storage_key: str, *, kind: str | None = None,
               name: str | None = None, tag: str | None = None,
               content_type: str | None = None, size_bytes: int | None = None,
               sha256: str | None = None) -> int:
        """Record one stored blob and return its id. `scope` is 'project' or 'org'; `name`/`tag` are
        the display filename + category shown in the org knowledge base."""
        if scope not in ("project", "org"):
            raise ValueError(f"blob scope must be 'project' or 'org', got {scope!r}")
        return self._repo.insert(scope, scope_id, kind, name, tag, storage_key, content_type,
                                 size_bytes, sha256)

    def list_for(self, scope: str, scope_id: str) -> list[dict]:
        return [dict(r) for r in self._repo.list_for(scope, scope_id)]

    def set_scope(self, blob_id: int, scope: str, scope_id: str) -> None:
        """Move a blob between scopes (project ⇄ org) — PRD §2.4 material scope toggle."""
        if scope not in ("project", "org"):
            raise ValueError(f"blob scope must be 'project' or 'org', got {scope!r}")
        self._repo.set_scope(blob_id, scope, scope_id)

    # -- org knowledge base (org-scoped docs + reuse count) -----------------------------
    def list_org_docs(self, org_id: str) -> list[dict]:
        """The org's knowledge-base docs, each with `used_count` = distinct projects that have
        imported it and `updated` (epoch seconds). Newest first."""
        return [dict(r) for r in self._repo.list_org_docs(org_id)]

    def get_blob(self, blob_id: int) -> dict | None:
        row = self._repo.by_id(blob_id)
        return dict(row) if row else None

    def record_use(self, blob_id: int, project_id: str) -> int:
        """Note that a project (`project_id`) imported this org doc; return the new distinct-project
        count. Re-recording the same project is a no-op for the count."""
        self._repo.record_use(blob_id, project_id)
        return self._repo.distinct_use_count(blob_id)

    def update(self, blob_id: int, *, name: str | None = None, tag: str | None = None) -> None:
        """Rename / retag a doc (only the provided fields)."""
        cols = {k: v for k, v in (("name", name), ("tag", tag)) if v is not None}
        self._repo.update_fields(blob_id, **cols)

    def delete(self, blob_id: int) -> None:
        self._repo.delete(blob_id)
