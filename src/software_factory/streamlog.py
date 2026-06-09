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


# OpenCode events carry no model id, so the token-pricing fallback uses the run's model.
OPENCODE_FALLBACK_MODEL = "openrouter/moonshotai/kimi-k2.6"


def cost_usd(text: str, prices: dict | None = None) -> float:
    # run.log APPENDS every stage's session; the log may be claude stream-json or opencode
    # --format json (one runtime per run — RunState.runtime pins it — but one parser handles
    # both vocabularies; the schemas are disjoint, so neither path miscounts the other).
    # claude: each finished session emits one authoritative `result.total_cost_usd`. True cost
    # = SUM of those, PLUS a token estimate for the in-flight session (events after the last
    # result line). Taking only the last result lost earlier stages.
    # opencode: each `step_finish` event carries authoritative `part.cost` (+ `part.tokens`
    # for the rare cost-less step, priced at the Kimi rate; reasoning bills as output).
    prices = prices or PRICES
    finished_total = 0.0            # Σ authoritative cost of completed sessions/steps
    tail_estimate = 0.0             # token estimate of the events since the last result line
    for ev in _events(text):
        if ev.get("type") == "result" and ev.get("total_cost_usd") is not None:
            finished_total += ev["total_cost_usd"]
            tail_estimate = 0.0     # everything after this belongs to the next session
            continue
        part = ev.get("part") or {}
        if ev.get("type") == "step_finish" and part.get("type") == "step-finish":
            if part.get("cost") is not None:
                finished_total += part["cost"]
            else:
                tokens = part.get("tokens") or {}
                rate = prices.get(OPENCODE_FALLBACK_MODEL, prices["claude-sonnet-4-6"])
                finished_total += (
                    tokens.get("input", 0) * rate["input"]
                    + (tokens.get("cache") or {}).get("read", 0) * rate["cached"]
                    + (tokens.get("output", 0) + tokens.get("reasoning", 0)) * rate["output"]
                )
            continue
        msg = ev.get("message") or {}
        usage = msg.get("usage")
        if usage:
            rate = prices.get(msg.get("model", ""), prices["claude-sonnet-4-6"])
            tail_estimate += (
                usage.get("input_tokens", 0) * rate["input"]
                + usage.get("cache_read_input_tokens", 0) * rate["cached"]
                + usage.get("output_tokens", 0) * rate["output"]
            )
    return round(finished_total + tail_estimate, 6)


def agents(text: str) -> list[dict]:
    """Subagents spawned via the Task tool, in spawn order, with done/running status."""
    nodes: dict[str, dict] = {}
    done: set[str] = set()
    for ev in _events(text):
        for c in (ev.get("message") or {}).get("content", []) or []:
            if c.get("type") == "tool_use" and c.get("name") in ("Task", "Agent"):
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
