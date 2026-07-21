"""Parse the headless `claude -p --output-format stream-json` log (project.log) into the live
COST and AGENT GRAPH the dashboard renders.

Cost comes from claude's own authoritative `result.total_cost_usd` when the run has finished,
otherwise from summing per-message `usage` through the price table. Agent nodes are the
subagents the orchestrator spawned via the `Task` tool — each tool_use is a node, marked done
once its tool_result arrives. Everything is derived from the real stream, so it can't lie.
"""
from __future__ import annotations

import json

from .constants import PRICES


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
# Accepted risk: this is a single GLOBAL constant, not per-run — recomputing cost_usd() on a
# HISTORICAL log whose step_finish events lack authoritative part.cost (the `else` branch below,
# ~line 68-72) reprices those old steps at whatever model this constant currently names. A
# K2.7-run log recomputed after this bump reprices its fallback-priced steps at K3 rates (~4x,
# upward only). Accepted: the normal path always carries authoritative part.cost (this fallback
# rarely fires) and per-event model tracking is machinery a model-alias bump doesn't justify.
# Revisit only if opencode ever starts emitting a model id per event.
OPENCODE_FALLBACK_MODEL = "openrouter/moonshotai/kimi-k3"


def cost_components(text: str, prices: dict | None = None) -> tuple[float, float]:
    """(authoritative, estimate) — split the same accumulation `cost_usd()` sums, so a caller that
    needs to tell "a session's real, final cost" apart from "a still-in-flight session's token
    guess" can (SOF-215). `authoritative` is `finished[sid]` summed (each session's own max-of-
    results, i.e. real billing); `estimate` is `tail[sid]` summed (token-priced guess for a
    session that hasn't emitted a terminal result yet — killed, or simply still running).
    See `cost_usd`'s docstring for the full per-runtime accounting rules; this is the same pass,
    just returning both halves instead of their sum."""
    # project.log APPENDS every stage's session, keyed per session; the log may be claude
    # stream-json or opencode --format json (one runtime per run — ProjectState.runtime pins it —
    # but one parser handles both vocabularies; the schemas are disjoint).
    # claude: `result.total_cost_usd` is CUMULATIVE for the whole resumed conversation, not a
    # per-invocation delta — `claude -p --resume <session>` must resend the full prior history,
    # so each resume's reported total already includes every earlier turn. A stage that gets
    # resumed/retried N times under the SAME session_id therefore emits N result events, each a
    # superset of the last (confirmed live 2026-07-02: project-8394d197a111467f's session
    # 21a542e7-... emitted 15 results with monotonically increasing totals [$0.94 .. $12.59] and
    # NON-monotonic num_turns/duration_ms per event — proof these are separate resumed invocations,
    # not one session's final total; SUMMING them gave $83.83 against the true $12.59, inflating
    # that project's reported spend from ~$19 to $100.64). Take the MAX per session, never sum —
    # a session's result-event sequence.
    # opencode: each `step_finish` event carries authoritative `part.cost` as a genuine PER-STEP
    # delta (not cumulative) — summing those remains correct.
    # A session that NEVER emitted a result (killed/OOM) keeps its token estimate — a later
    # session's result must not discard it (the run-d329e57c under-count scar); unaffected by the
    # sum-vs-max choice above, which only concerns multiple results for the SAME session.
    prices = prices or PRICES
    finished: dict = {}             # session id -> authoritative total (max of results / Σ of opencode steps)
    tail: dict = {}                 # session id -> token estimate since that session's last result
    for ev in _events(text):
        sid = ev.get("session_id") or ev.get("sessionID") or "?"
        if ev.get("type") == "result" and ev.get("total_cost_usd") is not None:
            finished[sid] = max(finished.get(sid, 0.0), ev["total_cost_usd"])
            tail[sid] = 0.0
            continue
        part = ev.get("part") or {}
        if ev.get("type") == "step_finish" and part.get("type") == "step-finish":
            if part.get("cost") is not None:
                step_cost = part["cost"]
            else:
                tokens = part.get("tokens") or {}
                rate = prices.get(OPENCODE_FALLBACK_MODEL, prices["claude-sonnet-4-6"])
                step_cost = (
                    tokens.get("input", 0) * rate["input"]
                    + (tokens.get("cache") or {}).get("read", 0) * rate["cached"]
                    + (tokens.get("output", 0) + tokens.get("reasoning", 0)) * rate["output"]
                )
            finished[sid] = finished.get(sid, 0.0) + step_cost
            continue
        msg = ev.get("message") or {}
        usage = msg.get("usage")
        if usage:
            rate = prices.get(msg.get("model", ""), prices["claude-sonnet-4-6"])
            tail[sid] = tail.get(sid, 0.0) + (
                usage.get("input_tokens", 0) * rate["input"]
                + usage.get("cache_read_input_tokens", 0) * rate["cached"]
                + usage.get("output_tokens", 0) * rate["output"]
            )
    return round(sum(finished.values()), 6), round(sum(tail.values()), 6)


def cost_usd(text: str, prices: dict | None = None) -> float:
    """Authoritative + estimate combined — the whole-run number the dashboard/budget-enforcement
    checks want. See `cost_components` for the split (SOF-215: the persisted monotonic spend floor
    must only ever be raised by the authoritative half, never the estimate — an in-flight guess
    can substantially overshoot what a session's eventual real total turns out to be, and once
    that got locked in as "spend can only go up," every later real stage's spend became invisible
    until it organically exceeded the false ceiling)."""
    authoritative, estimate = cost_components(text, prices)
    return round(authoritative + estimate, 6)


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
