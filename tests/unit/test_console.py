"""The operator console: turn a one-line app request into a headless factory run, expose
live status, and surface the deployed URL. The launcher is injected so tests never spawn a
real `claude` process.

This is the harness around the skill — it launches the skill and reads back the skill's own
artifacts; it does not do the building itself.
"""
from software_factory.console import Console, RunRequest, make_prompt, run_paths
from software_factory.agents import AgentRegistry
from software_factory.budget import Usage


class FakeLauncher:
    def __init__(self):
        self.argv = None
        self.env = None

    def __call__(self, argv, env=None, log_path=None):
        self.argv = argv
        self.env = env or {}
        self.log_path = log_path
        return {"pid": 1234}


def console(tmp_path, launcher):
    ids = iter(["run-xyz"])
    return Console(str(tmp_path), launch=launcher, new_id=lambda: next(ids))


def test_make_prompt_invokes_the_skill_with_run_id_target_and_budget():
    req = RunRequest(description="a guestbook app", context="dark theme", budget=100.0, target="railway")
    p = make_prompt(req, "run-xyz", runs_dir="/runs")
    assert "software-factory" in p          # explicit, deterministic invocation
    assert "run-xyz" in p
    assert "railway" in p
    assert "100" in p
    assert "guestbook" in p
    assert "/runs/run-xyz" in p             # tells the orchestrator where to write artifacts


def test_start_run_stamps_proof_marker_and_launches_headless_claude(tmp_path):
    launcher = FakeLauncher()
    c = console(tmp_path, launcher)
    run_id = c.start_run(RunRequest(description="a guestbook app", target="railway"))

    assert run_id == "run-xyz"
    # headless claude was launched with our prompt
    assert launcher.argv is not None
    assert "claude" in launcher.argv[0]
    assert any("software-factory" in a for a in launcher.argv)

    # the run is stamped at launch: this is the receipt of intent (teeth are in verify_evidence)
    st = c.status(run_id)
    assert st["skill"] == "software-factory"
    assert st["description"] == "a guestbook app"
    assert st["deploy_target"] == "railway"
    assert st["phase"] == "provision"
    assert st["done"] is False


def test_status_reflects_agents_phase_and_deployed_url(tmp_path):
    launcher = FakeLauncher()
    c = console(tmp_path, launcher)
    run_id = c.start_run(RunRequest(description="guestbook", target="railway"))

    # simulate the skill making progress in the SAME artifact locations the console reads
    paths = run_paths(str(tmp_path), run_id)
    reg = AgentRegistry(paths["agents_db"], clock=lambda: 1)
    reg.spawn("a1", run_id, 1, "build", "claude-opus-4-8")
    reg.record("a1", outcome="real_diff", usage=Usage("claude-opus-4-8", output_tokens=4000),
               cost_usd=0.42, pr=7, diff_lines=120)

    state = c._load_state(run_id)
    state.phase = "done"
    state.deploy_url = "https://guestbook.up.railway.app"
    state.spent_usd = 0.42
    state.save()

    st = c.status(run_id)
    assert st["phase"] == "done"
    assert st["done"] is True
    assert st["deploy_url"] == "https://guestbook.up.railway.app"
    assert st["agents"]["spawned"] == 1
    assert st["agents"]["done"] == 1


SECRET = "rwt_super_secret_token_value_123"


def test_byo_railway_token_is_passed_as_env_not_in_prompt_or_argv(tmp_path):
    launcher = FakeLauncher()
    c = console(tmp_path, launcher)
    c.start_run(RunRequest(description="guestbook", target="railway",
                           credentials={"RAILWAY_TOKEN": SECRET}))
    # injected into the child env...
    assert launcher.env["RAILWAY_TOKEN"] == SECRET
    # ...and NOWHERE in the command line (argv is logged / visible in process lists)
    assert all(SECRET not in str(a) for a in launcher.argv)


def test_credentials_are_never_written_to_disk(tmp_path):
    launcher = FakeLauncher()
    c = console(tmp_path, launcher)
    run_id = c.start_run(RunRequest(description="guestbook", target="railway",
                                    credentials={"RAILWAY_TOKEN": SECRET}))
    # scan every file under the runs dir — the token value must not appear anywhere
    import os
    for root, _, files in os.walk(str(tmp_path)):
        for fn in files:
            with open(os.path.join(root, fn), "rb") as f:
                assert SECRET.encode() not in f.read(), f"secret leaked into {fn}"
    # but the run records WHICH creds were provided (names only) for the live view
    assert "RAILWAY_TOKEN" in c.status(run_id)["creds_provided"]


def test_status_and_evidence_never_expose_secret_values(tmp_path):
    launcher = FakeLauncher()
    c = console(tmp_path, launcher)
    run_id = c.start_run(RunRequest(description="guestbook", target="railway",
                                    credentials={"RAILWAY_TOKEN": SECRET}))
    import json
    assert SECRET not in json.dumps(c.status(run_id))
    assert SECRET not in json.dumps(c.evidence(run_id))


def test_empty_credentials_are_ignored(tmp_path):
    launcher = FakeLauncher()
    c = console(tmp_path, launcher)
    run_id = c.start_run(RunRequest(description="guestbook", credentials={"RAILWAY_TOKEN": ""}))
    assert c.status(run_id)["creds_provided"] == []
    assert "RAILWAY_TOKEN" not in launcher.env


def test_run_output_is_captured_to_a_readable_log(tmp_path):
    launcher = FakeLauncher()
    c = console(tmp_path, launcher)
    run_id = c.start_run(RunRequest(description="guestbook"))
    # the launcher is told where to capture the run's stdout/stderr
    assert launcher.log_path.endswith("run.log")
    # and read_log surfaces whatever lands there
    import os
    with open(launcher.log_path, "w") as f:
        f.write("provision: checking creds\nhello from claude\n")
    assert "hello from claude" in c.read_log(run_id)


def test_status_reports_workspace_lifecycle(tmp_path):
    from software_factory import workspace
    launcher = FakeLauncher()
    c = console(tmp_path, launcher)
    run_id = c.start_run(RunRequest(description="guestbook"))
    # not created yet by the (faked) skill -> pending
    assert c.status(run_id)["workspace"] == "pending"

    ws = workspace.create(str(tmp_path), run_id)   # skill provisions it
    assert c.status(run_id)["workspace"] == "active"

    # terminal + torn down -> cleaned
    st = c._load_state(run_id); st.phase = "done"; st.deploy_url = "https://x"; st.save()
    workspace.destroy(ws, runs_dir=str(tmp_path))
    assert c.status(run_id)["workspace"] == "cleaned"


def test_evidence_verifies_the_run_was_really_built_by_the_skill(tmp_path):
    launcher = FakeLauncher()
    c = console(tmp_path, launcher)
    run_id = c.start_run(RunRequest(description="guestbook", target="railway"))

    paths = run_paths(str(tmp_path), run_id)
    reg = AgentRegistry(paths["agents_db"], clock=lambda: 1)
    reg.spawn("a1", run_id, 1, "build", "claude-opus-4-8")
    reg.record("a1", outcome="real_diff", cost_usd=0.42, pr=7, diff_lines=120)
    from software_factory.tickets import TicketStore
    ts = TicketStore(paths["tickets_db"])
    tid = ts.create_ticket("guestbook", acceptance="a", dod="d", wave=1)
    ts.mark_done(tid, pr=7, diff_lines=120)

    state = c._load_state(run_id)
    state.phase = "done"; state.deploy_url = "https://g.up.railway.app"; state.spent_usd = 0.42
    state.save()

    ev = c.evidence(run_id)
    assert ev["verified"] is True
    assert ev["reasons"] == []
    assert ev["bundle"]["skill"] == "software-factory"
