"""Pure CRUD for `sow` (SQLAlchemy Core). Global table, staff-only, no per-user ownership."""
from __future__ import annotations

from sqlalchemy import select, insert, update, func

from ..models import sow


class SowRepository:
    def __init__(self, exec_):
        self._x = exec_

    def list_all(self) -> list:
        return self._x.fetchall(select(sow).order_by(sow.c.id.desc()))

    def by_id(self, sow_id: int):
        return self._x.fetchone(select(sow).where(sow.c.id == sow_id))

    def insert(self, **vals) -> dict:
        stmt = insert(sow).values(**vals).returning(*sow.c)
        return self._x.fetchone(stmt)

    def update_fields(self, sow_id: int, **vals) -> dict:
        stmt = (update(sow).where(sow.c.id == sow_id).values(**vals, updated_at=func.now())
                .returning(*sow.c))
        return self._x.fetchone(stmt)
