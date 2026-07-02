"""Tools / MCP registry store (SOF-81) — `public.tools`.

The real, live tool set: `config` is the exact shape workspace_setup.mcp_config() composes into a
stage's .mcp.json (plus non-MCP tools like `github`, shaped {"kind": "api", "env_key": ...}).
`attached_to` names which system_agents callsigns / pipeline nodes use the tool. Key material is
never stored here — a key lives only in Supabase Vault (vault.py), same pattern as org_secrets;
this store holds only the vault_id pointer + a last4 display fragment.

DATA ACCESS: all SQL lives in `repositories.tools.ToolRepository`.
"""
from __future__ import annotations

from .repositories._exec import GlobalExec
from .repositories.tools import ToolRepository
from .services.errors import NotFound
from .vault import vault_store, vault_delete_many, vault_retrieve_many


class ToolStore:
    def __init__(self, repo=None):
        self._repo = repo if repo is not None else ToolRepository(GlobalExec())

    def all(self) -> list[dict]:
        return [_public(r) for r in self._repo.all()]

    def get(self, name: str) -> dict | None:
        row = self._repo.by_name(name)
        return _public(row) if row else None

    def config_for(self, name: str) -> dict | None:
        """A tool's `config` dict, or None if the tool doesn't exist — for a call site (e.g.
        research.py) that needs the DB-editable config value itself, not the FE-facing row shape."""
        row = self._repo.by_name(name)
        return row["config"] if row else None

    def upsert(self, name: str, config: dict, attached_to: list | None = None,
              by: str | None = None) -> dict:
        self._repo.upsert(name, config, attached_to, by)
        return _public(self._repo.by_name(name))

    def set_key(self, name: str, value: str, by: str | None = None) -> dict:
        row = self._repo.by_name(name)
        if not row:
            raise NotFound(f"tool '{name}' not found")
        old_vault_id = row["key_vault_id"]
        vault_id = vault_store(name, value)
        self._repo.set_key(name, vault_id, value[-4:], by)
        if old_vault_id:
            vault_delete_many([old_vault_id])  # best-effort cleanup of the superseded ciphertext
        return _public(self._repo.by_name(name))

    def delete_key(self, name: str) -> dict:
        row = self._repo.by_name(name)
        if not row:
            raise NotFound(f"tool '{name}' not found")
        self._repo.clear_key(name)
        if row["key_vault_id"]:
            vault_delete_many([row["key_vault_id"]])
        return _public(self._repo.by_name(name))

    def delete(self, name: str) -> None:
        row = self._repo.by_name(name)
        if row and row["key_vault_id"]:
            vault_delete_many([row["key_vault_id"]])
        self._repo.delete(name)

    def env_overrides(self, callsign: str) -> dict:
        """Vault-backed {env_var: value} overrides for `callsign` (e.g. "STAGE-3") — every tool
        attached to it that has BOTH a vault key set and a config.env_key declared. Internal-only
        (unlike all()/get(), touches key_vault_id directly) — workspace_setup.tool_env_overrides
        is the intended caller."""
        rows = [dict(r) for r in self._repo.all()
               if r["key_vault_id"] and callsign in (r["attached_to"] or [])
               and (r["config"] or {}).get("env_key")]
        if not rows:
            return {}
        vault_ids = {r["name"]: r["key_vault_id"] for r in rows}
        values = vault_retrieve_many(vault_ids)
        return {r["config"]["env_key"]: values[r["name"]] for r in rows if r["name"] in values}


def _public(row: dict) -> dict:
    """Never surface key_vault_id to a caller (FE-bound) — only whether a key exists + its last4."""
    d = dict(row)
    vault_id = d.pop("key_vault_id", None)
    d["has_key"] = bool(vault_id)
    return d
