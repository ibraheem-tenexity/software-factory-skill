#!/usr/bin/env python3
"""Measure concierge prompt fetch latency.

Reports direct PromptStore.get latency when DATABASE_URL is available, plus the cached resolver path
used by ChatAgentRunner. This is intentionally read-only.
"""
from __future__ import annotations

import json
import os
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from software_factory.agent_prompts import PromptStore, override_key  # noqa: E402
from software_factory.chat_agent import (  # noqa: E402
    reset_concierge_prompt_cache,
    resolve_concierge_instructions,
)


def _time_call(fn):
    start = time.perf_counter()
    fn()
    return (time.perf_counter() - start) * 1000.0


def _p95(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = min(len(ordered) - 1, int(len(ordered) * 0.95))
    return ordered[idx]


def _summary(values: list[float]) -> dict:
    return {
        "count": len(values),
        "p50_ms": round(statistics.median(values), 2) if values else None,
        "p95_ms": round(_p95(values), 2) if values else None,
        "min_ms": round(min(values), 2) if values else None,
        "max_ms": round(max(values), 2) if values else None,
    }


def main() -> int:
    report: dict[str, object] = {
        "database_url_present": bool(os.environ.get("DATABASE_URL")),
        "direct_prompt_store": None,
        "cached_resolver": None,
    }

    if os.environ.get("DATABASE_URL"):
        store = PromptStore()
        key = override_key("CONCIERGE")
        cold_ms = _time_call(lambda: store.get(key))
        sequential = [_time_call(lambda: PromptStore().get(key)) for _ in range(20)]
        report["direct_prompt_store"] = {
            "cold_first_ms": round(cold_ms, 2),
            "sequential_20": _summary(sequential),
        }

    reset_concierge_prompt_cache()
    cold_cached_ms = _time_call(resolve_concierge_instructions)
    cached = [_time_call(resolve_concierge_instructions) for _ in range(20)]
    report["cached_resolver"] = {
        "cold_first_ms": round(cold_cached_ms, 2),
        "cached_20": _summary(cached),
    }

    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
