"""Stage-3 swarm driver — parallel ticket execution via opencode-swarm (host-driven, §9).

Launched by the console INSTEAD of `opencode run` when SF_SWARM=1 (opencode runtime,
stage 3 only). One Kimi agent per open ticket, wave by wave: parallel within a wave,
waves in sequence. The driver is the stage's single tracked process; when the swarm
phase ends it EXECS the standard monolithic stage-3 agent (the argv after `--`) — same
PID, so the console's process handle, run.log redirection and budget teeth carry
straight through. That agent then finishes whatever the swarm left (failed/unclaimed
tickets), deploys, tests and fix-loops — graceful degradation, no contract fork.

Accounting: every swarm `agent-turn-done` is re-emitted on stdout (which IS run.log) as
an opencode `step_finish` line, so streamlog.cost_usd sees ONE spend stream and the
poller's mid-stage brake fires during the swarm too. Synthesized lines NEVER carry
part.reason="stop" — the zombie-session detector must not read a mid-swarm log as a
finished session. Agent rows fold into AgentRegistry via swarm_adapter.bridge_events.
"""
from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time

from .agents import AgentRegistry
from .swarm_adapter import (
    bridge_events,
    read_events,
    spend_usd,
    swarm_argv,
    swarm_config_for_tickets,
    swarm_env,
)
from .tickets import TicketStore


def synth_step_finish(ev: dict) -> str | None:
    """agent-turn-done -> a run.log step_finish line streamlog already knows how to sum.
    A 0/absent cost is OMITTED (not 0): part.cost=0 would read as authoritative-free and
    skip the token-price fallback."""
    if ev.get("type") != "agent-turn-done":
        return None
    part: dict = {"type": "step-finish", "tokens": ev.get("tokens") or {}}
    cost = ev.get("costUsd")
    if cost:
        part["cost"] = cost
    return json.dumps(
        {"type": "step_finish", "sessionID": f"swarm:{ev.get('agent', '?')}", "part": part}
    )


def fold_once(events_path: str, emitted: int, registry: AgentRegistry, run_id: str,
              model: str, out=sys.stdout) -> int:
    """One poll iteration: re-emit NEW turn-done events into run.log and re-fold agent
    rows (bridge_events is idempotent over the growing file). Returns the new emit
    watermark — the count of events already translated."""
    events = read_events(events_path)
    for ev in events[emitted:]:
        line = synth_step_finish(ev)
        if line:
            out.write(line + "\n")
    out.flush()
    bridge_events(events, registry, run_id, model)
    return len(events)


def run_swarm_waves(base: str, run_id: str, ws: str, model: str, budget_usd: float,
                    max_concurrent: int = 2, spawn=subprocess.Popen, poll_s: float = 10.0,
                    out=sys.stdout) -> float:
    """Run every open wave as a swarm. Returns total swarm spend. Never raises on a
    failed wave — the monolithic agent after exec is the recovery path."""
    run_db = os.path.join(base, "run.db")
    store = TicketStore(run_db)
    registry = AgentRegistry(run_db)
    remaining = budget_usd
    spent_total = 0.0

    for wave in store.open_waves():
        if remaining < 0.50:  # not enough left to do real work; let the agent triage
            break
        tickets = store.open_tickets(wave)
        if not tickets:
            continue
        cfg = swarm_config_for_tickets(
            tickets, model=model, run_db_path=run_db,
            budget_usd=remaining, max_concurrent=max_concurrent,
        )
        cfg_path = os.path.join(ws, f"swarm-wave{wave}.json")
        with open(cfg_path, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
        # Events live under the run base (accounting evidence survives workspace teardown).
        events_path = os.path.join(base, f"swarm-wave{wave}.events.jsonl")

        argv = swarm_argv(cfg_path, ws, os.path.join(ws, ".swarm", "swarm.db"), events_path)
        proc = spawn(argv, env=swarm_env(ws), cwd=ws, stdout=sys.stderr, stderr=sys.stderr)
        _CURRENT["proc"] = proc
        emitted = 0
        while proc.poll() is None:
            time.sleep(poll_s)
            emitted = fold_once(events_path, emitted, registry, run_id, model, out=out)
        fold_once(events_path, emitted, registry, run_id, model, out=out)
        _CURRENT["proc"] = None

        wave_spend = spend_usd(read_events(events_path))
        spent_total += wave_spend
        remaining = max(0.0, remaining - wave_spend)
    return spent_total


# The poller's budget brake terminates the TRACKED process — this driver. The live swarm
# child (and the opencode serve under it) must die with us, not linger as an orphan
# burning the ceiling (the zombie-linger scar, §9).
_CURRENT: dict = {"proc": None}


def _terminate(signum, frame):
    p = _CURRENT.get("proc")
    if p is not None and p.poll() is None:
        p.terminate()
    sys.exit(143)


def main(argv: list[str]) -> int:
    if "--" not in argv:
        sys.stderr.write(
            "usage: python3 -m software_factory.swarm_stage3 <runs_dir> <run_id> <ws> "
            "--budget <usd> --model <model> [--max-concurrent N] -- <stage-3 agent argv...>\n")
        return 2
    split = argv.index("--")
    head, agent_argv = argv[:split], argv[split + 1:]
    runs_dir, run_id, ws = head[0], head[1], head[2]
    opts = dict(zip(head[3::2], head[4::2]))
    model = opts.get("--model", "openrouter/moonshotai/kimi-k2.6")
    budget = float(opts.get("--budget", "0"))
    max_concurrent = int(opts.get("--max-concurrent",
                                  os.environ.get("SF_SWARM_CONCURRENCY", "2")))

    signal.signal(signal.SIGTERM, _terminate)
    signal.signal(signal.SIGINT, _terminate)

    base = os.path.join(runs_dir, run_id)
    # Restart-survivable liveness: a console that lost its process handle (server restart,
    # port eviction) must not read a mid-swarm quiet log as "stage finished" and relaunch a
    # second orchestrator (§1 race — happened live on run-5b7aef7a). The pid survives the
    # exec below, so this one file covers the whole stage.
    with open(os.path.join(base, "stage3.pid"), "w", encoding="utf-8") as f:
        f.write(str(os.getpid()))
    spent = run_swarm_waves(base, run_id, ws, model, budget, max_concurrent=max_concurrent)
    sys.stderr.write(f"[swarm_stage3] swarm phase done: ${spent:.4f}; exec stage-3 agent\n")
    sys.stderr.flush()
    sys.stdout.flush()
    # Same PID: the console's tracked handle keeps working across the swap.
    os.execvp(agent_argv[0], agent_argv)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
