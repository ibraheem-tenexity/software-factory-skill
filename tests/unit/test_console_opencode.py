"""The SF_RUNTIME=opencode launch path: opencode argv, config isolation env, per-run runtime
pinning, monolithic prompts, and the opencode workspace contract. The claude path's own tests
(test_console.py) stay green because the default runtime is claude."""
import json
import os

from software_factory.console import (
    Console, RunRequest, make_prompt_stage1, make_prompt_stage3,
)

KIMI = "openrouter/moonshotai/kimi-k2.7-code"
SECRET = "rwt_super_secret_token_value_123"


class FakeLauncher:
    def __init__(self):
        self.argv = None
        self.env = None

    def __call__(self, argv, env=None, log_path=None, cwd=None):
        self.argv = argv
        self.env = env or {}
        self.log_path = log_path
        self.cwd = cwd
        return {"pid": 1234}


def console(tmp_path, launcher):
    ids = iter(["run-oc"])
    return Console(str(tmp_path), launch=launcher, new_id=lambda: next(ids),
                   extract=lambda path: "# extracted")


def test_start_run_launches_opencode_with_kimi_and_no_max_turns(tmp_path, monkeypatch):
    monkeypatch.setenv("SF_RUNTIME", "opencode")
    launcher = FakeLauncher()
    c = console(tmp_path, launcher)
    c.start_run(RunRequest(description="a guestbook app", target="railway"))

    assert launcher.argv[0] == "opencode"
    assert launcher.argv[1] == "run"
    assert "--dangerously-skip-permissions" in launcher.argv
    assert launcher.argv[launcher.argv.index("--model") + 1] == KIMI
    assert "--agent" in launcher.argv and "factory" in launcher.argv
    assert "--max-turns" not in launcher.argv          # the steps cap lives in opencode.json
    assert "--format" in launcher.argv and "json" in launcher.argv


def test_opencode_launch_env_isolates_global_config_and_external_skills(tmp_path, monkeypatch):
    monkeypatch.setenv("SF_RUNTIME", "opencode")
    launcher = FakeLauncher()
    c = console(tmp_path, launcher)
    c.start_run(RunRequest(description="guestbook", target="railway"))

    # ~/.config/opencode (peer MCPs, global instructions) must NEVER leak into stage runs
    assert launcher.env["XDG_CONFIG_HOME"].startswith(launcher.cwd)
    assert launcher.env["XDG_DATA_HOME"].startswith(launcher.cwd)   # global auth.json hidden
    assert launcher.env["OPENCODE_DISABLE_CLAUDE_CODE_SKILLS"] == "1"
    assert launcher.env["OPENCODE_DISABLE_EXTERNAL_SKILLS"] == "1"
    # Popen doesn't update PWD; OpenCode trusts it for project resolution (live-debugged:
    # a stale PWD bound the session to the repo root and crashed createUserMessage)
    assert launcher.env["PWD"] == launcher.cwd


def test_opencode_secrets_stay_in_env_never_argv(tmp_path, monkeypatch):
    monkeypatch.setenv("SF_RUNTIME", "opencode")
    launcher = FakeLauncher()
    c = console(tmp_path, launcher)
    c.start_run(RunRequest(description="guestbook", target="railway",
                           credentials={"RAILWAY_TOKEN": SECRET}))
    assert launcher.env["RAILWAY_TOKEN"] == SECRET
    assert all(SECRET not in str(a) for a in launcher.argv)


def test_runtime_is_pinned_on_the_run_not_the_env(tmp_path, monkeypatch):
    # started under opencode -> stage 2 still opencode even after the env flips back
    monkeypatch.setenv("SF_RUNTIME", "opencode")
    launcher = FakeLauncher()
    c = console(tmp_path, launcher)
    run_id = c.start_run(RunRequest(description="guestbook", target="railway"))
    monkeypatch.delenv("SF_RUNTIME")

    state = c._load_state(run_id)
    assert state.runtime == "opencode"
    state.stage1_done = True
    state.save()
    c.start_stage2(run_id)
    assert launcher.argv[0] == "opencode"


def test_default_runtime_is_claude(tmp_path):
    launcher = FakeLauncher()
    c = console(tmp_path, launcher)
    run_id = c.start_run(RunRequest(description="guestbook", target="railway"))
    assert c._load_state(run_id).runtime == "claude"
    assert "claude" in launcher.argv[0]


def test_opencode_workspace_gets_opencode_json_not_claude_settings(tmp_path, monkeypatch):
    monkeypatch.setenv("SF_RUNTIME", "opencode")
    monkeypatch.setenv("SF_MAX_TURNS", "150")
    launcher = FakeLauncher()
    c = console(tmp_path, launcher)
    c.start_run(RunRequest(description="guestbook", target="railway"))

    ws = launcher.cwd
    cfg = json.loads(open(os.path.join(ws, "opencode.json")).read())
    assert "playwright" in cfg["mcp"]
    assert cfg["mcp"]["playwright"]["type"] == "local"
    assert cfg["agent"]["factory"]["steps"] == 150           # SF_MAX_TURNS -> steps cap
    assert cfg["instructions"] == ["SKILL.md"]               # contract injected ambiently
    assert cfg["permission"]["doom_loop"] == "allow"         # 'ask' would hang headless
    assert not os.path.exists(os.path.join(ws, "claude-settings.json"))
    # .mcp.json still written for BOTH runtimes — mcp_health hard-gates on it
    assert "playwright" in json.loads(open(os.path.join(ws, ".mcp.json")).read())["mcpServers"]


def test_opencode_prompts_are_monolithic_with_logical_agents():
    req = RunRequest(description="x")
    p1 = make_prompt_stage1(req, "run-1", "/runs", runtime="opencode")
    assert "MONOLITHIC" in p1 and "ORCHESTRATOR-ONLY" not in p1
    p3 = make_prompt_stage3(req, "run-1", "/runs", runtime="opencode")
    assert "TicketStore.claim" in p3                          # claim with the logical-agent id
    assert "one native Task sub-agent PER ticket" not in p3
    # claude prompts unchanged
    assert "ORCHESTRATOR-ONLY" in make_prompt_stage1(req, "run-1", "/runs")


def test_graph_orchestrator_label_reflects_runtime(tmp_path, monkeypatch):
    monkeypatch.setenv("SF_RUNTIME", "opencode")
    launcher = FakeLauncher()
    c = console(tmp_path, launcher)
    run_id = c.start_run(RunRequest(description="guestbook", target="railway"))
    g = c.graph(run_id)
    orch = next(n for n in g["nodes"] if n["data"]["id"] == "orchestrator")
    assert orch["data"]["label"].startswith("Kimi")


def test_request_runtime_overrides_env_default(tmp_path, monkeypatch):
    # The UI picker sends runtime per-request; it must beat the server's SF_RUNTIME default.
    monkeypatch.setenv("SF_RUNTIME", "claude")
    launcher = FakeLauncher()
    c = console(tmp_path, launcher)
    run_id = c.start_run(RunRequest(description="guestbook", runtime="opencode"))
    assert c._load_state(run_id).runtime == "opencode"
    assert launcher.argv[0] == "opencode"


def test_empty_request_runtime_falls_back_to_env(tmp_path, monkeypatch):
    monkeypatch.setenv("SF_RUNTIME", "opencode")
    launcher = FakeLauncher()
    c = console(tmp_path, launcher)
    run_id = c.start_run(RunRequest(description="guestbook"))
    assert c._load_state(run_id).runtime == "opencode"


def test_list_runs_flags_budget_stopped(tmp_path):
    # A budget-stopped run must surface as stopped, never as live/active (the
    # frozen-ghosts-shown-green UI confusion).
    from software_factory.db import RunDB
    from software_factory.console import run_paths
    launcher = FakeLauncher()
    c = console(tmp_path, launcher)
    rid = c.start_run(RunRequest(description="x"))
    RunDB(run_paths(str(tmp_path), rid)["db"]).add_blocker(
        "Budget cap $0.01 reached (spent $2.66) — stage stopped.", blocks="budget")
    runs = {r["run_id"]: r for r in c.list_runs()}
    assert runs[rid]["budget_stopped"] is True


def test_lingering_opencode_proc_with_completed_session_counts_as_finished(tmp_path, monkeypatch):
    # run-45b8c4d5 wedge: opencode procs LINGER after session-complete; a live handle must not
    # block auto-resume when the log shows step_finish reason=stop and 5+ min of silence.
    import json as _json, os as _os, time as _time
    monkeypatch.setenv("SF_RUNTIME", "opencode")

    class LiveProc:
        def poll(self): return None   # zombie: never exits

    ids = iter(["run-zz"])
    c = Console(str(tmp_path), launch=lambda *a, **k: LiveProc(), new_id=lambda: next(ids),
                extract=lambda p: "# x")
    rid = c.start_run(RunRequest(description="x"))
    log = _os.path.join(str(tmp_path), rid, "run.log")
    with open(log, "w") as f:
        f.write(_json.dumps({"type": "step_finish", "part": {"type": "step-finish",
                "reason": "stop", "cost": 0.1}}) + "\n")
    old = _time.time() - 400
    _os.utime(log, (old, old))
    assert c.stage_finished(rid) is True

    # mid-flight pause (reason=tool-calls) must NOT count as finished even when idle
    with open(log, "w") as f:
        f.write(_json.dumps({"type": "step_finish", "part": {"type": "step-finish",
                "reason": "tool-calls", "cost": 0.1}}) + "\n")
    _os.utime(log, (old, old))
    assert c.stage_finished(rid) is False


def test_claude_runtime_live_handle_never_false_finishes(tmp_path):
    # A claude stage quietly inside a long tool call must never false-finish into a
    # concurrent relaunch (SPEC §1 double-orchestrator race).
    import os as _os, time as _time

    class LiveProc:
        def poll(self): return None

    ids = iter(["run-cl"])
    c = Console(str(tmp_path), launch=lambda *a, **k: LiveProc(), new_id=lambda: next(ids),
                extract=lambda p: "# x")
    rid = c.start_run(RunRequest(description="x"))
    log = _os.path.join(str(tmp_path), rid, "run.log")
    open(log, "w").write("{}\n")
    old = _time.time() - 4000
    _os.utime(log, (old, old))
    assert c.stage_finished(rid) is False


def test_deploy_phase_never_skipped_when_deploy_artifact_exists(tmp_path):
    # run-45b8c4d5 canvas lie #1: the app was LIVE while 'deploy' rendered skipped —
    # a deploy-kind artifact IS deploy activity AND deploy's closing signal.
    from software_factory.db import RunDB
    from software_factory.console import run_paths
    c = console(tmp_path, FakeLauncher())
    rid = c.start_run(RunRequest(description="x"))
    db = RunDB(run_paths(str(tmp_path), rid)["db"])
    db.set_phase("build", "active")
    db.record_artifact("Live URL", "https://app.example.up.railway.app", kind="deploy")
    phases = c.derive_phases(rid)
    assert phases["deploy"] == "done"          # not 'skipped'
    assert phases["build"] == "active"


def test_fix_loop_bounces_active_back_to_build(tmp_path):
    # canvas lie #2: during a test->build fix loop the canvas must show build active again,
    # with test pending (it will re-run), not frozen on the furthest index.
    import time as _t
    from software_factory.db import RunDB
    from software_factory.console import run_paths
    c = console(tmp_path, FakeLauncher())
    rid = c.start_run(RunRequest(description="x"))
    db = RunDB(run_paths(str(tmp_path), rid)["db"])
    db.set_phase("build", "active"); _t.sleep(0.01)
    db.set_phase("test", "active"); _t.sleep(0.01)
    db.set_phase("build", "active")            # the loop: back to build
    phases = c.derive_phases(rid)
    assert phases["build"] == "active"
    assert phases["test"] == "pending"         # ran, didn't close, will run again


def test_mark_done_accepts_commit_sha_provenance(tmp_path):
    # run-45b8c4d5 finding: monolithic agents commit directly to main (no PRs) — a commit
    # sha is first-class provenance; hollow closes still refused.
    import pytest
    from software_factory.tickets import TicketStore, HollowWorkError
    ts = TicketStore(str(tmp_path / "t.db"))
    tid = ts.create_ticket("x", "acceptance", "dod", 1)
    ts.claim(tid, "ticket-1-build")
    ts.mark_done(tid, "a1b2c3d4e5f6a7b8", 42)
    assert ts.done_tickets()[0].pr == "a1b2c3d4e5f6a7b8"
    tid2 = ts.create_ticket("y", "a", "d", 1)
    with pytest.raises(HollowWorkError):
        ts.mark_done(tid2, "abc", 42)          # too short to be a sha — hollow
    with pytest.raises(HollowWorkError):
        ts.mark_done(tid2, "a1b2c3d4e5f6a7b8", 0)   # empty diff still refused


def test_evidence_opencode_run_corroborated_by_spend_not_agent_cost(tmp_path):
    # Monolithic agents can't see their own cost; the run-level spend corroborates model work.
    from software_factory.evidence import verify_evidence
    bundle = {"runtime": "opencode", "skill": "software-factory", "skill_version": "0.0.1",
              "spent_usd": 12.5, "deploy_url": "https://x",
              "agents": {"counts": {"spawned": 3}, "total_cost_usd": 0.0},
              "done_tickets": [{"id": 1, "pr": "a1b2c3d4e5f6a7b8", "diff_lines": 10}]}
    ok, reasons = verify_evidence(bundle)
    assert not any("cost is zero" in r for r in reasons)
    assert not any("without provenance" in r for r in reasons)


def test_sf_swarm_wraps_stage3_in_the_driver_but_not_stages_1_2(tmp_path, monkeypatch):
    # §9 swarm build mode: stage 3's tracked process is the swarm driver, which receives
    # the EXACT opencode argv after `--` to exec once the swarm phase ends. Stages 1-2
    # (and SF_SWARM unset) launch opencode directly, unchanged.
    import sys as _sys
    monkeypatch.setenv("SF_RUNTIME", "opencode")
    monkeypatch.setenv("SF_SWARM", "1")
    launcher = FakeLauncher()
    c = console(tmp_path, launcher)
    rid = c.start_run(RunRequest(description="guestbook", target="railway"))
    assert launcher.argv[0] == "opencode"                    # stage 1: no driver wrap

    st = c._load_state(rid)
    st.stage1_done = True; st.stage2_done = True; st.deps_satisfied = True
    st.save()
    c.start_stage3(rid)
    argv = launcher.argv
    assert argv[0] == _sys.executable
    assert argv[1:3] == ["-m", "software_factory.swarm_stage3"]
    assert "--budget" in argv and "--model" in argv
    tail = argv[argv.index("--") + 1:]
    assert tail[0] == "opencode" and "--dangerously-skip-permissions" in tail
    assert launcher.env.get("PYTHONPATH")                    # driver importable as a child
    assert launcher.env["PWD"] == launcher.cwd               # §9 hygiene still applies


def test_without_sf_swarm_stage3_launches_opencode_directly(tmp_path, monkeypatch):
    monkeypatch.setenv("SF_RUNTIME", "opencode")
    monkeypatch.delenv("SF_SWARM", raising=False)
    launcher = FakeLauncher()
    c = console(tmp_path, launcher)
    rid = c.start_run(RunRequest(description="guestbook", target="railway"))
    st = c._load_state(rid)
    st.stage1_done = True; st.stage2_done = True; st.deps_satisfied = True
    st.save()
    c.start_stage3(rid)
    assert launcher.argv[0] == "opencode"
    assert "software_factory.swarm_stage3" not in launcher.argv


def test_stage_finished_respects_a_live_stage3_pidfile_over_an_idle_log(tmp_path):
    # run-5b7aef7a live scar: server restart loses the process handle; the swarm driver
    # sits quiet in run.log for >2min mid-Kimi-turn; log-idle fallback said "finished" and
    # the poller relaunched a second orchestrator. A live stage3.pid must win.
    import subprocess
    import time as _time
    launcher = FakeLauncher()
    c = console(tmp_path, launcher)
    rid = "run-pid"
    base = os.path.join(str(tmp_path), rid)
    os.makedirs(base, exist_ok=True)
    log = os.path.join(base, "run.log")
    with open(log, "w") as f:
        f.write("{}\n")
    idle = _time.time() - 600
    os.utime(log, (idle, idle))                      # idle far past the 2-min grace
    p = subprocess.Popen(["bash", "-c", f"# {rid}\nsleep 30"])
    with open(os.path.join(base, "stage3.pid"), "w") as f:
        f.write(str(p.pid))
    try:
        assert c.stage_finished(rid) is False        # live driver pid = proof of life
    finally:
        p.kill()
        p.wait()
    assert c.stage_finished(rid) is True             # dead pid -> log-idle fallback


def test_stage_pid_alive_rejects_recycled_pids(tmp_path):
    launcher = FakeLauncher()
    c = console(tmp_path, launcher)
    rid = "run-pid2"
    base = os.path.join(str(tmp_path), rid)
    os.makedirs(base, exist_ok=True)
    with open(os.path.join(base, "stage3.pid"), "w") as f:
        f.write(str(os.getpid()))                    # alive, but cmdline lacks the run id
    assert c._stage_pid_alive(rid) is False


def test_budget_kill_escalates_to_sigkill_when_terminate_is_ignored(tmp_path):
    # opencode processes survive plain SIGTERM (production-confirmed by the swarm session:
    # `opencode serve` ignored SIGTERM and pkill). A budget-stopped run that keeps spending
    # is the failure mode the brake exists for — enforce_budget must escalate to kill().
    launcher = FakeLauncher()
    c = console(tmp_path, launcher)
    rid = c.start_run(RunRequest(description="x", target="railway"))

    class StubbornProc:
        def __init__(self):
            self.killed = False
        def poll(self):
            return None
        def terminate(self):
            pass                                  # ignores SIGTERM, like opencode
        def wait(self, timeout=None):
            raise TimeoutError("still alive")
        def kill(self):
            self.killed = True

    p = StubbornProc()
    c._procs[rid] = p
    st = c._load_state(rid)
    st.budget_ceiling = 0.01
    st.save()
    with open(os.path.join(str(tmp_path), rid, "run.log"), "w") as f:
        f.write(json.dumps({"type": "step_finish", "sessionID": "s",
                            "part": {"type": "step-finish", "cost": 5.0}}) + "\n")
    assert c.enforce_budget(rid) is True
    assert p.killed, "SIGTERM-immune process must be SIGKILLed"


def test_default_launch_child_owns_the_log_file_not_a_server_pipe(tmp_path):
    # run-5b7aef7a live scar: stdout piped through a server pump thread dies with the
    # server — run.log freezes and the §4 brake goes spend-blind while the orchestrator
    # keeps working. The child must write run.log through its OWN fd.
    from software_factory.console import _default_launch
    log = str(tmp_path / "run.log")
    p = _default_launch(["bash", "-c", "echo from-child; echo err-too >&2"], {}, log_path=log)
    p.wait(timeout=10)
    text = open(log).read()
    assert "from-child" in text          # stdout reaches the log with no pump alive
    assert "err-too" in text             # stderr merged, as the parsers expect
