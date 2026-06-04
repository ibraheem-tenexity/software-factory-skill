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

from . import events, gates, streamlog
from .agents import AgentRegistry
from .evidence import build_evidence, verify_evidence
from .runstate import JsonFileStore, RunState
from .tickets import TicketStore

SKILL_VERSION = "0.0.1"

# The pipeline the run advances through (matches SKILL.md). "wait-for-deps" is the phase that
# waits on infra/dependencies and surfaces blockers until they're ready.
PIPELINE = ["provision", "research", "architect", "wait-for-deps", "tickets", "build", "deploy", "test"]
PIPELINE_LABELS = {"wait-for-deps": "wait for deps"}

# The named agent roster per phase (from the skill). The graph ALWAYS shows these so the canvas
# reflects the swarm even before/without the live run emitting agent_spawned — they go
# planned → running → done as agent_spawned/agent_done events arrive. (build/fix agents are dynamic.)
PHASE_AGENTS = {
    "research": [("horizon", "HORIZON"), ("archivist", "ARCHIVIST"), ("vanguard", "VANGUARD"), ("chroma", "CHROMA")],
    "architect": [("architect", "software-architect")],
}


@dataclass
class RunRequest:
    description: str
    context: str = ""
    budget: float = 100.0
    target: str = "railway"
    # Secret env (e.g. {"RAILWAY_TOKEN": "..."}) for a bring-your-own run. Injected into the
    # headless child's environment only — never persisted, never put on the command line.
    credentials: dict = field(default_factory=dict)
    # Uploaded context files [{"name","content_b64"}] (txt/pdf/docx) — written to the run's
    # input/ dir for the extract phase to read.
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


def make_prompt(req: RunRequest, run_id: str, runs_dir: str) -> str:
    """Imperative runbook so the headless run EXECUTES the full pipeline instead of wandering."""
    base = os.path.join(runs_dir, run_id)
    ctx = f"\n\nContext / detailed input:\n{req.context}" if req.context else ""
    service = f"sf-{run_id}"
    emit = f"python -m software_factory.events emit {runs_dir} {run_id}"
    return (
        f"Use the **software-factory** skill to build, deploy, and browser-verify this customer "
        f"solution, FULLY AUTONOMOUSLY — never wait on a human.\n"
        f"run_id={run_id}. runs_dir={runs_dir}. Budget ${req.budget:.0f} (HARD cutoff). "
        f"Deploy target: {req.target}.\n\n"
        f"Read SKILL.md and the phases/ files. Execute these phases IN ORDER, and at each one run "
        f"`{emit} phase '{{\"name\":\"<phase>\"}}'` so the canvas shows progress.\n"
        f"ORCHESTRATION MODEL: you do NOT do the work yourself. From the start, ruflo is the swarm "
        f"runtime — for each task type start a ruflo swarm (`swarm_init`) and `agent_spawn` agents into "
        f"it, then coordinate + judge. Each agent: emit `agent_spawned {{\"id\":..,\"role\":..,\"phase\":..}}` "
        f"on spawn and `agent_done {{\"id\":..,\"outcome\":..}}` on result; it pulls/writes via ruflo (memory); "
        f"and it attributes any file it creates to itself via `emit artifact {{...,\"agent\":\"<its id>\"}}` so "
        f"the artifact shows as that agent's child on the canvas.\n"
        f"1. extract  — the console already saved the input under {base}/input/ and recorded the input "
        f"artifact (do NOT emit another). Read everything in {base}/input/ (txt/pdf/docx; install a "
        f"parser like python-docx / pdfplumber if needed) and extract it to usable text.\n"
        f"2. provision — `creds.check_all`; `GitHub.create_repo`; `Budget(100)`; `workspace.create`; seed ruflo.\n"
        f"3. research (PIPELINE 1) — `swarm_init` a research swarm, then `agent_spawn` the named agents IN "
        f"ORDER (each emits agent_spawned/agent_done + attributes its artifacts): "
        f"HORIZON(pm.lead: scope) → ARCHIVIST(reuse scan via ruflo) → VANGUARD(domain-expert: "
        f">=2 solution paths + REQUIRED WebSearch/WebFetch, >=3 real products WITH URLs) → "
        f"CHROMA(design.lead: screens + happy-flow journey) → HORIZON writes PRD.md with acceptance "
        f"criteria (given/when/then) + ticket seeds; commit; `{emit} artifact '{{\"title\":\"PRD\",\"path\":\"workspace/<repo>/PRD.md\",\"kind\":\"prd\"}}'`. "
        f"Do NOT advance until `artifacts.prd_is_complete(PRD.md)` passes.\n"
        f"4. architect (END OF PIPELINE 1) — the software-architect agent produces architecture.md "
        f"(fewest services; data model; dependency + required-token list) + a Mermaid diagram rendered "
        f"to architecture.svg via `diagram.render`; commit + emit both. PIPELINE-1 GATE: do NOT start "
        f"pipeline 2 until `artifacts.verify(run_dir, [PRD.md, architecture.md, architecture.svg])` passes.\n"
        f"5. wait-for-deps (PIPELINE 2) — provision infra (the Railway service '{service}', Supabase, "
        f"Vercel if used) and WAIT for readiness; `{emit} blocker '{{...}}'` for anything not ready.\n"
        f"6. tickets   — `TicketStore.create_ticket` in waves with acceptance + DoD (from PRD ticket seeds).\n"
        f"7. build     — per ticket: spawn a build agent (pull from ruflo), merge only via "
        f"`merge_if_green`, `mark_done`; record precedent via `memory.record_precedent`. No-op = retry.\n"
        f"8. deploy    — DEPLOY ISOLATION (critical): create + deploy to the dedicated service "
        f"'{service}' (`railway add --service {service}` then `railway up --service {service}`). "
        f"NEVER run a bare `railway up`, and NEVER deploy to the factory console's own service — that "
        f"would overwrite the console. `deploy.healthy(url)` must pass; `{emit} deployed '{{\"url\":...}}'`.\n"
        f"9. test      — drive the live URL with Playwright; `gate.happy_flow_passed`. Green => `{emit} done` "
        f"=> DONE. Red => fix agents => redeploy => re-test.\n"
        f"10. teardown — `workspace.destroy` on any terminal state; proof + events survive at the base.\n\n"
        f"Write run state and telemetry under {base}/ (runstate JsonFileStore at {base}; agents.db and "
        f"tickets.db there). Stamp the proof marker at provision.\n"
        f"App: {req.description}{ctx}"
    )


def _default_launch(argv: list[str], env: dict, log_path: str | None = None) -> Any:
    import subprocess
    import sys
    import threading

    # Tee the headless run's output to BOTH the per-run log file (for the /log endpoint) AND
    # the container's stdout, prefixed by run id, so it streams into the platform's live logs
    # (e.g. Railway). Secrets ride in env, never argv.
    proc = subprocess.Popen(
        argv, env={**os.environ, **env},
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, bufsize=1, text=True,
    )
    prefix = f"[{os.path.basename(os.path.dirname(log_path))}] " if log_path else ""

    def _pump():
        logf = open(log_path, "a") if log_path else None
        try:
            for line in proc.stdout:
                sys.stdout.write(prefix + line)   # → container stdout → Railway live logs
                sys.stdout.flush()
                if logf:
                    logf.write(line)              # → run.log → /api/runs/<id>/log
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

        # Persist any uploaded context files (txt/pdf/docx) to the run's input/ dir for the
        # extract phase. Basename-only — never let a filename escape the input dir.
        import base64
        inputs = []
        for f in (req.context_files or []):
            name = os.path.basename(f.get("name") or "upload")
            if not name or not f.get("content_b64"):
                continue
            os.makedirs(paths["input_dir"], exist_ok=True)
            with open(os.path.join(paths["input_dir"], name), "wb") as out:
                out.write(base64.b64decode(f["content_b64"]))
            inputs.append("input/" + name)
        # Persist a pasted description as a real file too, so the "input" artifact is never a hollow
        # placeholder — the canvas shows the actual context, and the extract phase reads it.
        if (req.description or "").strip():
            os.makedirs(paths["input_dir"], exist_ok=True)
            with open(os.path.join(paths["input_dir"], "context.txt"), "w") as cf:
                cf.write(req.description)
            inputs.append("input/context.txt")
        for rel in inputs:
            events.emit(self._runs_dir, run_id, "artifact",
                        {"title": "input", "path": rel, "kind": "context"})

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

    def _full_log(self, run_id: str) -> str:
        p = os.path.join(self._paths(run_id)["base"], "run.log")
        if not os.path.exists(p):
            return ""
        with open(p, "r", errors="replace") as f:
            return f.read()

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
            # Spec 2: live cost from the real claude stream, falling back to recorded state.
            "spent_usd": streamlog.cost_usd(self._full_log(run_id)) or state.spent_usd,
            "creds_provided": state.creds_provided,  # names only, never values
            "byo_railway": "RAILWAY_TOKEN" in (state.creds_provided or []),
            "workspace": self._workspace_state(run_id, state.phase),
            "agents": reg.counts(run_id),
            "no_op_rate": reg.no_op_rate(run_id),
        }

    def list_runs(self) -> list[dict]:
        """All launched runs (newest first) so the UI can reconnect after a reload (spec 3)."""
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
            })
        runs.sort(key=lambda r: os.path.getmtime(os.path.join(self._runs_dir, r["run_id"])), reverse=True)
        return runs

    def events(self, run_id: str) -> list:
        return events.read_events(self._runs_dir, run_id)

    def continue_run(self, run_id: str, gate: str) -> dict:
        """Dashboard 'Continue' — clear a review gate so the paused run proceeds."""
        gates.clear_gate(self._runs_dir, run_id, gate)
        return {"cleared": gate}

    def artifact(self, run_id: str, path: str) -> dict:
        """Read a committed artifact (PRD.md, architecture.svg, …) for the inspector. Path-safe."""
        base = os.path.realpath(self._paths(run_id)["base"])
        full = os.path.realpath(os.path.join(base, path))
        if os.path.commonpath([full, base]) != base or not os.path.isfile(full):
            return {"error": "not found", "path": path}
        with open(full, "r", errors="replace") as f:
            return {"path": path, "content": f.read()[:200000]}

    def graph(self, run_id: str) -> dict:
        """Cytoscape elements: orchestrator + the pipeline, with agents, artifacts, blockers and
        the pending review gate folded in from events + the claude stream (specs 4 + the canvas)."""
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
                                   "kind": "phase", "status": st}})
            edges.append({"data": {"source": prev, "target": pid}})
            prev = pid

        # Agents: start from the known per-phase roster (always visible as "planned"), then upgrade
        # from agent_spawned/agent_done events; build/fix agents come in dynamically; Task subagents
        # in the claude stream are a fallback.
        agent_info = {}  # agent_id -> {label, phase, status}
        for ph, roster in PHASE_AGENTS.items():
            for aid, role in roster:
                agent_info[aid] = {"label": role, "phase": ph, "status": "planned"}
        for e in evs:
            p = e.get("payload") or {}
            if e["type"] == "agent_spawned":
                aid = p.get("id") or p.get("role") or "agent"
                cur = agent_info.get(aid, {})
                agent_info[aid] = {"label": p.get("role") or cur.get("label") or aid,
                                   "phase": p.get("phase") or cur.get("phase"), "status": "running"}
            elif e["type"] == "agent_done":
                aid = p.get("id") or p.get("role")
                if aid in agent_info:
                    out = p.get("outcome")
                    agent_info[aid]["status"] = "done" if out in (None, "real_diff", "success") else out
        for a in streamlog.agents(self._full_log(run_id)):
            agent_info.setdefault(a["id"], {"label": a["label"], "phase": None, "status": a["status"]})
        agent_ids = set()
        for aid, info in agent_info.items():
            nid = "agent:" + aid; agent_ids.add(nid)
            nodes.append({"data": {"id": nid, "label": info["label"], "kind": "agent", "status": info["status"]}})
            src = "phase:" + info["phase"] if info.get("phase") in PIPELINE else "orchestrator"
            edges.append({"data": {"source": src, "target": nid}})  # orchestrator/phase spawns the agent

        for i, e in enumerate([e for e in evs if e["type"] == "artifact"]):
            p = e["payload"]; aid = "artifact:%d" % i
            path = p.get("path") or ""
            if path.startswith("http"):
                status = "created"   # a link (repo / deployed URL), not a local file to verify
            else:
                # Honesty: a file artifact that doesn't actually exist is "missing", not "created".
                status = "created" if (path and "content" in self.artifact(run_id, path)) else "missing"
            nodes.append({"data": {"id": aid, "label": p.get("title", "artifact"), "kind": "artifact",
                                   "path": path, "status": status, "url": path if path.startswith("http") else None}})
            # The artifact is a CHILD of the agent that created it (falls back to orchestrator).
            owner = "agent:" + p["agent"] if p.get("agent") and ("agent:" + p["agent"]) in agent_ids else "orchestrator"
            edges.append({"data": {"source": owner, "target": aid}})

        cleared = {e["payload"].get("what") for e in evs if e["type"] == "blocker_cleared"}
        for i, e in enumerate([e for e in evs if e["type"] == "blocker"]):
            p = e["payload"]
            if p.get("what") in cleared:
                continue
            bid = "blocker:%d" % i
            target = ("phase:" + p["blocks"]) if p.get("blocks") in PIPELINE else "orchestrator"
            nodes.append({"data": {"id": bid, "label": p.get("what", "blocker"), "kind": "blocker",
                                   "status": "open", "blocks": p.get("blocks")}})
            edges.append({"data": {"source": bid, "target": target}})

        g = gates.pending_gate(d, run_id)
        if g:
            gid = "gate:" + g
            nodes.append({"data": {"id": gid, "label": "awaiting review: " + g, "kind": "gate",
                                   "status": "awaiting", "gate": g}})
            edges.append({"data": {"source": gid, "target": "phase:" + g if ("phase:" + g) in
                                   [n["data"]["id"] for n in nodes] else "orchestrator"}})
        return {"nodes": nodes, "edges": edges}

    def evidence(self, run_id: str) -> dict:
        paths = self._paths(run_id)
        state = self._load_state(run_id)
        reg = AgentRegistry(paths["agents_db"])
        tickets = TicketStore(paths["tickets_db"])
        bundle = build_evidence(state, reg, tickets)
        ok, reasons = verify_evidence(bundle)
        return {"verified": ok, "reasons": reasons, "bundle": bundle}
