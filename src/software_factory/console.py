"""Operator console logic: turn a one-line app request into a headless factory run, read back
live status, and assemble proof.

The console is the HARNESS, not the builder. It orchestrates three stages — each a separate
`claude -p` invocation — with gates between them. Stage 1→2 is automatic (PRD passes gate).
Stage 2→3 requires user input (dependency tokens). The wait-for-deps step is a console-level
procedure, not inside any stage.
"""
from __future__ import annotations

import json
import os
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable

from . import artifacts, gates, streamlog
from .agents import AgentRegistry
from .evidence import build_evidence, verify_evidence
from .input_pipeline import persist_and_compose
from .pdf_extract import extract_to_markdown
from . import deps as deps_mod
from .mcp_health import check_mcp
from .runstate import RunState
from .db import RunDB
from . import dbshim
from .tickets import TicketStore
from .workspace_setup import prepare_workspace

SKILL_VERSION = "0.0.1"

STAGE_1 = ["extract", "provision", "research"]
STAGE_2 = ["architect", "tickets"]
STAGE_3 = ["build", "deploy", "test", "teardown"]
PIPELINE = STAGE_1 + STAGE_2 + STAGE_3
PIPELINE_LABELS = {"wait-for-deps": "wait for deps"}

PHASE_AGENTS = {
    "research": [
        ("horizon", "HORIZON"), ("archivist", "ARCHIVIST"),
        ("vanguard", "VANGUARD"), ("chroma", "CHROMA"),
        ("designer", "DESIGNER"),
    ],
    "architect": [("architect", "software-architect")],
}

PHASE_STAGE = {}
for _p in STAGE_1:
    PHASE_STAGE[_p] = 1
for _p in STAGE_2:
    PHASE_STAGE[_p] = 2
for _p in STAGE_3:
    PHASE_STAGE[_p] = 3

# Per-stage model: research (1) & design (2) on Opus 4.8; build (3) on Sonnet (cheaper for
# high-volume code edits). SF_MODEL env overrides all stages if set.
_STAGE_MODEL = {1: "claude-opus-4-8", 2: "claude-opus-4-8", 3: "claude-sonnet-4-6"}
# opencode runtime: one model for all stages (monolithic v1 — no per-stage split).
_STAGE_MODEL_OPENCODE = {s: "openrouter/moonshotai/kimi-k2.6" for s in (1, 2, 3)}
# Operator-pickable per-run models (claude runtime). The UI offers exactly these; anything
# else is ignored at start_run so a bad request can never launch an unknown/unpriced model.
PLANNING_MODELS = {"claude-opus-4-8", "claude-fable-5"}
IMPL_MODELS = {"claude-sonnet-4-6", "claude-opus-4-8"}


@dataclass
class RunRequest:
    description: str
    context: str = ""
    budget: float = 25.0
    target: str = "railway"
    credentials: dict = field(default_factory=dict)
    context_files: list = field(default_factory=list)
    runtime: str = ""  # claude | opencode; empty -> SF_RUNTIME env (default claude)
    planning_model: str = ""  # S1/S2 orchestrator model (claude runtime); empty -> stage default
    impl_model: str = ""      # S3 model (claude runtime); empty -> stage default
    name: str = ""            # operator-chosen project name (display label)
    gated: bool = False       # create held: registered + visible at $0, stage 1 launches on release


def run_paths(runs_dir: str, run_id: str) -> dict:
    base = os.path.join(runs_dir, run_id)
    # ONE SQLite db per run is the source of truth: runstate + tickets + agents + the
    # canvas-projected tables (phases/artifacts/blockers/gates/verifications) all live in run.db.
    db = os.path.join(base, "run.db")
    return {
        "base": base,
        "state_dir": base,
        "db": db,
        "agents_db": db,
        "tickets_db": db,
        "input_dir": os.path.join(base, "input"),
    }


def _orchestration_preamble(stage_title: str, run_id: str, runs_dir: str, budget: float,
                            runtime: str = "claude") -> str:
    db = "python3 -m software_factory.db"
    if runtime == "opencode":
        # Monolithic: one agent does the work itself, but records one LOGICAL agent per unit
        # of work so the done-gates (detect_stage3_done: spawned>0, tickets traceable) and the
        # canvas agent graph keep their per-unit accounting.
        work_model = (
            f"MONOLITHIC: you do ALL the work yourself, sequentially — there is no Task tool and no "
            f"sub-agents. For accounting, record one LOGICAL agent per unit of work (research unit / "
            f"ticket / bugfix): `spawn-agent` BEFORE you start the unit, `finish-agent` when it's done.\n"
        )
        spawn_line = f"  spawn-agent <id> <role> <model> <phase>   — before each unit of work you start\n"
        finish_line = (
            f"  finish-agent <id> <outcome> [cost] [pr] [diff_lines]  — when the unit is done; outcome MUST be one of\n"
        )
    else:
        work_model = (
            f"ORCHESTRATOR-ONLY: you coordinate; the actual work is done by sub-agents you launch with the "
            f"native **Task** tool (one per unit of work). Do NOT do the work in the main session.\n"
        )
        spawn_line = f"  spawn-agent <id> <role> <model> <phase>   — when you launch a Task sub-agent\n"
        finish_line = (
            f"  finish-agent <id> <outcome> [cost] [pr] [diff_lines]  — when it returns; outcome MUST be one of\n"
        )
    return (
        f"Use the **software-factory** skill ({stage_title}), FULLY AUTONOMOUSLY — never wait on a human.\n"
        f"**Your contract is SKILL.md in this workspace (your cwd). Read it and follow it exactly.** "
        f"Prior-stage artifacts are in context/.\n"
        f"run_id={run_id}. runs_dir={runs_dir}. Run base: {os.path.join(runs_dir, run_id)} "
        f"(your cwd is its workspace/). Budget ${budget:.0f} (HARD cutoff).\n\n"
        + work_model
        + f"RECORD canvas state in the datastore (there are NO events): `{db} <verb> {runs_dir} {run_id} ...`\n"
        f"  set-phase <name> [status]            — at each phase you enter\n"
        + spawn_line
        + finish_line
        + f"      real_diff|success (worked) · no_op (empty turn) · blocked · failed — anything else records as failed\n"
        f"  record-artifact <title> <path> [kind] [agent]  — for each file produced\n"
        f"  add-blocker <what> [blocks] / clear-blocker <what>\n"
        f"Tickets go in the TicketStore; runstate is written by the host.\n"
    )


def make_prompt_stage1(req: RunRequest, run_id: str, runs_dir: str, runtime: str = "claude") -> str:
    ctx = f"\n\nContext / detailed input:\n{req.context}" if req.context else ""
    if runtime == "opencode":
        units = ("The named research units and the done-gate are in SKILL.md. Do each unit yourself, "
                 "in order, recording each as a logical agent.")
    else:
        units = ("The named research sub-agents and the done-gate are in SKILL.md. Launch each as a "
                 "Task sub-agent.")
    return (
        _orchestration_preamble("Stage 1 — Research", run_id, runs_dir, req.budget, runtime)
        + "Goal: a validated PRD (PRD.md) that passes `artifacts.prd_is_complete` (≥3 real product "
          "URLs + acceptance criteria + ticket seeds). " + units + " THE MOMENT you create the "
          "GitHub repo, record it (CLEAN token-free https url): `record-artifact 'GitHub Repo' "
          "<https-url> repo` — the operator sees the repo link from the start. When the PRD passes, "
          "STOP — the console launches Stage 2.\n"
          f"App: {req.description}{ctx}"
    )


def make_prompt_stage2(req: RunRequest, run_id: str, runs_dir: str, runtime: str = "claude") -> str:
    return (
        _orchestration_preamble("Stage 2 — Design & Plan", run_id, runs_dir, req.budget, runtime)
        + "Goal (per SKILL.md): architecture.md + architecture.svg (fewest services; data model; a "
          "`## Required Tokens` section, UPPER_SNAKE_CASE) AND PERSISTED buildable tickets — "
          "`TicketStore.create_ticket` with real acceptance + DoD (an empty store dead-ends Stage 3). "
          "The Stage 3 build agent has the Supabase + Railway MCP, so design Supabase/Railway/NextAuth as "
          "agent-provisionable (don't require the operator for them); route every LLM/AI feature via "
          "OpenRouter (OPENROUTER_API_KEY). When PRD+architecture+svg exist and the store has buildable "
          "tickets, STOP — the console collects deps + launches Stage 3.\n"
          f"App: {req.description}"
    )


def _disposition_guidance(dispositions: dict | None) -> str:
    disp = dispositions or {}
    # Legacy 'env' (pre-removal runs) degrades to mock: a built app NEVER inherits the
    # runner's own keys (operator security rule).
    mock = sorted(n for n, d in disp.items() if d in ("mock", "env"))
    mcp = sorted(n for n, d in disp.items() if d == "mcp")
    if not disp:
        return ""
    return (
        f"\nDEPENDENCY DISPOSITIONS — satisfy each capability as marked:\n"
        f"- **MOCK** (build a WORKING LOCAL FAKE wired into the real app so the happy-flow passes "
        f"end-to-end — e.g. a 'sign in as demo admin' session for SSO, seeded DB rows for ERP/HR "
        f"data, emails written to a table/log for mail; NOT a dead stub): {mock or 'none'}\n"
        f"- **PROVISION VIA MCP** (you have the Supabase + Railway MCP — create the Supabase project "
        f"and read URL/anon/service-role keys; generate NEXTAUTH_SECRET; set NEXTAUTH_URL from the "
        f"deploy URL; set vars on the sf-<run_id> service): {mcp or 'none'}\n"
        f"- Operator-PROVIDED tokens ride in your environment with real values; NEVER copy any "
        f"other key from your own environment into the app (your keys are not the app's keys).\n"
        f"Do NOT block on a real third-party integration when its token is marked MOCK — build the fake.\n"
    )


def make_prompt_stage3(req: RunRequest, run_id: str, runs_dir: str, dispositions: dict | None = None,
                       runtime: str = "claude") -> str:
    service = f"sf-{run_id}"
    if runtime == "opencode":
        build_line = (
            f"BUILD: work ONE ticket at a time yourself, recording each as a logical agent "
            f"(spawn-agent before, finish-agent after) and claiming it (`TicketStore.claim`) with that "
            f"same agent id; merge only via `merge_if_green`; `TicketStore.mark_done`. Serialize per wave.\n"
        )
        fix_one = "fix it yourself (recorded as a logical fix agent)"
        fix_bug = "a logical fix agent per bug"
    else:
        build_line = (
            f"BUILD: one native Task sub-agent PER ticket (orchestrator-only — never edit app code yourself); "
            f"merge only via `merge_if_green`; `TicketStore.mark_done`. Serialize per wave.\n"
        )
        fix_one = "fix it (one Task sub-agent)"
        fix_bug = "a Task sub-agent per bug"
    return (
        _orchestration_preamble("Stage 3 — Build & Ship", run_id, runs_dir, req.budget, runtime)
        + _disposition_guidance(dispositions)
        + f"Deploy target: {req.target}. DEPLOY VIA THE **Railway MCP** (its project-scoped tools work "
          f"with the env's RAILWAY_TOKEN; `whoami`/`list_projects` do NOT — don't call them). Create + deploy "
          f"ONLY to the dedicated service '{service}': `create_service` '{service}' → `set_variables` (all runtime "
          f"env) → `deploy` → `generate_domain` (the app has NO public url until you do this; derive the health url "
          f"from it). NEVER deploy to the console service.\n"
          f"DEPLOY PREFLIGHT (Railway blocks the build otherwise): run `npm audit` and bump HIGH/CRITICAL deps to "
          f"patched versions + regen the lockfile; give module-load clients (e.g. Supabase) BUILD-TIME placeholder env "
          f"in the Dockerfile so `next build` doesn't throw (runtime values override); ship a Dockerfile. The build runs "
          f"REMOTELY on Railway — do NOT run `npm run build` locally (it OOM-kills the shared container).\n"
          f"HEALTH: use a FINITE health-wait (bounded attempts, never an infinite loop). On failure call the Railway MCP "
          f"`get_logs` (build AND deploy), read the real error, {fix_one}, redeploy.\n"
          f"Record the source repo (CLEAN url, strip any token): `record-artifact 'GitHub Repo' <https-url> repo`.\n"
          f"PHASE 0 — PLAN FIRST: before building, write `build-plan.md` (approach, wave/ticket order, "
          f"mock/MCP decisions, the happy-flow you will verify) and `record-artifact 'Build Plan' build-plan.md plan`. "
          f"THEN execute (no human approval — this is autonomous).\n"
          + build_line
          + f"GATE (mandatory — the ONLY definition of done): after deploy, drive the LIVE url with the "
          f"**Playwright MCP** through the primary journey, pass the structured result to "
          f"`gate.happy_flow_passed`, and record it: `record-verification <url> <0|1> <result-json>`. "
          f"A GREEN Playwright happy-flow on the live url is done; deploying/merging is NOT done. "
          f"Red → fix ({fix_bug}) → redeploy → re-test. See SKILL.md for the full contract.\n"
          f"DEMO LOGIN (how the operator demos the app): if the app has ANY sign-in, seed a demo "
          f"account (throwaway values — e.g. demo@example.com / a generated phrase, NEVER a real "
          f"secret), write it to `demo_credentials.md` (user + password, one per line), record it "
          f"(`record-artifact 'Demo credentials' demo_credentials.md demo-creds`), and run the "
          f"Playwright happy-flow signed in WITH those credentials.\n"
          f"App: {req.description}"
    )


# Keep the old prompt generator for backward compat with existing runs
def make_prompt(req: RunRequest, run_id: str, runs_dir: str) -> str:
    return make_prompt_stage1(req, run_id, runs_dir)


def _default_launch(argv: list[str], env: dict, log_path: str | None = None, cwd: str | None = None) -> Any:
    import subprocess
    import sys
    import threading

    proc = subprocess.Popen(
        argv, env={**os.environ, **env}, cwd=cwd,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, bufsize=1, text=True,
    )
    prefix = f"[{os.path.basename(os.path.dirname(log_path))}] " if log_path else ""

    def _pump():
        logf = open(log_path, "a") if log_path else None
        try:
            for line in proc.stdout:
                sys.stdout.write(prefix + line)
                sys.stdout.flush()
                if logf:
                    logf.write(line)
                    logf.flush()
        finally:
            if logf:
                logf.close()

    threading.Thread(target=_pump, daemon=True).start()
    return proc


class Console:
    def __init__(
        self,
        runs_dir: str,
        launch: Callable[..., Any] = _default_launch,
        new_id: Callable[[], str] = lambda: "run-" + uuid.uuid4().hex[:8],
        extract: Callable[[str], str] = extract_to_markdown,
    ):
        self._runs_dir = runs_dir
        self._launch = launch
        self._new_id = new_id
        self._extract = extract
        self._procs: dict = {}   # run_id -> last launched stage process (SPEC §1 handoff guard)
        # run_id -> ((mtime_ns, size), cost): the full-log cost reparse on EVERY status/poll
        # was the console's dominant CPU+IO — two pollers × every run × multi-MB stream logs.
        self._cost_cache: dict = {}
        os.makedirs(runs_dir, exist_ok=True)

    def _paths(self, run_id: str) -> dict:
        return run_paths(self._runs_dir, run_id)

    # ---- SPEC §1: stage process lifecycle ------------------------------------------------
    def _stage_process_alive(self, run_id: str) -> bool:
        p = self._procs.get(run_id)
        return p is not None and hasattr(p, "poll") and p.poll() is None

    def stage_finished(self, run_id: str) -> bool:
        """SPEC §1: the stage's orchestrator process has finished — the tracked process exited,
        or (no usable handle, e.g. after a server restart) the run.log has been idle past a
        2-minute grace (covers crash/OOM without wedging the run).

        Opencode-runtime exception: a LIVE handle is not proof of life — opencode processes
        LINGER after their session completes (run-45b8c4d5 wedged with a working app, a cleanly
        ended session, and a zombie proc blocking auto-resume). When the log's LAST event is the
        session-terminal `step_finish reason=stop` AND the log has been idle past a 5-minute
        grace, the stage is finished regardless of the handle. Claude stages are exempt: their
        long quiet tool calls (health-waits, builds) must never false-finish into a concurrent
        relaunch (the §1 double-orchestrator race)."""
        log = os.path.join(self._paths(run_id)["base"], "run.log")
        p = self._procs.get(run_id)
        if p is not None and hasattr(p, "poll"):
            if p.poll() is not None:
                return True
            if (self._load_state(run_id).runtime == "opencode"
                    and os.path.exists(log)
                    and (time.time() - os.path.getmtime(log)) > 300
                    and self._log_session_completed(log)):
                return True
            return False
        if not os.path.exists(log):
            return True
        return (time.time() - os.path.getmtime(log)) > 120

    @staticmethod
    def _log_session_completed(log_path: str) -> bool:
        """True when the log's last parseable event is opencode's session-terminal
        step_finish with reason=stop (a finished session, not a mid-flight pause)."""
        try:
            with open(log_path, "rb") as f:
                f.seek(0, 2)
                f.seek(max(0, f.tell() - 65536))
                tail = f.read().decode("utf-8", "replace")
        except OSError:
            return False
        last = None
        for line in tail.splitlines():
            line = line.strip()
            if not line.startswith("{"):
                continue
            try:
                ev = json.loads(line)
            except ValueError:
                continue
            if ev.get("type") in ("step_start", "step_finish", "error"):
                last = ev
        if not last:
            return False
        if last.get("type") == "error":
            return True   # crashed session — finished by definition
        return (last.get("type") == "step_finish"
                and (last.get("part") or {}).get("reason") == "stop")

    # ---- SPEC §1: host-derived phase state machine ----------------------------------------
    _CLOSED = ("done", "passed", "completed")

    def derive_phases(self, run_id: str) -> dict:
        """Phase states derived from recorded signals — agent set-phase calls are hints,
        never the source of truth. States: pending | active | done | skipped.

        Truthfulness rules (the run-45b8c4d5 canvas lies):
        - Activity is inferred from EVIDENCE, not just set-phase rows: a deploy-kind artifact
          is deploy activity (the app was live while 'deploy' rendered skipped), a recorded
          verification is test activity.
        - A phase with its CLOSING SIGNAL is done regardless of position: deploy closes on a
          deploy artifact, test on a passing verification, stage phases on their stage flags.
        - 'active' is the phase with the MOST RECENT activity (not the furthest index): a
          test→build fix loop truthfully bounces the canvas back to build.
        - Later phases that ran but didn't close render pending (they will run again);
          bypassed phases read skipped."""
        db = RunDB(self._paths(run_id)["db"])
        state = self._load_state(run_id)
        rows = db.phases()                                # append-only, ts-ordered
        last_ts = {}
        for r in rows:
            if r["name"] in PIPELINE:
                last_ts[r["name"]] = r["ts"]
        for a in db.artifacts():                          # evidence-implied activity
            if (a.get("kind") or "").lower() == "deploy":
                last_ts["deploy"] = max(last_ts.get("deploy", 0), a.get("ts") or 0)
        verifs = db.verifications()
        if verifs:
            last_ts["test"] = max(last_ts.get("test", 0), max(v.get("ts") or 0 for v in verifs))

        closed = set()
        if state.stage1_done:
            closed.update(("extract", "provision", "research"))
        if state.stage2_done:
            closed.update(("architect", "tickets"))
        if any((a.get("kind") or "").lower() == "deploy" for a in db.artifacts()):
            closed.add("deploy")
        if db.has_passing_verification():
            closed.add("test")
        recorded = db.phase_status()
        closed.update(n for n in PIPELINE if recorded.get(n) in self._CLOSED)

        activity = set(last_ts) | closed
        run_done = state.phase == "done"
        idx = {n: i for i, n in enumerate(PIPELINE)}
        furthest = max((idx[n] for n in activity), default=-1)
        active = None
        if not run_done:
            open_with_ts = {n: t for n, t in last_ts.items() if n not in closed}
            if open_with_ts:
                active = max(open_with_ts, key=open_with_ts.get)
        out = {}
        for i, n in enumerate(PIPELINE):
            if n == active:
                out[n] = "active"
            elif n in closed or (run_done and n in activity):
                out[n] = "done"
            elif n in activity:
                # ran without closing: behind the active phase it's spent (done); ahead of it
                # it will run again (pending) — the honest render of a fix loop.
                out[n] = "done" if active is not None and i < idx.get(active, -1) else "pending"
            elif i > furthest:
                out[n] = "pending"
            else:
                out[n] = "skipped"
        return out

    def current_phase(self, run_id: str) -> str:
        """The derived current phase for the header/API — never the stale RunState value."""
        state = self._load_state(run_id)
        if state.phase in ("done", "stopped"):
            return state.phase
        db = RunDB(self._paths(run_id)["db"])
        recorded = db.phase_status()
        implied = set()
        if state.stage2_done:
            implied.add("tickets")
        elif state.stage1_done:
            implied.add("research")
        idx = {n: i for i, n in enumerate(PIPELINE)}
        active = [n for n in PIPELINE if n in recorded] + [n for n in implied]
        if not active:
            return state.phase
        return max(active, key=lambda n: idx[n])

    def _terminal(self, state) -> bool:
        return state.phase in ("done", "stopped")

    def maybe_autosatisfy_deps(self, run_id: str) -> bool:
        """SPEC §3: if NO required token classifies as 'provide' (human secret), auto-satisfy
        deps (mock/mcp defaults apply) so the deps gate never becomes a hidden manual pause.
        Returns True iff deps are satisfied after the call."""
        state = self._load_state(run_id)
        if self._terminal(state) or not state.stage2_done:
            return False
        if state.deps_satisfied:
            return True
        disp = deps_mod.default_dispositions(state.deps_required)
        disp.update(state.deps_disposition or {})
        if any(d == "provide" for d in disp.values()):
            return False
        return bool(self.submit_deps(run_id, {}).get("satisfied"))

    def _load_state(self, run_id: str) -> RunState:
        return RunState.load(run_id, RunDB(self._paths(run_id)["db"]))

    def _run_spend(self, run_id: str) -> float:
        """THIS run's own spend (the per-run budget basis). Prior runs/projects do NOT count —
        each run/project is independently capped. Authoritative cost from the run.log, falling
        back to the recorded runstate spend."""
        # max(): the log-derived figure normally leads, but the persisted runstate spend survives
        # log loss / parser regressions — the budget guard must never silently under-count.
        return max(self._cost(run_id), self._load_state(run_id).spent_usd or 0)

    def _budget_ceiling(self, run_id: str) -> float:
        """SPEC §4: per-run ceiling — the run's own override, else SF_COST_CEILING (default 30)."""
        state = self._load_state(run_id)
        if state.budget_ceiling:
            return float(state.budget_ceiling)
        return float(os.environ.get("SF_COST_CEILING", "30") or 30)

    def enforce_budget(self, run_id: str) -> bool:
        """SPEC §4 mid-stage teeth: if this run's spend crossed its ceiling, terminate the live
        stage process, record a recoverable 'budget' blocker, and finalize orphaned agents.
        Returns True iff the run was (or already had been) stopped for budget this call."""
        ceiling = self._budget_ceiling(run_id)
        spend = self._run_spend(run_id)
        if spend <= ceiling:
            return False
        p = self._procs.get(run_id)
        killed = False
        if p is not None and hasattr(p, "poll") and p.poll() is None and hasattr(p, "terminate"):
            p.terminate()
            killed = True
        db = RunDB(self._paths(run_id)["db"])
        already = any(b.get("blocks") == "budget" and not b["cleared"] for b in db.blockers())
        if not already:
            db.add_blocker(
                f"Budget cap ${ceiling:.2f} reached (spent ${spend:.2f}) — stage stopped. "
                f"Raise the cap to continue.", blocks="budget")
            AgentRegistry(self._paths(run_id)["agents_db"]).finalize_orphans(run_id, stage_ok=False)
        return True   # over-ceiling: stopped now (killed) or already stopped

    def auto_resume_dead_stage(self, run_id: str) -> bool:
        """SPEC §3 zero-touch: a stage whose process died without passing its gate (OOM/crash)
        is resumed by the HOST — a human noticing the stall is an intervention. Never fires at
        the deps gate (stage complete, waiting by design) or on a budget stop (operator's call).
        Never resurrects a GHOST: a run.db with no recorded artifacts (e.g. created by a mere
        status query after state loss) has no brief to build from — resuming it burns spend on
        an empty prompt (the run-b594a5f4/run-0eb69fdd double-ghost scar)."""
        if not self.is_pipeline_run(run_id):
            return False
        state = self._load_state(run_id)
        if state.phase in ("done", "stopped") or not self.stage_finished(run_id):
            return False   # terminal/canceled runs are never resurrected
        stage = state.stage
        db = RunDB(self._paths(run_id)["db"])
        if any(b.get("blocks") == "budget" and not b["cleared"] for b in db.blockers()):
            return False
        incomplete = (
            (stage == 1 and not state.stage1_done)
            or (stage == 2 and not state.stage2_done)
            or (stage == 3 and not db.has_passing_verification())
        )
        if not incomplete:
            return False
        return self.retry_stage(run_id, stage) is not None

    def raise_budget(self, run_id: str, ceiling: float) -> dict:
        """SPEC §4 recovery: persist a higher per-run ceiling and clear the budget blocker(s);
        the operator then resumes via /retry against the preserved workspace."""
        state = self._load_state(run_id)
        state.budget_ceiling = float(ceiling)
        state.save()
        db = RunDB(self._paths(run_id)["db"])
        for b in db.blockers():
            if b.get("blocks") == "budget" and not b["cleared"]:
                db.clear_blocker(b["what"])
        return {"run_id": run_id, "budget_ceiling": float(ceiling)}

    def _launch_stage(self, run_id: str, stage: int, prompt: str, env: dict) -> Any:
        """Prepare workspace, health-check MCP, and launch a claude -p process for a stage."""
        paths = self._paths(run_id)

        # Mechanical PER-RUN cost ceiling: the in-prompt budget is advisory-only and stages don't
        # share a counter, so refuse to launch the next stage when THIS run's own spend (+ a stage
        # reserve) would cross the run's ceiling (per-run override else SF_COST_CEILING).
        ceiling = self._budget_ceiling(run_id)
        reserve = float(os.environ.get("SF_STAGE_RESERVE", "5") or 5)
        spend = self._run_spend(run_id)
        if spend + reserve > ceiling:
            RunDB(paths["db"]).add_blocker(
                f"Per-run budget: this run ${spend:.2f} + reserve ${reserve:.2f} "
                f"> ceiling ${ceiling:.2f} — stage {stage} launch refused",
                blocks="budget",
            )
            return None

        state = self._load_state(run_id)
        runtime = state.runtime or "claude"
        ws = prepare_workspace(
            self._runs_dir, run_id, stage, runtime=runtime,
        )
        mcp_path = os.path.join(ws, ".mcp.json")
        checks = check_mcp(mcp_path)
        unhealthy = [c for c in checks if not c.ok]
        # Hard-gate ONLY playwright (the happy-flow verification gate needs it). The deploy/provision
        # MCPs (railway, supabase) are best-effort: record a blocker if unhealthy but still launch —
        # a transient npx/token hiccup must not block the whole stage, and the agent surfaces real
        # deploy-tool failures itself (bounded health-wait + get_logs).
        _HARD = {"playwright", "config"}
        if unhealthy:
            db = RunDB(paths["db"])
            for c in unhealthy:
                db.add_blocker(f"MCP:{c.name} — {c.detail}", blocks="mcp")
            if any(c.name in _HARD for c in unhealthy):
                return None

        state.stage = stage
        state.save()

        if runtime == "opencode":
            model = os.environ.get("SF_MODEL") or _STAGE_MODEL_OPENCODE.get(
                stage, "openrouter/moonshotai/kimi-k2.6")
            argv = [
                "opencode", "run", prompt,
                "--model", model,
                "--agent", "factory",
                "--format", "json",
                "--dangerously-skip-permissions",
            ]
            # Isolate from the host's global opencode config (~/.config/opencode injects
            # unrelated MCPs/instructions) and from externally scanned skills (~/.claude/skills
            # holds dozens of dev-box skills) — the workspace opencode.json is the whole contract.
            # The steps cap (claude's --max-turns analogue) lives in that opencode.json.
            env = {
                **env,
                "XDG_CONFIG_HOME": os.path.join(ws, ".oc-config"),
                "OPENCODE_DISABLE_CLAUDE_CODE_SKILLS": "1",
                "OPENCODE_DISABLE_EXTERNAL_SKILLS": "1",
                # Popen(cwd=ws) changes the real cwd but NOT the inherited PWD env var, and
                # OpenCode trusts PWD for project resolution — a stale PWD (e.g. the repo root)
                # makes it bind the session to the wrong directory and crash createUserMessage.
                "PWD": ws,
            }
        else:
            # Model precedence: the operator's per-run pick (most specific — pinned in state at
            # start_run, so retries keep it) > SF_MODEL env (deploy-wide knob) > stage defaults
            # (research & design on Opus 4.8; build on Sonnet, cheaper for code volume).
            pick = state.planning_model if stage in (1, 2) else state.impl_model
            model = pick or os.environ.get("SF_MODEL") \
                or _STAGE_MODEL.get(stage, "claude-sonnet-4-6")
            if stage == 3 and state.impl_model:
                # The stage-3 SKILL contract pins sonnet for Task subagents; an explicit
                # operator pick must override that in-prompt or the orchestrator fights it.
                prompt = (f"{prompt}\n\nMODEL OVERRIDE (operator-pinned): this stage and every "
                          f"Task subagent run on {model} — this overrides any model named in "
                          f"SKILL.md.")
            max_turns = os.environ.get("SF_MAX_TURNS", "200")
            argv = [
                "claude", "-p", prompt,
                "--model", model,
                "--max-turns", max_turns,
                "--permission-mode", "bypassPermissions",
                "--output-format", "stream-json", "--verbose",
            ]
        # cwd = the workspace so the stage's SKILL.md / phases/ / context/ (its contract) load.
        result = self._launch(argv, env, os.path.join(paths["base"], "run.log"), cwd=ws)
        if result is not None:
            self._procs[run_id] = result   # SPEC §1: tracked for the stage-handoff guard
        return result

    def start_run(self, req: RunRequest) -> str:
        """Start a new run (Stage 1). Returns run_id."""
        run_id = self._new_id()
        paths = self._paths(run_id)
        os.makedirs(paths["base"], exist_ok=True)

        # input -> (pdf->markdown) -> markdown + prompt -> composed Stage 1 input.
        written = persist_and_compose(
            paths["input_dir"], req.description, req.context_files or [],
            extract=self._extract,
        )
        input_db = RunDB(paths["db"])
        for name in written:
            input_db.record_artifact("input", "input/" + name, kind="context")
        # SPEC §1: the HOST performs extraction — record it (and provision opening) itself,
        # so these phases are never trust-based and extract can never sit 'pending' forever.
        input_db.set_phase("extract", "done")
        if not req.gated:
            input_db.set_phase("provision", "active")

        state = self._load_state(run_id)
        env = {k: v for k, v in (req.credentials or {}).items() if v}
        state.skill = "software-factory"
        state.skill_version = SKILL_VERSION
        state.description = req.description
        state.name = req.name or ""
        state.deploy_target = req.target
        state.creds_provided = sorted(env.keys())
        state.stage = 1
        # Pin the agent runtime for the whole run (all stages + retries) at start.
        # Per-request choice (the UI's Claude/Kimi picker) wins over the SF_RUNTIME env default.
        state.runtime = req.runtime or os.environ.get("SF_RUNTIME", "claude")
        # Pin the operator's model picks (claude runtime); unknown values are dropped so only
        # the offered choices can ever launch. Empty = stage defaults.
        state.planning_model = req.planning_model if req.planning_model in PLANNING_MODELS else ""
        state.impl_model = req.impl_model if req.impl_model in IMPL_MODELS else ""
        state.held = bool(req.gated)
        state.save()

        if req.gated:
            # Held: registered + visible at $0; stage 1 launches on release_run. Create-time
            # credential VALUES are not persisted (names only), so gated runs rely on the
            # stage-3 deps flow for app credentials.
            return run_id
        prompt = make_prompt_stage1(req, run_id, self._runs_dir, runtime=state.runtime)
        self._launch_stage(run_id, 1, prompt, env)
        return run_id

    def release_run(self, run_id: str) -> bool:
        """Release a gated hold: launch Stage 1. False if not held (double-release refuses)."""
        state = self._load_state(run_id)
        if not state.held:
            return False
        state.held = False
        state.save()
        RunDB(self._paths(run_id)["db"]).set_phase("provision", "active")
        req = RunRequest(
            description=state.description or "",
            target=state.deploy_target or "railway",
            runtime=state.runtime,
            planning_model=state.planning_model,
            impl_model=state.impl_model,
            name=state.name,
        )
        prompt = make_prompt_stage1(req, run_id, self._runs_dir, runtime=state.runtime)
        self._launch_stage(run_id, 1, prompt, {})
        return True

    def is_pipeline_run(self, run_id: str) -> bool:
        """True only if this run was actually started by THIS pipeline (start_run records ≥1
        artifact in run.db). A resurfaced pre-redesign dir — PRD.md on disk but an empty run.db
        (created fresh on load) — is False, so the poller never auto-advances/zombie-launches it."""
        db = RunDB(self._paths(run_id)["db"])
        return bool(db.artifacts())

    def detect_stage1_done(self, run_id: str) -> bool:
        """Stage 1 is done when the PRD passes the mechanical gate (the artifact IS the proof —
        no event needed; the datastore + the committed PRD are the source of truth)."""
        state = self._load_state(run_id)
        if state.stage1_done:
            return True
        # SPEC §1: a stage is done only when its gate passes AND its process finished —
        # never flip (and so never let the poller launch S2) while S1 is still alive.
        if not self.stage_finished(run_id):
            return False
        base = self._paths(run_id)["base"]
        for root, _dirs, files in os.walk(base):
            if "PRD.md" in files:
                with open(os.path.join(root, "PRD.md")) as f:
                    text = f.read()
                ok, _reasons = artifacts.prd_is_complete(text)
                if ok:
                    state.stage1_done = True
                    state.skill, state.skill_version = "software-factory", SKILL_VERSION  # heal host-owned stamp (agents share the db file)
                    state.spent_usd = self._cost(run_id) or state.spent_usd
                    state.save()
                    # SPEC §5: the stage is over — close any agent rows it forgot to finish.
                    AgentRegistry(self._paths(run_id)["agents_db"]).finalize_orphans(run_id, stage_ok=True)
                    return True
        return False

    def start_stage2(self, run_id: str) -> str | None:
        """Launch Stage 2. Returns run_id or None if blocked (prior stage alive / MCP unhealthy)."""
        state = self._load_state(run_id)
        if self._terminal(state) or not state.stage1_done:
            return None   # terminal (done/stopped) runs are never relaunched
        if self._stage_process_alive(run_id):
            return None   # SPEC §1: never two stage orchestrators for one run
        req = RunRequest(description=state.description or "", target=state.deploy_target or "railway")
        env = {k: v for k, v in os.environ.items()
               if k in (state.creds_provided or [])}
        prompt = make_prompt_stage2(req, run_id, self._runs_dir, runtime=state.runtime)
        result = self._launch_stage(run_id, 2, prompt, env)
        return run_id if result is not None else None

    def detect_stage2_done(self, run_id: str) -> bool:
        """Stage 2 is done when PRD+architecture+svg exist AND the store holds buildable tickets
        (the artifacts + the ticket DB are the proof — no event needed)."""
        state = self._load_state(run_id)
        if state.stage2_done:
            return True
        if not self.stage_finished(run_id):
            return False   # SPEC §1: gate + finished process, never mid-flight
        base = self._paths(run_id)["base"]
        ok, _missing = artifacts.verify(base, ["PRD.md", "architecture.md", "architecture.svg"])
        if not ok:
            for root, _dirs, files in os.walk(base):
                ok2, _ = artifacts.verify(root, ["PRD.md", "architecture.md", "architecture.svg"])
                if ok2:
                    ok = True
                    break
        if not ok:
            return False
        # The store must hold real, buildable tickets (acceptance + DoD) — not just
        # ticket *events* on the canvas. An empty/hollow store is NOT a done Stage 2.
        tickets = TicketStore(self._paths(run_id)["tickets_db"])
        if tickets.buildable_count() < 1:
            return False
        state.stage2_done = True
        state.skill, state.skill_version = "software-factory", SKILL_VERSION  # heal host-owned stamp (agents share the db file)
        state.spent_usd = self._cost(run_id) or state.spent_usd
        # Parse required tokens from architecture.md
        for root, _dirs, files in os.walk(base):
            if "architecture.md" in files:
                with open(os.path.join(root, "architecture.md")) as f:
                    tokens = artifacts.parse_required_tokens(f.read())
                state.deps_required = [t["name"] for t in tokens]
                break
        state.save()
        AgentRegistry(self._paths(run_id)["agents_db"]).finalize_orphans(run_id, stage_ok=True)
        return True

    def detect_stage3_done(self, run_id: str) -> bool:
        """Stage 3 is done ONLY when BOTH hard gates pass (no hollow done):
        (a) the completed tickets trace to recorded native-Task agents — not a monolithic build, and
        (b) a PASSING Playwright happy-flow against the live URL is recorded in run.db.
        On success, record the deploy_url (from the passing verification) and mark phase=done."""
        state = self._load_state(run_id)
        if state.phase == "done":
            return True
        paths = self._paths(run_id)
        db = RunDB(paths["db"])
        # Gate (b): a real green browser test on the live url must be recorded.
        if not db.has_passing_verification():
            return False
        # Gate (a): tickets were built by per-ticket agents, not one monolithic session.
        done = TicketStore(paths["tickets_db"]).done_tickets()
        spawned = len(AgentRegistry(paths["agents_db"]).agents_for(run_id))
        if not done or spawned == 0 or any(t.agent is None for t in done):
            return False
        passing = [v for v in db.verifications() if v["passed"]]
        if passing:
            state.deploy_url = passing[-1]["url"]
        state.phase = "done"
        state.skill, state.skill_version = "software-factory", SKILL_VERSION  # heal host-owned stamp (agents share the db file)
        # Persist the final spend into run.db so cost survives log loss (SPEC §4 durability),
        # and so verify_evidence's spent_usd comparison has a real basis.
        state.spent_usd = max(state.spent_usd or 0, self._cost(run_id))
        state.save()
        AgentRegistry(paths["agents_db"]).finalize_orphans(run_id, stage_ok=True)
        return True

    def run_links(self, run_id: str) -> dict:
        """SPEC §6 delivery: the run's outward links from the artifacts table —
        {'repo': <github url>|None, 'live': <deploy url>|None}."""
        db = RunDB(self._paths(run_id)["db"])
        repo = live = None
        for a in db.artifacts():
            path = a.get("path") or ""
            if not path.startswith("http"):
                continue
            title = (a.get("title") or "").lower()
            kind = (a.get("kind") or "").lower()
            if repo is None and ("repo" in title or kind == "repo"):
                repo = path
            elif live is None and ("live" in title or kind == "deploy"):
                live = path
        state = self._load_state(run_id)
        return {"repo": repo or state.repo_url, "live": live or state.deploy_url}

    def demo_credentials(self, run_id: str) -> str | None:
        """SPEC §6 delivery: the seeded demo login (recorded by Stage 3 as a 'demo-creds'
        artifact) — an app with a sign-in is only demo-able if this reaches the operator.
        These are throwaway demo values by contract, never operator secrets."""
        db = RunDB(self._paths(run_id)["db"])
        for a in db.artifacts():
            if (a.get("kind") or "").lower() == "demo-creds":
                content = self.artifact(run_id, a.get("path") or "").get("content")
                if content:
                    return content.strip()
        return None

    def stage2_artifacts(self, run_id: str) -> dict:
        """Return Stage 2 artifact paths + parsed required tokens + default dispositions."""
        state = self._load_state(run_id)
        base = self._paths(run_id)["base"]
        # default disposition per token (smart-classified), overlaid with any saved choices
        disposition = deps_mod.default_dispositions(state.deps_required)
        disposition.update(state.deps_disposition or {})
        result = {"deps_required": state.deps_required, "deps_provided": state.deps_provided,
                  "deps_satisfied": state.deps_satisfied, "disposition": disposition, "tokens": []}
        for root, _dirs, files in os.walk(base):
            if "architecture.md" in files:
                with open(os.path.join(root, "architecture.md")) as f:
                    result["tokens"] = artifacts.parse_required_tokens(f.read())
                break
        return result

    def submit_deps(self, run_id: str, deps: dict) -> dict:
        """Accept per-dep dispositions (+ values for `provide`). Accepts both the new shape
        `{name: {disposition, value?}}` and legacy `{name: value_string}` (treated as provide).

        Persists NAMES + dispositions (metadata) to state. Provided VALUES are NEVER written to
        disk — they ride into the Stage 3 env via `start_stage3(extra_creds=...)`."""
        state = self._load_state(run_id)
        disposition = deps_mod.default_dispositions(state.deps_required)
        disposition.update(state.deps_disposition or {})
        provided = set(state.deps_provided)
        for name, spec in deps.items():
            if isinstance(spec, dict):
                disposition[name] = spec.get("disposition") or deps_mod.classify_dep(name)
                if disposition[name] == "env":   # removed option (stale UI/state) -> mock
                    disposition[name] = "mock"
                if disposition[name] == "provide" and spec.get("value") not in (None, ""):
                    provided.add(name)
            else:  # legacy: a bare value string => provide
                disposition[name] = "provide"
                if spec not in (None, ""):
                    provided.add(name)
        state.deps_disposition = disposition
        state.deps_provided = sorted(provided)
        state.deps_satisfied = deps_mod.resolve_satisfied(
            state.deps_required, disposition, state.deps_provided)
        state.save()
        missing = [n for n in state.deps_required
                   if not deps_mod.resolve_satisfied([n], disposition, state.deps_provided)]
        return {
            "deps_provided": state.deps_provided,
            "deps_required": state.deps_required,
            "disposition": disposition,
            "missing": missing,
            "satisfied": state.deps_satisfied,
        }

    def start_stage3(self, run_id: str, extra_creds: dict | None = None) -> str | None:
        """Launch Stage 3. Returns run_id or None if blocked."""
        state = self._load_state(run_id)
        if self._terminal(state) or not state.stage2_done or not state.deps_satisfied:
            return None   # terminal (done/stopped) runs are never relaunched
        if self._stage_process_alive(run_id):
            return None   # SPEC §1: never two stage orchestrators for one run
        req = RunRequest(description=state.description or "", target=state.deploy_target or "railway")
        env = {k: v for k, v in os.environ.items()
               if k in (state.creds_provided or [])}
        if extra_creds:
            env.update(extra_creds)
        prompt = make_prompt_stage3(req, run_id, self._runs_dir, dispositions=state.deps_disposition,
                                    runtime=state.runtime)
        result = self._launch_stage(run_id, 3, prompt, env)
        return run_id if result is not None else None

    def retry_stage(self, run_id: str, stage: int, extra_creds: dict | None = None) -> str | None:
        """Re-run a single stage against the EXISTING workspace + prior-stage artifacts.

        Unlike `start_stageN`, this does not require the stage's own completion — it's for
        re-running a stage that produced incomplete/bad output (e.g. Stage 2 emitted tickets
        as events but didn't persist them). The prior stage must be done so its inputs exist;
        `workspace.create` is idempotent so earlier stages are reused, never repeated.
        """
        if stage not in (1, 2, 3):
            return None
        if self._stage_process_alive(run_id):
            return None   # SPEC §1: never two stage orchestrators for one run
        state = self._load_state(run_id)
        if state.phase == "stopped":
            return None   # canceled runs stay canceled (budget-paused runs are NOT 'stopped')
        if stage >= 2 and not state.stage1_done:
            return None
        if stage >= 3 and not state.stage2_done:
            return None
        # Invalidate this stage's (and downstream) completion so the done-gates re-evaluate.
        if stage <= 1:
            state.stage1_done = False
        if stage <= 2:
            state.stage2_done = False
        state.save()

        req = RunRequest(description=state.description or "", target=state.deploy_target or "railway")
        env = {k: v for k, v in os.environ.items() if k in (state.creds_provided or [])}
        if extra_creds:
            env.update(extra_creds)
        if stage == 3:
            prompt = make_prompt_stage3(req, run_id, self._runs_dir, dispositions=state.deps_disposition,
                                        runtime=state.runtime)
        else:
            prompt = {1: make_prompt_stage1, 2: make_prompt_stage2}[stage](
                req, run_id, self._runs_dir, runtime=state.runtime)
        RunDB(self._paths(run_id)["db"]).set_phase("retry-stage-%d" % stage, "started")
        result = self._launch_stage(run_id, stage, prompt, env)
        return run_id if result is not None else None

    def _cost(self, run_id: str) -> float:
        """streamlog.cost_usd with an (mtime,size)-keyed cache — an unchanged run.log always
        yields the same cost, so the multi-MB reparse only happens when the log actually grew.
        Safe for the budget teeth: a stale hit is impossible (any append changes the key)."""
        p = os.path.join(self._paths(run_id)["base"], "run.log")
        try:
            st = os.stat(p)
            key = (st.st_mtime_ns, st.st_size)
        except OSError:
            return 0.0
        hit = self._cost_cache.get(run_id)
        if hit and hit[0] == key:
            return hit[1]
        val = streamlog.cost_usd(self._full_log(run_id))
        self._cost_cache[run_id] = (key, val)
        return val

    def _full_log(self, run_id: str) -> str:
        p = os.path.join(self._paths(run_id)["base"], "run.log")
        if not os.path.exists(p):
            return ""
        with open(p, "r", errors="replace") as f:
            return f.read()

    def read_log(self, run_id: str, max_bytes: int | None = 20000) -> str:
        if max_bytes is None:
            return self._full_log(run_id)
        return self._read_log_tail(run_id, max_bytes)

    def read_log_envelope(self, run_id: str, max_bytes: int = 20000) -> dict:
        """Tail of run.log with honesty about truncation — the UI must never present a
        partial log as the whole thing."""
        p = os.path.join(self._paths(run_id)["base"], "run.log")
        total = os.path.getsize(p) if os.path.exists(p) else 0
        log = self._read_log_tail(run_id, max_bytes)
        return {
            "log": log,
            "capped": total > max_bytes,
            "returned_bytes": min(total, max_bytes),
            "total_bytes": total,
        }

    def _read_log_tail(self, run_id: str, max_bytes: int) -> str:
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
            "name": state.name,
            "deploy_target": state.deploy_target,
            "phase": self.current_phase(run_id),
            "done": state.phase == "done",
            "deploy_url": state.deploy_url,
            "spent_usd": self._cost(run_id) or state.spent_usd,
            "creds_provided": state.creds_provided,
            "byo_railway": "RAILWAY_TOKEN" in (state.creds_provided or []),
            "workspace": self._workspace_state(run_id, state.phase),
            "agents": reg.counts(run_id),
            "no_op_rate": reg.no_op_rate(run_id),
            "stage": state.stage,
            "stage1_done": state.stage1_done,
            "stage2_done": state.stage2_done,
            "deps_required": state.deps_required,
            "deps_provided": state.deps_provided,
            "deps_satisfied": state.deps_satisfied,
            "planning_model": state.planning_model,
            "impl_model": state.impl_model,
            "budget_ceiling": self._budget_ceiling(run_id),
            "held": state.held,
        }

    def list_runs(self) -> list[dict]:
        runs = []
        # Local dirs ∪ the pg registry (pg mode): a run can exist only in the registry —
        # fresh container, wiped volume — and must still surface. Local wins the dedupe.
        local = [n for n in os.listdir(self._runs_dir)
                 if os.path.isdir(os.path.join(self._runs_dir, n))
                 and os.path.exists(os.path.join(self._runs_dir, n, "run.db"))]
        created = {}
        for r in dbshim.registry_runs():
            created[r["run_id"]] = r.get("created") or 0
        names = local + [rid for rid in created if rid not in set(local)]
        for name in names:
            st = self._load_state(name)
            # A budget-stopped run is NOT active: surfacing it with a live/green status misled
            # the operator into thinking frozen ghosts were consuming (the b594a5f4/0eb69fdd UI
            # confusion). An uncleared budget blocker = stopped, full stop.
            budget_stopped = any(
                b.get("blocks") == "budget" and not b["cleared"]
                for b in RunDB(self._paths(name)["db"]).blockers()
            )
            runs.append({
                "run_id": name,
                "phase": self.current_phase(name),
                "description": st.description,
                "name": st.name,
                "deploy_url": st.deploy_url,
                "spent_usd": self._cost(name) or st.spent_usd,
                "stage": st.stage,
                "budget_stopped": budget_stopped,
                "held": st.held,
            })
        def _sort_key(r):
            p = os.path.join(self._runs_dir, r["run_id"])
            try:
                return os.path.getmtime(p)
            except OSError:  # registry-only run, no local dir yet
                return created.get(r["run_id"], 0)
        runs.sort(key=_sort_key, reverse=True)
        return runs

    def events(self, run_id: str) -> list:
        """Recent run activity, projected from run.db for the live activity feed. Shaped like the
        old event records ({type, payload, ts}) so the frontend renders unchanged — but the DATASTORE
        is the source of truth; there is no event log."""
        db = RunDB(self._paths(run_id)["db"])
        items = []
        for p in db.phases():
            items.append({"ts": p["ts"], "type": "phase",
                          "payload": {"name": p["name"], "status": p["status"]}})
        for a in db.artifacts():
            items.append({"ts": a["ts"], "type": "artifact",
                          "payload": {"title": a["title"], "path": a["path"]}})
        for b in db.blockers():
            if not b["cleared"]:
                items.append({"ts": b["ts"], "type": "blocker", "payload": {"what": b["what"]}})
        for v in db.verifications():
            if v["passed"]:
                items.append({"ts": v["ts"], "type": "done", "payload": {"url": v["url"]}})
        items.sort(key=lambda e: e["ts"])
        return items

    def continue_run(self, run_id: str, gate: str) -> dict:
        gates.clear_gate(self._runs_dir, run_id, gate)
        return {"cleared": gate}

    def artifact(self, run_id: str, path: str) -> dict:
        # Artifact paths arrive relative to wherever the recording agent worked: the run base
        # (host: "input/..."), the workspace (orchestrator: "architecture.md"), or the cloned
        # project repo INSIDE the workspace (S1 agents: "PRD.md", "research/x.md"). Resolve
        # against all three levels — the file must still stay under the run base (no escape).
        base = os.path.realpath(self._paths(run_id)["base"])
        ws = os.path.join(base, "workspace")
        roots = [base, ws]
        try:
            roots += [os.path.join(ws, d) for d in sorted(os.listdir(ws))
                      if os.path.isdir(os.path.join(ws, d))]
        except OSError:
            pass
        for root in roots:
            full = os.path.realpath(os.path.join(root, path))
            if os.path.commonpath([full, base]) == base and os.path.isfile(full):
                with open(full, "r", errors="replace") as f:
                    return {"path": path, "content": f.read()[:200000]}
        return {"error": "not found", "path": path}

    def graph(self, run_id: str) -> dict:
        """Cytoscape elements projected ENTIRELY from run.db (the single source of truth):
        pipeline phases + stage gates + deps from runstate/phases; agents from the agents table;
        artifacts/blockers from their tables; the pending review gate from the gates table.
        No event log, no stream-log parsing — the canvas is a pure projection of the datastore."""
        paths = self._paths(run_id)
        db = RunDB(paths["db"])
        state = self._load_state(run_id)
        orch_label = ("Kimi · software-factory" if state.runtime == "opencode"
                      else "Claude · software-factory")
        nodes = [{"data": {"id": "orchestrator", "label": orch_label,
                           "kind": "orchestrator", "status": self.current_phase(run_id)}}]
        edges = []

        derived = self.derive_phases(run_id)
        prev = "orchestrator"
        for name in PIPELINE:
            st = derived.get(name, "pending")
            pid = "phase:" + name
            nodes.append({"data": {"id": pid, "label": PIPELINE_LABELS.get(name, name),
                                   "kind": "phase", "status": st, "stage": PHASE_STAGE.get(name)}})
            edges.append({"data": {"source": prev, "target": pid, "etype": "flow"}})
            prev = pid
            if name == "research":
                gid = "gate:stage1"
                nodes.append({"data": {"id": gid, "label": "Stage 1 Gate", "kind": "gate",
                                       "status": "passed" if state.stage1_done else "pending"}})
                edges.append({"data": {"source": pid, "target": gid, "etype": "flow"}})
                prev = gid
            elif name == "tickets":
                gid = "gate:stage2"
                nodes.append({"data": {"id": gid, "label": "Stage 2 Gate", "kind": "gate",
                                       "status": "passed" if state.stage2_done else "pending"}})
                edges.append({"data": {"source": pid, "target": gid, "etype": "flow"}})
                did = "deps:wait"
                nodes.append({"data": {"id": did, "label": "wait for deps", "kind": "deps",
                                       "status": "satisfied" if state.deps_satisfied else "pending",
                                       "deps_required": state.deps_required,
                                       "deps_provided": state.deps_provided}})
                edges.append({"data": {"source": gid, "target": did, "etype": "flow"}})
                prev = did

        edges.append({"data": {"source": "phase:test", "target": "phase:build", "etype": "feedback"}})

        # Agents — projected from the agents table (recorded native Task sub-agents)
        reg = AgentRegistry(paths["agents_db"])
        agent_ids = set()
        for rec in reg.agents_for(run_id):
            nid = "agent:" + rec.agent_id
            agent_ids.add(nid)
            nodes.append({"data": {"id": nid, "label": rec.role, "kind": "agent",
                                   "status": rec.status, "real": True}})
            src = "phase:" + rec.phase if rec.phase in PIPELINE else "orchestrator"
            edges.append({"data": {"source": src, "target": nid, "etype": "hierarchy"}})

        # Artifacts — from the artifacts table
        for i, a in enumerate(db.artifacts()):
            path = a.get("path") or ""
            if path.startswith("http"):
                status = "created"
            else:
                status = "created" if (path and "content" in self.artifact(run_id, path)) else "missing"
            aid = "artifact:%d" % i
            nodes.append({"data": {"id": aid, "label": a.get("title") or "artifact", "kind": "artifact",
                                   "path": path, "status": status,
                                   "url": path if path.startswith("http") else None}})
            owner = ("agent:" + a["agent"]) if a.get("agent") and ("agent:" + a["agent"]) in agent_ids else "orchestrator"
            edges.append({"data": {"source": owner, "target": aid, "etype": "hierarchy"}})

        # Blockers — from the blockers table (uncleared)
        for i, b in enumerate([b for b in db.blockers() if not b["cleared"]]):
            bid = "blocker:%d" % i
            target = ("phase:" + b["blocks"]) if b.get("blocks") in PIPELINE else "orchestrator"
            nodes.append({"data": {"id": bid, "label": b.get("what") or "blocker", "kind": "blocker",
                                   "status": "open", "blocks": b.get("blocks")}})
            edges.append({"data": {"source": bid, "target": target, "etype": "hierarchy"}})

        # Pending review gate — from the gates table (status 'awaiting')
        existing_ids = {n["data"]["id"] for n in nodes}
        for gname, gstat in db.gate_status().items():
            if gstat == "awaiting":
                gid = "gate:" + gname
                if gid not in existing_ids:
                    nodes.append({"data": {"id": gid, "label": "awaiting review: " + gname,
                                           "kind": "gate", "status": "awaiting", "gate": gname}})
                    tgt = ("phase:" + gname) if ("phase:" + gname) in existing_ids else "orchestrator"
                    edges.append({"data": {"source": gid, "target": tgt, "etype": "flow"}})
        return {"nodes": nodes, "edges": edges}

    def evidence(self, run_id: str) -> dict:
        paths = self._paths(run_id)
        state = self._load_state(run_id)
        reg = AgentRegistry(paths["agents_db"])
        tickets = TicketStore(paths["tickets_db"])
        bundle = build_evidence(state, reg, tickets)
        ok, reasons = verify_evidence(bundle)
        return {"verified": ok, "reasons": reasons, "bundle": bundle}
