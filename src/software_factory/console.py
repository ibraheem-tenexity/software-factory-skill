"""Operator console logic: turn a one-line app request into a headless factory run, read back
live status, and assemble proof.

The console is the HARNESS, not the builder. It orchestrates three stages — each a separate
`claude -p` invocation — with gates between them. Stage 1→2 is automatic (PRD passes gate).
Stage 2→3 requires user input (dependency tokens). The wait-for-deps step is a console-level
procedure, not inside any stage.
"""
from __future__ import annotations

import os
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable

from . import artifacts, events, gates, streamlog
from .agents import AgentRegistry
from .evidence import build_evidence, verify_evidence
from .input_pipeline import persist_and_compose
from .pdf_extract import extract_to_markdown
from . import deps as deps_mod
from .mcp_health import check_mcp
from .runstate import JsonFileStore, RunState
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


@dataclass
class RunRequest:
    description: str
    context: str = ""
    budget: float = 100.0
    target: str = "railway"
    credentials: dict = field(default_factory=dict)
    context_files: list = field(default_factory=list)


def run_paths(runs_dir: str, run_id: str) -> dict:
    base = os.path.join(runs_dir, run_id)
    return {
        "base": base,
        "state_dir": base,
        "agents_db": os.path.join(base, "agents.db"),
        "tickets_db": os.path.join(base, "tickets.db"),
        "input_dir": os.path.join(base, "input"),
    }


def make_prompt_stage1(req: RunRequest, run_id: str, runs_dir: str) -> str:
    base = os.path.join(runs_dir, run_id)
    ctx = f"\n\nContext / detailed input:\n{req.context}" if req.context else ""
    emit = f"python -m software_factory.events emit {runs_dir} {run_id}"
    return (
        f"Use the **software-factory** skill (Stage 1 — Research) to research and define this "
        f"customer solution, FULLY AUTONOMOUSLY — never wait on a human.\n"
        f"run_id={run_id}. runs_dir={runs_dir}. Budget ${req.budget:.0f} (HARD cutoff).\n\n"
        f"Read SKILL.md and the phases/ files. Execute these phases IN ORDER, and at each one run "
        f"`{emit} phase '{{\"name\":\"<phase>\"}}'` so the canvas shows progress.\n"
        f"ORCHESTRATION MODEL: you do NOT do the work yourself. ruflo is the swarm runtime — "
        f"for each task type start a ruflo swarm (`swarm_init`) and `agent_spawn` agents into it. "
        f"Each agent: emit `agent_spawned` on spawn and `agent_done` on result; it pulls/writes via "
        f"ruflo (memory); and attributes any file it creates via `emit artifact {{...,\"agent\":\"<id>\"}}` "
        f"so the artifact shows as that agent's child.\n"
        f"1. extract — the console already saved the input under {base}/input/. Read everything "
        f"there (txt/pdf/docx; install a parser if needed) and extract it to usable text.\n"
        f"2. provision — `creds.check_all`; `GitHub.create_repo`; `Budget(100)`; `workspace.create`; seed ruflo.\n"
        f"3. research — `swarm_init` a research swarm, then `agent_spawn` the named agents IN ORDER: "
        f"HORIZON(pm.lead: scope) → ARCHIVIST(reuse scan via ruflo) → VANGUARD(domain-expert: "
        f"≥2 solution paths + REQUIRED WebSearch/WebFetch, ≥3 real products WITH URLs) → "
        f"CHROMA(design.lead: screens + happy-flow journey) → DESIGNER(frontend-design: visual "
        f"design guidance using the frontend-design + ui-ux-pro-max skills in skills/) → "
        f"HORIZON writes PRD.md with acceptance criteria (given/when/then) + ticket seeds; commit; "
        f"`{emit} artifact '{{\"title\":\"PRD\",\"path\":\"workspace/<repo>/PRD.md\",\"kind\":\"prd\"}}'`. "
        f"Do NOT advance until `artifacts.prd_is_complete(PRD.md)` passes.\n\n"
        f"When the PRD passes `prd_is_complete()`: "
        f"`{emit} stage_done '{{\"stage\":1}}'` then STOP.\n\n"
        f"Write run state and telemetry under {base}/.\n"
        f"App: {req.description}{ctx}"
    )


def make_prompt_stage2(req: RunRequest, run_id: str, runs_dir: str) -> str:
    base = os.path.join(runs_dir, run_id)
    emit = f"python -m software_factory.events emit {runs_dir} {run_id}"
    return (
        f"Use the **software-factory** skill (Stage 2 — Design & Plan) to architect and plan "
        f"this customer solution, FULLY AUTONOMOUSLY.\n"
        f"run_id={run_id}. runs_dir={runs_dir}. Budget ${req.budget:.0f} (HARD cutoff).\n\n"
        f"Read SKILL.md and context/ for Stage 1 artifacts (PRD.md, design spec).\n"
        f"Read phases/ files. Emit `{emit} phase '{{\"name\":\"<phase>\"}}'` at each phase.\n"
        f"1. architect — `swarm_init` + `agent_spawn` software-architect. From the PRD + design spec, "
        f"produce architecture.md (fewest services; data model; dependency + required-token list with "
        f"a `## Required Tokens` section using UPPER_SNAKE_CASE names) + Mermaid → architecture.svg via "
        f"`diagram.render`. Commit + emit both artifacts.\n"
        f"   The Stage 3 build agent will have the **Supabase MCP + Railway MCP** (and Railway/Supabase "
        f"tokens in env) — design Supabase (DB/auth/storage) + Railway (compute) as agent-provisionable; "
        f"do NOT require the operator to supply Supabase/Railway/NextAuth creds. External integrations "
        f"(SSO/ERP/email) may be mocked for the demo. List every runtime token regardless; the console "
        f"auto-classifies each as provide/mock/mcp.\n"
        f"2. tickets — `TicketStore.create_ticket` in waves with acceptance + DoD (from PRD ticket seeds + "
        f"architecture + design spec). Emit a node per ticket.\n\n"
        f"Done-gate: `artifacts.verify(run_dir, [\"PRD.md\", \"architecture.md\", \"architecture.svg\"])` "
        f"passes AND ≥1 ticket exists.\n"
        f"When both gates pass: `{emit} stage_done '{{\"stage\":2}}'` then STOP.\n\n"
        f"Write run state and telemetry under {base}/.\n"
        f"App: {req.description}"
    )


def _disposition_guidance(dispositions: dict | None) -> str:
    disp = dispositions or {}
    mock = sorted(n for n, d in disp.items() if d == "mock")
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
        f"- All other required tokens with real values are already in your environment.\n"
        f"Do NOT block on a real third-party integration when its token is marked MOCK — build the fake.\n"
    )


def make_prompt_stage3(req: RunRequest, run_id: str, runs_dir: str, dispositions: dict | None = None) -> str:
    base = os.path.join(runs_dir, run_id)
    service = f"sf-{run_id}"
    emit = f"python -m software_factory.events emit {runs_dir} {run_id}"
    return (
        f"Use the **software-factory** skill (Stage 3 — Build & Ship) to build, deploy, and "
        f"browser-verify this customer solution, FULLY AUTONOMOUSLY.\n"
        f"run_id={run_id}. runs_dir={runs_dir}. Budget ${req.budget:.0f} (HARD cutoff). "
        f"Deploy target: {req.target}.\n\n"
        f"{_disposition_guidance(dispositions)}"
        f"Read SKILL.md and context/ for prior-stage artifacts (PRD.md, architecture.md, architecture.svg).\n"
        f"Read phases/ files. Emit `{emit} phase '{{\"name\":\"<phase>\"}}'` at each phase.\n"
        f"1. build — per ticket: spawn a build agent (pull from ruflo), merge only via "
        f"`merge_if_green`, `mark_done`; record precedent. No-op = retry.\n"
        f"2. deploy — DEPLOY ISOLATION (critical): create + deploy to dedicated service "
        f"'{service}' (`railway add --service {service}` then `railway up --service {service}`). "
        f"NEVER run a bare `railway up`. `deploy.healthy(url)` must pass.\n"
        f"3. test — drive the live URL with Playwright; `gate.happy_flow_passed`. Green → "
        f"`{emit} done` → DONE. Red → fix agents → redeploy → re-test.\n"
        f"4. teardown — `workspace.destroy` on any terminal state; proof + events survive.\n\n"
        f"Write run state and telemetry under {base}/.\n"
        f"App: {req.description}"
    )


# Keep the old prompt generator for backward compat with existing runs
def make_prompt(req: RunRequest, run_id: str, runs_dir: str) -> str:
    return make_prompt_stage1(req, run_id, runs_dir)


def _default_launch(argv: list[str], env: dict, log_path: str | None = None) -> Any:
    import subprocess
    import sys
    import threading

    proc = subprocess.Popen(
        argv, env={**os.environ, **env},
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
        os.makedirs(runs_dir, exist_ok=True)

    def _paths(self, run_id: str) -> dict:
        return run_paths(self._runs_dir, run_id)

    def _load_state(self, run_id: str) -> RunState:
        return RunState.load(run_id, JsonFileStore(self._paths(run_id)["state_dir"]))

    def _launch_stage(self, run_id: str, stage: int, prompt: str, env: dict) -> Any:
        """Prepare workspace, health-check MCP, and launch a claude -p process for a stage."""
        paths = self._paths(run_id)
        ws = prepare_workspace(
            self._runs_dir, run_id, stage,
        )
        mcp_path = os.path.join(ws, ".mcp.json")
        checks = check_mcp(mcp_path)
        unhealthy = [c for c in checks if not c.ok]
        if unhealthy:
            for c in unhealthy:
                events.emit(self._runs_dir, run_id, "blocker",
                            {"what": f"MCP:{c.name} — {c.detail}", "blocks": "mcp"})
            return None

        state = self._load_state(run_id)
        state.stage = stage
        state.save()

        model = os.environ.get("SF_MODEL", "claude-sonnet-4-6")
        max_turns = os.environ.get("SF_MAX_TURNS", "60")
        argv = [
            "claude", "-p", prompt,
            "--model", model,
            "--max-turns", max_turns,
            "--permission-mode", "bypassPermissions",
            "--output-format", "stream-json", "--verbose",
        ]
        return self._launch(argv, env, os.path.join(paths["base"], "run.log"))

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
        for name in written:
            events.emit(self._runs_dir, run_id, "artifact",
                        {"title": "input", "path": "input/" + name, "kind": "context"})

        state = self._load_state(run_id)
        env = {k: v for k, v in (req.credentials or {}).items() if v}
        state.skill = "software-factory"
        state.skill_version = SKILL_VERSION
        state.description = req.description
        state.deploy_target = req.target
        state.creds_provided = sorted(env.keys())
        state.stage = 1
        state.save()

        prompt = make_prompt_stage1(req, run_id, self._runs_dir)
        self._launch_stage(run_id, 1, prompt, env)
        return run_id

    def detect_stage1_done(self, run_id: str) -> bool:
        """Check if Stage 1 is complete: stage_done event + PRD passes mechanical gate."""
        evs = self.events(run_id)
        has_event = any(
            e["type"] == "stage_done" and e.get("payload", {}).get("stage") == 1
            for e in evs
        )
        if not has_event:
            return False
        state = self._load_state(run_id)
        if state.stage1_done:
            return True
        base = self._paths(run_id)["base"]
        for root, _dirs, files in os.walk(base):
            if "PRD.md" in files:
                with open(os.path.join(root, "PRD.md")) as f:
                    text = f.read()
                ok, _reasons = artifacts.prd_is_complete(text)
                if ok:
                    state.stage1_done = True
                    state.save()
                    return True
        return False

    def start_stage2(self, run_id: str) -> str | None:
        """Launch Stage 2. Returns run_id or None if MCP unhealthy."""
        state = self._load_state(run_id)
        if not state.stage1_done:
            return None
        req = RunRequest(description=state.description or "", target=state.deploy_target or "railway")
        env = {k: v for k, v in os.environ.items()
               if k in (state.creds_provided or [])}
        prompt = make_prompt_stage2(req, run_id, self._runs_dir)
        result = self._launch_stage(run_id, 2, prompt, env)
        return run_id if result is not None else None

    def detect_stage2_done(self, run_id: str) -> bool:
        """Check if Stage 2 is complete: stage_done event + artifacts + tickets."""
        evs = self.events(run_id)
        has_event = any(
            e["type"] == "stage_done" and e.get("payload", {}).get("stage") == 2
            for e in evs
        )
        if not has_event:
            return False
        state = self._load_state(run_id)
        if state.stage2_done:
            return True
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
        # Parse required tokens from architecture.md
        for root, _dirs, files in os.walk(base):
            if "architecture.md" in files:
                with open(os.path.join(root, "architecture.md")) as f:
                    tokens = artifacts.parse_required_tokens(f.read())
                state.deps_required = [t["name"] for t in tokens]
                break
        state.save()
        return True

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
        if not state.stage2_done or not state.deps_satisfied:
            return None
        req = RunRequest(description=state.description or "", target=state.deploy_target or "railway")
        env = {k: v for k, v in os.environ.items()
               if k in (state.creds_provided or [])}
        if extra_creds:
            env.update(extra_creds)
        prompt = make_prompt_stage3(req, run_id, self._runs_dir, dispositions=state.deps_disposition)
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
        state = self._load_state(run_id)
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
            prompt = make_prompt_stage3(req, run_id, self._runs_dir, dispositions=state.deps_disposition)
        else:
            prompt = {1: make_prompt_stage1, 2: make_prompt_stage2}[stage](req, run_id, self._runs_dir)
        events.emit(self._runs_dir, run_id, "phase",
                    {"name": "retry-stage-%d" % stage, "status": "started"})
        result = self._launch_stage(run_id, stage, prompt, env)
        return run_id if result is not None else None

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
            "deploy_target": state.deploy_target,
            "phase": state.phase,
            "done": state.phase == "done",
            "deploy_url": state.deploy_url,
            "spent_usd": streamlog.cost_usd(self._full_log(run_id)) or state.spent_usd,
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
        }

    def list_runs(self) -> list[dict]:
        runs = []
        for name in os.listdir(self._runs_dir):
            base = os.path.join(self._runs_dir, name)
            state_json = os.path.join(base, f"{name}.json")
            if not os.path.isdir(base) or not os.path.exists(state_json):
                continue
            st = self._load_state(name)
            runs.append({
                "run_id": name,
                "phase": st.phase,
                "description": st.description,
                "deploy_url": st.deploy_url,
                "spent_usd": streamlog.cost_usd(self._full_log(name)) or st.spent_usd,
                "stage": st.stage,
            })
        runs.sort(key=lambda r: os.path.getmtime(os.path.join(self._runs_dir, r["run_id"])), reverse=True)
        return runs

    def events(self, run_id: str) -> list:
        return events.read_events(self._runs_dir, run_id)

    def continue_run(self, run_id: str, gate: str) -> dict:
        gates.clear_gate(self._runs_dir, run_id, gate)
        return {"cleared": gate}

    def artifact(self, run_id: str, path: str) -> dict:
        base = os.path.realpath(self._paths(run_id)["base"])
        full = os.path.realpath(os.path.join(base, path))
        if os.path.commonpath([full, base]) != base or not os.path.isfile(full):
            return {"error": "not found", "path": path}
        with open(full, "r", errors="replace") as f:
            return {"path": path, "content": f.read()[:200000]}

    def graph(self, run_id: str) -> dict:
        """Cytoscape elements: orchestrator + the pipeline phases + stage gates + deps node,
        with agents, artifacts, blockers and the pending review gate folded in."""
        d = self._runs_dir
        evs = self.events(run_id)
        state = self._load_state(run_id)
        nodes = [{"data": {"id": "orchestrator", "label": "Claude · software-factory",
                           "kind": "orchestrator", "status": state.phase}}]
        edges = []

        phase_status = {e["payload"].get("name"): e["payload"].get("status", "active")
                        for e in evs if e["type"] == "phase"}
        prev = "orchestrator"
        for name in PIPELINE:
            st = "active" if state.phase == name else phase_status.get(name, "pending")
            pid = "phase:" + name
            nodes.append({"data": {"id": pid, "label": PIPELINE_LABELS.get(name, name),
                                   "kind": "phase", "status": st,
                                   "stage": PHASE_STAGE.get(name)}})
            edges.append({"data": {"source": prev, "target": pid, "etype": "flow"}})
            prev = pid

            # Insert stage gate nodes between stages
            if name == "research":
                gid = "gate:stage1"
                gst = "passed" if state.stage1_done else "pending"
                nodes.append({"data": {"id": gid, "label": "Stage 1 Gate",
                                       "kind": "gate", "status": gst}})
                edges.append({"data": {"source": pid, "target": gid, "etype": "flow"}})
                prev = gid
            elif name == "tickets":
                gid = "gate:stage2"
                gst = "passed" if state.stage2_done else "pending"
                nodes.append({"data": {"id": gid, "label": "Stage 2 Gate",
                                       "kind": "gate", "status": gst}})
                edges.append({"data": {"source": pid, "target": gid, "etype": "flow"}})
                # Deps node between stage 2 gate and build
                did = "deps:wait"
                dst = "satisfied" if state.deps_satisfied else "pending"
                nodes.append({"data": {"id": did, "label": "wait for deps",
                                       "kind": "deps", "status": dst,
                                       "deps_required": state.deps_required,
                                       "deps_provided": state.deps_provided}})
                edges.append({"data": {"source": gid, "target": did, "etype": "flow"}})
                prev = did

        # Fix-loop: dashed feedback edge from test back to build
        edges.append({"data": {"source": "phase:test", "target": "phase:build", "etype": "feedback"}})

        # Agents: roster + events + stream
        agent_info = {}
        roster_keys = {label.lower(): aid for _ph, r in PHASE_AGENTS.items() for aid, label in r}
        for ph, roster in PHASE_AGENTS.items():
            for aid, role in roster:
                agent_info[aid] = {"label": role, "phase": ph, "status": "planned"}

        def _akey(p):
            r = (p.get("role") or "").strip().lower()
            if r in roster_keys:
                return roster_keys[r]
            return p.get("id") or p.get("role") or "agent"

        for e in evs:
            p = e.get("payload") or {}
            if e["type"] == "agent_spawned":
                k = _akey(p); cur = agent_info.get(k, {})
                agent_info[k] = {"label": p.get("role") or cur.get("label") or k,
                                 "phase": p.get("phase") or cur.get("phase"), "status": "running"}
            elif e["type"] == "agent_done":
                k = _akey(p)
                if k in agent_info:
                    out = p.get("outcome")
                    agent_info[k]["status"] = "done" if out in (None, "real_diff", "success") else out

        for a in streamlog.agents(self._full_log(run_id)):
            lbl = (a.get("label") or "").lower()
            matched = next((aid for labelkey, aid in roster_keys.items() if labelkey in lbl), None)
            if matched:
                agent_info[matched]["status"] = a["status"]
                agent_info[matched]["real"] = True
            else:
                agent_info.setdefault(a["id"], {"label": a["label"], "phase": None,
                                                "status": a["status"], "real": True})
        agent_ids = set()
        for aid, info in agent_info.items():
            nid = "agent:" + aid; agent_ids.add(nid)
            nodes.append({"data": {"id": nid, "label": info["label"], "kind": "agent",
                                   "status": info["status"], "real": bool(info.get("real"))}})
            src = "phase:" + info["phase"] if info.get("phase") in PIPELINE else "orchestrator"
            edges.append({"data": {"source": src, "target": nid, "etype": "hierarchy"}})

        for i, e in enumerate([e for e in evs if e["type"] == "artifact"]):
            p = e["payload"]; aid = "artifact:%d" % i
            path = p.get("path") or ""
            if path.startswith("http"):
                status = "created"
            else:
                status = "created" if (path and "content" in self.artifact(run_id, path)) else "missing"
            nodes.append({"data": {"id": aid, "label": p.get("title", "artifact"), "kind": "artifact",
                                   "path": path, "status": status, "url": path if path.startswith("http") else None}})
            owner = "agent:" + p["agent"] if p.get("agent") and ("agent:" + p["agent"]) in agent_ids else "orchestrator"
            edges.append({"data": {"source": owner, "target": aid, "etype": "hierarchy"}})

        cleared = {e["payload"].get("what") for e in evs if e["type"] == "blocker_cleared"}
        for i, e in enumerate([e for e in evs if e["type"] == "blocker"]):
            p = e["payload"]
            if p.get("what") in cleared:
                continue
            bid = "blocker:%d" % i
            target = ("phase:" + p["blocks"]) if p.get("blocks") in PIPELINE else "orchestrator"
            nodes.append({"data": {"id": bid, "label": p.get("what", "blocker"), "kind": "blocker",
                                   "status": "open", "blocks": p.get("blocks")}})
            edges.append({"data": {"source": bid, "target": target, "etype": "hierarchy"}})

        g = gates.pending_gate(d, run_id)
        if g:
            gid = "gate:" + g
            existing_ids = [n["data"]["id"] for n in nodes]
            if gid not in existing_ids:
                nodes.append({"data": {"id": gid, "label": "awaiting review: " + g, "kind": "gate",
                                       "status": "awaiting", "gate": g}})
                edges.append({"data": {"source": gid, "target": "phase:" + g if ("phase:" + g) in
                                       existing_ids else "orchestrator", "etype": "flow"}})
        return {"nodes": nodes, "edges": edges}

    def evidence(self, run_id: str) -> dict:
        paths = self._paths(run_id)
        state = self._load_state(run_id)
        reg = AgentRegistry(paths["agents_db"])
        tickets = TicketStore(paths["tickets_db"])
        bundle = build_evidence(state, reg, tickets)
        ok, reasons = verify_evidence(bundle)
        return {"verified": ok, "reasons": reasons, "bundle": bundle}
