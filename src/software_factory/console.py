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
import shutil
import sys
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable

from .constants import (
    PROJECT_ID_RE,
    STAGE_1, STAGE_2, STAGE_3, PIPELINE,
    STAGE_MODEL as _STAGE_MODEL,
    OPENCODE_MODEL_IDS as _OPENCODE_MODEL_IDS,
    OPENCODE_DEFAULT_ALIAS as _OPENCODE_DEFAULT_ALIAS,
    CODEX_MODEL as _CODEX_MODEL,
    PLANNING_MODELS, IMPL_MODELS,
    RUNNER_KEYS as _RUNNER_KEYS,
)
from . import artifacts, checkpoint as ckpt, deploy_db, env as _env, recovery, streamlog, vault as _vault
from .project_view import INPUT_ONLY_KINDS
from .runtime_agents import AgentRegistry
from .input_pipeline import persist_and_compose
from .pdf_extract import extract_to_markdown
from .projects.intake import ProjectIntake, compose_description as _compose_description, project_paths
from .recipes.store import RecipeStore
from . import deps as deps_mod
from .mcp_health import check_mcp
from .projectstate import ProjectState
from .db import ProjectStore
from . import dbshim
from .repositories._exec import PathExec
from .repositories.canvas import ProjectStateRepository, PhaseRepository, BlockerRepository, ArtifactRepository
from .repositories.runtime_agents import AgentRepository
from .tickets import TicketStore
from .workspace_setup import prepare_workspace, tool_env_overrides, write_agent_file, RecipeSeedError
from .log import get_logger

logger = get_logger(__name__)


def _log_teardown_failures(result: dict | None, project_id: str = "") -> None:
    """SOF-160: surface deploy-DB teardown failures LOUDLY. `deploy_db.reap()` records failures in
    result["failed"] and logs them, but every caller passes log=logger.info, so a failed teardown
    (notably a serviceDelete 403 from the token-scope gap — SOF-160 — which comes back ok=False, NOT
    as an exception) is logged at INFO and effectively invisible: the DB leaks silently. Re-log each
    failure at ERROR with the service_id + detail so a leaked DB is visible. Non-fatal by design —
    the caller still completes its lifecycle/archive write regardless."""
    if not result:
        return
    for f in result.get("failed", []):
        logger.error("[deploy-db] TEARDOWN FAILED — DB NOT reclaimed (leaked; likely SOF-160 "
                     "RAILWAY_TOKEN 403 on serviceDelete): project=%s service=%s detail=%s",
                     f.get("project_id") or project_id, f.get("service_id"), f.get("detail"))
    for vf in (result.get("detached_volumes") or {}).get("failed", []):
        logger.error("[deploy-db] DETACHED-VOLUME SWEEP FAILED — volume NOT reclaimed: %s", vf)


SKILL_VERSION = "0.0.1"

PIPELINE_LABELS = {"wait-for-deps": "wait for deps"}

PHASE_STAGE = {}
for _p in STAGE_1:
    PHASE_STAGE[_p] = 1
for _p in STAGE_2:
    PHASE_STAGE[_p] = 2
for _p in STAGE_3:
    PHASE_STAGE[_p] = 3


def _key_source(runtime: str, creds_provided: list) -> str:
    """'BYOK' if the user supplied the runner key for this runtime; 'TENEXITY' otherwise."""
    runner_key = _RUNNER_KEYS.get(runtime, "ANTHROPIC_API_KEY")
    return "BYOK" if runner_key in (creds_provided or []) else "TENEXITY"


@dataclass
class ProjectRequest:
    description: str
    context: str = ""
    budget: float = 25.0
    target: str = "railway"
    credentials: dict = field(default_factory=dict)
    context_files: list = field(default_factory=list)
    runtime: str = ""  # claude | opencode | codex; empty -> SF_RUNTIME env (default claude)
    planning_model: str = ""  # S1/S2 orchestrator model (claude runtime); empty -> stage default
    impl_model: str = ""      # S3 model (claude runtime); empty -> stage default
    model: str = ""           # opencode model alias: "kimi"|"glm"; empty -> _OPENCODE_DEFAULT_ALIAS
    name: str = ""            # operator-chosen project name (display label)
    owner: str = ""           # email of the creating user (multi-tenant: members see only their own)
    owner_github_username: str = ""  # SOF-3: owner's GitHub handle, if on file — invites them onto the repo


def _orchestration_preamble(stage_title: str, project_id: str, projects_dir: str, budget: float,
                            runtime: str = "claude") -> str:
    """The per-run VARIABLE context block. ALL instructions live in the stage's SKILL.md (the
    agent's contract, loaded from its cwd); this supplies ONLY the run-specific data SKILL.md
    references — no instructions. Kept per-runtime signature for callers; runtime doesn't change
    the variables (the claude/opencode work-model is stated in the SKILL.md variant)."""
    return (
        f"software-factory {stage_title}. Run this fully autonomously per SKILL.md (your cwd).\n"
        f"THIS RUN:\n"
        f"  project_id   = {project_id}\n"
        f"  projects_dir = {projects_dir}\n"
        f"  run base     = {os.path.join(projects_dir, project_id)}  (your cwd is its workspace/; prior-stage artifacts in context/)\n"
        f"  budget       = ${budget:.0f} (HARD cutoff)\n"
        f"  db-verb call = python3 -m software_factory.db <verb> {projects_dir} {project_id} ...\n"
    )


def make_prompt_stage1(req: ProjectRequest, project_id: str, projects_dir: str, runtime: str = "claude",
                       brief_block: str = "") -> str:
    ctx = f"\n\nContext / detailed input:\n{req.context}" if req.context else ""
    # The concierge-authored product brief is the richest context — inject it directly so the
    # council seats plan from it; the full markdown is also at input/brief.md and the transcript
    # at input/interview.md.
    brief = (f"\n\nThe user was interviewed; the product brief follows (also at input/brief.md; "
             f"full transcript at input/interview.md). Treat it as authoritative project context:\n"
             f"{brief_block.strip()}") if brief_block.strip() else ""
    return (
        _orchestration_preamble("Stage 1 — Research", project_id, projects_dir, req.budget, runtime)
        + f"  app          = {req.description}{ctx}{brief}"
    )


def make_prompt_stage2(req: ProjectRequest, project_id: str, projects_dir: str, runtime: str = "claude") -> str:
    return (
        _orchestration_preamble("Stage 2 — Design & Plan", project_id, projects_dir, req.budget, runtime)
        + f"  app          = {req.description}"
    )


def _disposition_guidance(dispositions: dict | None) -> str:
    """The per-run VARIABLE lists of which tokens fall in each disposition. What MOCK/DEPLOY-DB/MCP
    MEAN (and how to satisfy each) is instruction — it lives in SKILL.md Phase 1. This supplies only
    the token names for THIS run."""
    disp = dispositions or {}
    # Legacy 'env' (pre-removal runs) degrades to mock: a built app NEVER inherits the
    # runner's own keys (operator security rule).
    mock = sorted(n for n, d in disp.items() if d in ("mock", "env"))
    mcp = sorted(n for n, d in disp.items() if d == "mcp")
    dbtok = sorted(n for n, d in disp.items() if d == "deploy-db")
    if not disp:
        return ""
    return (
        f"  dispositions (see SKILL.md Phase 1 for what each means):\n"
        f"    MOCK     = {', '.join(mock) or 'none'}\n"
        f"    DEPLOY-DB= {', '.join(dbtok) or 'none'}\n"
        f"    SELF/MCP = {', '.join(mcp) or 'none'}\n"
    )


def make_prompt_stage3(req: ProjectRequest, project_id: str, projects_dir: str, dispositions: dict | None = None,
                       runtime: str = "claude") -> str:
    return (
        _orchestration_preamble("Stage 3 — Build & Ship", project_id, projects_dir, req.budget, runtime)
        + f"  deploy target= {req.target}  (own service sf-{project_id}[-<app>]; deploy per SKILL.md)\n"
        + _disposition_guidance(dispositions)
        + f"  app          = {req.description}"
    )


def _make_drop_privileges(uid: int, gid: int):
    """Return a preexec_fn that drops from root to (uid, gid) in the child process."""
    import os as _os
    def _drop():
        _os.setgid(gid)
        _os.setuid(uid)
    return _drop


def _proc_state(pid: int) -> str | None:
    """The process-state char from /proc/{pid}/stat ('Z' = zombie/defunct), or None if the pid
    doesn't exist at all (already fully reaped by something else). An independent, OS-level
    signal — #129: a tracked Popen handle's own .poll() was observed to persistently report
    "not exited" for hours for a process `ps` showed as `<defunct>`, so it must never be the
    ONLY signal of whether a stage process is actually still alive."""
    try:
        with open(f"/proc/{pid}/stat", encoding="utf-8") as f:
            text = f.read()
    except OSError:
        return None
    # Format: "pid (comm) state ...". comm can itself contain spaces/parens, so split on the
    # LAST ')' rather than the first.
    after = text.rsplit(")", 1)[-1].split()
    return after[0] if after else None


def _default_launch(argv: list[str], env: dict, log_path: str | None = None, cwd: str | None = None) -> Any:
    """Launch a stage with stdout appended DIRECTLY to project.log — never through a pipe
    pumped by this server. A pump thread dies with the server, leaving the orchestrator
    writing into a readerless pipe: project.log freezes, the §4 brake goes spend-blind, and
    the child can wedge on the full pipe buffer (run-5b7aef7a live scar — the monolithic
    agent built for an hour with zero log visibility after a server restart). The child
    owning its own log fd survives any number of server deaths."""
    import subprocess

    # Claude Code refuses --dangerously-skip-permissions when run as root. When the factory
    # is running as root (Railway may start the container as root despite the Dockerfile USER
    # directive, or the entrypoint setpriv may not be available), drop the child process to the
    # unprivileged `node` user (uid/gid 1000 in node:20-bookworm) before exec. The parent
    # server process keeps its uid — only the spawned stage agent drops.
    preexec_fn = None
    if os.geteuid() == 0:
        import pwd as _pwd
        try:
            pw = _pwd.getpwnam("node")
            preexec_fn = _make_drop_privileges(pw.pw_uid, pw.pw_gid)
        except KeyError:
            pass  # node user absent (local dev); proceed as-is

    if log_path:
        with open(log_path, "ab") as logf:
            return subprocess.Popen(
                argv, env=_env.stage_env_baseline(env), cwd=cwd,
                stdout=logf, stderr=subprocess.STDOUT,
                preexec_fn=preexec_fn,
            )
    return subprocess.Popen(
        argv, env=_env.stage_env_baseline(env), cwd=cwd,
        stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT,
        preexec_fn=preexec_fn,
    )


class Console:
    def __init__(
        self,
        projects_dir: str,
        launch: Callable[..., Any] = _default_launch,
        new_id: Callable[[], str] = lambda: "project-" + uuid.uuid4().hex[:16],
        extract: Callable[[str], str] = extract_to_markdown,
    ):
        self._projects_dir = projects_dir
        self._launch = launch
        self._new_id = new_id
        self._extract = extract
        self._intake = ProjectIntake(
            projects_dir,
            new_id=new_id,
            extract=extract,
            skill_version=SKILL_VERSION,
        )
        self._procs: dict = {}   # project_id -> last launched stage process (SPEC §1 handoff guard)
        # project_id -> ((mtime_ns, size), cost): the full-log cost reparse on EVERY status/poll
        # was the console's dominant CPU+IO — two pollers × every run × multi-MB stream logs.
        self._cost_cache: dict = {}
        os.makedirs(projects_dir, exist_ok=True)

    def _paths(self, project_id: str) -> dict:
        return project_paths(self._projects_dir, project_id)

    @property
    def intake(self) -> ProjectIntake:
        """Project onboarding owner composed with this execution facade."""
        return self._intake

    # ---- SPEC §1: stage process lifecycle ------------------------------------------------
    def _stage_process_alive(self, project_id: str) -> bool:
        p = self._procs.get(project_id)
        if p is not None and hasattr(p, "poll") and p.poll() is None and not self._reap_if_os_zombie(p):
            return True   # authoritative live handle in THIS process (fast path, no DB read)
        # SOF-161: no live in-process handle — either the tracked process exited, or this is a fresh
        # console after a restart (self._procs is wiped). Fall back to the DURABLE, self-healing
        # persisted claim so a genuinely-live orphaned orchestrator (surviving a restart, or launched
        # by the un-guarded _provision_and_launch caller) is still refused a second launch.
        return self._launch_token_alive(self._load_state(project_id))

    def _launch_token_alive(self, state: ProjectState) -> bool:
        """SOF-161: True iff this run's persisted launch claim is held by a genuinely-live
        orchestrator. Self-healing: a pid that is gone or a zombie, or a REUSED pid now belonging to
        an unrelated process, reads as NOT alive — so a fresh console clears a stale lock instead of
        blocking forever (today's post-restart bug) or trusting it forever (the naive fix). The
        pid-reuse guard anchors via /proc/<pid>/cwd: every stage launches with cwd = the run's
        workspace (<projects_dir>/<project_id>/workspace), so a live claimant's cwd still contains
        the project_id — even after the workspace dir is deleted (the readlink keeps the id)."""
        pid = getattr(state, "launch_run_pid", 0) or 0
        if not getattr(state, "launch_run_token", "") or pid <= 0:
            return False
        if _proc_state(pid) in (None, "Z"):
            return False   # dead / zombie → stale claim, self-heal
        try:
            cwd = os.readlink(f"/proc/{pid}/cwd")
        except OSError:
            return False   # can't read cwd (pid gone / no perm) → not a live claim we can trust
        return state.project_id in cwd   # a reused pid on an unrelated process fails this anchor

    @staticmethod
    def _reap_if_os_zombie(p) -> bool:
        """#129: `p.poll()` was observed to persistently report "not exited" for HOURS for a
        process `ps` independently showed as `<defunct>` — a stuck/stale Popen handle must never
        be the ONLY signal. Cross-checks the OS-level state via /proc directly; if it says the
        pid is a zombie ('Z') or already fully gone (None), reaps it via the real `Popen.wait()`
        (not a raw os.waitpid — keeps this SAME object's internal bookkeeping consistent so every
        future .poll()/.wait() caller on it agrees) and returns True. Returns False (no-op) for a
        genuinely still-running process."""
        pid = getattr(p, "pid", None)
        if pid is None or _proc_state(pid) not in ("Z", None):
            return False
        try:
            p.wait(timeout=1)
        except Exception:
            pass
        return True

    def stage_finished(self, project_id: str) -> bool:
        """SPEC §1: the stage's orchestrator process has finished — the tracked process exited,
        or (no usable handle, e.g. after a server restart) the project.log has been idle past a
        2-minute grace (covers crash/OOM without wedging the run).

        Opencode-runtime exception: a LIVE handle is not proof of life — opencode processes
        LINGER after their session completes (run-45b8c4d5 wedged with a working app, a cleanly
        ended session, and a zombie proc blocking auto-resume). When the log's LAST event is the
        session-terminal `step_finish reason=stop` AND the log has been idle past a 5-minute
        grace, the stage is finished regardless of the handle. Claude stages are exempt: their
        long quiet tool calls (health-waits, builds) must never false-finish into a concurrent
        relaunch (the §1 double-orchestrator race)."""
        log = os.path.join(self._paths(project_id)["base"], "project.log")
        p = self._procs.get(project_id)
        if p is not None and hasattr(p, "poll"):
            if p.poll() is not None:
                return True
            if self._reap_if_os_zombie(p):
                return True
            if (self._load_state(project_id).runtime == "opencode"
                    and os.path.exists(log)
                    and (time.time() - os.path.getmtime(log)) > 300
                    and self._log_session_completed(log)):
                return True
            return False
        if not os.path.exists(log):
            return True
        # No handle (server restart / port eviction). Opencode processes LINGER after a COMPLETED
        # session (zombie proc), so a still-alive stage pid is NOT proof of work: when the log's last
        # event is the session-terminal step_finish AND it's idle past the 5-min grace, the stage is
        # FINISHED — let the poller advance Stage2→3 even though the lingering pid is alive. Inverse of
        # the live-pid-over-idle-log guard below (a finished-session signal wins over a live pid).
        # Mirrors the live-handle opencode exception above for the post-restart no-handle path.
        if (self._load_state(project_id).runtime == "opencode"
                and (time.time() - os.path.getmtime(log)) > 300
                and self._log_session_completed(log)):
            return True
        # A live stage3.pid is proof of life — the swarm driver can sit quiet in project.log for >2min
        # mid-Kimi-turn, and treating that as finished relaunched a second orchestrator on run-5b7aef7a
        # (§1 race). Claude has no session-complete signal, so it stays gated here.
        if self._stage_pid_alive(project_id):
            return False
        return (time.time() - os.path.getmtime(log)) > 120

    def _stage_pid_alive(self, project_id: str) -> bool:
        """True iff the run's stage3.pid names a live process whose cmdline mentions this
        run (pid-recycling guard). The pid survives the driver's exec into the agent, so
        one file covers the whole stage."""
        pid_path = os.path.join(self._paths(project_id)["base"], "stage3.pid")
        try:
            with open(pid_path, encoding="utf-8") as f:
                pid = int(f.read().strip())
            with open(f"/proc/{pid}/cmdline", "rb") as f:
                return project_id.encode() in f.read()
        except (OSError, ValueError):
            return False

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

    @staticmethod
    def _claude_session_completed(log_path: str) -> bool:
        """True when the claude stream-json log's last parseable session event is the
        session-terminal `result` event — the orchestrator declared ITSELF done (streamlog
        treats `result.total_cost_usd` as the authoritative session end). Claude's analog of
        opencode's step_finish=stop. Used ONLY by reap_completed_zombie: it means the agent
        said it finished, so reaping a still-alive handle cannot race an actively-orchestrating
        claude (the §1 double-orchestrator guard) — it only ever reaps a declared-done zombie."""
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
            if ev.get("type") in ("system", "user", "assistant", "result"):
                last = ev
        return bool(last) and last.get("type") == "result"

    # ---- SPEC §1: host-derived phase state machine ----------------------------------------
    _CLOSED = ("done", "passed", "completed")

    def derive_phases(self, project_id: str) -> dict:
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
        db = ProjectStore(self._paths(project_id)["db"])
        state = self._load_state(project_id)
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
            closed.update(STAGE_1)
        if state.stage2_done:
            closed.update(STAGE_2)
        if any((a.get("kind") or "").lower() == "deploy" for a in db.artifacts()):
            closed.add("deploy")
        if db.has_passing_verification():
            closed.add("test")
        recorded = db.phase_status()
        closed.update(n for n in PIPELINE if recorded.get(n) in self._CLOSED)

        activity = set(last_ts) | closed
        project_done = state.phase == "done"
        idx = {n: i for i, n in enumerate(PIPELINE)}
        furthest = max((idx[n] for n in activity), default=-1)
        active = None
        if not project_done:
            open_with_ts = {n: t for n, t in last_ts.items() if n not in closed}
            if open_with_ts:
                active = max(open_with_ts, key=open_with_ts.get)
        out = {}
        for i, n in enumerate(PIPELINE):
            if n == active:
                out[n] = "active"
            elif n in closed or (project_done and n in activity):
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

    def current_phase(self, project_id: str) -> str:
        """The derived current phase for the header/API. `ProjectState.phase` is authoritative for
        every NON-pipeline state (done/stopped/draft/paused/crashed — set directly by an operator
        action or a terminal gate, never written into the phases canvas table); for everything else
        (an in-progress pipeline run) the phases canvas table's recorded node history is the source
        of truth instead, since that scalar is never advanced node-by-node (see #326/#329/#332/#333
        — the recurring bug is trusting the scalar for a pipeline-progress state, or not trusting it
        for a non-pipeline one)."""
        state = self._load_state(project_id)
        if state.phase in ("done", "stopped", "draft", "paused", "crashed"):
            # SOF-149: "crashed"/"paused" must ALSO be trusted directly — found live re-verifying
            # #332's relaunch fix: crashed_at_node was correctly set, but the DISPLAYED phase still
            # showed the phases-canvas table's stale last entry (e.g. "provision"), because this
            # trusted-scalar check didn't include "crashed" yet. The frontend's RecoveryBar gates
            # strictly on the STRING "paused"/"crashed" (FactoryConsole.tsx's `halted` check) — so
            # a correct crashed_at_node with a wrong displayed phase means the RecoveryBar never
            # renders at all, even though the underlying recovery state is fully correct. "paused"
            # has the identical exposure (nothing ever writes "paused" into the phases table
            # either) — fixed alongside rather than leaving the same class of bug half-closed.
            # SOF-98: "draft" must be trusted directly, same as "done"/"stopped" — otherwise a
            # promote_draft that failed and restored phase="draft" still reports the phases
            # canvas table's leftover history (e.g. "provision") from the failed attempt, since
            # that append-only table is never cleaned up. Before this fix, a failed promote never
            # RETURNED to "draft" at all, so this scenario couldn't previously occur — discovered
            # live while verifying #326/#327 (is_draft()/the router's retry gate were correctly
            # restored, but the status API's displayed phase still showed "provision").
            return state.phase
        db = ProjectStore(self._paths(project_id)["db"])
        recorded = db.phase_status()
        implied = set()
        if state.stage2_done:
            implied.add("tickets")
        elif state.stage1_done:
            implied.add("product")
        idx = {n: i for i, n in enumerate(PIPELINE)}
        active = [n for n in PIPELINE if n in recorded] + [n for n in implied]
        if not active:
            return state.phase
        return max(active, key=lambda n: idx[n])

    def _terminal(self, state) -> bool:
        return state.phase in ("done", "stopped")

    def maybe_autosatisfy_deps(self, project_id: str) -> bool:
        """SPEC §3: if NO required token classifies as 'provide' (human secret), auto-satisfy
        deps (mock/mcp defaults apply) so the deps gate never becomes a hidden manual pause.
        Returns True iff deps are satisfied after the call."""
        state = self._load_state(project_id)
        if self._terminal(state) or not state.stage2_done:
            return False
        if state.deps_satisfied:
            return True
        disp = deps_mod.default_dispositions(state.deps_required)
        disp.update(state.deps_disposition or {})
        if any(d == "provide" for d in disp.values()):
            return False
        return bool(self.submit_deps(project_id, {}).get("satisfied"))

    def _load_state(self, project_id: str) -> ProjectState:
        return ProjectState.load(project_id, ProjectStore(self._paths(project_id)["db"]))

    def _load_states(self, project_ids: list[str]) -> dict[str, ProjectState]:
        """Batch-load ProjectState objects for many runs in one DB round-trip.

        Runs with no projectstate row get a default state, matching the behaviour of
        ``ProjectState.load(..., empty data)``.
        """
        out: dict[str, ProjectState] = {}
        if not project_ids:
            return out
        exec_ = PathExec(self._projects_dir)
        try:
            rows = ProjectStateRepository.batch_by_projects(exec_, project_ids)
        finally:
            exec_.close()
        for row in rows:
            data = json.loads(row["data"])
            data["name"] = row["name"]
            data["summary"] = row["summary"]
            out[row["project_id"]] = ProjectState.from_data(row["project_id"], data)
        # Legacy / registry-only edge cases: produce default states without persisting.
        for pid in project_ids:
            if pid not in out:
                out[pid] = ProjectState(pid, _store=None)
        return out

    def _phase_statuses(self, project_ids: list[str]) -> dict[str, dict[str, str]]:
        """Latest phase name -> status for each of the given projects (one batch query)."""
        out = {pid: {} for pid in project_ids}
        if not project_ids:
            return out
        exec_ = PathExec(self._projects_dir)
        try:
            rows = PhaseRepository.batch_statuses(exec_, project_ids)
        finally:
            exec_.close()
        for row in rows:
            out[row["project_id"]][row["name"]] = row["status"]
        return out

    def _blockers_by_project(self, project_ids: list[str]) -> dict[str, list[dict]]:
        """Return blockers grouped by project_id without N+1 DB calls."""
        out = {pid: [] for pid in project_ids}
        if not project_ids:
            return out
        exec_ = PathExec(self._projects_dir)
        try:
            rows = BlockerRepository.batch_by_projects(exec_, project_ids)
        finally:
            exec_.close()
        for row in rows:
            out[row["project_id"]].append(
                {"blocks": row.get("blocks"), "cleared": row["cleared"]}
            )
        return out

    def _agent_roles_by_project(self, project_ids: list[str]) -> dict[str, list[str]]:
        """Distinct agent roles per project, preserving first-seen order, batched."""
        out = {pid: [] for pid in project_ids}
        if not project_ids:
            return out
        exec_ = PathExec(self._projects_dir)
        try:
            rows = AgentRepository(exec_).batch_roles(project_ids)
        finally:
            exec_.close()
        seen = {pid: set() for pid in project_ids}
        for row in rows:
            pid, role = row["project_id"], row.get("role")
            if role and role not in seen[pid]:
                seen[pid].add(role)
                out[pid].append(role)
        return out

    def _current_phase_from_state(self, state: ProjectState, phase_status: dict[str, str]) -> str:
        """Compute the live phase for the dashboard without an extra DB call."""
        if state.phase in ("done", "stopped"):
            return state.phase
        recorded = phase_status
        implied: set[str] = set()
        if state.stage2_done:
            implied.add("tickets")
        elif state.stage1_done:
            implied.add("product")
        idx = {n: i for i, n in enumerate(PIPELINE)}
        active = [n for n in PIPELINE if n in recorded] + [n for n in implied]
        if not active:
            return state.phase
        return max(active, key=lambda n: idx[n])

    def _run_spend(self, project_id: str, state=None) -> float:
        """SOF-186: THIS run's monotonic spend basis, EXCLUDING console-side ingestion. It is the
        banked cost of all superseded stage attempts (prior_attempts_usd) PLUS the current attempt's
        live log cost (project.log from spend_seal_offset onward), floored by the persisted
        high-water spent_usd. Monotonic across a stage auto-resume/retry: retry_stage banks the dead
        attempt into prior_attempts_usd and reseals, so the relaunched attempt ADDS on top instead of
        the live parse silently dropping the dead attempt (the $20.07->$14.13 regression).

        SOF-215: the persisted floor is raised using ONLY the authoritative half of the current
        attempt's cost (completed sessions' real `result.total_cost_usd`/opencode step costs) —
        NEVER a still-in-flight session's token estimate. An estimate can substantially overshoot
        what that session's eventual authoritative total turns out to be (observed live: a stage-2
        session's in-flight estimate read $22.77 against its own final, authoritative $7.12). Once
        an inflated estimate got locked into "spend only ever goes up," an entire later stage's
        real cost (~$8, stage 3) became invisible — never displayed, never re-persisted — because
        it never organically exceeded the false ceiling. The RETURNED value still includes the
        fuller estimate-inclusive total (budget enforcement must see a still-growing in-flight cost
        in real time, not wait for a session's terminal result) — only the PERSISTED floor is
        estimate-immune. Despite the name (kept for the docstring history above), this is the one
        place that owns floor persistence: every direct `state.spent_usd = self._run_spend(...)`
        call site relies on this write happening here."""
        state = state or self._load_state(project_id)
        prior = state.prior_attempts_usd or 0.0
        authoritative, estimate = self._attempt_cost_components(project_id, state)
        authoritative_total = prior + authoritative
        if authoritative_total > (state.spent_usd or 0.0):
            state.spent_usd = authoritative_total
            state.save()
        return max(prior + authoritative + estimate, state.spent_usd or 0.0)

    def _project_spend(self, project_id: str) -> float:
        """THIS run's own spend (the per-project budget basis). Prior runs/projects do NOT count —
        each run/project is independently capped. The run spend (SOF-186 monotonic accumulator, see
        _run_spend) PLUS console-side ingestion spend (SOF-27) — a separate accumulator, since
        ingestion never runs as a stage process and so never appears in project.log."""
        state = self._load_state(project_id)
        return self._run_spend(project_id, state) + (state.ingestion_spent_usd or 0.0)

    def _budget_ceiling(self, project_id: str) -> float:
        """SPEC §4: per-project ceiling — the run's own override, else SF_COST_CEILING (default 30)."""
        state = self._load_state(project_id)
        if state.budget_ceiling:
            return float(state.budget_ceiling)
        return float(os.environ.get("SF_COST_CEILING", "30") or 30)

    def _kill_stage_process(self, project_id: str) -> bool:
        """Terminate this run's live stage process: SIGTERM → 5s grace → SIGKILL. opencode processes
        SURVIVE a plain SIGTERM (confirmed in prod — serve ignored SIGTERM and even pkill), so escalate
        to SIGKILL if still alive. Returns True iff a live process was killed. Only reaches THIS
        instance's tracked process (self._procs); a process orphaned by a console restart has no handle
        here (phase=stopped still halts its re-advance, it just can't be signalled)."""
        p = self._procs.get(project_id)
        if p is not None and hasattr(p, "poll") and p.poll() is None and hasattr(p, "terminate"):
            p.terminate()
            if hasattr(p, "wait") and hasattr(p, "kill"):
                try:
                    p.wait(timeout=5)
                except Exception:
                    p.kill()
            return True
        return False

    def reap_completed_zombie(self, project_id: str) -> int | None:
        """SPEC §1 zombie reap (#104): a claude orchestrator that emitted its session-terminal
        `result` event but whose process is STILL ALIVE — i.e. it SAID it's done and then hung at
        teardown (observed as a remote-MCP connection-close hang after #100 wired the exa MCP into
        every stage). A live handle is normally proof of work, so `stage_finished` stays False
        forever and the run never advances past 'research' despite a complete PRD on disk.

        When THIS run's tracked handle is live, the runtime is claude, the log's terminal event is
        `result` (the agent declared itself done), and it's been idle past a short grace measured
        from the log mtime (the `result` line is the last write), SIGTERM→SIGKILL it via
        `_kill_stage_process`. That converts the zombie to the exited state the EXISTING
        completed-detection in `stage_finished` already advances on — no relaunch.

        Because it fires ONLY after the orchestrator's own terminal `result`, it can never reap an
        actively-orchestrating claude — it does NOT race the §1 double-orchestrator guard, it
        completes it for the hung-teardown case. Keyed strictly off THIS run's handle + THIS run's
        project.log (never a global signal), so a healthy concurrent stage is untouched. Systemic by
        design: it reaps ANY hung remote-MCP teardown, not just exa. Returns the reaped pid, else None.

        #105 root-fix note: Claude Code CLI has no config for lazy MCP connection or a teardown
        timeout (confirmed against upstream — anthropics/claude-code#31198 open/unimplemented for
        lazy-connect; #1935/#41024 for the unbounded teardown hang itself); it eagerly connects every
        configured server every session and there's nothing we can set to bound its exit-time
        teardown. So the grace window below isn't "wait for a slow-but-working teardown" — observed
        teardown hangs never resolve on their own — it exists only so a process that DOES exit
        cleanly within grace isn't needlessly SIGTERM'd. Keep it just above one poller tick (3s, see
        console/poller.py), not the original 60s, since every extra second here is pure stall on
        every claude+exa stage."""
        p = self._procs.get(project_id)
        if not (p is not None and hasattr(p, "poll") and p.poll() is None):
            return None   # no live tracked handle → the no-handle idle-advance path already covers it
        if self._load_state(project_id).runtime == "opencode":
            return None   # opencode's linger is handled by the step_finish=stop path in stage_finished
        log = os.path.join(self._paths(project_id)["base"], "project.log")
        if not os.path.exists(log) or not self._claude_session_completed(log):
            return None   # not done yet — an actively-orchestrating claude, leave it alone
        grace = float(os.environ.get("SF_STAGE_REAP_GRACE_SEC", "5") or 5)
        if (time.time() - os.path.getmtime(log)) <= grace:
            return None   # within grace — give a clean teardown a chance to exit on its own first
        pid = getattr(p, "pid", None)
        if self._kill_stage_process(project_id):
            logger.info("[stage-reap] %s: reaped completed-but-hung claude process %s "
                        "(%.0fs after terminal result event) — stage will now self-advance",
                        project_id, pid, grace)
            return pid
        return None

    def stop_project(self, project_id: str) -> dict:
        """Operator 'stop all progress': kill any live stage process + set phase=stopped (TERMINAL —
        the poller won't re-advance, relaunch, or re-enter deploy-db provision; a stopped run stays
        stopped, NOT budget-paused) + finalize orphaned agents so the canvas shows no ghost-running
        agents. Idempotent: a second call re-kills (no-op) and leaves the stopped state untouched."""
        killed = self._kill_stage_process(project_id)
        state = self._load_state(project_id)
        if state.phase != "stopped":
            state.phase = "stopped"
            state.spent_usd = self._run_spend(project_id, state)
            self._upload_project_log(project_id, state)
            state.save()
            AgentRegistry(self._paths(project_id)["agents_db"]).finalize_orphans(project_id, stage_ok=False)
        return {"project_id": project_id, "phase": "stopped", "killed": killed}

    def enforce_budget(self, project_id: str) -> bool:
        """SPEC §4 mid-stage teeth: if this run's spend crossed its ceiling, terminate the live
        stage process, record a recoverable 'budget' blocker, and finalize orphaned agents.
        Returns True iff the run was (or already had been) stopped for budget this call."""
        ceiling = self._budget_ceiling(project_id)
        spend = self._project_spend(project_id)
        if spend <= ceiling:
            return False
        self._kill_stage_process(project_id)
        db = ProjectStore(self._paths(project_id)["db"])
        already = any(b.get("blocks") == "budget" and not b["cleared"] for b in db.blockers())
        if not already:
            db.add_blocker(
                f"Budget cap ${ceiling:.2f} reached (spent ${spend:.2f}) — stage stopped. "
                f"Raise the cap to continue.", blocks="budget")
            AgentRegistry(self._paths(project_id)["agents_db"]).finalize_orphans(project_id, stage_ok=False)
        return True   # over-ceiling: stopped now (killed) or already stopped

    def auto_resume_dead_stage(self, project_id: str) -> bool:
        """SPEC §3 zero-touch: a stage whose process died without passing its gate (OOM/crash)
        is resumed by the HOST — a human noticing the stall is an intervention. Never fires at
        the deps gate (stage complete, waiting by design) or on a budget stop (operator's call).
        Never resurrects a GHOST: a project store with no recorded artifacts (e.g. created by a mere
        status query after state loss) has no brief to build from — resuming it burns spend on
        an empty prompt (the run-b594a5f4/run-0eb69fdd double-ghost scar).

        NEVER-ARMED GUARD (SOF-23): a project row seeded directly for a test/verify fixture (not
        via create_draft, which the poller already ignores) can still pass the GHOST check above
        if the seed also records an artifact — it then looks identical to a stage that "died
        without passing its gate", because a project.log that was never created reads the same
        as one that existed and finished (see stage_finished). Require independent proof this
        project's CURRENT stage was actually launched at least once: either state.launch_attempted
        (set unconditionally on every real _launch_stage call, even a refused one) or an existing
        project.log on disk (covers every real run launched before this guard shipped). Neither
        signal is ever true for a bare seeded row, since it never goes through _launch_stage.

        STAGE-3 GATE: a passing Playwright verification alone does NOT prove the stage is over;
        the real indicator is the health of the Claude Code process. The state machine mirrors
        Stages 1/2: detect_stage3_done only flips done once stage_finished() reports the process
        has exited, AND the QA loop is fully closed. auto_resume_dead_stage simply resumes a
        dead Stage-3 process unless the run is already done. (Pairs with #111: resume resets
        in-flight tickets so the swarm continues, not rebuilds.)

        CRASH/PAUSE RECONCILIATION: this method relaunches within the poller's _AUTO_RESUME_MAX
        cap (transient crashes self-heal). Runs already in 'paused' or 'crashed' (operator-
        controlled or already-exhausted) are skipped. When the poller exhausts its retry count
        it calls mark_stage_crashed() to land the run in a resumable 'crashed' state for the
        Recovery bar."""
        if not self.is_pipeline_project(project_id):
            return False
        state = self._load_state(project_id)
        log_path = os.path.join(self._paths(project_id)["base"], "project.log")
        if not (state.launch_attempted or os.path.exists(log_path)):
            return False   # never armed — nothing to resume (SOF-23)
        if state.phase in ("done", "stopped", "paused", "crashed") or not self.stage_finished(project_id):
            return False   # terminal or operator-controlled — never auto-resume
        stage = state.stage
        # SOF-116: verify complete BEFORE relaunching — a dead process is not proof of incomplete
        # work. Stage 3 in particular can finish (tickets approved, app deployed and tested) and
        # still look "dead" to this function if the specific record-verification call never landed;
        # re-check the real DB-backed completion gate first so a truly-finished run is never
        # relaunched just because its process exited.
        if stage == 3 and self.detect_stage3_done(project_id):
            return False   # already done — detect_stage3_done just persisted deploy_url + phase
        db = ProjectStore(self._paths(project_id)["db"])
        # SOF-116: LAYERING — this check runs BEFORE the persisted auto_resume_count cap below.
        # Two independent money-protections live in this function; budget wins. Once spend+reserve
        # exceeds the ceiling, every tick returns False here regardless of auto_resume_count, so the
        # cap can freeze mid-count (e.g. at 1/6) without ever reaching mark_stage_crashed — that is
        # correct: a budget stop is a deliberate parked state ("operator resumes via /budget +
        # /retry"), not a crash to auto-heal from. Live-observed on staging (project-87603c93):
        # the counter froze at 1 across a second container restart because this check started
        # firing, not because the cap logic broke.
        if any(b.get("blocks") == "budget" and not b["cleared"] for b in db.blockers()):
            return False   # budget stop is intentional — operator resumes via /budget + /retry
        # SOF-148: a rejected/missing credential (GH_TOKEN invalid, etc.) is unrecoverable by
        # retrying — the stage-1 SKILL.md tags this exact failure `blocks="credential"` and halts
        # its own turn immediately, but that alone can't stop THIS function from blindly relaunching
        # the same doomed attempt up to SF_AUTO_RESUME_MAX more times (the actual retry-burn SOF-148
        # measured: ~$6.25 across repeat stage-1 launches, each failing the same gh-auth check).
        # Same shape as the budget check above: a credential stop is a parked state an operator
        # resolves by provisioning the real credential and retrying, not a crash to auto-heal from.
        if any(b.get("blocks") == "credential" and not b["cleared"] for b in db.blockers()):
            return False   # credential/config stop is unrecoverable by retry — needs an operator fix
        incomplete = (
            (stage == 1 and not state.stage1_done)
            or (stage == 2 and not state.stage2_done)
            or stage == 3
        )
        if not incomplete:
            return False
        # SOF-116: persisted hard cap — money/lifecycle machinery, not agent judgment. Unlike the
        # old in-process retry counter, this survives a console restart, so repeated redeploys
        # can't each hand out a fresh set of "free" auto-resumes and retry forever.
        max_resumes = int(os.environ.get("SF_AUTO_RESUME_MAX", "2") or 2)
        if state.auto_resume_count >= max_resumes:
            return False   # cap exhausted — poller lands this in 'crashed' for operator recovery
        if stage == 3:
            self._reset_stuck_tickets(project_id)
        state.auto_resume_count += 1
        state.save()
        logger.info("[auto-resume] %s relaunching dead stage %s (attempt %d/%d)",
                    project_id, stage, state.auto_resume_count, max_resumes)
        return self.retry_stage(project_id, stage) is not None

    def mark_stage_crashed(self, project_id: str) -> bool:
        """Called by the poller after _AUTO_RESUME_MAX auto-resume attempts are exhausted.
        If the stage is still dead+incomplete, marks phase='crashed' so the Recovery bar
        shows the operator a resumable crashed state. Returns True if marked, False if
        the run is terminal or already recovered (no-op)."""
        if not self.is_pipeline_project(project_id):
            return False
        state = self._load_state(project_id)
        if state.phase in ("done", "stopped", "paused", "crashed"):
            return False   # already terminal or operator-controlled
        if not self.stage_finished(project_id):
            return False   # stage is still alive — don't mark crashed prematurely
        stage = state.stage
        # SOF-116: never crash a run that actually finished (see auto_resume_dead_stage) — the
        # narrow window between this tick's auto-resume check and this call is enough for the
        # agent's own verification write to land.
        if stage == 3 and self.detect_stage3_done(project_id):
            return False
        db = ProjectStore(self._paths(project_id)["db"])
        incomplete = (
            (stage == 1 and not state.stage1_done)
            or (stage == 2 and not state.stage2_done)
            or stage == 3
        )
        if not incomplete:
            return False
        # SOF-116: the honest signal, not the frozen one. state.phase is a scalar set once at
        # pipeline kickoff and never advanced through the per-node pipeline (see current_phase's
        # own docstring: "never the stale ProjectState value") — recording it here is exactly the
        # lying crashed_at_node the ticket reported (stuck at 'provision' while the app was live).
        state.crashed_at_node = self.current_phase(project_id)
        state.phase = "crashed"
        state.save()
        logger.warning("[crash] %s marked crashed at node %s (stage %s) — auto-resume exhausted",
                       project_id, state.crashed_at_node, stage)
        # SOF-165: ADDITIVELY record the unified tier-2 recovery action. phase='crashed' above stays
        # the Recovery-bar's driver (UX byte-identical); this only unifies the underlying record so
        # the benchmark autopsy path lands the same primitive. Best-effort — never breaks the crash mark.
        recovery.open_recovery_action(project_id, kind="dead_stage", cause=state.crashed_at_node,
                                     evidence={"stage": stage, "auto_resume_count": getattr(state, "auto_resume_count", 0)})
        return True

    def pause_project(self, project_id: str) -> dict:
        """Operator 'pause': kill the live stage process and set phase='paused'.
        Unlike 'stop', pause is RESUMABLE — the run stays active and the Recovery bar
        allows the operator to resume, retry a node, or rewind. Returns current state."""
        state = self._load_state(project_id)
        if state.phase in ("done", "stopped"):
            return {"project_id": project_id, "phase": state.phase, "paused": False,
                    "detail": "run is already terminal"}
        # SOF-116: the honest signal — state.phase never advances past the pipeline-kickoff value
        # it's set to once in promote_draft (see current_phase's docstring); recording it as the
        # pause point would be stale from the very first pause.
        node = self.current_phase(project_id)
        self._kill_stage_process(project_id)
        state = self._load_state(project_id)  # reload after kill (stop_project may have saved)
        if state.phase not in ("done", "stopped"):  # don't overwrite a concurrent terminal
            state.paused_at_node = node
            state.phase = "paused"
            state.save()
        return {"project_id": project_id, "phase": "paused", "paused_at_node": node, "paused": True}

    def resume_project(self, project_id: str) -> str | None:
        """Resume a paused or crashed run from where it left off.
        Determines the right stage from the recorded at-node and calls retry_stage.
        Clears the paused/crashed markers ONLY if retry_stage actually launches. Returns
        project_id or None."""
        state = self._load_state(project_id)
        original_phase = state.phase
        if original_phase not in ("paused", "crashed"):
            return None
        original_paused_at_node = state.paused_at_node
        original_crashed_at_node = state.crashed_at_node
        resume_node = state.paused_at_node or state.crashed_at_node or ""
        stage = state.stage
        if stage == 3:
            self._reset_stuck_tickets(project_id)
        state.paused_at_node = ""
        state.crashed_at_node = ""
        state.auto_resume_count = 0  # SOF-116: explicit operator recovery — a fresh cap
        state.phase = resume_node or "provision"
        state.save()

        def _restore_recovery_markers() -> None:
            # SOF-150: a resume attempt that itself fails (refused or raised) must not leave the
            # row worse off than before the attempt — restore exactly what was cleared above, not
            # try/finally (that would also fire on a genuine success and undo a legitimate resume).
            st = self._load_state(project_id)
            if st.phase not in ("done", "stopped"):  # don't clobber a concurrent terminal
                st.phase = original_phase
                st.paused_at_node = original_paused_at_node
                st.crashed_at_node = original_crashed_at_node
                st.save()

        try:
            result = self.retry_stage(project_id, stage)
        except Exception:
            _restore_recovery_markers()
            raise
        if result is None:
            _restore_recovery_markers()
        else:
            # SOF-165: a successful operator resume RESTORES the run — resolve its open recovery
            # action(s). Idempotent no-op if none were open (e.g. a paused run that never crashed).
            recovery.resolve_recovery_actions(project_id, resolution="restored")
        return result

    def resume_failure_reason(self, project_id: str) -> str | None:
        """SOF-150: the honest reason a resume attempt failed (the newest uncleared blocker's
        text — e.g. the budget-refusal message retry_stage's launch attempt recorded), for the
        router to surface instead of a generic 'not paused or crashed' when the row genuinely
        WAS paused/crashed and the retry itself is what failed. None if there's no blocker on
        file (a crash/refusal with no recorded reason — rare, but honestly reported as such)."""
        blockers = [b for b in ProjectStore(self._paths(project_id)["db"]).blockers() if not b["cleared"]]
        return blockers[-1]["what"] if blockers else None

    def retry_node(self, project_id: str, node: str) -> str | None:
        """Invalidate checkpoints at `node` and downstream, then resume the stage.
        Upstream checkpoints are preserved — the stage skips those nodes.
        Returns project_id or None."""
        deleted = ckpt.delete_from(project_id, node)
        state = self._load_state(project_id)
        if node in STAGE_1 or node == "stage:1":
            stage = 1
            state.stage1_done = False
            state.stage2_done = False
        elif node in STAGE_2 or node == "stage:2":
            stage = 2
            state.stage2_done = False
        else:
            stage = 3
        if stage == 3:
            self._reset_stuck_tickets(project_id)
        state.paused_at_node = ""
        state.crashed_at_node = ""
        state.auto_resume_count = 0  # SOF-116: explicit operator recovery — a fresh cap
        state.phase = node
        state.save()
        return self.retry_stage(project_id, stage)

    def rewind_to_node(self, project_id: str, node: str) -> dict:
        """Invalidate checkpoints at `node` and downstream, then set phase='paused'.
        Does NOT auto-resume — the operator decides when to resume via /resume."""
        self._kill_stage_process(project_id)
        deleted = ckpt.delete_from(project_id, node)
        state = self._load_state(project_id)
        if node in STAGE_1 or node == "stage:1":
            state.stage1_done = False
            state.stage2_done = False
        elif node in STAGE_2 or node == "stage:2":
            state.stage2_done = False
        state.paused_at_node = node
        state.phase = "paused"
        state.save()
        return {"project_id": project_id, "rewound_to": node,
                "deleted_checkpoints": deleted, "phase": "paused"}

    def _reset_stuck_tickets(self, project_id: str) -> None:
        """Reset 'in_progress' tickets to 'open' so a resumed swarm re-dispatches them."""
        ts = TicketStore(self._paths(project_id)["db"])
        ts.reset_in_progress_tickets()

    def reclaim_orphaned_tickets(self, project_id: str) -> list[int]:
        """SOF-163: `_reset_stuck_tickets` above is a BLANKET reset, only invoked when the whole
        STAGE is judged dead (auto-resume/resume_project). This is the SELECTIVE counterpart —
        it catches a single ticket orphaned while the stage is still alive and everything else is
        progressing fine (confirmed in real prod history: a ticket left `in_progress` for 32+
        hours after its own agent had already failed, with the rest of the project completing
        normally around it). Two independent, host-detectable signals, checked per ticket against
        its claimed agent's real AgentRegistry row (runtime-agnostic — both claude-native and
        opencode swarm write the same spawn-agent/finish-agent bookkeeping):

          (a) DETERMINISTIC — the agent row is already terminal (done/failed) but the ticket is
              still in_progress. The agent proved it will never call finish() again; no threshold
              needed, this is unconditionally a bug to fix.
          (b) HEURISTIC — the agent row is still `running` but started more than
              SF_TICKET_STALL_HOURS ago (default 6, matching run_autopsy's own TIMEOUT_HOURS).
              Deliberately generous: real build-phase turns have legitimately run up to ~12h in
              prod history, so this must sit comfortably above that to avoid false-positiving a
              merely-slow ticket.

        Neither case can literally interrupt a live sub-agent call (Task calls run inside the
        one tracked stage process; individual sub-agent execution is opaque to the host in both
        runtimes) — this reclaims the TICKET's state, not the process. Returns the list of ticket
        ids actually reclaimed this call; a ticket at its stall cap is left untouched here (see
        `TicketStore.reclaim_stalled`) for the caller to escalate via `add-blocker`.

        Once escalated, a ticket is SKIPPED on every later call while its blocker is uncleared —
        `add_blocker` has no dedup of its own, and this tick re-runs every ~5 minutes, so without
        this check an over-cap ticket (still in_progress, agent still terminal) would re-match
        forever and add a fresh blocker each time (~288/day). The uncleared blocker IS the
        "already escalated, waiting on an operator" signal; an operator clearing it (or the
        ticket transitioning away from in_progress some other way) is what re-arms this ticket."""
        ts = TicketStore(self._paths(project_id)["db"])
        registry = AgentRegistry(self._paths(project_id)["db"])
        db = ProjectStore(self._paths(project_id)["db"])
        stall_hours = float(os.environ.get("SF_TICKET_STALL_HOURS", "6") or 6)
        already_escalated = {
            b["what"].split(" ", 2)[1]  # "Ticket <id> stalled ..." -> "<id>"
            for b in db.blockers()
            if b.get("blocks") == "stall" and not b["cleared"] and b["what"].startswith("Ticket ")
        }
        reclaimed = []
        for t in ts.all_tickets():
            if t.status != "in_progress" or not t.agent:
                continue
            if str(t.id) in already_escalated:
                continue   # already escalated, waiting on an operator — don't re-process or re-block
            try:
                agent = registry.get(t.agent)
            except KeyError:
                continue   # no matching agent row to correlate against — leave it alone
            if agent.status in ("done", "failed"):
                reason = f"agent `{t.agent}` already finished ({agent.status}) but this ticket was never reverted"
            elif agent.status == "running" and (time.time() - agent.started_at) > stall_hours * 3600:
                age_h = (time.time() - agent.started_at) / 3600
                reason = f"agent `{t.agent}` has been running {age_h:.1f}h (past the {stall_hours:g}h bound)"
            else:
                continue
            if ts.reclaim_stalled(t.id, reason):
                reclaimed.append(t.id)
                logger.info("[reclaim] %s ticket %s reclaimed to open: %s", project_id, t.id, reason)
            else:
                db.add_blocker(f"Ticket {t.id} stalled repeatedly ({reason}) — stall cap exceeded, "
                               "needs an operator", blocks="stall")
                logger.warning("[reclaim] %s ticket %s at stall cap, escalated via blocker", project_id, t.id)
        return reclaimed

    def raise_budget(self, project_id: str, ceiling: float) -> dict:
        """Persist a new per-project spend ceiling (raise or lower) and clear any budget blocker.
        Lowering is allowed — caller is responsible for policy checks if desired."""
        state = self._load_state(project_id)
        state.budget_ceiling = float(ceiling)
        state.save()
        db = ProjectStore(self._paths(project_id)["db"])
        for b in db.blockers():
            if b.get("blocks") == "budget" and not b["cleared"]:
                db.clear_blocker(b["what"])
        return {"project_id": project_id, "budget_ceiling": float(ceiling)}

    def _launch_stage(self, project_id: str, stage: int, prompt: str, env: dict) -> Any:
        """Prepare workspace, health-check MCP, and launch a claude -p process for a stage."""
        # §1 double-orchestrator guard: refuse if an orchestrator is already alive for this run.
        # start_stage2/3 and retry_stage check _stage_process_alive before calling here, but
        # _provision_and_launch does not — and even for the callers, there is a
        # TOCTOU window between their check and the _procs[project_id] write below. Checking here
        # closes both gaps: the un-guarded callers are covered and TOCTOU window shrinks to the
        # launch() call itself (a tight native Popen, not an LLM round-trip).
        if self._stage_process_alive(project_id):
            logger.debug("[launch] %s stage %s refused — orchestrator already alive", project_id, stage)
            return None

        paths = self._paths(project_id)

        # Mechanical PER-RUN cost ceiling: the in-prompt budget is advisory-only and stages don't
        # share a counter, so refuse to launch the next stage when THIS run's own spend (+ a stage
        # reserve) would cross the run's ceiling (per-project override else SF_COST_CEILING).
        ceiling = self._budget_ceiling(project_id)
        reserve = float(os.environ.get("SF_STAGE_RESERVE", "5") or 5)
        spend = self._project_spend(project_id)
        if spend + reserve > ceiling:
            logger.info("[launch] %s stage %s refused — per-run budget: $%.2f + reserve $%.2f > ceiling $%.2f",
                        project_id, stage, spend, reserve, ceiling)
            db = ProjectStore(paths["db"])
            already = any(b.get("blocks") == "budget" and not b["cleared"] for b in db.blockers())
            if not already:
                db.add_blocker(
                    f"Per-run budget: this run ${spend:.2f} + reserve ${reserve:.2f} "
                    f"> ceiling ${ceiling:.2f} — stage {stage} launch refused",
                    blocks="budget",
                )
            return None

        state = self._load_state(project_id)
        # SOF-23: stamp BEFORE the hard-gate MCP check below (which can still return None) — a
        # seeded test/verify row never reaches this line at all, so this is a reliable "the
        # pipeline actually attempted to launch this project" signal, unlike project.log (which
        # only proves a process actually spawned, not that a launch was attempted and refused).
        if not state.launch_attempted:
            state.launch_attempted = True
            state.save()
        vault_ids = getattr(state, "creds_vault_ids", {}) or {}
        if vault_ids:
            try:
                decrypted = _vault.vault_retrieve_many(vault_ids)
                env = {**decrypted, **env}  # vault base; caller env (extra_creds) wins
            except Exception:
                logger.debug("[launch] %s vault retrieve failed — caller env used as-is",
                             project_id, exc_info=True)  # Vault unavailable — best-effort
        # SOF-81: a key an operator attached to a `tools` row (OS Tools tab) for THIS stage
        # overrides the console's own env passthrough for that tool (e.g. a rotated EXA_API_KEY
        # or RAILWAY_TOKEN) — absent key, behavior is unchanged. Lower precedence than the run's
        # own BYOK creds above (`env` already wins on collision).
        env = {**tool_env_overrides(stage), **env}
        runtime = state.runtime or "claude"
        # The stage RUNNER (`claude -p` / `opencode run` / `codex exec`) is itself an LLM agent and needs its OWN
        # provider key to authenticate. stage_env_baseline scrubs the console's env down to a tiny
        # allowlist (so the BUILT APP can't inherit factory secrets) — which also strips the runner's
        # key, leaving Stage 1 unable to even start (claude -p dies at auth → no PRD → run parked at
        # 0%). Inject ONLY the active runtime's key into the runner env here. This reaches the
        # `claude -p`/`opencode` process; it does NOT reach the customer's deployed app, whose Railway
        # env is set explicitly by the Stage-3 agent (deps only) and never inherits this process env.
        # Resolution is PER-RUN, not platform-hardcoded: BYOK first (the run declared its own
        # provider key in req.credentials → already in `env`), else the platform key from the console
        # env ("use ours"). Don't overwrite a BYOK key with the platform one. (Stage-2/3 retry
        # re-injection of a BYOK value — not in os.environ — is a tracked follow-up.)
        _runner_key = _RUNNER_KEYS.get(runtime)
        if not _runner_key:
            ProjectStore(paths["db"]).add_blocker(
                f"Unsupported stage runtime '{runtime}' — choose Claude, OpenCode, or Codex.",
                blocks="runtime",
            )
            logger.warning("[launch] %s stage %s refused — unsupported runtime=%s",
                           project_id, stage, runtime)
            return None
        if not env.get(_runner_key) and os.environ.get(_runner_key):
            env = {**env, _runner_key: os.environ[_runner_key]}
        if not env.get(_runner_key):
            ProjectStore(paths["db"]).add_blocker(
                f"{_runner_key} is required for the {runtime} runtime. Attach a BYOK key or configure the platform key.",
                blocks="runtime",
            )
            logger.warning("[launch] %s stage %s refused — %s is missing", project_id, stage, _runner_key)
            return None
        # Project Memory MCP (SOF-41/T4.2): mint a fresh scope token for THIS project and point the
        # stage at the console's own memory endpoint. Per-run (unlike EXA_API_KEY, which is a
        # single factory-wide static key), so it's injected here rather than in
        # env._STAGE_ESSENTIAL. Always wired (SOF-71 — memory is core, not opt-in). Best-effort on
        # a missing SF_APP_URL — same tolerance as admin_service.py's access_resend, which
        # degrades rather than blocking a launch.
        from . import auth as _auth
        # SOF-155: derive the console's public base URL for the per-run proxy callbacks. SF_APP_URL
        # is an OPTIONAL override; fall back to Railway's always-auto-injected RAILWAY_PUBLIC_DOMAIN
        # (e.g. console.tenexity.ai) so this can't silently no-op from a forgotten env var — which
        # is exactly what left BOTH the memory MCP (SOF-41) and the research proxy unwired in every
        # environment (SF_APP_URL was set nowhere; the guard below was always false).
        _pub = os.environ.get("RAILWAY_PUBLIC_DOMAIN")
        base_url = (os.environ.get("SF_APP_URL")
                    or (f"https://{_pub}" if _pub else "")).rstrip("/")
        if base_url:
            env = {**env, "SF_MEMORY_TOKEN": _auth.sign_scope_token(project_id),
                  # SOF-157: FastMCP serves the streamable-HTTP handler at the sub-app's /mcp path,
                  # so the endpoint is /mcp/memory/mcp (the bare /mcp/memory 307-redirects then 404s).
                  "SF_MEMORY_MCP_URL": f"{base_url}/mcp/memory/mcp",
                  # SOF-155: in-stage Fusion research reaches the console proxy with a research-scoped,
                  # per-run token — OPENROUTER_API_KEY stays in the console, never the scrubbed build
                  # env. Distinct purpose from the memory token (can't cross to /mcp/memory).
                  "SF_RESEARCH_TOKEN": _auth.sign_scope_token(project_id, purpose="research"),
                  "SF_RESEARCH_URL": f"{base_url}/api/research/fusion"}
        else:
            logger.warning("[launch] %s no console base URL (SF_APP_URL and RAILWAY_PUBLIC_DOMAIN both "
                           "unset) — memory MCP + research proxy NOT wired for this stage", project_id)
        # Operator override: if staff edited THIS stage's prompt for THIS runtime in the OS Agents
        # dashboard, that stored text drives the run (written as ws/SKILL.md); else the on-disk
        # default. Per-runtime + best-effort — a store hiccup must never block a launch.
        # system_agents has ONE row per stage callsign (STAGE-1), no longer a per-runtime override
        # key (was STAGE-1::claude / STAGE-1::opencode) — the claude & opencode SKILL.md variants now
        # share the single stored prompt for this stage.
        override = None
        # SOF-73: PRODUCT (stage 1) / DESIGN (stage 2, Phase 2) — claude runtime only.
        # SOF-100: stage 2 ALSO materializes TICKETS (Phase 3) — two distinct claude-native
        # subagent slots now live in one stage, so this is a list, not a single (callsign, row).
        # SOF-119: stage 3 materializes REVIEW (Phase 3a) — the adversarial in-pipeline reviewer,
        # dispatched once per ticket-wave between the shared deploy+happy-flow gate and the
        # existing per-ticket QA loop.
        agent_rows: list = []
        try:
            from .system_agents import SystemAgentStore
            store = SystemAgentStore()
            row = store.get(f"STAGE-{stage}")
            override = row["prompt"] if row and (row.get("prompt") or "").strip() else None
            if runtime == "claude" and stage in (1, 2, 3):
                callsigns = {1: ["PRODUCT"], 2: ["DESIGN", "TICKETS"], 3: ["REVIEW"]}[stage]
                for callsign in callsigns:
                    candidate = store.get(callsign)
                    if candidate and (candidate.get("prompt") or "").strip():
                        agent_rows.append((callsign, candidate))
        except Exception:
            logger.debug("[launch] %s prompt-override lookup failed — using on-disk default",
                         project_id, exc_info=True)
            override = None
        # CBT-9: a picked recipe seeds the workspace (build tree at stage 3, AGENTS.md context at
        # stages 1-2) + the fork-and-extend SKILL block. A seed clone failure is an honest launch
        # refusal (the git error recorded as a blocker), same shape as the hard-gated MCP check below.
        recipe = RecipeStore().get(state.recipe_id) if state.recipe_id else None
        try:
            ws = prepare_workspace(
                self._projects_dir, project_id, stage, runtime=runtime, skill_override=override,
                recipe=recipe, stage_env=env,
            )
        except RecipeSeedError as e:
            logger.warning("[launch] %s stage %s refused — recipe seed clone failed: %s",
                           project_id, stage, e)
            ProjectStore(paths["db"]).add_blocker(f"Recipe seed: {e}", blocks="recipe")
            return None
        for callsign, row in agent_rows:
            try:
                write_agent_file(ws, callsign, row)
            except Exception:
                logger.debug("[launch] %s %s agent-file materialization failed",
                             project_id, callsign, exc_info=True)
        # Stage 3 with a database dependency provisions its OWN Railway Postgres via the
        # `provision-db` db-CLI verb (which wraps deploy_db.provision and persists the teardown
        # handles to ProjectState) — see skills/stage-3-build. The console no longer provisions;
        # the reaper still reads state.deploy_db_service_id, now written by the verb.
        mcp_path = os.path.join(ws, ".mcp.json")
        checks = check_mcp(mcp_path)
        unhealthy = [c for c in checks if not c.ok]
        # Hard-gate ONLY playwright (the happy-flow verification gate needs it). The railway deploy
        # MCP is best-effort: record a blocker if unhealthy but still launch —
        # a transient npx/token hiccup must not block the whole stage, and the agent surfaces real
        # deploy-tool failures itself (bounded health-wait + get_logs).
        _HARD = {"playwright", "config"}
        if unhealthy:
            db = ProjectStore(paths["db"])
            for c in unhealthy:
                db.add_blocker(f"MCP:{c.name} — {c.detail}", blocks="mcp")
            if any(c.name in _HARD for c in unhealthy):
                logger.warning("[launch] %s stage %s refused — hard-gated MCP unhealthy: %s",
                               project_id, stage,
                               ", ".join(c.name for c in unhealthy if c.name in _HARD))
                return None

        state.stage = stage
        state.save()

        if runtime == "opencode":
            alias = state.opencode_model or _OPENCODE_DEFAULT_ALIAS
            model = os.environ.get("SF_MODEL") or _OPENCODE_MODEL_IDS.get(
                alias, _OPENCODE_MODEL_IDS[_OPENCODE_DEFAULT_ALIAS])
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
                # XDG_DATA_HOME hides the host's global auth.json so OPENROUTER_API_KEY (env)
                # is the ONLY credential — same as the container, where this is load-bearing.
                # Live scar (run-d81f37da): auth.json held a spend-limited key; every stage-3
                # swarm agent died "requires more credits" while the env key had $350+.
                "XDG_DATA_HOME": os.path.join(ws, ".oc-data"),
                "OPENCODE_DISABLE_CLAUDE_CODE_SKILLS": "1",
                "OPENCODE_DISABLE_EXTERNAL_SKILLS": "1",
                # Popen(cwd=ws) changes the real cwd but NOT the inherited PWD env var, and
                # OpenCode trusts PWD for project resolution — a stale PWD (e.g. the repo root)
                # makes it bind the session to the wrong directory and crash createUserMessage.
                "PWD": ws,
            }
            if stage == 3 and os.environ.get("SF_SWARM") == "1":
                # §9 swarm build mode: the tracked process becomes the swarm driver, which
                # runs the open tickets as parallel swarm agents and then EXECS this exact
                # opencode argv (same PID — handle, project.log and budget teeth carry through).
                swarm_budget = max(0.0, ceiling - spend - reserve)
                src_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                env["PYTHONPATH"] = (
                    src_root + os.pathsep + env["PYTHONPATH"]
                    if env.get("PYTHONPATH") else src_root
                )
                argv = [
                    sys.executable, "-m", "software_factory.swarm_stage3",
                    os.path.abspath(self._projects_dir), project_id, ws,
                    "--budget", f"{swarm_budget:.2f}",
                    "--model", model,
                    "--",
                ] + argv
        elif runtime == "codex":
            model = _CODEX_MODEL
            argv = [
                "codex", "exec",
                "--model", model,
                "--json",
                "--ephemeral",
                "--dangerously-bypass-approvals-and-sandbox",
                prompt,
            ]
            # A stage must not inherit a developer machine's login, config, MCP list, or stored
            # transcripts. CODEX_API_KEY is deliberately the only auth route for `codex exec`.
            env = {
                **env,
                "CODEX_HOME": os.path.join(ws, ".codex"),
                "PWD": ws,
            }
        else:
            # Model precedence: the operator's per-project pick (most specific — pinned in state at
            # promote_draft, so retries keep it) > SF_MODEL env (deploy-wide knob) > stage defaults
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
            argv = [
                "claude", "-p", prompt,
                "--model", model,
                "--dangerously-skip-permissions",
                "--output-format", "stream-json", "--verbose",
            ]
        # cwd = the workspace so the stage's SKILL.md / phases/ / context/ (its contract) load.
        logger.info("[launch] %s stage %s — runtime=%s model=%s", project_id, stage, runtime, model)
        # SOF-161: stake the DURABLE launch claim right before Popen (token now, real pid the moment
        # we have it). Same lifecycle as self._procs below, but PERSISTED — so a console restart
        # mid-stage self-heals from this claim (via _launch_token_alive) instead of forgetting the
        # orphan. The token is the CAS key: a failed launch releases only its OWN claim.
        _claim = uuid.uuid4().hex
        _st = self._load_state(project_id)
        _st.launch_run_token, _st.launch_run_pid = _claim, 0
        _st.save()
        result = self._launch(argv, env, os.path.join(paths["base"], "project.log"), cwd=ws)
        if result is not None:
            self._procs[project_id] = result   # SPEC §1: tracked for the stage-handoff guard
            _st.launch_run_pid = result.pid     # anchor the durable claim to the live orchestrator
            _st.save()
        else:
            # Failed launch releases its own claim (CAS: clear only if the token is still ours, so a
            # concurrent successful launch's claim is never clobbered).
            _cur = self._load_state(project_id)
            if _cur.launch_run_token == _claim:
                _cur.launch_run_token, _cur.launch_run_pid = "", 0
                _cur.save()
            logger.warning("[launch] %s stage %s — _launch returned no handle", project_id, stage)
        return result

    def _provision_and_launch(self, project_id: str, req: ProjectRequest, *,
                              interview_md: str | None = None) -> str:
        """Provision a run dir (id already minted), persist state, and launch Stage 1.
        Called by promote_draft (the only path into a run — Option C's create_draft mints the id
        up front, so this always runs against an existing draft id)."""
        paths = self._paths(project_id)
        os.makedirs(paths["base"], exist_ok=True)

        # input -> (pdf/docx->markdown[+images]) -> markdown + prompt -> composed Stage 1 input,
        # plus the interview transcript when promoting an interviewed draft.
        # SOF-63: a Concierge-finalized product brief (the kind='product_brief' ARTIFACT, written
        # by the Concierge's finalize_product_brief tool — the single source, per the operator's
        # storage ruling) supersedes the raw composition as context.md.
        brief_block = self._intake.product_brief(project_id) or ""
        # A picked recipe's body IS the Stage-1 baseline input (written as recipe.md) — the only
        # external framing; the retired genre-recipe path is gone (mirrors the
        # concierge-context swap in services/conversation.py).
        recipe_id = self._load_state(project_id).recipe_id
        recipe_md = RecipeStore().body(recipe_id) if recipe_id else None
        written = persist_and_compose(
            paths["input_dir"], req.description, req.context_files or [],
            extract=self._extract, interview_md=interview_md,
            product_brief_md=brief_block or None,
            recipe_md=recipe_md,
        )
        input_db = ProjectStore(paths["db"])
        for name in written:
            input_db.record_artifact("input", "input/" + name, kind="context")
        # SPEC §1: the HOST performs extraction — record it (and provision opening) itself,
        # so these phases are never trust-based and extract can never sit 'pending' forever.
        input_db.set_phase("extract", "done")
        input_db.set_phase("provision", "active")

        state = self._load_state(project_id)
        env = {k: v for k, v in (req.credentials or {}).items() if v}
        # Preserve vault entries from a prior store_draft_creds call (draft BYOK path). Keys
        # in req.credentials overwrite same-named draft entries; unmatched draft entries survive.
        existing_vault_ids = dict(getattr(state, "creds_vault_ids", {}) or {})
        vault_ids = {}
        for key_name, value in env.items():
            try:
                uid = _vault.vault_store(f"byok-{project_id}-{key_name}", value)
                if uid:
                    vault_ids[key_name] = uid
            except Exception:
                logger.warning(
                    "[vault] store failed for %s key %s; key will still reach Stage 1 via env",
                    project_id,
                    key_name,
                    exc_info=True,
                )
        state.skill = "software-factory"
        state.skill_version = SKILL_VERSION
        state.description = req.description
        state.name = req.name or state.name or ""
        state.deploy_target = req.target
        merged_vault_ids = {**existing_vault_ids, **vault_ids}
        state.creds_vault_ids = merged_vault_ids
        state.creds_provided = sorted({*existing_vault_ids, *env})
        state.stage = 1
        # Pin the agent runtime for the whole run (all stages + retries) at start.
        # Per-request choice (the UI's Claude/Kimi picker) wins over the SF_RUNTIME env default.
        state.runtime = req.runtime or os.environ.get("SF_RUNTIME", "claude")
        # Pin the operator's model picks (claude runtime); unknown values are dropped so only
        # the offered choices can ever launch. Empty = stage defaults.
        state.planning_model = req.planning_model if req.planning_model in PLANNING_MODELS else ""
        state.impl_model = req.impl_model if req.impl_model in IMPL_MODELS else ""
        state.opencode_model = req.model if req.model in _OPENCODE_MODEL_IDS else ""
        state.held = False   # drafts hold via create_draft; a provisioned run is never held
        state.owner = (req.owner or state.owner or "").lower()
        state.owner_github_username = (req.owner_github_username or state.owner_github_username or "").strip()
        # Immutable creator stamp — set ONCE (create_draft already stamped it for every real path
        # into this method, so this is a defensive no-op guard, not the primary stamp site).
        # Falls back to owner.
        if not state.created_by:
            state.created_by = state.owner
            state.created_at = time.time()
        state.save()

        prompt = make_prompt_stage1(req, project_id, self._projects_dir, runtime=state.runtime,
                                    brief_block=brief_block)
        if self._launch_stage(project_id, 1, prompt, env) is None:
            # SOF-98: _launch_stage can cleanly REFUSE (budget-at-launch, a hard-gated unhealthy
            # MCP) rather than raise — returning `project_id` here would claim success while
            # nothing actually launched, the same dishonest-success shape as an uncaught crash.
            # A budget refusal in particular happens BEFORE _launch_stage's own launch_attempted
            # stamp, so it isn't even reachable by SOF-116's auto_resume_dead_stage (which requires
            # launch_attempted or an existing project.log) — a real recorded blocker explains why.
            raise RuntimeError(f"stage 1 launch was refused for {project_id} — see its recorded blockers")
        return project_id

    def promote_draft(self, project_id: str, description: str = "",
                      interview_md: str | None = None, target: str = "railway") -> str:
        """Promote a draft into a real run: launch Stage 1 against the EXISTING draft id, threading
        the concierge-finalized product brief + interview transcript into the Stage-1 input. No
        new id is minted.

        SOF-137 (Minimum Machinery): the only gate is a mechanical fact — a product brief exists
        (`self.intake.product_brief(project_id)` returns non-None) — checked HERE, not just at the HTTP
        router, so every caller (the promote route, the concierge's `hand_off_to_factory` tool) is
        gated by construction and sees the SAME honest reason. Raises Conflict (409, same wire
        shape app.py's global ServiceError handler serializes exc.detail verbatim)."""
        from .services.errors import Conflict
        if self._intake.product_brief(project_id) is None:
            raise Conflict("no product brief exists yet — finalize one first")
        state = self._load_state(project_id)
        # The description anchors the prompt; prefer an explicit one, else the plain goal.
        desc = (description or state.description or state.goal or "").strip()
        req = ProjectRequest(
            description=desc,
            target=target or state.deploy_target or "railway",
            runtime=state.runtime,
            planning_model=state.planning_model,
            impl_model=state.impl_model,
            model=state.opencode_model,
            name=state.name,
            owner=state.owner,
        )
        state.phase = "provision"
        state.held = False
        state.save()
        try:
            return self._provision_and_launch(project_id, req, interview_md=interview_md)
        except Exception:
            # SOF-98: a launch that fails or crashes anywhere in this chain (workspace prep, MCP
            # check, the subprocess spawn itself) must not strand the row at phase="provision"
            # forever — nothing else ever un-sticks it (is_pipeline_project can be True here via
            # the context.md artifact _provision_and_launch just recorded, yet auto_resume_dead_stage
            # requires launch_attempted/a project.log to even consider it, neither of which may exist
            # if the crash happened before _launch_stage got that far). Restore the honest state: the
            # hand-off simply didn't happen, so the draft goes back to being a draft — the SAME
            # onboarding screen the user is already on already re-enables its Hand off button and
            # shows the real error (OnboardingScreen.tsx's catch), so this is a real, working retry
            # with zero new UI needed. Re-raise so the caller (router + the concierge's
            # hand_off_to_factory tool) still sees the actual failure, not a silent success.
            state = self._load_state(project_id)
            if state.phase not in ("done", "stopped"):  # don't clobber a concurrent terminal
                state.phase = "draft"
                state.held = False
                state.save()
            raise

    def relaunch_project(self, source_id: str, owner: str = "") -> str:
        """Mint a fresh run from the same spec as a stopped/done project.

        'Relaunch' is a NEW project_id — not un-stopping the old run. Stopped is terminal by design
        to prevent double-orchestrator races; this sidesteps that by creating a sibling run seeded
        from the source's spec. The source is left untouched (its spend/checkpoints stay intact).

        Copies the source's input/ materials (already-converted markdown, not raw binaries) and
        creds_vault_ids refs so the new run has identical context. Returns the new project_id.
        """
        source_state = self._load_state(source_id)
        if source_state.phase not in ("stopped", "done"):
            raise ValueError(
                f"Only stopped or done projects can be relaunched (phase={source_state.phase!r})"
            )
        new_id = self._new_id()
        new_paths = self._paths(new_id)
        os.makedirs(new_paths["base"], exist_ok=True)

        # Copy input/ materials: already-converted markdown (originals consumed on ingest), so no
        # binary duplication. Independent copy — new run can't mutate the source's files.
        src_input = self._paths(source_id)["input_dir"]
        if os.path.isdir(src_input):
            shutil.copytree(src_input, new_paths["input_dir"])

        state = self._load_state(new_id)
        state.description = source_state.description
        state.goal = source_state.goal or ""
        state.scope = list(source_state.scope or [])
        state.runtime = source_state.runtime or os.environ.get("SF_RUNTIME", "claude")
        state.planning_model = source_state.planning_model
        state.impl_model = source_state.impl_model
        state.opencode_model = source_state.opencode_model
        state.deploy_target = source_state.deploy_target or "railway"
        state.budget_ceiling = source_state.budget_ceiling
        state.creds_vault_ids = dict(source_state.creds_vault_ids or {})
        state.creds_provided = list(source_state.creds_provided or [])
        state.relaunched_from = source_id
        effective_owner = (owner or source_state.owner or "").lower()
        state.owner = effective_owner
        state.created_by = effective_owner
        state.created_at = time.time()
        state.skill = "software-factory"
        state.skill_version = SKILL_VERSION
        state.save()

        req = ProjectRequest(
            description=state.description or "",
            target=state.deploy_target or "railway",
            runtime=state.runtime,
            planning_model=state.planning_model,
            impl_model=state.impl_model,
            model=state.opencode_model,
            owner=state.owner,
            owner_github_username=source_state.owner_github_username,
        )
        try:
            return self._provision_and_launch(new_id, req)
        except Exception:
            # SOF-149: a relaunch that fails (a refused launch — #327's honest RuntimeError — or
            # any other crash) must not strand the freshly-minted row at phase="provision" forever,
            # the same class of bug #326 fixed for promote_draft. Unlike a draft promotion, there's
            # no earlier "draft" to fall back to here — by this point the row already carries real
            # content (copied input/ materials, relaunched_from=source_id, the full copied spec),
            # so land it in "crashed" rather than deleting it: the EXISTING RecoveryBar/`/resume`
            # already handles a crashed stage-1 relaunch correctly (proven in SOF-98's investigation)
            # — zero new UI needed, and the operator gets a real Resume affordance on THIS row
            # instead of having to hit Restart again from the source (minting yet another id).
            state = self._load_state(new_id)
            if state.phase not in ("done", "stopped"):  # don't clobber a concurrent terminal
                state.crashed_at_node = "provision"
                state.phase = "crashed"
                state.save()
            raise

    def deployments(self, project_id: str) -> dict:
        """Per-deliverable deployments (a run ships 1..N apps; no single run-level deploy_url)."""
        rows = ProjectStore(self._paths(project_id)["db"]).deployments()
        return {"deployments": rows, "apps": sorted({r["app"] for r in rows if r.get("app")})}

    def tickets(self, project_id: str) -> dict:
        """Build-ticket projection for the kanban view. Empty before Stage 2 persists tickets —
        the frontend renders an empty-state, not an error (TicketStore CREATE-IF-NOT-EXISTS)."""
        store = TicketStore(self._paths(project_id)["tickets_db"])
        items = [
            {"id": t.id, "title": t.title, "wave": t.wave, "status": t.status,
             "agent": t.agent, "provenance": t.provenance, "provenance_type": t.provenance_type,
             "diff_lines": t.diff_lines, "acceptance": t.acceptance, "dod": t.dod,
             "app": getattr(t, "app", None), "description": getattr(t, "description", ""),
             "goal": getattr(t, "goal", ""), "design_refs": getattr(t, "design_refs", None),
             "dependencies": getattr(t, "dependencies", None),
             "scope_genre": getattr(t, "scope_genre", None),
             "implementation_notes": getattr(t, "implementation_notes", ""),
             "decision_log": getattr(t, "decision_log", None)}
            for t in store.all_tickets()
        ]
        waves = sorted({t["wave"] for t in items})
        return {"tickets": items, "waves": waves}

    def agents(self, project_id: str) -> list[dict]:
        """Agents on a run (Project View §2.5) — a flat projection of the agent registry."""
        regs = AgentRegistry(self._paths(project_id)["agents_db"]).agents_for(project_id)
        return [{"agent_id": a.agent_id, "role": a.role, "model": a.model, "phase": a.phase,
                 "status": a.status, "outcome": a.outcome, "ticket_id": a.ticket_id,
                 "cost_usd": a.cost_usd}
                for a in regs]

    def artifacts(self, project_id: str) -> list[dict]:
        """Factory-produced artifacts for a run (Project View Documents tab / produced docs)."""
        return ProjectStore(self._paths(project_id)["db"]).artifacts()

    def project_created(self, project_id: str) -> float | None:
        """Best-available creation time: the earliest recorded phase timestamp (projectstate carries no
        created column). None if nothing has been recorded yet."""
        ts = [p["ts"] for p in ProjectStore(self._paths(project_id)["db"]).phases() if p.get("ts")]
        return min(ts) if ts else None

    def is_pipeline_project(self, project_id: str) -> bool:
        """True only if this run was actually started by THIS pipeline (promote_draft's
        _provision_and_launch records ≥1 artifact in project store). A resurfaced pre-redesign
        dir — PRD.md on disk but an empty project store
        (created fresh on load) — is False, so the poller never auto-advances/zombie-launches it.
        A DRAFT (pre-run interview) is always False, even though attached files record artifacts,
        so the poller ignores it until promotion."""
        if self._load_state(project_id).phase == "draft":
            return False
        db = ProjectStore(self._paths(project_id)["db"])
        return bool(db.artifacts())

    def detect_stage1_done(self, project_id: str) -> bool:
        """Stage 1 is done when the PRD passes the mechanical gate (the artifact IS the proof —
        no event needed; the datastore + the committed PRD are the source of truth)."""
        state = self._load_state(project_id)
        if state.stage1_done:
            return True
        # SPEC §1: a stage is done only when its gate passes AND its process finished —
        # never flip (and so never let the poller launch S2) while S1 is still alive.
        if not self.stage_finished(project_id):
            return False
        base = self._paths(project_id)["base"]
        for root, _dirs, files in os.walk(base):
            if "PRD.md" in files:
                with open(os.path.join(root, "PRD.md")) as f:
                    text = f.read()
                ok, _reasons = artifacts.prd_is_complete(text)
                if ok:
                    ok, _reasons = artifacts.prd_required_sections_complete(text, state.scope)
                if ok and artifacts.prd_lock_in_verdict(text) not in ("SHIP_AS_IS", "SHIP_WITH_EDITS"):
                    return False   # SEND_BACK or missing verdict — the product phase isn't done
                if ok:
                    state.stage1_done = True
                    state.skill, state.skill_version = "software-factory", SKILL_VERSION  # heal host-owned stamp (agents share the db file)
                    state.spent_usd = self._run_spend(project_id, state)
                    self._upload_project_log(project_id, state)
                    state.save()
                    ckpt.write(project_id, "stage:1")
                    # SPEC §5: the stage is over — close any agent rows it forgot to finish.
                    AgentRegistry(self._paths(project_id)["agents_db"]).finalize_orphans(project_id, stage_ok=True)
                    return True
        return False

    def start_stage2(self, project_id: str) -> str | None:
        """Launch Stage 2. Returns project_id or None if blocked (prior stage alive / MCP unhealthy)."""
        state = self._load_state(project_id)
        if self._terminal(state) or not state.stage1_done:
            return None   # terminal (done/stopped) runs are never relaunched
        if self._stage_process_alive(project_id):
            return None   # SPEC §1: never two stage orchestrators for one run
        req = ProjectRequest(description=state.description or "", target=state.deploy_target or "railway")
        env: dict = {}  # BYOK values retrieved from Vault inside _launch_stage
        prompt = make_prompt_stage2(req, project_id, self._projects_dir, runtime=state.runtime)
        result = self._launch_stage(project_id, 2, prompt, env)
        return project_id if result is not None else None

    def detect_stage2_done(self, project_id: str) -> bool:
        """Stage 2 is done when PRD+architecture+svg exist AND the store holds buildable tickets
        (the artifacts + the ticket DB are the proof — no event needed)."""
        state = self._load_state(project_id)
        if state.stage2_done:
            return True
        if not self.stage_finished(project_id):
            return False   # SPEC §1: gate + finished process, never mid-flight
        required = ["PRD.md", "architecture.md", "architecture.svg", "design-spec.md", "flow-map.md",
                   "decision-log.md"]
        base = self._paths(project_id)["base"]
        found_root = base
        ok, _missing = artifacts.verify(base, required)
        if not ok:
            found_root = None
            for root, _dirs, files in os.walk(base):
                ok2, _ = artifacts.verify(root, required)
                if ok2:
                    ok = True
                    found_root = root
                    break
        if not ok:
            return False
        # design-spec.md must actually cover the PRD's screen catalog, not just exist.
        with open(os.path.join(found_root, "PRD.md")) as f:
            prd_text = f.read()
        with open(os.path.join(found_root, "design-spec.md")) as f:
            design_text = f.read()
        design_ok, _reasons = artifacts.design_spec_is_complete(
            design_text, artifacts.parse_screen_ids(prd_text))
        if not design_ok:
            return False
        # SOF-99: no build start without a real per-screen mockup for every V1 screen, plus a
        # flow map that references them all — file-existence facts, not the text-substring
        # coverage design_spec_is_complete does for design-spec.md's prose.
        v1_screen_ids = artifacts.parse_v1_screen_ids(prd_text)
        mockups_ok, _reasons = artifacts.mockups_cover_v1_screens(found_root, v1_screen_ids)
        if not mockups_ok:
            return False
        with open(os.path.join(found_root, "flow-map.md")) as f:
            flow_map_text = f.read()
        flow_map_ok, _reasons = artifacts.flow_map_is_complete(flow_map_text, v1_screen_ids)
        if not flow_map_ok:
            return False
        # SOF-118: the design stage's own decision log — real disclosed content or an explicit
        # "nothing to declare," never a blank/placeholder file.
        with open(os.path.join(found_root, "decision-log.md")) as f:
            decision_log_text = f.read()
        decision_log_ok, _reasons = artifacts.decision_log_is_complete(decision_log_text)
        if not decision_log_ok:
            return False
        # The store must hold real, buildable tickets (acceptance + DoD) — not just
        # ticket *events* on the canvas. An empty/hollow store is NOT a done Stage 2.
        tickets = TicketStore(self._paths(project_id)["tickets_db"])
        if tickets.buildable_count() < 1:
            return False
        # SOF-100: not just "buildable" (non-empty acceptance/dod) — real ticket depth (goal,
        # honest design_refs/dependencies, valid screen refs, per-genre coverage).
        depth_ok, _reasons = tickets.depth_ok(v1_screen_ids, state.scope)
        if not depth_ok:
            return False
        state.stage2_done = True
        state.skill, state.skill_version = "software-factory", SKILL_VERSION  # heal host-owned stamp (agents share the db file)
        state.spent_usd = self._run_spend(project_id, state)
        self._upload_project_log(project_id, state)
        # Parse required tokens from architecture.md
        for root, _dirs, files in os.walk(base):
            if "architecture.md" in files:
                with open(os.path.join(root, "architecture.md")) as f:
                    tokens = artifacts.parse_required_tokens(f.read())
                state.deps_required = [t["name"] for t in tokens]
                break
        state.save()
        ckpt.write(project_id, "stage:2")
        AgentRegistry(self._paths(project_id)["agents_db"]).finalize_orphans(project_id, stage_ok=True)
        return True

    def detect_stage3_done(self, project_id: str) -> bool:
        """Stage 3 is done ONLY when the Claude Code process has finished AND all hard gates pass
        (no hollow done):
        (a) the completed tickets trace to recorded native-Task agents — not a monolithic build,
        (b) a PASSING Playwright happy-flow against the live URL is recorded in project store, and
        (c) the QA loop closed: EVERY ticket reached `approved` (deployed → qa_testing → approved).
            A ticket that QA bounced (qa_reject → open) re-opens the run until it's rebuilt + re-passed.
        On success, record the deploy_url (from the passing verification) and mark phase=done."""
        state = self._load_state(project_id)
        if state.phase == "done":
            return True
        # Process health is the real indicator of whether the stage is still running;
        # never flip done while Claude Code is alive (mirrors detect_stage1/2_done).
        if not self.stage_finished(project_id):
            return False
        paths = self._paths(project_id)
        db = ProjectStore(paths["db"])
        # Gate (b): a real green browser test on the live url must be recorded.
        if not db.has_passing_verification():
            return False
        # Gate (a): tickets were built by per-ticket agents, not one monolithic session.
        tickets = TicketStore(paths["tickets_db"])
        done = tickets.done_tickets()
        spawned = len(AgentRegistry(paths["agents_db"]).agents_for(project_id))
        if not done or spawned == 0 or any(t.agent is None for t in done):
            return False
        # Gate (c): QA approved every ticket. The QA agent drives each deployed ticket's happy flow
        # and qa_approve/qa_reject's it; the run is not done while any ticket is unapproved.
        if not tickets.all_approved():
            return False
        # SOF-118: Stage 3's own stage-wide decision log (cross-cutting build shortcuts not tied
        # to one ticket — per-ticket decisions are already enforced individually by mark_done()).
        # Named DISTINCTLY from Stage 2's decision-log.md ("build-decision-log.md", not
        # "decision-log.md") — Stage 3 clones the SAME canonical repo Stage 2 committed to (SOF-22),
        # so it would otherwise inherit Stage 2's already-gated file via git history and this check
        # could never tell "Stage 2's leftover" from "Stage 3 actually wrote its own."
        # SOF-187: read via the shared DB-first helper, not a raw disk walk — the agent's own
        # teardown step deletes the workspace AFTER recording this artifact, so a disk-only read
        # here made this gate permanently unsatisfiable post-teardown (the exact incident: a real
        # done run got relaunched because this gate could never find the file again).
        decision_log_text = self._artifact_content(project_id, "build-decision-log.md")
        if decision_log_text is None:
            return False
        decision_log_ok, _reasons = artifacts.decision_log_is_complete(decision_log_text)
        if not decision_log_ok:
            return False
        passing = [v for v in db.verifications() if v["passed"]]
        # Gate (d): if auth is present (agent recorded a demo-creds artifact), the happy-flow must
        # include a real sign-in step — a post-login flow with no sign-in step is not done.
        has_demo_creds = any((a.get("kind") or "").lower() == "demo-creds" for a in db.artifacts())
        if has_demo_creds:
            from .gate import has_signin_step
            latest_result = json.loads(passing[-1]["result"]) if passing else None
            if not has_signin_step(latest_result):
                return False
        if passing:
            state.deploy_url = passing[-1]["url"]
        state.phase = "done"
        state.skill, state.skill_version = "software-factory", SKILL_VERSION  # heal host-owned stamp (agents share the db file)
        # Persist the final spend into project store so cost survives log loss (SPEC §4 durability).
        state.spent_usd = self._run_spend(project_id, state)
        self._upload_project_log(project_id, state)
        state.save()
        ckpt.write(project_id, "stage:3")
        AgentRegistry(paths["agents_db"]).finalize_orphans(project_id, stage_ok=True)
        return True

    def project_links(self, project_id: str) -> dict:
        """SPEC §6 delivery: the run's outward links from the artifacts table —
        {'repo': <github url>|None, 'live': <deploy url>|None}."""
        db = ProjectStore(self._paths(project_id)["db"])
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
        state = self._load_state(project_id)
        return {"repo": repo or state.repo_url, "live": live or state.deploy_url}

    def demo_credentials(self, project_id: str) -> str | None:
        """SPEC §6 delivery: the seeded demo login (recorded by Stage 3 as a 'demo-creds'
        artifact) — an app with a sign-in is only demo-able if this reaches the operator.
        These are throwaway demo values by contract, never operator secrets."""
        db = ProjectStore(self._paths(project_id)["db"])
        for a in db.artifacts():
            if (a.get("kind") or "").lower() == "demo-creds":
                content = self.artifact(project_id, a.get("path") or "").get("content")
                if content:
                    return content.strip()
        return None

    def repo_shared_with_owner(self, project_id: str) -> bool:
        """SOF-3: True once Stage 1 recorded a 'repo-shared' artifact — the owner successfully
        received a real GitHub collaborator invite. This is the durable signal the repo-reaper
        checks so it never deletes a repo the owner has actual access to."""
        db = ProjectStore(self._paths(project_id)["db"])
        return any((a.get("kind") or "").lower() == "repo-shared" for a in db.artifacts())

    def stage2_artifacts(self, project_id: str) -> dict:
        """Return Stage 2 artifact paths + parsed required tokens + default dispositions."""
        state = self._load_state(project_id)
        base = self._paths(project_id)["base"]
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

    def submit_deps(self, project_id: str, deps: dict) -> dict:
        """Accept per-dep dispositions (+ values for `provide`). Accepts both the new shape
        `{name: {disposition, value?}}` and legacy `{name: value_string}` (treated as provide).

        Persists NAMES + dispositions (metadata) to state. Provided VALUES are NEVER written to
        disk — they ride into the Stage 3 env via `start_stage3(extra_creds=...)`."""
        state = self._load_state(project_id)
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

    def provide_deployed_dep(self, project_id: str, name: str, value: str) -> dict:
        """#107 — a user REVISITING an already-deployed project replaces one mocked provider dep
        (e.g. OPENROUTER_API_KEY) with their own real value. Unlike `submit_deps`/`start_stage3`
        (the pre-build gate: value rides ephemerally into a fresh Stage-3 launch, never persisted),
        this pushes the value onto the LIVE Railway service via `deploy_db.set_app_variable`
        (triggers a redeploy) and only then records the disposition flip + vault entry — so a
        failed live push never silently marks the dep as provided. FAILS LOUD: returns
        {"ok": False, "detail": ...} on any failure, matching `deploy_db.set_app_variable`; never
        raises, never no-ops silently. Zero-touch (SPEC §3) is unaffected — this is a normal
        authed user action on a finished project, not a mid-build pause.

        A vault-store failure after a SUCCESSFUL live push does not undo the disposition flip —
        the deployed app already has the real key and works — but the response's `vault_saved`
        flag goes False so the caller can surface that the value wasn't recorded (a later
        replace/retry would need it re-entered)."""
        state = self._load_state(project_id)
        if not state.deploy_url:
            return {"ok": False, "detail": "project has no live deployment yet"}
        if name not in (state.deps_required or []):
            return {"ok": False, "detail": f"{name!r} is not a known dependency for this project"}
        if not (value or "").strip():
            return {"ok": False, "detail": "value required"}
        result = deploy_db.set_app_variable(project_id, name, value)
        if not result.get("ok"):
            return result
        try:
            uid = _vault.vault_store(f"byok-{project_id}-{name}", value)
        except Exception:
            uid = None
            logger.warning("[vault] store failed for %s key %s after live app update",
                           project_id, name, exc_info=True)
        disposition = deps_mod.default_dispositions(state.deps_required)
        disposition.update(state.deps_disposition or {})
        disposition[name] = "provide"
        state.deps_disposition = disposition
        state.deps_provided = sorted({*(state.deps_provided or []), name})
        state.deps_satisfied = deps_mod.resolve_satisfied(
            state.deps_required, disposition, state.deps_provided)
        if uid:
            state.creds_vault_ids = {**(state.creds_vault_ids or {}), name: uid}
        state.save()
        return {"ok": True, "name": name, "disposition": "provide", "vault_saved": uid is not None}

    def start_stage3(self, project_id: str, extra_creds: dict | None = None) -> str | None:
        """Launch Stage 3. Returns project_id or None if blocked."""
        state = self._load_state(project_id)
        if self._terminal(state) or not state.stage2_done or not state.deps_satisfied:
            return None   # terminal (done/stopped) runs are never relaunched
        if self._stage_process_alive(project_id):
            return None   # SPEC §1: never two stage orchestrators for one run
        req = ProjectRequest(description=state.description or "", target=state.deploy_target or "railway")
        env: dict = {}  # BYOK values retrieved from Vault inside _launch_stage
        if extra_creds:
            env.update(extra_creds)
        prompt = make_prompt_stage3(req, project_id, self._projects_dir, dispositions=state.deps_disposition,
                                    runtime=state.runtime)
        result = self._launch_stage(project_id, 3, prompt, env)
        return project_id if result is not None else None

    def retry_stage(self, project_id: str, stage: int, extra_creds: dict | None = None) -> str | None:
        """Re-run a single stage against the EXISTING workspace + prior-stage artifacts.

        Unlike `start_stageN`, this does not require the stage's own completion — it's for
        re-running a stage that produced incomplete/bad output (e.g. Stage 2 emitted tickets
        as events but didn't persist them). The prior stage must be done so its inputs exist;
        `workspace.create` is idempotent so earlier stages are reused, never repeated.
        """
        if stage not in (1, 2, 3):
            return None
        if self._stage_process_alive(project_id):
            return None   # SPEC §1: never two stage orchestrators for one run
        state = self._load_state(project_id)
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
        # SOF-186: bank the just-ended attempt's cost into the run-level accumulator and reseal the
        # log at its current end, so the relaunched attempt's spend ADDS to the run total instead of
        # the live log-parse silently dropping the dead attempt (the $20.07->$14.13 regression). The
        # prior orchestrator is already gone (the _stage_process_alive guard above returned), so its
        # log region is complete; _attempt_cost reads it (authoritative result if it produced one,
        # else the token estimate) before we move the seal past it.
        state.prior_attempts_usd = (state.prior_attempts_usd or 0.0) + self._attempt_cost(project_id, state)
        state.spend_seal_offset = self._log_size(project_id)
        state.save()

        req = ProjectRequest(description=state.description or "", target=state.deploy_target or "railway")
        env: dict = {}  # BYOK values retrieved from Vault inside _launch_stage
        if extra_creds:
            env.update(extra_creds)
        if stage == 3:
            prompt = make_prompt_stage3(req, project_id, self._projects_dir, dispositions=state.deps_disposition,
                                        runtime=state.runtime)
        else:
            prompt = {1: make_prompt_stage1, 2: make_prompt_stage2}[stage](
                req, project_id, self._projects_dir, runtime=state.runtime)
        ProjectStore(self._paths(project_id)["db"]).set_phase("retry-stage-%d" % stage, "started")
        result = self._launch_stage(project_id, stage, prompt, env)
        return project_id if result is not None else None

    def _attempt_cost(self, project_id: str, state=None) -> float:
        """SOF-186: the CURRENT stage attempt's total cost (authoritative + in-flight estimate) —
        see `_attempt_cost_components` for the split this sums. Used by `retry_stage`'s banking
        write: at that moment the attempt's process is already confirmed dead, so whatever this
        returns for its now-frozen log region IS the final answer for it (a killed session's own
        estimate never becomes MORE authoritative later — the process is gone), unlike the
        still-alive-session case `_run_spend` guards against."""
        return sum(self._attempt_cost_components(project_id, state))

    def _attempt_cost_components(self, project_id: str, state=None) -> tuple[float, float]:
        """(authoritative, estimate) over the CURRENT stage attempt's region of project.log — the
        bytes from the run's spend_seal_offset onward (retry_stage reseals to the log end on every
        relaunch, so prior attempts live before the offset and are banked in prior_attempts_usd
        instead). See `streamlog.cost_components` for what each half means.

        (mtime,size,offset)-keyed cache — an unchanged log always yields the same cost, so the
        multi-MB reparse only happens when the log grew or was resealed; a stale hit is impossible
        (any append changes st_size, any reseal changes the offset)."""
        state = state or self._load_state(project_id)
        off = state.spend_seal_offset or 0
        p = os.path.join(self._paths(project_id)["base"], "project.log")
        try:
            st = os.stat(p)
            key = (st.st_mtime_ns, st.st_size, off)
        except OSError:
            return (0.0, 0.0)
        hit = self._cost_cache.get(project_id)
        if hit and hit[0] == key:
            return hit[1]
        try:
            with open(p, "rb") as f:
                f.seek(off)
                text = f.read().decode("utf-8", "replace")
        except OSError:
            return (0.0, 0.0)
        val = streamlog.cost_components(text)
        self._cost_cache[project_id] = (key, val)
        return val

    def _log_size(self, project_id: str) -> int:
        try:
            return os.path.getsize(os.path.join(self._paths(project_id)["base"], "project.log"))
        except OSError:
            return 0

    def _workspace_state(self, project_id: str, phase: str) -> str:
        ws = os.path.join(self._paths(project_id)["base"], "workspace")
        if os.path.isdir(ws):
            return "active"
        return "cleaned" if phase in ("done", "blocked", "stopped") else "pending"

    def status(self, project_id: str) -> dict:
        state = self._load_state(project_id)
        reg = AgentRegistry(self._paths(project_id)["agents_db"])
        return {
            "project_id": project_id,
            "skill": state.skill,
            "skill_version": state.skill_version,
            "description": state.description,
            "name": state.name,
            "summary": state.summary,
            "deploy_target": state.deploy_target,
            "phase": self.current_phase(project_id),
            "done": state.phase == "done",
            "deploy_url": state.deploy_url,
            "spent_usd": self._run_spend(project_id, state),
            "creds_provided": state.creds_provided,
            "byo_railway": "RAILWAY_TOKEN" in (state.creds_provided or []),
            "workspace": self._workspace_state(project_id, state.phase),
            "agents": reg.counts(project_id),
            "no_op_rate": reg.no_op_rate(project_id),
            "stage": state.stage,
            "stage1_done": state.stage1_done,
            "stage2_done": state.stage2_done,
            "deps_required": state.deps_required,
            "deps_provided": state.deps_provided,
            "deps_satisfied": state.deps_satisfied,
            "planning_model": state.planning_model,
            "impl_model": state.impl_model,
            "opencode_model": state.opencode_model,
            "runtime": state.runtime or "claude",
            "model": ((state.opencode_model or "kimi") if (state.runtime or "claude") == "opencode"
                      else (_CODEX_MODEL if (state.runtime or "claude") == "codex"
                            else (state.impl_model or state.planning_model or ""))),
            "key_source": _key_source(state.runtime or "claude", state.creds_provided or []),
            "budget_ceiling": self._budget_ceiling(project_id),
            "paused_at_node": state.paused_at_node or "",
            "crashed_at_node": state.crashed_at_node or "",
            "auto_resume_count": state.auto_resume_count,
            "held": state.held,
            "owner": state.owner,
            "maintenance_enabled": state.maintenance_enabled,
            # SOF-165 PR2: count of open tier-2 recovery actions for this run — a lightweight signal
            # the Recovery bar / dashboard can read without a second call. Cheap COUNT over the small,
            # partial-index-covered recovery_actions table; best-effort (0 on any error).
            "open_recovery_actions": recovery.open_recovery_action_count(project_id),
        }

    def recovery_actions(self, project_id: str) -> list[dict]:
        """SOF-165 PR2: this run's recovery-action history (open + resolved, newest first) — read
        surface behind GET /api/projects/{pid}/recovery-actions. Read-only."""
        return recovery.recovery_actions_for(project_id)

    def project_exists(self, project_id: str) -> bool:
        """True if the project exists on disk OR in the pg registry. Pure read — never materializes a dir."""
        base = os.path.join(self._projects_dir, project_id)
        return os.path.isdir(base) or dbshim.project_in_registry(project_id)

    def project_owner(self, project_id: str) -> str:
        """The email that owns this run ('' = legacy/unowned). The per-route visibility gate."""
        return (self._load_state(project_id).owner or "").lower()

    def assign_unowned(self, owner_email: str) -> int:
        """One-time-ish backfill: give every ownerless run an owner (the pre-multitenancy runs).
        Idempotent — runs that already have an owner are left alone. Returns how many it set."""
        owner_email = (owner_email or "").lower()
        if not owner_email:
            return 0
        n = 0
        for r in self.list_projects():            # owner=None → all runs
            st = self._load_state(r["project_id"])
            if not (st.owner or ""):
                st.owner = owner_email
                st.save()
                n += 1
        return n

    def backfill_created_by(self) -> int:
        """Backfill the immutable creator stamp from the current owner for pre-existing projects that
        have no created_by yet. Idempotent (skips any already stamped). Returns how many it set."""
        n = 0
        for r in self.list_projects():
            st = self._load_state(r["project_id"])
            if not (st.created_by or "") and (st.owner or ""):
                st.created_by = st.owner
                if not st.created_at:
                    st.created_at = r.get("updated") or time.time()
                st.save()
                n += 1
        return n

    def list_projects(self, owner: str | None = None, include_archived: bool = False) -> list[dict]:
        """All runs (owner=None — admin/internal callers like the poller), or only those
        owned by `owner` (a member's email; '' never matches, so unowned runs stay admin-only).

        include_archived=True keeps soft-deleted rows (the dashboard's Archived section); the
        default hides them (every existing caller relies on that). Every row carries an
        `archived` flag so the caller can split active from archived.

        The dashboard list is intentionally read-only here: live spend is recomputed by the
        poller and persisted to projectstate.spent_usd, so we do NOT reparse the project.log
        on every listing.
        """
        runs = []
        owner = owner.lower() if owner else None
        # Local dirs ∪ the pg registry (pg mode): a run can exist only in the registry —
        # fresh container, wiped volume — and must still surface. Local wins the dedupe.
        # Only factory-shaped ids list (same rule as the pg registry guard): agents calling
        # db verbs with garbage args once littered the volume with dirs like
        # "build-plan.md"/project store, and discovery showed them as runs.
        local = [n for n in os.listdir(self._projects_dir)
                 if PROJECT_ID_RE.fullmatch(n)
                 and os.path.isdir(os.path.join(self._projects_dir, n))]
        created = {}
        for r in dbshim.registry_projects():
            if PROJECT_ID_RE.fullmatch(r["project_id"]):
                created[r["project_id"]] = r.get("created") or 0
        names = local + [pid for pid in created if pid not in set(local)]
        if not names:
            return []

        # Batch-load the three foreign projections used by every row so the loop is O(1)
        # queries instead of O(runs).
        states = self._load_states(names)
        phase_statuses = self._phase_statuses(names)
        blocker_rows = self._blockers_by_project(names)
        agent_roles = self._agent_roles_by_project(names)

        for name in names:
            st = states[name]
            if st.archived and not include_archived:
                continue   # soft-deleted — hidden unless the caller asked to include them
            if owner is not None and (st.owner or "").lower() != owner:
                continue   # member view: skip runs they don't own (unowned '' never matches)
            # A budget-stopped run is NOT active: surfacing it with a live/green status misled
            # the operator into thinking frozen ghosts were consuming (the b594a5f4/0eb69fdd UI
            # confusion). An uncleared budget blocker = stopped, full stop.
            budget_stopped = any(
                b.get("blocks") == "budget" and not b["cleared"]
                for b in blocker_rows[name]
            )
            # SOF-148: same reasoning as budget_stopped — a credential-blocked run's auto-resume
            # returns False forever (never reaches 'crashed'), so without a surfaced flag it sits
            # invisible, looking like whatever phase it was last in. An uncleared credential
            # blocker means the run needs an operator to provision the real credential, not a
            # crash to auto-heal from.
            credential_stopped = any(
                b.get("blocks") == "credential" and not b["cleared"]
                for b in blocker_rows[name]
            )
            # Last activity (epoch) for the dashboard's "updated" column; falls back to the
            # registry create time for a registry-only run with no local dir yet.
            try:
                updated = os.path.getmtime(os.path.join(self._projects_dir, name))
            except OSError:
                updated = created.get(name, 0)
            runs.append({
                "project_id": name,
                "phase": self._current_phase_from_state(st, phase_statuses[name]),
                "description": st.description,
                "name": st.name,
                "summary": st.summary,
                "deploy_url": st.deploy_url,
                "spent_usd": st.spent_usd or 0,
                "stage": st.stage,
                "budget_stopped": budget_stopped,
                "credential_stopped": credential_stopped,
                "held": st.held,
                "owner": st.owner,
                # Immutable creator (falls back to current owner for not-yet-backfilled rows).
                "created_by": getattr(st, "created_by", "") or st.owner,
                "created_at": getattr(st, "created_at", 0.0) or None,
                "agents": agent_roles[name][:5],
                "updated": updated,
                "runtime": st.runtime,
                "is_demo": bool(getattr(st, "is_demo", False)),
                "archived": bool(getattr(st, "archived", False)),
            })
        runs.sort(key=lambda r: r["updated"], reverse=True)
        return runs

    def set_demo(self, project_id: str, is_demo: bool) -> bool:
        """Tenexity OS REAL/DEMO toggle (§3.3). Returns the new flag."""
        state = self._load_state(project_id)
        state.is_demo = bool(is_demo)
        state.save()
        return state.is_demo

    def set_archived(self, project_id: str, archived: bool) -> bool:
        """Soft-delete / restore a project (DELETE /api/projects/{id}). Archived projects vanish from lists."""
        state = self._load_state(project_id)
        state.archived = bool(archived)
        state.save()
        if archived:
            vault_ids = getattr(state, "creds_vault_ids", {}) or {}
            if vault_ids:
                try:
                    _vault.vault_delete_many(list(vault_ids.values()))
                    state.creds_vault_ids = {}
                    state.save()
                except Exception:
                    pass  # best-effort: archive write must never fail due to Vault hiccup
            self._maybe_teardown_deploy_db(project_id, state)
            # SOF-165: archiving/discarding a run resolves its open recovery action(s) as
            # 'cancelled' — a dead project must never leave a zombie-open action accumulating in the
            # ledger (the exact silent-accumulation class the 2026-07-11 sweep hand-cleaned).
            recovery.resolve_recovery_actions(project_id, resolution="cancelled")
        return state.archived

    def set_maintenance(self, project_id: str, enabled: bool) -> bool:
        """SOF-94: toggle the maintenance-agent placeholder preference. Persists the flag on project
        state; it is a no-op stub — the maintenance agent does not exist yet, so nothing reads this
        to drive behavior. Surfaced on completed projects so an owner can opt in ahead of ship."""
        state = self._load_state(project_id)
        state.maintenance_enabled = bool(enabled)
        state.save()
        return state.maintenance_enabled

    def delete_project(self, project_id: str) -> dict:
        """Permanently remove a run (DELETE /api/projects/{id}/permanent). Runs the same external
        cleanup as archive (Vault creds + deploy-DB teardown), then deletes the run directory and
        every flat-schema row so the run does NOT reappear from the registry. Idempotent — deleting
        an already-gone run never raises."""
        state = self._load_state(project_id)
        # External cleanup, mirroring the archive path (best-effort — a hiccup must never wedge the
        # permanent delete that follows).
        vault_ids = getattr(state, "creds_vault_ids", {}) or {}
        if vault_ids:
            try:
                _vault.vault_delete_many(list(vault_ids.values()))
            except Exception:
                pass
        self._maybe_teardown_deploy_db(project_id, state)
        recovery.resolve_recovery_actions(project_id, resolution="cancelled")  # SOF-165: no zombie-open rows
        # Drop the persisted state (projectstate row → out of the registry) BEFORE the dir, so a
        # registry-only run with no local dir is still fully removed.
        try:
            ProjectStore(self._paths(project_id)["db"]).delete_project(project_id)
        except Exception:
            logger.exception("[delete] state-row delete failed for %s", project_id)
        shutil.rmtree(self._paths(project_id)["base"], ignore_errors=True)
        self._procs.pop(project_id, None)
        return {"project_id": project_id, "deleted": True}

    def _upload_project_log(self, project_id: str, state: "ProjectState") -> None:
        """Best-effort: upload project.log to Supabase Storage and stamp state.log_url.
        No-op when storage is not configured. Never raises — a failed upload must never
        block the lifecycle transition (stage done / stop) that triggered it."""
        from software_factory import storage
        log_path = os.path.join(self._paths(project_id)["base"], "project.log")
        if not os.path.exists(log_path):
            return
        try:
            state.log_url = storage.put(project_id, "logs/project.log", log_path)
            logger.info("[storage] uploaded project.log for %s: %s", project_id, state.log_url)
        except Exception:
            logger.exception("[storage] log upload failed for %s", project_id)

    def _maybe_teardown_deploy_db(self, project_id: str, state: ProjectState | None = None) -> dict | None:
        """Reap THIS run's captured deploy-DB on a terminal/archive transition, per the configured
        A/B policy (disarmed by default → dry-run-logs only). No-op when the run never provisioned a
        DB. Best-effort: a teardown hiccup must never break the archive/lifecycle write that called it."""
        try:
            st = state or self._load_state(project_id)
            sid = (getattr(st, "deploy_db_service_id", "") or "").strip()
            if not sid:
                return None
            rec = deploy_db.ReapRecord(
                project_id=project_id, service_id=sid,
                archived=bool(getattr(st, "archived", False)),
                phase=getattr(st, "phase", "") or "",
                has_verified_deploy=bool(getattr(st, "deploy_url", None)),
                volume_id=getattr(st, "deploy_db_volume_id", "") or "",
            )
            result = deploy_db.reap([rec], log=logger.info)
            _log_teardown_failures(result, project_id)   # SOF-160: don't let a 403 leak silently
            return result
        except Exception:
            logger.exception("[deploy-db] teardown hook error for %s", project_id)
            return None

    def reap_deploy_dbs(self, dry_run: bool = False) -> dict:
        """Sweep EVERY run (including archived — which list_projects hides, yet are prime reap targets)
        and tear down the deploy-DB of each whose run is terminal/discarded per the configured policy.
        Disarmed by default (dry-run-logs candidates); dry_run=True forces a preview even when armed.
        Matches persisted captured serviceIds ↔ run state — it only ever touches ids WE provisioned."""
        local = [n for n in os.listdir(self._projects_dir)
                 if PROJECT_ID_RE.fullmatch(n) and os.path.isdir(os.path.join(self._projects_dir, n))]
        seen = set(local)
        ids = local + [r["project_id"] for r in dbshim.registry_projects()
                       if PROJECT_ID_RE.fullmatch(r["project_id"]) and r["project_id"] not in seen]
        records = []
        for pid in ids:
            st = self._load_state(pid)
            sid = (getattr(st, "deploy_db_service_id", "") or "").strip()
            if not sid:
                continue                                   # never provisioned a DB — nothing to reap
            records.append(deploy_db.ReapRecord(
                project_id=pid, service_id=sid,
                archived=bool(getattr(st, "archived", False)),
                phase=getattr(st, "phase", "") or "",
                has_verified_deploy=bool(getattr(st, "deploy_url", None)),
                volume_id=getattr(st, "deploy_db_volume_id", "") or "",
            ))
        result = deploy_db.reap(records, log=logger.info, dry_run=dry_run)
        _log_teardown_failures(result)   # SOF-160: surface batch-sweep teardown failures loudly
        return result

    def _bulk_repo_signals(self, project_ids: list[str]) -> tuple[dict[str, str], set[str]]:
        """Batch equivalent of calling `project_links(pid)["repo"]` + `repo_shared_with_owner(pid)`
        for MANY projects, in ONE query instead of two fresh `ProjectStore` connections (=two
        pooler round-trips) PER PROJECT. SOF-7 perf fix: those per-project round-trips against the
        prod Supabase pooler were the actual cause of a 9-minute dry-run timeout with zero output
        (a regression #217/SOF-8 introduced onto the reaper path). Mirrors both methods' own
        matching rules exactly — same semantics, just batched.

        Returns (project_id -> exact "GitHub Repo" artifact URL, {project_ids with a
        'repo-shared' artifact})."""
        repo_urls: dict[str, str] = {}
        shared: set[str] = set()
        if not project_ids:
            return repo_urls, shared
        exec_ = PathExec(self._projects_dir)
        try:
            rows = ArtifactRepository.batch_for_projects(exec_, project_ids)
        finally:
            exec_.close()
        for row in rows:
            pid = row["project_id"]
            kind = (row.get("kind") or "").lower()
            if kind == "repo-shared":
                shared.add(pid)
                continue
            if pid in repo_urls:
                continue
            path = row.get("path") or ""
            title = (row.get("title") or "").lower()
            if path.startswith("http") and ("repo" in title or kind == "repo"):
                repo_urls[pid] = path
        return repo_urls, shared

    def reap_github_repos(self, org: str, dry_run: bool = False) -> dict:
        """Sweep factory-created repos in `org` and reap those whose project is confirmed dead.

        SAFETY: prefers an EXACT match — the repo Stage 3 itself recorded via
        `record-artifact("GitHub Repo", <clean url>, kind="repo")` — over the old suffix-pattern
        guess. Falls back to the <name>-[0-9a-f]{8,16} suffix heuristic only for projects with no
        exact record (older runs that predate this convention, or a run whose Stage 3 skipped that
        step). Repos matching neither are LOG-ONLY (returned in report["unknown_repos"], never
        auto-deleted). Reap policy mirrors the deploy-DB reaper: archived |
        stopped-without-deploy → reap; everything else → keep. Disarmed by default
        (SF_GITHUB_REPO_REAPER=on to arm). dry_run=True forces preview.

        PERF: all project state (dispositions, repo urls, owner-shared flags) is read via
        _load_states/_bulk_repo_signals — a HANDFUL of batch queries total, not O(N) round-trips
        for N projects (#SOF-7 perf fix)."""
        from . import github_repo_reaper as _ghr
        all_repos = _ghr.list_org_repos(org)
        local = [n for n in os.listdir(self._projects_dir)
                 if PROJECT_ID_RE.fullmatch(n) and os.path.isdir(os.path.join(self._projects_dir, n))]
        seen = set(local)
        all_pids = local + [r["project_id"] for r in dbshim.registry_projects()
                            if PROJECT_ID_RE.fullmatch(r["project_id"]) and r["project_id"] not in seen]
        states = self._load_states(all_pids)
        repo_urls, owner_shared_pids = self._bulk_repo_signals(all_pids)
        # Exact index (preferred): repo full name -> (project_id, state), from Stage 3's own
        # recorded "GitHub Repo" artifact. Suffix index (fallback): the first
        # FACTORY_REPO_SUFFIX_LENGTH (8) hex chars of the project_id hex part, for projects
        # with no exact record.
        exact_by_repo: dict[str, tuple[str, object]] = {}
        pid_by_suffix: dict[str, tuple[str, object]] = {}
        for pid in all_pids:
            st = states[pid]
            exact = _ghr.org_repo_from_url(repo_urls.get(pid) or getattr(st, "repo_url", None))
            if exact and exact not in exact_by_repo:
                exact_by_repo[exact] = (pid, st)
            hex_part = pid[len("project-"):]         # strip "project-" prefix
            for length in (_ghr.FACTORY_REPO_SUFFIX_LENGTH, len(hex_part)):
                key = hex_part[:length]
                if key and key not in pid_by_suffix:
                    pid_by_suffix[key] = (pid, st)
        records, unknown_repos = [], []
        for repo in all_repos:
            name = repo.get("name", "")
            full_name = f"{org}/{name}"
            match = exact_by_repo.get(full_name)
            if not match:
                m = _ghr.FACTORY_REPO_SUFFIX_RE.search(name)
                if not m:
                    continue
                suffix = m.group(1)
                # Try exact suffix match first, then its 8-char prefix as a fallback.
                match = pid_by_suffix.get(suffix) or pid_by_suffix.get(suffix[:_ghr.FACTORY_REPO_SUFFIX_LENGTH])
                if not match:
                    # Suffix has no DB match — log-only, never auto-delete.
                    unknown_repos.append({"repo": full_name, "suffix": suffix})
                    logger.warning("[github-reaper] UNKNOWN suffix %r on %s/%s — surfaced for manual review",
                                   suffix, org, name)
                    continue
            pid, st = match
            records.append(_ghr.ReapRecord(
                project_id=pid,
                repo_full_name=full_name,
                archived=bool(getattr(st, "archived", False)),
                phase=getattr(st, "phase", "") or "",
                has_verified_deploy=bool(getattr(st, "deploy_url", None)),
                owner_repo_shared=pid in owner_shared_pids,
            ))
        report = _ghr.reap(records, log=logger.info, dry_run=dry_run)
        report["unknown_repos"] = unknown_repos
        return report

    def rename_project(self, project_id: str, name: str | None = None,
                       description: str | None = None, scope: list | None = None,
                       summary: str | None = None) -> dict:
        """Update a project's name / scope / description / summary in place (post-promotion edit).
        When `scope` is given the description is recomposed (goal + scope line), exactly like the
        draft setter. `summary` is the customer-facing blurb (populated externally)."""
        state = self._load_state(project_id)
        if name is not None:
            state.name = name
        if scope is not None:
            state.scope = list(scope)
            state.description = _compose_description(state.goal or "", state.scope)
        elif description is not None:
            state.description = description
        if summary is not None:
            state.summary = summary
        state.save()
        return {"project_id": project_id, "name": state.name, "scope": list(state.scope or []),
                "description": state.description, "summary": state.summary}

    def events(self, project_id: str) -> list:
        """Recent run activity, projected from project store for the live activity feed. Shaped like the
        old event records ({type, payload, ts}) so the frontend renders unchanged — but the DATASTORE
        is the source of truth; there is no event log."""
        db = ProjectStore(self._paths(project_id)["db"])
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

    def _artifact_content(self, project_id: str, path: str) -> str | None:
        """Read an artifact's full text content: the DB-inlined `content` column first (SOF-138 —
        survives workspace teardown), falling back to the live filesystem for pre-SOF-138 rows or
        a still-live workspace. Returns None if the artifact isn't found anywhere.

        SOF-187: this is the ONE shared read path any stage-completion gate (or artifact fetch)
        should use. A gate that reads straight from disk becomes PERMANENTLY unsatisfiable once
        the stage-3 agent's own teardown step (workspace.destroy) deletes the workspace — which
        defeats auto_resume_dead_stage's "already done, don't relaunch" check for stage 3, since
        that check depends entirely on detect_stage3_done() seeing every gate pass. Any future
        stage-completion gate that needs to read a recorded document (e.g. PR #364's PRD.md gate)
        should call this instead of its own os.walk — that's the whole fix, reused."""
        db = ProjectStore(self._paths(project_id)["db"])
        row = db.artifact_by_path(path)
        if row and row.get("content") is not None:
            return row["content"]

        # Artifact paths arrive relative to wherever the recording agent worked: the run base
        # (host: "input/..."), the workspace (orchestrator: "architecture.md"), or the cloned
        # project repo INSIDE the workspace (S1 agents: "PRD.md", "research/x.md"). Resolve
        # against all three levels — the file must still stay under the run base (no escape).
        base = os.path.realpath(self._paths(project_id)["base"])
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
                    return f.read()
        return None

    def artifact(self, project_id: str, path: str) -> dict:
        content = self._artifact_content(project_id, path)
        if content is not None:
            return {"path": path, "content": content[:200000]}
        return {"error": "not found", "path": path}

    def graph(self, project_id: str) -> dict:
        """Cytoscape elements projected ENTIRELY from project store (the single source of truth):
        pipeline phases + stage gates + deps from projectstate/phases; agents from the agents table;
        artifacts/blockers from their tables; the pending review gate from the gates table.
        No event log, no stream-log parsing — the canvas is a pure projection of the datastore."""
        paths = self._paths(project_id)
        db = ProjectStore(paths["db"])
        state = self._load_state(project_id)
        orch_label = ("Kimi · software-factory" if state.runtime == "opencode"
                      else "Codex · software-factory" if state.runtime == "codex"
                      else "Claude · software-factory")
        nodes = [{"data": {"id": "orchestrator", "label": orch_label,
                           "kind": "orchestrator", "status": self.current_phase(project_id)}}]
        edges = []

        derived = self.derive_phases(project_id)
        prev = "orchestrator"
        for name in PIPELINE:
            st = derived.get(name, "pending")
            pid = "phase:" + name
            nodes.append({"data": {"id": pid, "label": PIPELINE_LABELS.get(name, name),
                                   "kind": "phase", "status": st, "stage": PHASE_STAGE.get(name)}})
            edges.append({"data": {"source": prev, "target": pid, "etype": "flow"}})
            prev = pid
            if name == "product":
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
        for rec in reg.agents_for(project_id):
            nid = "agent:" + rec.agent_id
            agent_ids.add(nid)
            nodes.append({"data": {"id": nid, "label": rec.role, "kind": "agent",
                                   "status": rec.status, "real": True}})
            src = "phase:" + rec.phase if rec.phase in PIPELINE else "orchestrator"
            edges.append({"data": {"source": src, "target": nid, "etype": "hierarchy"}})

        # Artifacts — from the artifacts table. SOF-199: skip input-only kinds (context,
        # product_brief) the same way project_view.documents() already does for the Documents tab
        # — an input artifact shouldn't appear as a peer node of the factory's real output (the
        # product_brief-vs-prd duplication SOF-182 found).
        for i, a in enumerate(a for a in db.artifacts() if a.get("kind") not in INPUT_ONLY_KINDS):
            path = a.get("path") or ""
            if path.startswith("http"):
                status = "created"
            else:
                status = "created" if (path and "content" in self.artifact(project_id, path)) else "missing"
            aid = "artifact:%d" % i
            nodes.append({"data": {"id": aid, "label": a.get("title") or "artifact", "kind": "artifact",
                                   "path": path, "status": status,
                                   "url": path if path.startswith("http") else None,
                                   "artifact_id": a.get("id")}})
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
