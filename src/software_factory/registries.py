"""Tools/MCP registry + agent registry stores (Tenexity OS §3.4/§3.5).

Real datastore replacing the former code constants — both tables are SEEDED with the factory's
canonical defaults the first time they're read (so the data is durable + CRUD-able, not hardcoded in
the response). Mirrors the dbshim pattern used by `users`/`blobs`.

DATA ACCESS: all SQL lives in `repositories.registries` (ToolRepository / AgentRegistryRepository).
"""
from __future__ import annotations

import os

from .repositories._exec import GlobalExec
from .repositories.registries import ToolRepository, AgentRegistryRepository

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
            from .constants import STAGE_MODEL
            return os.environ.get("SF_MODEL") or STAGE_MODEL.get(stage, "") or ""
        if agent["callsign"] == "CONCIERGE":
            from .chat_agent import chat_model_label
            return chat_model_label()
    except Exception:
        return ""
    return ""


class ToolStore:
    def __init__(self):
        self._repo = ToolRepository(GlobalExec())

    def _seed_if_empty(self):
        if not self._repo.any_row():
            for t in SEED_TOOLS:
                self._repo.insert(t["name"], t["type"], t["provider"], t["scope"], t["status"],
                                  t["auth"])

    def all(self) -> list[dict]:
        self._seed_if_empty()
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


class AgentRegistryStore:
    def __init__(self):
        self._repo = AgentRegistryRepository(GlobalExec())
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
            self._repo.delete_by_callsign(cs)
        for a in REAL_AGENTS:
            self._repo.insert_if_absent(a["callsign"], a["name"], a["role"], _real_agent_model(a),
                                        a["cost_tier"], a["descr"])

    def sync_real_agents(self) -> list[dict]:
        """On-demand reconciliation for POST /api/admin/agents/sync.

        Unlike _ensure_real_agents (boot-time, ON CONFLICT DO NOTHING), this does a true upsert:
        existing rows for the 4 canonical agents are UPDATED to match their authoritative definitions
        so a stale model string or renamed callsign is corrected without a redeploy. Legacy fake rows
        are purged. Custom (non-canonical) rows are never touched. Returns the 4 synced rows."""
        for cs in LEGACY_FAKE_CALLSIGNS:
            self._repo.delete_by_callsign(cs)
        canonical_callsigns = {a["callsign"] for a in REAL_AGENTS}
        for a in REAL_AGENTS:
            model = _real_agent_model(a)
            self._repo.upsert(a["callsign"], a["name"], a["role"], model, a["cost_tier"], a["descr"])
        return [r for r in self.all() if r["callsign"] in canonical_callsigns]

    def all(self) -> list[dict]:
        # Pure read — never reseeds (that was the per-request bug). Reconciliation is at init only.
        return [dict(r) for r in self._repo.all()]

    def get(self, callsign: str) -> dict | None:
        row = self._repo.by_callsign(callsign)
        return dict(row) if row else None

    def create(self, callsign, name, role=None, model=None, cost_tier=1, descr=None):
        self._repo.insert_if_absent(callsign, name, role, model, cost_tier, descr)
        return self.get(callsign)

    def update(self, callsign: str, fields: dict) -> dict | None:
        cols = {c: fields[c] for c in ("name", "role", "model", "cost_tier", "descr") if c in fields}
        self._repo.update_fields(callsign, **cols)
        return self.get(callsign)

    def delete(self, callsign: str) -> None:
        self._repo.delete(callsign)
