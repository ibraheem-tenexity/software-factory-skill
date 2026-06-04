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
from dataclasses import dataclass, field
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
    # Secret env (e.g. {"RAILWAY_TOKEN": "..."}) for a bring-your-own run. Injected into the
    # headless child's environment only — never persisted, never put on the command line.
    credentials: dict = field(default_factory=dict)


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


def _default_launch(argv: list[str], env: dict, log_path: str | None = None) -> Any:
    import subprocess

    # Capture the headless run's output to a per-run log so it's visible (and debuggable)
    # regardless of the platform's log pipeline. Secrets ride in env, never argv.
    out = open(log_path, "ab") if log_path else None
    return subprocess.Popen(argv, env={**os.environ, **env}, stdout=out, stderr=out)


class Console:
    def __init__(
        self,
        runs_dir: str,
        launch: Callable[..., Any] = _default_launch,
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
        # Secrets are kept out of run state entirely; we persist only the NAMES provided.
        env = {k: v for k, v in (req.credentials or {}).items() if v}
        state.skill = "software-factory"
        state.skill_version = SKILL_VERSION
        state.description = req.description
        state.deploy_target = req.target
        state.creds_provided = sorted(env.keys())
        state.save()

        # Model + turn cap are cost controls. Default to Sonnet (≈5x cheaper than Opus) and a
        # bounded number of turns so a wandering headless run can never burn tokens unbounded.
        model = os.environ.get("SF_MODEL", "claude-sonnet-4-6")
        max_turns = os.environ.get("SF_MAX_TURNS", "60")
        argv = [
            "claude", "-p", make_prompt(req, run_id, self._runs_dir),
            "--model", model,
            "--max-turns", max_turns,
            "--permission-mode", "bypassPermissions",
            "--output-format", "stream-json", "--verbose",
        ]
        self._launch(argv, env, os.path.join(paths["base"], "run.log"))
        return run_id

    def read_log(self, run_id: str, max_bytes: int = 20000) -> str:
        """Tail of the headless run's captured stdout/stderr (run.log)."""
        p = os.path.join(self._paths(run_id)["base"], "run.log")
        if not os.path.exists(p):
            return ""
        with open(p, "rb") as f:
            f.seek(0, 2)
            size = f.tell()
            f.seek(max(0, size - max_bytes))
            return f.read().decode("utf-8", "replace")

    def _workspace_state(self, run_id: str, phase: str) -> str:
        ws = os.path.join(self._paths(run_id)["base"], "workspace")
        if os.path.isdir(ws):
            return "active"
        return "cleaned" if phase in ("done", "blocked", "stopped") else "pending"

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
            "creds_provided": state.creds_provided,  # names only, never values
            "byo_railway": "RAILWAY_TOKEN" in (state.creds_provided or []),
            "workspace": self._workspace_state(run_id, state.phase),
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
