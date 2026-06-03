"""Operator console logic: turn a one-line app request into a headless factory run, read back
live status, and assemble proof.

The console is the HARNESS, not the builder. `start_run` stamps the run with its proof marker
and launches a headless Claude that invokes the software-factory skill; the skill does the
work and writes its own artifacts under the run dir. `status`/`evidence` read those artifacts.
The launcher is injectable so this is testable without spawning a real `claude`.
"""
from __future__ import annotations

import os
import uuid
from dataclasses import dataclass
from typing import Any, Callable

from .agents import AgentRegistry
from .evidence import build_evidence, verify_evidence
from .runstate import JsonFileStore, RunState
from .tickets import TicketStore

SKILL_VERSION = "0.0.1"


@dataclass
class RunRequest:
    description: str
    context: str = ""
    budget: float = 100.0
    target: str = "railway"


def run_paths(runs_dir: str, run_id: str) -> dict:
    base = os.path.join(runs_dir, run_id)
    return {
        "base": base,
        "state_dir": base,
        "agents_db": os.path.join(base, "agents.db"),
        "tickets_db": os.path.join(base, "tickets.db"),
    }


def make_prompt(req: RunRequest, run_id: str, runs_dir: str) -> str:
    base = os.path.join(runs_dir, run_id)
    ctx = f"\nContext: {req.context}" if req.context else ""
    return (
        "Use the software-factory skill to build, deploy, and browser-verify this app, "
        "fully autonomously.\n"
        f"run_id={run_id}. Budget ${req.budget:.0f} (hard cutoff). Deploy target: {req.target}.\n"
        f"Write run state and telemetry under {base}/ "
        f"(runstate JsonFileStore at {base}, agents.db and tickets.db in that dir), and stamp "
        "the run's proof marker at provision.\n"
        f"App: {req.description}{ctx}"
    )


def _default_launch(argv: list[str]) -> Any:
    import subprocess

    return subprocess.Popen(argv)


class Console:
    def __init__(
        self,
        runs_dir: str,
        launch: Callable[[list[str]], Any] = _default_launch,
        new_id: Callable[[], str] = lambda: "run-" + uuid.uuid4().hex[:8],
    ):
        self._runs_dir = runs_dir
        self._launch = launch
        self._new_id = new_id
        os.makedirs(runs_dir, exist_ok=True)

    def _paths(self, run_id: str) -> dict:
        return run_paths(self._runs_dir, run_id)

    def _load_state(self, run_id: str) -> RunState:
        return RunState.load(run_id, JsonFileStore(self._paths(run_id)["state_dir"]))

    def start_run(self, req: RunRequest) -> str:
        run_id = self._new_id()
        paths = self._paths(run_id)
        os.makedirs(paths["base"], exist_ok=True)

        # Stamp the proof marker at launch — the receipt of which skill is driving this run.
        # The teeth (that real work happened) live in verify_evidence, not here.
        state = self._load_state(run_id)
        state.skill = "software-factory"
        state.skill_version = SKILL_VERSION
        state.description = req.description
        state.deploy_target = req.target
        state.save()

        argv = [
            "claude", "-p", make_prompt(req, run_id, self._runs_dir),
            "--permission-mode", "bypassPermissions",
            "--output-format", "stream-json", "--verbose",
        ]
        self._launch(argv)
        return run_id

    def status(self, run_id: str) -> dict:
        state = self._load_state(run_id)
        reg = AgentRegistry(self._paths(run_id)["agents_db"])
        return {
            "run_id": run_id,
            "skill": state.skill,
            "skill_version": state.skill_version,
            "description": state.description,
            "deploy_target": state.deploy_target,
            "phase": state.phase,
            "done": state.phase == "done",
            "deploy_url": state.deploy_url,
            "spent_usd": state.spent_usd,
            "agents": reg.counts(run_id),
            "no_op_rate": reg.no_op_rate(run_id),
        }

    def evidence(self, run_id: str) -> dict:
        paths = self._paths(run_id)
        state = self._load_state(run_id)
        reg = AgentRegistry(paths["agents_db"])
        tickets = TicketStore(paths["tickets_db"])
        bundle = build_evidence(state, reg, tickets)
        ok, reasons = verify_evidence(bundle)
        return {"verified": ok, "reasons": reasons, "bundle": bundle}
