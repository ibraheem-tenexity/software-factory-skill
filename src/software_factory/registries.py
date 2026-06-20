"""Tools/MCP registry + agent registry stores (Tenexity OS §3.4/§3.5).

Real datastore replacing the former code constants — both tables are SEEDED with the factory's
canonical defaults the first time they're read (so the data is durable + CRUD-able, not hardcoded in
the response). Mirrors the dbshim pattern used by `users`/`blobs`.
"""
from __future__ import annotations

import os

from . import dbshim

# Canonical seeds (durable defaults, inserted once into an empty table — not returned from code).
SEED_TOOLS = [
    {"name": "Playwright MCP", "type": "MCP", "provider": "Microsoft",
     "scope": "browser automation · e2e verification", "status": "connected", "auth": "none"},
    {"name": "Railway MCP", "type": "MCP", "provider": "Railway",
     "scope": "deploy · services · domains · logs", "status": "connected", "auth": "token"},
    {"name": "GitHub", "type": "API", "provider": "GitHub",
     "scope": "repos · commits · PRs", "status": "connected", "auth": "token"},
    {"name": "Factory DB", "type": "native", "provider": "Supabase / Postgres",
     "scope": "per-run database provisioning", "status": "connected", "auth": "service key"},
    {"name": "OpenAI", "type": "API", "provider": "OpenAI",
     "scope": "concierge + agent models", "status": "connected", "auth": "service key"},
    {"name": "OpenRouter", "type": "API", "provider": "OpenRouter",
     "scope": "Kimi K2.7 + model routing", "status": "available", "auth": "service key"},
    {"name": "Langfuse", "type": "HTTP", "provider": "Langfuse",
     "scope": "LLM tracing", "status": "available", "auth": "token"},
    {"name": "Resend", "type": "HTTP", "provider": "Resend",
     "scope": "operator email", "status": "available", "auth": "service key"},
]

SEED_AGENTS = [
    {"callsign": "ATLAS", "name": "Orchestrator", "role": "orchestrator", "model": "claude-opus-4-8",
     "cost_tier": 3, "descr": "Plans the run, spawns + sequences stage agents."},
    {"callsign": "HORIZON", "name": "Product Manager", "role": "horizon", "model": "claude-opus-4-8",
     "cost_tier": 2, "descr": "Synthesizes the PRD from research + brief."},
    {"callsign": "CHROMA", "name": "Design", "role": "chroma", "model": "claude-sonnet-4-6",
     "cost_tier": 2, "descr": "Designs screens + the visual system."},
    {"callsign": "SIREN", "name": "Marketing", "role": "siren", "model": "claude-sonnet-4-6",
     "cost_tier": 1, "descr": "Positioning + marketing copy."},
    {"callsign": "TENDER", "name": "Proposal", "role": "tender", "model": "claude-sonnet-4-6",
     "cost_tier": 1, "descr": "Drafts proposals + scoping."},
    {"callsign": "FORGE", "name": "DevOps", "role": "forge", "model": "claude-sonnet-4-6",
     "cost_tier": 2, "descr": "Provisions infra + deploys."},
    {"callsign": "GARRISON", "name": "Ops", "role": "garrison", "model": "claude-sonnet-4-6",
     "cost_tier": 1, "descr": "Runtime ops + monitoring."},
    {"callsign": "MATRIX", "name": "Data", "role": "matrix", "model": "claude-sonnet-4-6",
     "cost_tier": 2, "descr": "Data modeling + pipelines."},
    {"callsign": "LEDGER", "name": "EDI", "role": "ledger", "model": "claude-sonnet-4-6",
     "cost_tier": 1, "descr": "EDI + document interchange."},
    {"callsign": "CONDUIT", "name": "ERP", "role": "conduit", "model": "claude-sonnet-4-6",
     "cost_tier": 2, "descr": "ERP integration (Epicor etc.)."},
    {"callsign": "CARGO", "name": "WMS", "role": "cargo", "model": "claude-sonnet-4-6",
     "cost_tier": 1, "descr": "Warehouse / inventory flows."},
    {"callsign": "PROFIT", "name": "Pricing", "role": "profit", "model": "claude-sonnet-4-6",
     "cost_tier": 2, "descr": "Pricing rules + approvals."},
]


def _conn():
    return dbshim._pg_connect(os.environ["DATABASE_URL"])


def _rows(sql, params=()):
    conn = _conn()
    try:
        with conn.transaction():
            cur = conn.cursor()
            cur.execute(sql, params)
            return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


def _exec(sql, params=()):
    conn = _conn()
    try:
        with conn.transaction():
            conn.cursor().execute(sql, params)
    finally:
        conn.close()


class ToolStore:
    def __init__(self, sqlite_path: str = ""):
        pass

    def _seed_if_empty(self):
        if not _rows("SELECT 1 FROM public.mcp_tools LIMIT 1"):
            for t in SEED_TOOLS:
                _exec("INSERT INTO public.mcp_tools (name,type,provider,scope,status,auth) "
                      "VALUES (%s,%s,%s,%s,%s,%s)",
                      (t["name"], t["type"], t["provider"], t["scope"], t["status"], t["auth"]))

    def all(self) -> list[dict]:
        self._seed_if_empty()
        return _rows("SELECT id,name,type,provider,scope,status,auth FROM public.mcp_tools "
                     "ORDER BY id")

    def create(self, name, type=None, provider=None, scope=None, auth=None, status="available"):
        rows = _rows("INSERT INTO public.mcp_tools (name,type,provider,scope,status,auth) "
                     "VALUES (%s,%s,%s,%s,%s,%s) RETURNING id,name,type,provider,scope,status,auth",
                     (name, type, provider, scope, status, auth))
        return rows[0]

    def update(self, tool_id: int, fields: dict) -> dict | None:
        cols = [c for c in ("name", "type", "provider", "scope", "status", "auth") if c in fields]
        if cols:
            sets = ", ".join(f"{c}=%s" for c in cols)
            _exec(f"UPDATE public.mcp_tools SET {sets} WHERE id=%s",
                  (*[fields[c] for c in cols], tool_id))
        rows = _rows("SELECT id,name,type,provider,scope,status,auth FROM public.mcp_tools WHERE id=%s",
                     (tool_id,))
        return rows[0] if rows else None

    def delete(self, tool_id: int) -> None:
        _exec("DELETE FROM public.mcp_tools WHERE id=%s", (tool_id,))


class AgentRegistryStore:
    def __init__(self, sqlite_path: str = ""):
        pass

    def _seed_if_empty(self):
        if not _rows("SELECT 1 FROM public.agent_registry LIMIT 1"):
            for a in SEED_AGENTS:
                _exec("INSERT INTO public.agent_registry (callsign,name,role,model,cost_tier,descr) "
                      "VALUES (%s,%s,%s,%s,%s,%s)",
                      (a["callsign"], a["name"], a["role"], a["model"], a["cost_tier"], a["descr"]))

    def all(self) -> list[dict]:
        self._seed_if_empty()
        return _rows("SELECT callsign,name,role,model,cost_tier,descr FROM public.agent_registry "
                     "ORDER BY callsign")

    def get(self, callsign: str) -> dict | None:
        rows = _rows("SELECT callsign,name,role,model,cost_tier,descr FROM public.agent_registry "
                     "WHERE callsign=%s", (callsign,))
        return rows[0] if rows else None

    def create(self, callsign, name, role=None, model=None, cost_tier=1, descr=None):
        _exec("INSERT INTO public.agent_registry (callsign,name,role,model,cost_tier,descr) "
              "VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT (callsign) DO NOTHING",
              (callsign, name, role, model, cost_tier, descr))
        return self.get(callsign)

    def update(self, callsign: str, fields: dict) -> dict | None:
        cols = [c for c in ("name", "role", "model", "cost_tier", "descr") if c in fields]
        if cols:
            sets = ", ".join(f"{c}=%s" for c in cols)
            _exec(f"UPDATE public.agent_registry SET {sets} WHERE callsign=%s",
                  (*[fields[c] for c in cols], callsign))
        return self.get(callsign)

    def delete(self, callsign: str) -> None:
        _exec("DELETE FROM public.agent_registry WHERE callsign=%s", (callsign,))
