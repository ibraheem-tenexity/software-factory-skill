"""Pure CRUD for `blobs` + `blob_uses` + the `directories` source-tree (SQLAlchemy Core). Global
tables — no project-path scoping, so every method takes its filter values explicitly; no
getter/closure, no cycle risk (see #212).

`directories` (SOF-251/SOF-253) is the Files-browser tree that source blobs live in; its SQL lives
here beside the blob membership column (`blobs.directory_id`) rather than in a separate pass-through
repository, so the source-material persistence boundary stays one owner."""
from __future__ import annotations

from sqlalchemy import select, insert, update, delete, func, distinct

from ..models import blobs, blob_uses, directories
from ._compile import epoch_cast, serialize_jsonb, uuid_str_cast

# directory_id/created_at are new to the projection (SOF-253): the Files tree needs each blob's
# persisted directory membership and upload time. UUID/epoch columns go through the GlobalExec
# raw-SQL casts so they decode to str/float, not uuid.UUID/Decimal.
_BLOB_COLS = (blobs.c.id, blobs.c.scope, blobs.c.scope_id, blobs.c.kind, blobs.c.name, blobs.c.tag,
              blobs.c.storage_key, blobs.c.content_type, blobs.c.size_bytes, blobs.c.sha256,
              blobs.c.source_blob_id, blobs.c.source_page, blobs.c.provenance,
              uuid_str_cast(blobs.c.directory_id).label("directory_id"),
              epoch_cast(blobs.c.created_at).label("created_at"))

_DIR_COLS = (uuid_str_cast(directories.c.id).label("id"), directories.c.scope,
             directories.c.scope_id, uuid_str_cast(directories.c.parent_id).label("parent_id"),
             directories.c.name, directories.c.summary_md, directories.c.summary_status,
             directories.c.summary_source_hash,
             epoch_cast(directories.c.last_successful_summary_at).label("last_successful_summary_at"),
             epoch_cast(directories.c.created_at).label("created_at"),
             epoch_cast(directories.c.updated_at).label("updated_at"))


class BlobRepository:
    def __init__(self, exec_):
        self._x = exec_

    def insert(self, scope, scope_id, kind, name, tag, storage_key, content_type, size_bytes,
              sha256, *, source_blob_id=None, source_page=None, provenance=None,
              directory_id=None) -> int:
        # provenance is JSONB; this repo's GlobalExec compiles to raw SQL + a plain psycopg3
        # cursor.execute (not a real SQLAlchemy Connection), so the JSONB Python-type adapter
        # never runs — a bare dict must be pre-serialized, same as key_facts/outline in
        # memory/store.py, or every blob insert (incl. the already-live upload routes, since
        # provenance now defaults on every call) breaks.
        # directory_id (SOF-253): membership is written in the SAME insert as the blob row, so an
        # upload into a directory can never persist a blob without its directory (no orphan). The
        # composite FK (directory_id, scope, scope_id) rejects a cross-scope directory at write.
        stmt = insert(blobs).values(scope=scope, scope_id=scope_id, kind=kind, name=name, tag=tag,
                                    storage_key=storage_key, content_type=content_type,
                                    size_bytes=size_bytes, sha256=sha256,
                                    source_blob_id=source_blob_id, source_page=source_page,
                                    directory_id=directory_id,
                                    provenance=serialize_jsonb(provenance, default={})).returning(blobs.c.id)
        return self._x.fetchone(stmt)["id"]

    def list_for(self, scope, scope_id) -> list:
        return self._x.fetchall(select(*_BLOB_COLS)
                                .where(blobs.c.scope == scope, blobs.c.scope_id == scope_id)
                                .order_by(blobs.c.id))

    def set_scope(self, blob_id, scope, scope_id) -> None:
        # Clearing directory_id is required, not cosmetic: a blob's directory FK pins
        # (directory_id, scope, scope_id) to a same-scope directory, so carrying the old
        # scope's directory into the new scope would violate that FK. The moved blob lands
        # unfiled in its new scope; SOF-253 re-homes it under the new scope's tree.
        self._x.execute(update(blobs).where(blobs.c.id == blob_id)
                        .values(scope=scope, scope_id=scope_id, directory_id=None))

    def list_org_docs(self, org_id) -> list:
        j = blobs.outerjoin(blob_uses, blob_uses.c.blob_id == blobs.c.id)
        stmt = (select(blobs.c.id, blobs.c.name, blobs.c.tag, blobs.c.kind, blobs.c.content_type,
                      blobs.c.size_bytes, blobs.c.storage_key,
                      epoch_cast(blobs.c.created_at).label("updated"),
                      func.count(distinct(blob_uses.c.project_id)).label("used_count"))
               .select_from(j)
               .where(blobs.c.scope == "org", blobs.c.scope_id == org_id)
               .group_by(blobs.c.id).order_by(blobs.c.id.desc()))
        return self._x.fetchall(stmt)

    def by_id(self, blob_id):
        return self._x.fetchone(select(*_BLOB_COLS).where(blobs.c.id == blob_id))

    def children_of(self, blob_id) -> list:
        return self._x.fetchall(select(*_BLOB_COLS).where(blobs.c.source_blob_id == blob_id)
                                .order_by(blobs.c.id))

    def record_use(self, blob_id, project_id) -> None:
        self._x.execute(insert(blob_uses).values(blob_id=blob_id, project_id=project_id))

    def distinct_use_count(self, blob_id) -> int:
        row = self._x.fetchone(select(func.count(distinct(blob_uses.c.project_id)).label("n"))
                               .where(blob_uses.c.blob_id == blob_id))
        return row["n"]

    def update_fields(self, blob_id, **cols) -> None:
        """Patch the given blob columns (only non-None fields should be passed)."""
        if not cols:
            return
        self._x.execute(update(blobs).where(blobs.c.id == blob_id).values(**cols))

    def delete(self, blob_id) -> None:
        self._x.execute(delete(blob_uses).where(blob_uses.c.blob_id == blob_id))
        self._x.execute(delete(blobs).where(blobs.c.id == blob_id))

    def set_directory(self, blob_id, directory_id) -> None:
        """Re-home a blob under a directory (or NULL to unfile it). Only membership changes; scope,
        keys, hashes, summaries are untouched. The composite FK guarantees `directory_id` is a
        same-scope directory, so the caller must validate scope before assigning."""
        self._x.execute(update(blobs).where(blobs.c.id == blob_id).values(directory_id=directory_id))

    # ---- directories: the Files-browser source tree (SOF-251/SOF-253) ----------------------
    def list_directories(self, scope, scope_id) -> list:
        """Every directory row in one scope, ordered by name — the caller assembles the tree in
        memory from parent_id (child/member counts are cheap to derive once the whole scope is
        loaded), so row order is display-only."""
        return self._x.fetchall(select(*_DIR_COLS)
                                .where(directories.c.scope == scope, directories.c.scope_id == scope_id)
                                .order_by(directories.c.name))

    def directory_by_id(self, directory_id):
        return self._x.fetchone(select(*_DIR_COLS).where(directories.c.id == directory_id))

    def find_root(self, scope, scope_id):
        """The persisted per-scope root (parent_id IS NULL), or None if the scope owns no tree yet
        (a project that has never had a source blob filed — the migration only backfilled roots for
        scopes that already owned top-level blobs)."""
        return self._x.fetchone(select(*_DIR_COLS)
                                .where(directories.c.scope == scope, directories.c.scope_id == scope_id,
                                       directories.c.parent_id.is_(None)))

    def insert_directory(self, scope, scope_id, parent_id, name) -> str:
        """Create one directory and return its id. `parent_id` NULL = a scope root; a non-NULL
        parent must already exist in the same scope (the composite parent FK enforces it)."""
        stmt = insert(directories).values(scope=scope, scope_id=scope_id, parent_id=parent_id,
                                          name=name).returning(uuid_str_cast(directories.c.id).label("id"))
        return self._x.fetchone(stmt)["id"]

    def sibling_name_exists(self, scope, scope_id, parent_id, name) -> bool:
        """Is `name` already taken among a parent's children (or among roots when parent is NULL)?
        Mirrors the two partial unique indexes so the app can return a precise 409 before the DB
        raises an opaque integrity error."""
        cond = [directories.c.scope == scope, directories.c.scope_id == scope_id,
                directories.c.name == name]
        cond.append(directories.c.parent_id == parent_id if parent_id is not None
                    else directories.c.parent_id.is_(None))
        return self._x.fetchone(select(directories.c.id).where(*cond)) is not None

    def touch_directory(self, directory_id) -> None:
        """A directory's member set changed (a blob moved in/out), so any prior rollup summary is
        stale: bump updated_at and flag it for re-summary. This writes only summary-invalidation
        inputs — it never fabricates a 'ready' rollup."""
        self._x.execute(update(directories).where(directories.c.id == directory_id)
                        .values(updated_at=func.now(), summary_status="needs_refresh"))
