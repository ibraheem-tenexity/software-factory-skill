"""Model pricing: real token usage -> USD.

`PRICES` is the price table and `Usage` the per-call token record; `streamlog` and the
swarm adapter price cost-less events through them. Live budget ENFORCEMENT is
`Console.enforce_budget` (poll-based, reads spend parsed from project.log) — there is no
in-process cutoff class here. Spend is computed from real token counts; an un-priced
model must never bill as free, because free calls hide real spend.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Usage:
    """Real per-call token usage as reported by the model API."""

    model: str
    input_tokens: int = 0
    cached_tokens: int = 0
    output_tokens: int = 0
    reasoning_tokens: int = 0


# USD per token. Reasoning tokens bill at the output rate. Cached (cache-read) is cheaper
# than fresh input. Numbers reflect Claude list pricing.
PRICES: dict[str, dict[str, float]] = {
    "claude-opus-4-8": {
        "input": 15.0 / 1_000_000,
        "cached": 1.5 / 1_000_000,
        "output": 75.0 / 1_000_000,
    },
    "claude-sonnet-4-6": {
        "input": 3.0 / 1_000_000,
        "cached": 0.3 / 1_000_000,
        "output": 15.0 / 1_000_000,
    },
    "claude-haiku-4-5": {
        "input": 1.0 / 1_000_000,
        "cached": 0.1 / 1_000_000,
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
}


