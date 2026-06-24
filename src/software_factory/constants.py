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
STAGE_1 = ["extract", "provision", "research"]
STAGE_2 = ["architect", "tickets"]
STAGE_3 = ["build", "deploy", "test", "teardown"]
PIPELINE = STAGE_1 + STAGE_2 + STAGE_3

# ── Model configuration ───────────────────────────────────────────────────────
# Per-stage defaults (SF_MODEL env overrides all stages when set).
# Research (1) & design (2) on Opus 4.8; build (3) on Sonnet (cheaper for high-volume edits).
STAGE_MODEL = {1: "claude-opus-4-8", 2: "claude-opus-4-8", 3: "claude-sonnet-4-6"}

# opencode runtime: short alias → full OpenRouter model ID (all stages use the same model).
OPENCODE_MODEL_IDS = {
    "kimi": "openrouter/moonshotai/kimi-k2.7-code",
    "glm":  "z-ai/glm-5.2",
}
OPENCODE_DEFAULT_ALIAS = "kimi"

# Operator-pickable models for the claude runtime.
# The UI exposes exactly these; anything else is rejected at project-create time.
PLANNING_MODELS = {"claude-opus-4-8", "claude-fable-5"}
IMPL_MODELS = {"claude-sonnet-4-6", "claude-opus-4-8"}

# ── Runner keys ───────────────────────────────────────────────────────────────
# Maps runtime name → environment variable that holds the API key.
RUNNER_KEYS = {"opencode": "OPENROUTER_API_KEY", "claude": "ANTHROPIC_API_KEY"}

# ── Caps ──────────────────────────────────────────────────────────────────────
# Hard cap on deploy-db provision attempts per run — prevents unbounded orphan DB spawns on failure.
DEPLOY_DB_MAX_ATTEMPTS = 2
