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


def test_uploaded_context_files_are_written_to_the_run_input_dir(tmp_path):
    import base64, os
    c = console(tmp_path, FakeLauncher())
    b64 = base64.b64encode(b"EPC contract T&C brief...").decode()
    run_id = c.start_run(RunRequest(description="analyze this",
                                    context_files=[{"name": "brief.pdf", "content_b64": b64}]))
    p = os.path.join(str(tmp_path), run_id, "input", "brief.pdf")
    assert os.path.exists(p)
    assert open(p, "rb").read() == b"EPC contract T&C brief..."


def test_uploaded_filenames_are_basename_only_no_traversal(tmp_path):
    import base64, os
    c = console(tmp_path, FakeLauncher())
    b64 = base64.b64encode(b"x").decode()
    run_id = c.start_run(RunRequest(description="d",
                                    context_files=[{"name": "../../evil.txt", "content_b64": b64}]))
    assert os.path.exists(os.path.join(str(tmp_path), run_id, "input", "evil.txt"))
    assert not os.path.exists(os.path.join(str(tmp_path), "evil.txt"))


def test_make_prompt_targets_a_dedicated_service_not_the_runner(tmp_path):
    # Spec 1: the built app must deploy to its OWN service, never the runner's own.
    p = make_prompt(RunRequest(description="x", target="railway"), "run-xyz", runs_dir="/runs")
    assert "sf-run-xyz" in p           # per-run dedicated service name
    assert "never" in p.lower() and "factory" in p.lower()  # explicit don't-clobber warning


def test_status_cost_is_derived_from_the_run_log(tmp_path):
    # Spec 2: live cost comes from the real claude stream, not self-reported state.
    launcher = FakeLauncher()
    c = console(tmp_path, launcher)
    run_id = c.start_run(RunRequest(description="guestbook"))
    with open(launcher.log_path, "w") as f:
        f.write('{"type":"result","subtype":"success","total_cost_usd":0.0731}\n')
    assert c.status(run_id)["spent_usd"] == 0.0731


def test_list_runs_returns_launched_runs_for_reconnect(tmp_path):
    # Spec 3: persistence — the server can enumerate runs so the UI reconnects after reload.
    c = console(tmp_path, FakeLauncher())
    ids = []
    for i in range(2):
        c._new_id = lambda i=i: f"run-{i}"
        ids.append(c.start_run(RunRequest(description=f"app {i}")))
    listed = {r["run_id"] for r in c.list_runs()}
    assert set(ids) <= listed
    one = [r for r in c.list_runs() if r["run_id"] == "run-0"][0]
    assert one["description"] == "app 0" and "phase" in one


def test_graph_folds_pipeline_agents_artifacts_blockers_gates(tmp_path):
    from software_factory import events, gates
    launcher = FakeLauncher()
    c = console(tmp_path, launcher)
    run_id = c.start_run(RunRequest(description="guestbook"))
    d = str(tmp_path)
    # an agent (from the claude stream), an artifact, a blocker, and an open gate
    with open(launcher.log_path, "w") as f:
        f.write('{"type":"assistant","message":{"content":[{"type":"tool_use","id":"t1","name":"Task","input":{"description":"build form","subagent_type":"general-purpose"}}]}}\n')
    events.emit(d, run_id, "artifact", {"title": "PRD", "path": "PRD.md", "kind": "prd"})
    events.emit(d, run_id, "blocker", {"what": "Supabase project not ready", "blocks": "wait-for-deps"})
    events.emit(d, run_id, "awaiting_review", {"gate": "prd"})

    g = c.graph(run_id)
    kinds = {n["data"]["kind"] for n in g["nodes"]}
    assert {"orchestrator", "phase", "agent", "artifact", "blocker", "gate"} <= kinds
    # the pipeline the user defined is present as phase nodes
    phase_labels = {n["data"]["label"] for n in g["nodes"] if n["data"]["kind"] == "phase"}
    assert {"research", "architect", "wait for deps", "deploy"} <= phase_labels
    # edges connect things (orchestrator -> first phase exists)
    assert any(e["data"]["source"] == "orchestrator" for e in g["edges"])


def test_graph_marks_artifacts_missing_until_the_file_really_exists(tmp_path):
    # The "no hollow done" scar at the artifact level: an emitted artifact whose file does not
    # exist is status="missing" (red on the canvas), not a fake green "created".
    import os
    from software_factory import events
    c = console(tmp_path, FakeLauncher())
    rid = c.start_run(RunRequest(description="x"))
    events.emit(str(tmp_path), rid, "artifact", {"title": "PRD", "path": "workspace/PRD.md", "kind": "prd"})
    art = lambda: [n["data"] for n in c.graph(rid)["nodes"] if n["data"].get("path") == "workspace/PRD.md"][0]
    assert art()["status"] == "missing"                     # emitted but no file -> hollow
    os.makedirs(os.path.join(str(tmp_path), rid, "workspace"), exist_ok=True)
    open(os.path.join(str(tmp_path), rid, "workspace", "PRD.md"), "w").write("a real PRD")
    assert art()["status"] == "created"                     # file now exists -> real


def test_real_agent_tool_spawns_flag_the_roster_node(tmp_path):
    # A genuine subagent spawn in the stream (Agent tool) marks the roster node real=True and sets
    # its status — proof, vs an emitted event alone. No duplicate node.
    import os, json
    c = console(tmp_path, FakeLauncher())
    rid = c.start_run(RunRequest(description="x"))
    with open(os.path.join(str(tmp_path), rid, "run.log"), "w") as f:
        f.write(json.dumps({"type": "assistant", "message": {"content": [
            {"type": "tool_use", "id": "a1", "name": "Agent",
             "input": {"description": "HORIZON agent: context assembly", "subagent_type": "Explore"}}]}}) + "\n")
    hs = [n["data"] for n in c.graph(rid)["nodes"] if n["data"]["kind"] == "agent" and n["data"]["label"] == "HORIZON"]
    assert len(hs) == 1 and hs[0]["real"] is True and hs[0]["status"] == "running"
    # a roster agent with NO real spawn stays planned + not real
    av = [n["data"] for n in c.graph(rid)["nodes"] if n["data"]["label"] == "VANGUARD"][0]
    assert av["status"] == "planned" and av["real"] is False


def test_graph_always_shows_the_named_phase_agents(tmp_path):
    from software_factory import events
    c = console(tmp_path, FakeLauncher())
    rid = c.start_run(RunRequest(description="x"))
    labels = lambda: {n["data"]["label"]: n["data"] for n in c.graph(rid)["nodes"] if n["data"]["kind"] == "agent"}
    L = labels()
    assert {"HORIZON", "ARCHIVIST", "VANGUARD", "CHROMA", "software-architect"} <= set(L)
    assert L["HORIZON"]["status"] == "planned"                    # shown before any event
    # an event with a MISMATCHED id but the same role upgrades the roster node (no duplicate)
    events.emit(str(tmp_path), rid, "agent_spawned", {"id": "HORIZON", "role": "HORIZON", "phase": "research"})
    g2 = c.graph(rid)
    horizons = [n for n in g2["nodes"] if n["data"]["kind"] == "agent" and n["data"]["label"] == "HORIZON"]
    assert len(horizons) == 1 and horizons[0]["data"]["status"] == "running"
    g = c.graph(rid)
    assert any(e["data"]["source"] == "phase:research" and e["data"]["target"] == "agent:horizon" for e in g["edges"])


def test_pasted_description_is_persisted_and_input_artifact_is_real(tmp_path):
    # The user pastes context (no file) → it's saved as input/context.txt and the input artifact
    # is a REAL green node, not a hollow placeholder.
    import os
    c = console(tmp_path, FakeLauncher())
    rid = c.start_run(RunRequest(description="the full SOW text"))
    assert open(os.path.join(str(tmp_path), rid, "input", "context.txt")).read() == "the full SOW text"
    inp = [n["data"] for n in c.graph(rid)["nodes"] if n["data"]["kind"] == "artifact" and n["data"]["label"] == "input"]
    assert inp and inp[0]["status"] == "created"


def test_url_artifacts_are_links_not_missing(tmp_path):
    from software_factory import events
    c = console(tmp_path, FakeLauncher())
    rid = c.start_run(RunRequest(description="x"))
    events.emit(str(tmp_path), rid, "artifact", {"title": "GitHub Repo", "path": "https://github.com/a/b", "kind": "repo"})
    repo = [n["data"] for n in c.graph(rid)["nodes"] if n["data"]["label"] == "GitHub Repo"][0]
    assert repo["status"] == "created" and repo["url"] == "https://github.com/a/b"


def test_artifacts_are_children_of_the_agent_that_created_them(tmp_path):
    import os
    from software_factory import events
    c = console(tmp_path, FakeLauncher())
    rid = c.start_run(RunRequest(description="x"))
    d = str(tmp_path)
    events.emit(d, rid, "agent_spawned", {"id": "horizon", "role": "HORIZON", "phase": "research"})
    os.makedirs(os.path.join(d, rid, "workspace"), exist_ok=True)
    open(os.path.join(d, rid, "workspace", "PRD.md"), "w").write("real")
    events.emit(d, rid, "artifact", {"title": "PRD", "path": "workspace/PRD.md", "kind": "prd", "agent": "horizon"})
    g = c.graph(rid)
    ids = {n["data"]["id"]: n["data"] for n in g["nodes"]}
    assert "agent:horizon" in ids and ids["agent:horizon"]["label"] == "HORIZON"
    art_id = [n["data"]["id"] for n in g["nodes"] if n["data"].get("path") == "workspace/PRD.md"][0]
    # the PRD artifact's parent edge comes FROM the agent that made it
    assert any(e["data"]["source"] == "agent:horizon" and e["data"]["target"] == art_id for e in g["edges"])
    # and the agent itself hangs off its phase (orchestrator spawns per-phase)
    assert any(e["data"]["source"] == "phase:research" and e["data"]["target"] == "agent:horizon" for e in g["edges"])


def test_events_continue_and_artifact(tmp_path):
    from software_factory import events, gates
    c = console(tmp_path, FakeLauncher())
    run_id = c.start_run(RunRequest(description="guestbook"))
    d = str(tmp_path)
    events.emit(d, run_id, "awaiting_review", {"gate": "prd"})
    assert gates.pending_gate(d, run_id) == "prd"
    c.continue_run(run_id, "prd")                       # dashboard "Continue"
    assert gates.pending_gate(d, run_id) is None
    assert any(e["type"] == "awaiting_review" for e in c.events(run_id))

    # artifact read stays inside the run dir
    import os
    os.makedirs(os.path.join(d, run_id, "workspace"), exist_ok=True)
    open(os.path.join(d, run_id, "workspace", "PRD.md"), "w").write("# PRD\nproblem...")
    assert "PRD" in c.artifact(run_id, "workspace/PRD.md")["content"]
    assert "error" in c.artifact(run_id, "../../etc/passwd")  # traversal rejected


def test_run_uses_sonnet_model_and_a_turn_cap_by_default(tmp_path):
    # Cost controls, pinned: default model is Sonnet 4.6 and turns are bounded.
    launcher = FakeLauncher()
    c = console(tmp_path, launcher)
    c.start_run(RunRequest(description="guestbook"))
    argv = launcher.argv
    assert "--model" in argv and argv[argv.index("--model") + 1] == "claude-sonnet-4-6"
    assert "--max-turns" in argv


def test_read_log_tails_by_default_but_full_returns_everything(tmp_path):
    import os
    c = console(tmp_path, FakeLauncher())
    rid = c.start_run(RunRequest(description="x"))
    big = "L\n" * 30000  # ~60KB of saved log
    with open(os.path.join(str(tmp_path), rid, "run.log"), "w") as f:
        f.write(big)
    assert len(c.read_log(rid)) <= 20000              # feed gets the tail
    assert len(c.read_log(rid, max_bytes=None)) == len(big)  # full saved log is retrievable


def test_default_launch_tees_agent_output_to_the_log_file(tmp_path):
    # Real subprocess: the launcher tees child output to run.log (and to container stdout,
    # which Railway captures — verified live, not here).
    import time
    from software_factory.console import _default_launch
    log = str(tmp_path / "run.log")
    proc = _default_launch(["python3", "-c", "print('hello-from-agent')"], {}, log)
    proc.wait()
    time.sleep(0.3)  # let the pump thread flush
    assert "hello-from-agent" in open(log).read()


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
