"""Pure CRUD for `sow` (SQLAlchemy Core). Global table, staff-only, no per-user ownership.

created_at/updated_at are DateTime columns — since this codebase executes Core statements over a
raw psycopg3 connection (see repositories/_exec.py), SQLAlchemy's own bind/result processors never
run, so psycopg3's default DateTime decoding applies: a bare `sow.c.created_at` in a select/
returning list comes back as a Python `datetime` object, not the epoch float the rest of the app
returns. A bare `func.extract("epoch", ...)` isn't enough either — Postgres's EXTRACT returns
`numeric`, which psycopg3 decodes to `decimal.Decimal`, not `float` (see repositories/users.py's
docstring for the SOF-55 fix). `cast(..., Float)` on top forces a real double-precision result.
"""
from __future__ import annotations

from sqlalchemy import select, insert, update, func

from ..models import sow
from ._compile import epoch_cast

_SOW_COLS = (
    sow.c.id, sow.c.title, sow.c.org, sow.c.project, sow.c.value, sow.c.file, sow.c.version,
    sow.c.status, sow.c.body,
    epoch_cast(sow.c.created_at).label("created_at"),
    epoch_cast(sow.c.updated_at).label("updated_at"),
)


class SowRepository:
    def __init__(self, exec_):
        self._x = exec_

    def list_all(self) -> list:
        return self._x.fetchall(select(*_SOW_COLS).select_from(sow).order_by(sow.c.id.desc()))

    def by_id(self, sow_id: int):
        return self._x.fetchone(select(*_SOW_COLS).select_from(sow).where(sow.c.id == sow_id))

    def insert(self, **vals) -> dict:
        stmt = insert(sow).values(**vals).returning(*_SOW_COLS)
        return self._x.fetchone(stmt)

    def update_fields(self, sow_id: int, **vals) -> dict:
        stmt = (update(sow).where(sow.c.id == sow_id).values(**vals, updated_at=func.now())
                .returning(*_SOW_COLS))
        return self._x.fetchone(stmt)
