"""Pure CRUD for `tools` (SQLAlchemy Core) — the real tools/MCP registry (SOF-81) consumed by
tools.ToolStore and, at workspace-prep time, workspace_setup.mcp_config()."""
from __future__ import annotations

from sqlalchemy import select, insert, update, delete, func

from ..models import tools
from ._compile import serialize_jsonb

_COLS = (tools.c.name, tools.c.config, tools.c.attached_to, tools.c.key_vault_id,
          tools.c.key_last4, tools.c.updated_by, tools.c.updated_at)


class ToolRepository:
    def __init__(self, exec_):
        self._x = exec_

    def all(self) -> list:
        return self._x.fetchall(select(*_COLS).order_by(tools.c.name))

    def by_name(self, name: str):
        return self._x.fetchone(select(*_COLS).where(tools.c.name == name))

    def upsert(self, name: str, config: dict, attached_to: list | None, by: str | None) -> None:
        existing = self._x.fetchone(select(tools.c.name).where(tools.c.name == name))
        if existing:
            values = {"config": serialize_jsonb(config), "updated_by": by, "updated_at": func.now()}
            if attached_to is not None:
                values["attached_to"] = serialize_jsonb(attached_to)
            self._x.execute(update(tools).where(tools.c.name == name).values(**values))
        else:
            self._x.execute(insert(tools).values(name=name, config=serialize_jsonb(config),
                                                 attached_to=serialize_jsonb(attached_to, default=[]),
                                                 updated_by=by))

    def set_key(self, name: str, vault_id: str, last4: str, by: str | None) -> None:
        self._x.execute(update(tools).where(tools.c.name == name)
                        .values(key_vault_id=vault_id, key_last4=last4, updated_by=by,
                                updated_at=func.now()))

    def clear_key(self, name: str) -> None:
        self._x.execute(update(tools).where(tools.c.name == name)
                        .values(key_vault_id=None, key_last4=None, updated_at=func.now()))

    def delete(self, name: str) -> None:
        self._x.execute(delete(tools).where(tools.c.name == name))
