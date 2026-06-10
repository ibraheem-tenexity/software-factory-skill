"""The SF_RUNTIME=opencode launch path: opencode argv, config isolation env, per-run runtime
pinning, monolithic prompts, and the opencode workspace contract. The claude path's own tests
(test_console.py) stay green because the default runtime is claude."""
import json
import os

from software_factory.console import (
    Console, RunRequest, make_prompt_stage1, make_prompt_stage3,
)

KIMI = "openrouter/moonshotai/kimi-k2.6"
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
