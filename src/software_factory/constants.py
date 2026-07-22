"""Shared constants used across multiple software_factory modules.

Single source of truth for values that would otherwise be copy-pasted or require
cross-module imports that create coupling (e.g. console._STAGE_MODEL imported by
tenexity_os, registries, poller).
"""
import re

# ── Project-id patterns ───────────────────────────────────────────────────────
# Loose — discovery and tests (test suites mint 'project-xyz' style ids; legacy
# envs may have uppercase). Used by console.py and poller.py.
PROJECT_ID_RE = re.compile(r"project-[A-Za-z0-9-]+")
# Strict — Postgres registry write guard (8+ lowercase hex, canonical form).
# Used by db.py.
PROJECT_ID_STRICT_RE = re.compile(r"project-[0-9a-f]{8,}")

# ── Pipeline stages ───────────────────────────────────────────────────────────
STAGE_1 = ["extract", "provision", "research", "product"]
STAGE_2 = ["architect", "design", "tickets"]
STAGE_3 = ["build", "deploy", "test", "teardown"]
PIPELINE = STAGE_1 + STAGE_2 + STAGE_3

# ── Model configuration ───────────────────────────────────────────────────────
# Per-stage defaults (SF_MODEL env overrides all stages when set).
# Research (1) & design (2) on Opus 4.8; build (3) on Sonnet (cheaper for high-volume edits).
STAGE_MODEL = {1: "claude-opus-4-8", 2: "claude-opus-4-8", 3: "claude-sonnet-4-6"}

# opencode runtime: short alias → full OpenRouter model ID (all stages use the same model).
OPENCODE_MODEL_IDS = {
    "kimi": "openrouter/moonshotai/kimi-k3",
    "glm":  "z-ai/glm-5.2",
}
OPENCODE_DEFAULT_ALIAS = "kimi"

# Codex is a complete third runtime. Keep its model fixed per the runtime contract so the
# command, spend estimate, and staging verification all describe the same executable behavior.
CODEX_MODEL = "gpt-5.6"

# Operator-pickable models for the claude runtime.
# The UI exposes exactly these; anything else is rejected at project-create time.
PLANNING_MODELS = {"claude-opus-4-8", "claude-fable-5"}
IMPL_MODELS = {"claude-sonnet-4-6", "claude-opus-4-8"}

# ── Runner keys ───────────────────────────────────────────────────────────────
# Maps runtime name → environment variable that holds the API key.
RUNNER_KEYS = {
    "claude": "ANTHROPIC_API_KEY",
    "opencode": "OPENROUTER_API_KEY",
    "codex": "CODEX_API_KEY",
}

# ── Caps ──────────────────────────────────────────────────────────────────────
# Hard cap on deploy-db provision attempts per run — prevents unbounded orphan DB spawns on failure.
DEPLOY_DB_MAX_ATTEMPTS = 2

# ── Concierge chat model ────────────────────────────────────────────────────────
# The LangChain Concierge chooses between OpenAI (default) and Kimi (Moonshot, served via
# OpenRouter, which is OpenAI-wire-compatible — same client class, different base_url/key).
# SF_CHAT_MODEL overrides; empty + no OPENAI_API_KEY + an OPENROUTER_API_KEY present ⇒ Kimi.
CONCIERGE_DEFAULT_MODEL = "gpt-5.4"
CONCIERGE_KIMI_MODEL = "moonshotai/kimi-k2.7-code"
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
# The five focuses one Concierge takes on (concierge-agent-spec.md §2/§4.6) — same identity,
# different framing per session.
CONCIERGE_CONTEXTS = ("intake", "overview", "build", "docs", "ingesting")
# Operator-override prompt cache TTL — a Tenexity OS prompt edit drives the next session within this window.
CONCIERGE_PROMPT_CACHE_TTL_SECONDS = 60.0
# Shown when a generation still fails to produce a valid ConciergeTurn after one retry (spec §3):
# a bad generation must never 500 the turn.
CONCIERGE_SAFE_FALLBACK = "Sorry, I didn't quite catch that — could you say that again?"


# USD per token. Reasoning tokens bill at the output rate. Cached (cache-read) is cheaper
# than fresh input; a cache WRITE (populating the cache) costs 1.25x fresh input at Anthropic's
# standard 5-minute TTL (SOF-218) — the only TTL stage agents use, none of this repo's `claude -p`
# invocations set the extended 1h-cache beta header (confirmed: no `cache_control`/`1h` config
# anywhere in software_factory/*.py), so a single flat multiplier is exact, not an approximation.
PRICES: dict[str, dict[str, float]] = {
    "claude-opus-4-8": {
        "input": 15.0 / 1_000_000,
        "cached": 1.5 / 1_000_000,
        "cache_write": 15.0 / 1_000_000 * 1.25,
        "output": 75.0 / 1_000_000,
    },
    "claude-sonnet-4-6": {
        "input": 3.0 / 1_000_000,
        "cached": 0.3 / 1_000_000,
        "cache_write": 3.0 / 1_000_000 * 1.25,
        "output": 15.0 / 1_000_000,
    },
    "claude-haiku-4-5": {
        "input": 1.0 / 1_000_000,
        "cached": 0.1 / 1_000_000,
        "cache_write": 1.0 / 1_000_000 * 1.25,
        "output": 5.0 / 1_000_000,
    },
    # OpenRouter list pricing, confirmed 2026-06-09 via /api/v1/models. OpenCode's stream
    # already carries authoritative per-step cost; this entry is the fallback rate when a
    # step_finish event has tokens but no cost.
    "openrouter/moonshotai/kimi-k2.7-code": {
        "input": 0.75 / 1_000_000,
        "cached": 0.375 / 1_000_000,
        "output": 3.50 / 1_000_000,
    },
    # OpenRouter list pricing, confirmed 2026-07-20 via /api/v1/models (K3 bump, CBT-13 rider).
    "openrouter/moonshotai/kimi-k3": {
        "input": 3.0 / 1_000_000,
        "cached": 0.3 / 1_000_000,
        "output": 15.0 / 1_000_000,
    },
    # OpenAI list pricing for the gpt-5.6 alias (Sol), confirmed 2026-07-20. Codex JSONL reports
    # tokens but no provider-issued dollar total, so this is the budget-meter fallback.
    CODEX_MODEL: {
        "input": 5.0 / 1_000_000,
        "cached": 0.5 / 1_000_000,
        "output": 30.0 / 1_000_000,
    },
}
