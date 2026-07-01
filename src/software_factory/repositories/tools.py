"""Pure CRUD for `mcp_tools` (SQLAlchemy Core) — the tools/MCP registry consumed by tools.ToolStore."""
from __future__ import annotations

from sqlalchemy import select, insert, update, delete

from ..models import mcp_tools

_TOOL_COLS = (mcp_tools.c.id, mcp_tools.c.name, mcp_tools.c.type, mcp_tools.c.provider,
              mcp_tools.c.scope, mcp_tools.c.status, mcp_tools.c.auth)


class ToolRepository:
    def __init__(self, exec_):
        self._x = exec_

    def any_row(self) -> bool:
        return self._x.fetchone(select(mcp_tools.c.id).limit(1)) is not None

    def insert(self, name, type, provider, scope, status, auth) -> None:
        self._x.execute(insert(mcp_tools).values(name=name, type=type, provider=provider,
                                                 scope=scope, status=status, auth=auth))

    def all(self) -> list:
        return self._x.fetchall(select(*_TOOL_COLS).order_by(mcp_tools.c.id))

    def insert_returning(self, name, type, provider, scope, status, auth) -> dict:
        stmt = insert(mcp_tools).values(name=name, type=type, provider=provider, scope=scope,
                                        status=status, auth=auth).returning(*_TOOL_COLS)
        return self._x.fetchone(stmt)

    def update_fields(self, tool_id, **cols) -> None:
        if cols:
            self._x.execute(update(mcp_tools).where(mcp_tools.c.id == tool_id).values(**cols))

    def by_id(self, tool_id):
        return self._x.fetchone(select(*_TOOL_COLS).where(mcp_tools.c.id == tool_id))

    def delete(self, tool_id) -> None:
        self._x.execute(delete(mcp_tools).where(mcp_tools.c.id == tool_id))
