"""Bridge between opencode-swarm and the factory engine — stage-3 parallel tickets.

Host-driven topology (SPEC §9): the factory generates the swarm config from the
TicketStore, runs the swarm CLI with --events, and folds the event stream back into
the factory's sources of truth (AgentRegistry rows, run spend). opencode-swarm never
learns factory concepts; this module is the only place the two vocabularies meet.

Event-shape ground truth: tests/fixtures/swarm-events.jsonl (captured from a real
Kimi K2.6 swarm against opencode-swarm @ 881630e). Two semantics that fixture proved:
- `agent-done.costUsd` is NOT the agent's final cost — sweep-phase turns land after it.
  All aggregation here therefore folds over `agent-turn-done` events only.
- A turn's `costUsd` is 0 when the provider omits it; the `tokens` object + `model` id
  are the price-fallback path (same rule as streamlog's step_finish handling).
"""
from __future__ import annotations

import json
import os
from typing import Optional

from .data_transfer_objects import Usage
from .constants import PRICES
from .tickets import Ticket

# Ticket agents do file work + db verbs; everything else (MCP bloat) stays off so the
# OpenAI-API-family 128-tool cap is never hit (swarm coordination tools are force-enabled
# by opencode-swarm itself).
_TICKET_AGENT_TOOLS = {
    "*": False,
    "read": True,
    "glob": True,
    "grep": True,
    "edit": True,
    "write": True,
    "bash": True,
}

# Ticket agents build; they don't deliberate. One delivery round handles stragglers.
_TICKET_MAX_ROUNDS = 2

_AGENT_PREFIX = "ticket-"


def agent_name_for(ticket_id: int) -> str:
    return f"{_AGENT_PREFIX}{ticket_id}"


def ticket_id_for(agent_name: str) -> Optional[int]:
    if not agent_name.startswith(_AGENT_PREFIX):
        return None
    try:
        return int(agent_name[len(_AGENT_PREFIX):])
    except ValueError:
        return None


def _ticket_task(t: Ticket, project_db_path: str) -> str:
    """The per-ticket contract — SKILL.opencode.md's claim/mark_done discipline, minus the
    spawn-agent/finish-agent verbs: in host-driven swarm mode the HOST records agent rows
    from the event stream (bridge_events), so an agent recording itself would double-count.
    The agent name doubles as the claim id, which is what keeps detect_stage3_done and the
    evidence bundle truthful."""
    name = agent_name_for(t.id)
    return (
        f"You own ticket #{t.id}: {t.title}\n"
        f"Acceptance: {t.acceptance}\n"
        f"Definition of done: {t.dod}\n\n"
        "Work ONLY this ticket, in the current workspace repo. Protocol (mandatory, in order):\n"
        f"1. Claim it: python3 -c \"from software_factory.tickets import TicketStore; "
        f"TicketStore('{project_db_path}').claim({t.id}, '{name}')\"\n"
        "2. Implement until the acceptance criteria pass locally. Run the relevant checks yourself.\n"
        "3. Commit your work as ONE commit on main whose message names the ticket. Capture provenance:\n"
        "   SHA=$(git rev-parse HEAD) and the changed-lines count from `git show --stat HEAD | tail -1`.\n"
        f"4. Close it IMMEDIATELY after the commit: python3 -c \"from software_factory.tickets import "
        f"TicketStore; TicketStore('{project_db_path}').mark_done({t.id}, '<SHA>', <diff_lines>, "
        "decision_log=<list>)\"\n"
        "   (diff_lines must be the real non-zero count — a hollow close is refused by the store.)\n"
        "   decision_log is REQUIRED (SOF-118): pass [] if there is honestly nothing to declare, or "
        "[{'type': 'assumption'|'shortcut'|'known-gap', 'statement': ..., 'reason': ..., "
        "'affected_surface': ...}, ...] to disclose what you assumed, shortcut, or left as a known "
        "gap while building THIS ticket — e.g. seeded fewer rows than the PRD implied, or a check "
        "that only runs client-side. Never omit it or silently ship an undeclared gap.\n"
        "An attempt that produced an empty diff is a no-op: never mark it done; report what blocked you.\n"
        "If you are blocked by another ticket's files, say so via swarm_send to that ticket's agent "
        "and finish with what you completed. Do not touch files owned by other tickets. Do NOT call "
        "spawn-agent/finish-agent — the host records your lifecycle."
    )


def swarm_config_for_tickets(
    tickets: list[Ticket],
    *,
    model: str,
    project_db_path: str,
    budget_usd: float,
    max_concurrent: int = 2,
) -> dict:
    """opencode-swarm swarm.json for one build wave: one agent per ticket."""
    return {
        "name": "sf-stage3-tickets",
        "model": model,
        "maxRounds": _TICKET_MAX_ROUNDS,
        "maxConcurrent": max_concurrent,
        "budgetUsd": round(budget_usd, 4),
        "agents": [
            {
                "name": agent_name_for(t.id),
                "task": _ticket_task(t, project_db_path),
                "tools": dict(_TICKET_AGENT_TOOLS),
            }
            for t in tickets
        ],
    }


def swarm_argv(config_path: str, ws: str, db_path: str, events_path: str) -> list[str]:
    """CLI invocation. SF_SWARM_BIN points at the compiled `swarm` binary (release
    tarball) or a `bun .../cli.ts` shim on the dev box; never secrets in argv."""
    bin_path = os.environ.get("SF_SWARM_BIN", "swarm")
    return [
        bin_path, "run", config_path,
        "--dir", ws,
        "--db", db_path,
        "--events", events_path,
        "--json",
    ]


def swarm_env(ws: str, base_env: Optional[dict] = None) -> dict:
    """Child env with the §9 launch hygiene — the swarm CLI spawns `opencode serve`,
    which has the exact same leak surface as `opencode run` (each of these bit a real run)."""
    env = dict(base_env if base_env is not None else os.environ)
    env["PWD"] = ws
    env["XDG_CONFIG_HOME"] = os.path.join(ws, ".oc-config")
    # Hide the host's global auth.json (spend-limited key) — the env key is authoritative,
    # exactly as in the container. Live scar: run-d81f37da, all swarm agents credit-refused.
    env["XDG_DATA_HOME"] = os.path.join(ws, ".oc-data")
    env["OPENCODE_DISABLE_CLAUDE_CODE_SKILLS"] = "1"
    env["OPENCODE_DISABLE_EXTERNAL_SKILLS"] = "1"
    env["OPENCODE_SWARM_DB"] = os.path.join(ws, ".swarm", "swarm.db")
    return env


def read_events(path: str) -> list[dict]:
    """Tolerant JSONL read: a half-written tail line (crash mid-flush) must not void
    the run's accounting."""
    events: list[dict] = []
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    ev = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(ev, dict) and "type" in ev:
                    events.append(ev)
    except FileNotFoundError:
        return []
    return events


def _turn_usage(ev: dict) -> Usage:
    tok = ev.get("tokens") or {}
    cache = tok.get("cache") or {}
    return Usage(
        model=ev.get("model", ""),
        input_tokens=int(tok.get("input", 0)),
        cached_tokens=int(cache.get("read", 0)),
        output_tokens=int(tok.get("output", 0)),
        reasoning_tokens=int(tok.get("reasoning", 0)),
    )


def _turn_cost(ev: dict, prices: dict) -> float:
    cost = float(ev.get("costUsd", 0) or 0)
    if cost > 0:
        return cost
    u = _turn_usage(ev)
    if not (u.input_tokens or u.output_tokens or u.reasoning_tokens or u.cached_tokens):
        return 0.0
    # KeyError on an unknown model is intentional (budget.py rule): tokens were spent,
    # and an un-priced call must never bill as free.
    rate = prices[u.model]
    return (
        u.input_tokens * rate["input"]
        + u.cached_tokens * rate["cached"]
        + (u.output_tokens + u.reasoning_tokens) * rate["output"]
    )


def spend_usd(events: list[dict], prices: dict = PRICES) -> float:
    """Authoritative swarm spend: fold over agent-turn-done (resumable truth even when
    the stream is truncated mid-run), cross-checked against swarm-done's total — take
    the max so the brake can never under-count."""
    turned = sum(_turn_cost(ev, prices) for ev in events if ev.get("type") == "agent-turn-done")
    reported = max(
        (float(ev.get("totalCostUsd", 0) or 0) for ev in events if ev.get("type") == "swarm-done"),
        default=0.0,
    )
    return max(turned, reported)


# swarm terminal event -> AgentRegistry outcome (§5 vocabulary). agent-settled (emitted
# after the sweep, opencode-swarm >= df0a10d) supersedes these when present: its costUsd
# and status include sweep activity, which agent-done's do not.
_OUTCOME_FOR = {"agent-done": "success", "agent-failed": "failed"}
_SETTLED_OUTCOME = {"done": "success", "failed": "failed"}


def bridge_events(events: list[dict], registry, project_id: str, model: str,
                  prices: dict = PRICES) -> dict:
    """Fold a swarm event stream into AgentRegistry rows. Idempotent: safe to re-run
    over the growing file while the swarm is live (the poller's model). Agents the
    swarm skipped (already done on resume) keep their existing rows untouched.
    Returns {agent_name: cost_usd} for the agents folded."""
    per_agent: dict[str, dict] = {}
    for ev in events:
        name = ev.get("agent")
        if not name:
            continue
        a = per_agent.setdefault(
            name, {"usage": Usage(model=model), "cost": 0.0, "outcome": None, "settled": False}
        )
        kind = ev.get("type")
        if kind == "agent-settled":
            a["settled"] = True
            a["cost"] = float(ev.get("costUsd", 0) or 0) or a["cost"]
            a["outcome"] = _SETTLED_OUTCOME.get(ev.get("status"), "failed")
        elif kind == "agent-turn-done":
            u = _turn_usage(ev)
            t = a["usage"]
            a["usage"] = Usage(
                model=u.model or t.model,
                input_tokens=t.input_tokens + u.input_tokens,
                cached_tokens=t.cached_tokens + u.cached_tokens,
                output_tokens=t.output_tokens + u.output_tokens,
                reasoning_tokens=t.reasoning_tokens + u.reasoning_tokens,
            )
            if not a["settled"]:
                a["cost"] += _turn_cost(ev, prices)
        elif kind in _OUTCOME_FOR and not a["settled"]:
            a["outcome"] = _OUTCOME_FOR[kind]

    known = {r.agent_id for r in registry.agents_for(project_id)}
    folded: dict[str, float] = {}
    for name, a in per_agent.items():
        if name not in known:
            registry.spawn(name, project_id, ticket_id_for(name), role="swarm-ticket",
                           model=a["usage"].model or model, phase="build")
        if a["outcome"] is not None:
            registry.record(name, a["outcome"], usage=a["usage"], cost_usd=a["cost"])
        folded[name] = a["cost"]
    return folded
