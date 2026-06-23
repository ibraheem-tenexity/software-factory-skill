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

# Legacy demo-roster callsigns — fake agents that "don't do anything" (the old seed-the-dashboard
# convenience). PURGED on every store init so they can't reappear, and a delete STICKS. Scoped to this
# EXACT list so a custom agent is never touched.
LEGACY_FAKE_CALLSIGNS = ["ATLAS", "HORIZON", "CHROMA", "SIREN", "TENDER", "FORGE",
                         "GARRISON", "MATRIX", "LEDGER", "CONDUIT", "CARGO", "PROFIT"]

# The REAL working orchestrators — the agents that actually run. Their prompts live in the SKILL.md
# files / CONCIERGE_INSTRUCTIONS (editable via the PromptStore override, #43). callsigns MATCH the
# tenexity_os live cards + PromptStore keys. `model` is resolved from LIVE config at ensure-time (data
# provenance — never a guessed literal); `stage` is only used to look up that model, not stored.
REAL_AGENTS = [
    {"callsign": "STAGE-1", "name": "Stage 1 · Research", "role": "stage-orchestrator", "stage": 1,
     "cost_tier": 3, "descr": "Research orchestrator — a validated PRD from the brief."},
    {"callsign": "STAGE-2", "name": "Stage 2 · Design", "role": "stage-orchestrator", "stage": 2,
     "cost_tier": 3, "descr": "Design orchestrator — architecture, dependencies, tickets."},
    {"callsign": "STAGE-3", "name": "Stage 3 · Build", "role": "stage-orchestrator", "stage": 3,
     "cost_tier": 3, "descr": "Build orchestrator — builds, deploys, browser-verifies the app."},
    {"callsign": "CONCIERGE", "name": "Factory Concierge", "role": "concierge", "stage": 0,
     "cost_tier": 2, "descr": "Onboarding concierge — gathers requirements and drives the pipeline."},
]


def _real_agent_model(agent: dict) -> str:
    """The model an orchestrator ACTUALLY runs on, read from live config (no guessed values; empty if
    no real source). Lazy imports avoid a registries↔console/chat_agent import cycle."""
    try:
        stage = agent.get("stage") or 0
        if stage >= 1:
            from .console import _STAGE_MODEL
            return os.environ.get("SF_MODEL") or _STAGE_MODEL.get(stage, "") or ""
        if agent["callsign"] == "CONCIERGE":
            from .chat_agent import chat_model_label
            return chat_model_label()
    except Exception:
        return ""
    return ""


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
        # Reconcile the registry ONCE at init (boot), NOT on the read path — the old _seed_if_empty was
        # called by all() on EVERY request, so a delete was undone on the next dashboard load. Best-effort
        # so a transient boot DB issue never crashes app start (retried next boot).
        try:
            self._ensure_real_agents()
        except Exception:
            pass

    def _ensure_real_agents(self):
        """Purge the legacy fake roster (permanently — a delete now STICKS) and ensure the 4 REAL
        orchestrators exist with model data from live config. Scoped to the exact known fake callsigns,
        so a custom agent is never touched; reals are created ON CONFLICT DO NOTHING (idempotent)."""
        for cs in LEGACY_FAKE_CALLSIGNS:
            _exec("DELETE FROM public.agent_registry WHERE callsign=%s", (cs,))
        for a in REAL_AGENTS:
            _exec("INSERT INTO public.agent_registry (callsign,name,role,model,cost_tier,descr) "
                  "VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT (callsign) DO NOTHING",
                  (a["callsign"], a["name"], a["role"], _real_agent_model(a), a["cost_tier"], a["descr"]))

    def all(self) -> list[dict]:
        # Pure read — never reseeds (that was the per-request bug). Reconciliation is at init only.
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
