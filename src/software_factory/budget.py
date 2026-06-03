"""Run-level budget: real token usage -> USD, with a HARD cutoff at the ceiling.

The orchestrator feeds every real model call's usage into `charge()`. The instant
cumulative spend reaches the ceiling, `charge()` raises `BudgetExceeded` and the run
stops — cutoff, not escalate-and-wait. Spend is computed from real token counts via a
price table; there are no char-count estimates and no silent free calls.
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


class BudgetExceeded(Exception):
    """Raised the moment cumulative spend reaches the ceiling. Carries the honest total."""

    def __init__(self, spent: float, ceiling: float):
        self.spent = spent
        self.ceiling = ceiling
        super().__init__(f"budget cutoff: spent ${spent:.2f} >= ceiling ${ceiling:.2f}")


# USD per token. Reasoning tokens bill at the output rate. Cached (cache-read) is cheaper
# than fresh input. Numbers reflect Claude list pricing; override via Budget(prices=...).
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
}


class Budget:
    def __init__(
        self,
        ceiling_usd: float = 100.0,
        prices: dict[str, dict[str, float]] | None = None,
        spent_usd: float = 0.0,
    ):
        self.ceiling_usd = ceiling_usd
        self._prices = prices if prices is not None else PRICES
        self._spent = spent_usd

    def cost_of(self, usage: Usage) -> float:
        # KeyError on an unknown model is intentional: an un-priced call must never
        # bill as free, because free calls hide real spend.
        rate = self._prices[usage.model]
        return (
            usage.input_tokens * rate["input"]
            + usage.cached_tokens * rate["cached"]
            + (usage.output_tokens + usage.reasoning_tokens) * rate["output"]
        )

    def charge(self, usage: Usage) -> float:
        """Record a call's cost. Returns the cost of THIS call. Raises at the ceiling."""
        cost = self.cost_of(usage)
        self._spent += cost
        if self._spent >= self.ceiling_usd:
            raise BudgetExceeded(self._spent, self.ceiling_usd)
        return cost

    def spent(self) -> float:
        return self._spent

    def remaining(self) -> float:
        return max(0.0, self.ceiling_usd - self._spent)
