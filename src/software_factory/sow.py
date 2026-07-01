"""Statement-of-Work store (PRD §2.x SOW editor, wsp0uq99 FE task).

DATA ACCESS: all `sow` SQL lives in `repositories.sow.SowRepository` (SQLAlchemy Core); this
store keeps only the status validation + the allowed-fields filter.
"""
from __future__ import annotations

from typing import Optional

from .repositories._exec import GlobalExec
from .repositories.sow import SowRepository

SOW_STATUSES = ("Template", "Draft", "In review", "Sent", "Signed")


class SowStore:
    """CRUD store for the sow table. Staff-only; no per-user ownership."""

    def __init__(self):
        self._repo = SowRepository(GlobalExec())

    def list_all(self) -> list[dict]:
        return self._repo.list_all()

    def get(self, sow_id: int) -> Optional[dict]:
        return self._repo.by_id(sow_id)

    def create(self, title: str, *, org: str = None, project: str = None,
               value: str = None, file: str = None, version: int = 1,
               status: str = "Draft", body: str = None) -> dict:
        if status not in SOW_STATUSES:
            raise ValueError(f"invalid status {status!r}; must be one of {SOW_STATUSES}")
        return self._repo.insert(title=title, org=org, project=project, value=value, file=file,
                                 version=version, status=status, body=body)

    def update(self, sow_id: int, fields: dict) -> Optional[dict]:
        allowed = {"title", "org", "project", "value", "file", "version", "status", "body"}
        updates = {k: v for k, v in fields.items() if k in allowed and v is not None}
        if not updates:
            return self.get(sow_id)
        if "status" in updates and updates["status"] not in SOW_STATUSES:
            raise ValueError(f"invalid status {updates['status']!r}")
        return self._repo.update_fields(sow_id, **updates)
