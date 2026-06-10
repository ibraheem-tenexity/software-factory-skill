"""Dependency disposition — how each required token is satisfied at the deps gate.

Four dispositions, with smart defaults by token name:
  provide — operator supplies a real value (value -> Stage 3 env, NEVER written to disk)
  mock    — Stage 3 builds a WORKING LOCAL FAKE for that capability
  mcp     — Stage 3 provisions it itself via the Supabase/Railway MCP (or generates it)
  env     — inherited from the runner service environment

Only the disposition (metadata) is ever persisted; provided VALUES never touch disk.
"""
from __future__ import annotations

import os

# Tokens the build agent can provision/derive itself via the Supabase + Railway MCP.
_MCP_PATTERNS = ("SUPABASE_", "DATABASE_URL", "RAILWAY_", "NEXTAUTH_")
# LLM keys already present on the runner service.
_FROM_ENV = ("OPENAI_API_KEY", "ANTHROPIC_API_KEY")
# The app's LLM standard. SPEC §3 zero-touch: if the real key sits in the runner env it
# classifies 'env' (auto); if absent it classifies 'mock' (the SKILL builds a WORKING local
# fake) — the pipeline never pauses for a human unless a token genuinely has no fallback.
_LLM_KEYS = ("OPENROUTER_API_KEY",)


def classify_dep(name: str) -> str:
    n = name.upper()
    if n in _LLM_KEYS:
        return "env" if os.environ.get(n) else "mock"
    if n in _FROM_ENV:
        return "env"
    for pat in _MCP_PATTERNS:
        if n == pat or n.startswith(pat):
            return "mcp"
    return "mock"


def default_dispositions(required: list) -> dict:
    return {name: classify_dep(name) for name in required}


def resolve_satisfied(required: list, disposition: dict, provided_names: list) -> bool:
    """Satisfied when every required dep is resolved: mock/mcp/env outright, or
    provide with a value present."""
    provided = set(provided_names)
    for name in required:
        d = disposition.get(name) or classify_dep(name)
        if d in ("mock", "mcp", "env"):
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
