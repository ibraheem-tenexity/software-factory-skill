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
               sha256: str | None = None, source_blob_id: int | None = None,
               source_page: int | None = None, provenance: dict | None = None,
               directory_id: str | None = None) -> int:
        """Record one stored blob and return its id. `scope` is 'project' or 'org'; `name`/`tag` are
        the display filename + category shown in the org knowledge base. `source_blob_id`/
        `source_page`/`provenance` (SOF-32) are set only when this blob is itself an asset
        extracted FROM another blob (e.g. an image pulled out of a document page) — leave unset
        for an original upload. `directory_id` (SOF-253) files the blob under a Files-tree directory
        of the SAME scope in the same insert; leave None for an unfiled blob."""
        if scope not in ("project", "org"):
            raise ValueError(f"blob scope must be 'project' or 'org', got {scope!r}")
        return self._repo.insert(scope, scope_id, kind, name, tag, storage_key, content_type,
                                 size_bytes, sha256, source_blob_id=source_blob_id,
                                 source_page=source_page, provenance=provenance,
                                 directory_id=directory_id)

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

    def descendants(self, blob_id: int) -> list[dict]:
        """Return a source blob and extraction descendants, with children before parents."""
        root = self.get_blob(blob_id)
        if not root:
            return []

        def collect(blob: dict) -> list[dict]:
            children = [dict(row) for row in self._repo.children_of(blob["id"])]
            return [item for child in children for item in collect(child)] + [blob]

        return collect(root)

    def delete_tree(self, blob_id: int) -> list[dict]:
        """Delete a source blob and extraction descendants, returning children before parents."""
        rows = self.descendants(blob_id)
        for row in rows:
            self._repo.delete(row["id"])
        return rows

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

    # -- source-directory tree (SOF-251/SOF-253) ----------------------------------------
    def list_directories(self, scope: str, scope_id: str) -> list[dict]:
        """Every directory row in one scope (roots first). The caller derives the tree + counts."""
        return [dict(r) for r in self._repo.list_directories(scope, scope_id)]

    def get_directory(self, directory_id: str) -> dict | None:
        row = self._repo.directory_by_id(directory_id)
        return dict(row) if row else None

    def ensure_root(self, scope: str, scope_id: str, name: str) -> dict:
        """Return the persisted per-scope root, creating it if the scope owns no tree yet. Idempotent
        and matches the migration's backfill (one NULL-parent root per scope), so the Files browser
        always has a real root id to hang folders under even for a scope that gained its first blob
        after 0034 ran."""
        if scope not in ("project", "org"):
            raise ValueError(f"directory scope must be 'project' or 'org', got {scope!r}")
        row = self._repo.find_root(scope, scope_id)
        if row:
            return dict(row)
        self._repo.insert_directory(scope, scope_id, None, name or scope_id)
        return dict(self._repo.find_root(scope, scope_id))

    def create_directory(self, scope: str, scope_id: str, parent_id: str, name: str) -> str:
        """Create a child directory under a real same-scope parent and return its id. Scope match is
        enforced by the composite parent FK; sibling-name uniqueness is validated by the caller."""
        if scope not in ("project", "org"):
            raise ValueError(f"directory scope must be 'project' or 'org', got {scope!r}")
        return self._repo.insert_directory(scope, scope_id, parent_id, name)

    def sibling_name_exists(self, scope: str, scope_id: str, parent_id: str, name: str) -> bool:
        return self._repo.sibling_name_exists(scope, scope_id, parent_id, name)

    def assign_directory(self, blob_id: int, directory_id: str | None) -> None:
        """Re-home a blob to a directory (or None to unfile). Caller validates same-scope first."""
        self._repo.set_directory(blob_id, directory_id)

    def touch_directory(self, directory_id: str) -> None:
        """Flag a directory's rollup summary stale after its member set changed."""
        self._repo.touch_directory(directory_id)
