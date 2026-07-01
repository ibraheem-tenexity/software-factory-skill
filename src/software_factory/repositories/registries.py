"""Pure CRUD for `mcp_tools` + `agent_registry` (SQLAlchemy Core). One class per table, both grouped
here since they're both consumed exclusively by registries.py (ToolStore / AgentRegistryStore)."""
from __future__ import annotations

from sqlalchemy import select, insert, update, delete
from sqlalchemy.dialects.postgresql import insert as pg_insert

from ..models import mcp_tools, agent_registry

_TOOL_COLS = (mcp_tools.c.id, mcp_tools.c.name, mcp_tools.c.type, mcp_tools.c.provider,
              mcp_tools.c.scope, mcp_tools.c.status, mcp_tools.c.auth)
_AGENT_COLS = (agent_registry.c.callsign, agent_registry.c.name, agent_registry.c.role,
               agent_registry.c.model, agent_registry.c.cost_tier, agent_registry.c.descr)


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


class AgentRegistryRepository:
    def __init__(self, exec_):
        self._x = exec_

    def delete_by_callsign(self, callsign) -> None:
        self._x.execute(delete(agent_registry).where(agent_registry.c.callsign == callsign))

    def insert_if_absent(self, callsign, name, role, model, cost_tier, descr) -> None:
        stmt = pg_insert(agent_registry).values(callsign=callsign, name=name, role=role,
                                                model=model, cost_tier=cost_tier, descr=descr)
        self._x.execute(stmt.on_conflict_do_nothing(index_elements=["callsign"]))

    def upsert(self, callsign, name, role, model, cost_tier, descr) -> None:
        stmt = pg_insert(agent_registry).values(callsign=callsign, name=name, role=role,
                                                model=model, cost_tier=cost_tier, descr=descr)
        stmt = stmt.on_conflict_do_update(
            index_elements=["callsign"],
            set_={"name": stmt.excluded.name, "role": stmt.excluded.role,
                  "model": stmt.excluded.model, "cost_tier": stmt.excluded.cost_tier,
                  "descr": stmt.excluded.descr})
        self._x.execute(stmt)

    def all(self) -> list:
        return self._x.fetchall(select(*_AGENT_COLS).order_by(agent_registry.c.callsign))

    def by_callsign(self, callsign):
        return self._x.fetchone(select(*_AGENT_COLS).where(agent_registry.c.callsign == callsign))

    def update_fields(self, callsign, **cols) -> None:
        if cols:
            self._x.execute(update(agent_registry).where(agent_registry.c.callsign == callsign)
                            .values(**cols))

    def delete(self, callsign) -> None:
        self._x.execute(delete(agent_registry).where(agent_registry.c.callsign == callsign))
