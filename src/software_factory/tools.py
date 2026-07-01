"""Tools / MCP registry store (Tenexity OS §3.5) — `public.mcp_tools`.

Real datastore, CRUD-able. `all()` is a pure read — nothing is seeded from code; the OS shows only
the rows actually in the table.

DATA ACCESS: all SQL lives in `repositories.tools.ToolRepository`.
"""
from __future__ import annotations

from .repositories._exec import GlobalExec
from .repositories.tools import ToolRepository


class ToolStore:
    def __init__(self, repo=None):
        self._repo = repo if repo is not None else ToolRepository(GlobalExec())

    def all(self) -> list[dict]:
        return [dict(r) for r in self._repo.all()]

    def create(self, name, type=None, provider=None, scope=None, auth=None, status="available"):
        return dict(self._repo.insert_returning(name, type, provider, scope, status, auth))

    def update(self, tool_id: int, fields: dict) -> dict | None:
        cols = {c: fields[c] for c in ("name", "type", "provider", "scope", "status", "auth")
               if c in fields}
        self._repo.update_fields(tool_id, **cols)
        row = self._repo.by_id(tool_id)
        return dict(row) if row else None

    def delete(self, tool_id: int) -> None:
        self._repo.delete(tool_id)
