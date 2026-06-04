"""Parse the headless `claude -p --output-format stream-json` log (run.log) into the live
COST and AGENT GRAPH the dashboard renders.

Cost comes from claude's own authoritative `result.total_cost_usd` when the run has finished,
otherwise from summing per-message `usage` through the price table. Agent nodes are the
subagents the orchestrator spawned via the `Task` tool — each tool_use is a node, marked done
once its tool_result arrives. Everything is derived from the real stream, so it can't lie.
"""
from __future__ import annotations

import json

from .budget import PRICES


def _events(text: str):
    for line in (text or "").splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            yield json.loads(line)
        except (ValueError, TypeError):
            continue


def cost_usd(text: str, prices: dict | None = None) -> float:
    prices = prices or PRICES
    total_from_result = None
    summed = 0.0
    for ev in _events(text):
        if ev.get("type") == "result" and ev.get("total_cost_usd") is not None:
            total_from_result = ev["total_cost_usd"]
        msg = ev.get("message") or {}
        usage = msg.get("usage")
        if usage:
            rate = prices.get(msg.get("model", ""), prices["claude-sonnet-4-6"])
            summed += (
                usage.get("input_tokens", 0) * rate["input"]
                + usage.get("cache_read_input_tokens", 0) * rate["cached"]
                + usage.get("output_tokens", 0) * rate["output"]
            )
    return round(total_from_result if total_from_result is not None else summed, 6)


def agents(text: str) -> list[dict]:
    """Subagents spawned via the Task tool, in spawn order, with done/running status."""
    nodes: dict[str, dict] = {}
    done: set[str] = set()
    for ev in _events(text):
        for c in (ev.get("message") or {}).get("content", []) or []:
            if c.get("type") == "tool_use" and c.get("name") == "Task":
                inp = c.get("input", {}) or {}
                nodes[c["id"]] = {
                    "id": c["id"],
                    "label": inp.get("description", "agent"),
                    "type": inp.get("subagent_type", "agent"),
                    "status": "running",
                }
            elif c.get("type") == "tool_result" and c.get("tool_use_id"):
                done.add(c["tool_use_id"])
    for tid in done:
        if tid in nodes:
            nodes[tid]["status"] = "done"
    return list(nodes.values())


def summary(text: str, prices: dict | None = None) -> dict:
    return {"cost_usd": cost_usd(text, prices), "agents": agents(text)}
