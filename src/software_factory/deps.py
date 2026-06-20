"""Dependency disposition — how each required token is satisfied at the deps gate.

Dispositions (SPEC §3), with smart defaults by token name:
  provide   — operator supplies a real value (value -> Stage 3 env, NEVER written to disk)
  mock      — Stage 3 builds a WORKING LOCAL FAKE for that capability
  deploy-db — a DATABASE the FACTORY provisions (per-project Railway Postgres) and hands the agent
              as context/deploy-db.json; the agent NEVER provisions a DB and has NO Supabase access
  mcp       — Stage 3 self-handles via the Railway MCP / generates it (e.g. NEXTAUTH_SECRET)

There is deliberately NO 'env' disposition: a built app must never inherit the runner's
own keys (operator security rule). LLM keys default to mock; a real key is only ever
'provide'd explicitly. Runs persisted before the removal may still carry 'env' — it
degrades to mock (stays satisfied, never re-pauses, never signals runner-key use).

Only the disposition (metadata) is ever persisted; provided VALUES never touch disk.
"""
from __future__ import annotations

# A DATABASE the factory provisions and hands over via context/deploy-db.json (agent has no
# Supabase access and never provisions a DB itself).
_DEPLOY_DB_PATTERNS = ("DATABASE_URL", "DB_URL", "POSTGRES", "PG_", "SUPABASE_URL", "SUPABASE_DB")
# Tokens the build agent self-handles (Railway MCP for deploy, or self-generated secrets).
_MCP_PATTERNS = ("RAILWAY_", "NEXTAUTH_")


def classify_dep(name: str) -> str:
    n = name.upper()
    for pat in _DEPLOY_DB_PATTERNS:
        if n == pat or n.startswith(pat):
            return "deploy-db"
    # Any remaining Supabase token (anon/service keys etc.) is part of the factory-provided DB
    # bundle, not something the agent provisions.
    if n.startswith("SUPABASE_"):
        return "deploy-db"
    for pat in _MCP_PATTERNS:
        if n == pat or n.startswith(pat):
            return "mcp"
    return "mock"


def default_dispositions(required: list) -> dict:
    return {name: classify_dep(name) for name in required}


def resolve_satisfied(required: list, disposition: dict, provided_names: list) -> bool:
    """Satisfied when every required dep is resolved: mock/mcp outright, or provide with
    a value present. Legacy 'env' (pre-removal runs) degrades to mock — still satisfied."""
    provided = set(provided_names)
    for name in required:
        d = disposition.get(name) or classify_dep(name)
        if d in ("mock", "mcp", "deploy-db", "env"):
            continue
        if d == "provide" and name in provided:
            continue
        return False
    return True


def extract_env_creds(deps: dict) -> dict:
    """Pull the real {name: value} pairs to inject into the Stage 3 env. Accepts both the
    new `{name: {disposition, value}}` shape and legacy `{name: value_string}`. Entries with
    no value (mock/mcp, or blank) are omitted."""
    out = {}
    for name, spec in deps.items():
        if isinstance(spec, dict):
            v = spec.get("value")
            if v not in (None, ""):
                out[name] = v
        elif spec not in (None, ""):
            out[name] = spec
    return out
