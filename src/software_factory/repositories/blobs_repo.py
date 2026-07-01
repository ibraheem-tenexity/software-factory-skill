"""Pure CRUD for `blobs` + `blob_uses` (SQLAlchemy Core). Global tables — no project-path scoping,
so every method takes its filter values explicitly; no getter/closure, no cycle risk (see #212)."""
from __future__ import annotations

import json

from sqlalchemy import select, insert, update, delete, func, distinct

from ..models import blobs, blob_uses

_BLOB_COLS = (blobs.c.id, blobs.c.scope, blobs.c.scope_id, blobs.c.kind, blobs.c.name, blobs.c.tag,
              blobs.c.storage_key, blobs.c.content_type, blobs.c.size_bytes, blobs.c.sha256,
              blobs.c.source_blob_id, blobs.c.source_page, blobs.c.provenance)


class BlobRepository:
    def __init__(self, exec_):
        self._x = exec_

    def insert(self, scope, scope_id, kind, name, tag, storage_key, content_type, size_bytes,
              sha256, *, source_blob_id=None, source_page=None, provenance=None) -> int:
        # provenance is JSONB; this repo's GlobalExec compiles to raw SQL + a plain psycopg3
        # cursor.execute (not a real SQLAlchemy Connection), so the JSONB Python-type adapter
        # never runs — a bare dict must be pre-serialized, same as key_facts/outline in
        # memory/store.py, or every blob insert (incl. the already-live upload routes, since
        # provenance now defaults on every call) breaks.
        stmt = insert(blobs).values(scope=scope, scope_id=scope_id, kind=kind, name=name, tag=tag,
                                    storage_key=storage_key, content_type=content_type,
                                    size_bytes=size_bytes, sha256=sha256,
                                    source_blob_id=source_blob_id, source_page=source_page,
                                    provenance=json.dumps(provenance or {})).returning(blobs.c.id)
        return self._x.fetchone(stmt)["id"]

    def list_for(self, scope, scope_id) -> list:
        return self._x.fetchall(select(*_BLOB_COLS)
                                .where(blobs.c.scope == scope, blobs.c.scope_id == scope_id)
                                .order_by(blobs.c.id))

    def set_scope(self, blob_id, scope, scope_id) -> None:
        self._x.execute(update(blobs).where(blobs.c.id == blob_id)
                        .values(scope=scope, scope_id=scope_id))

    def list_org_docs(self, org_id) -> list:
        j = blobs.outerjoin(blob_uses, blob_uses.c.blob_id == blobs.c.id)
        stmt = (select(blobs.c.id, blobs.c.name, blobs.c.tag, blobs.c.kind, blobs.c.content_type,
                      blobs.c.size_bytes,
                      func.extract("epoch", blobs.c.created_at).label("updated"),
                      func.count(distinct(blob_uses.c.project_id)).label("used_count"))
               .select_from(j)
               .where(blobs.c.scope == "org", blobs.c.scope_id == org_id)
               .group_by(blobs.c.id).order_by(blobs.c.id.desc()))
        return self._x.fetchall(stmt)

    def by_id(self, blob_id):
        return self._x.fetchone(select(*_BLOB_COLS).where(blobs.c.id == blob_id))

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
