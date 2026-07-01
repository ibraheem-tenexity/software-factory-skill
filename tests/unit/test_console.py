"""The operator console: turn a one-line app request into a headless factory run, expose
live status, and surface the deployed URL. The launcher is injected so tests never spawn a
real `claude` process.

This is the harness around the skill — it launches the skill and reads back the skill's own
artifacts; it does not do the building itself.
"""
from software_factory.console import (
    Console, ProjectRequest, make_prompt, make_prompt_stage1, make_prompt_stage2,
    make_prompt_stage3, project_paths,
)
from software_factory.agents import AgentRegistry
from software_factory.budget import Usage


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


def console(tmp_path, launcher, extract=lambda path: "# Extracted\n\nbrief contents"):
    ids = iter(["project-xyz"])
    return Console(str(tmp_path), launch=launcher, new_id=lambda: next(ids), extract=extract)


def test_make_prompt_invokes_the_skill_with_run_id_target_and_budget():
    req = ProjectRequest(description="a guestbook app", context="dark theme", budget=100.0, target="railway")
    p = make_prompt(req, "project-xyz", projects_dir="/runs")
    assert "software-factory" in p          # explicit, deterministic invocation
    assert "project-xyz" in p
    assert "100" in p
    assert "guestbook" in p
    assert "/runs/project-xyz" in p          # tells the orchestrator where to write artifacts
    # Stage 3 prompt carries the deploy target
    p3 = make_prompt_stage3(req, "project-xyz", projects_dir="/runs")
    assert "railway" in p3
    assert "sf-project-xyz" in p3


def test_start_run_stamps_proof_marker_and_launches_headless_claude(tmp_path):
    launcher = FakeLauncher()
    c = console(tmp_path, launcher)
    project_id = c.start_project(ProjectRequest(description="a guestbook app", target="railway"))

    assert project_id == "project-xyz"
    # headless claude was launched with our prompt
    assert launcher.argv is not None
    assert "claude" in launcher.argv[0]
    assert any("software-factory" in a for a in launcher.argv)
    # v2.1.195+ renamed --permission-mode bypassPermissions to --dangerously-skip-permissions
    assert "--dangerously-skip-permissions" in launcher.argv
    assert "--permission-mode" not in launcher.argv

    # the run is stamped at launch: this is the receipt of intent (teeth are in verify_evidence)
    st = c.status(project_id)
    assert st["skill"] == "software-factory"
    assert st["description"] == "a guestbook app"
    assert st["deploy_target"] == "railway"
    assert st["phase"] == "provision"
    assert st["done"] is False


def test_status_reflects_agents_phase_and_deployed_url(tmp_path):
    launcher = FakeLauncher()
    c = console(tmp_path, launcher)
    project_id = c.start_project(ProjectRequest(description="guestbook", target="railway"))

    # simulate the skill making progress in the SAME artifact locations the console reads
    paths = project_paths(str(tmp_path), project_id)
    reg = AgentRegistry(paths["agents_db"], clock=lambda: 1)
    reg.spawn("a1", project_id, 1, "build", "claude-opus-4-8")
    reg.record("a1", outcome="real_diff", usage=Usage("claude-opus-4-8", output_tokens=4000),
               cost_usd=0.42, provenance="7", diff_lines=120)

    state = c._load_state(project_id)
    state.phase = "done"
    state.deploy_url = "https://guestbook.up.railway.app"
    state.spent_usd = 0.42
    state.save()

    st = c.status(project_id)
    assert st["phase"] == "done"
    assert st["done"] is True
    assert st["deploy_url"] == "https://guestbook.up.railway.app"
    assert st["agents"]["spawned"] == 1
    assert st["agents"]["done"] == 1


SECRET = "rwt_super_secret_token_value_123"


def test_byo_railway_token_is_passed_as_env_not_in_prompt_or_argv(tmp_path):
    launcher = FakeLauncher()
    c = console(tmp_path, launcher)
    c.start_project(ProjectRequest(description="guestbook", target="railway",
                           credentials={"RAILWAY_TOKEN": SECRET}))
    # injected into the child env...
    assert launcher.env["RAILWAY_TOKEN"] == SECRET
    # ...and NOWHERE in the command line (argv is logged / visible in process lists)
    assert all(SECRET not in str(a) for a in launcher.argv)


def test_credentials_are_never_written_to_disk(tmp_path):
    launcher = FakeLauncher()
    c = console(tmp_path, launcher)
    project_id = c.start_project(ProjectRequest(description="guestbook", target="railway",
                                    credentials={"RAILWAY_TOKEN": SECRET}))
    # scan every file under the runs dir — the token value must not appear anywhere
    import os
    for root, _, files in os.walk(str(tmp_path)):
        for fn in files:
            with open(os.path.join(root, fn), "rb") as f:
                assert SECRET.encode() not in f.read(), f"secret leaked into {fn}"
    # but the run records WHICH creds were provided (names only) for the live view
    assert "RAILWAY_TOKEN" in c.status(project_id)["creds_provided"]


def test_status_and_evidence_never_expose_secret_values(tmp_path):
    launcher = FakeLauncher()
    c = console(tmp_path, launcher)
    project_id = c.start_project(ProjectRequest(description="guestbook", target="railway",
                                    credentials={"RAILWAY_TOKEN": SECRET}))
    import json
    assert SECRET not in json.dumps(c.status(project_id))
    assert SECRET not in json.dumps(c.evidence(project_id))


def test_empty_credentials_are_ignored(tmp_path):
    launcher = FakeLauncher()
    c = console(tmp_path, launcher)
    project_id = c.start_project(ProjectRequest(description="guestbook", credentials={"RAILWAY_TOKEN": ""}))
    assert c.status(project_id)["creds_provided"] == []
    assert "RAILWAY_TOKEN" not in launcher.env


def test_uploaded_pdf_is_extracted_to_markdown_and_composed_into_stage1_input(tmp_path):
    import base64, os
    c = console(tmp_path, FakeLauncher(), extract=lambda path: "# Brief\n\nEPC contract T&C")
    b64 = base64.b64encode(b"%PDF-1.4 ...").decode()
    project_id = c.start_project(ProjectRequest(description="analyze this",
                                    context_files=[{"name": "brief.pdf", "content_b64": b64}]))
    input_dir = os.path.join(str(tmp_path), project_id, "input")
    # original PDF is kept on disk (for blob storage); markdown is what Stage 1 reads
    assert os.path.exists(os.path.join(input_dir, "brief.pdf"))
    assert "EPC contract T&C" in open(os.path.join(input_dir, "brief.pdf.md")).read()
    # the composed Stage 1 input merges the user prompt and the extracted markdown
    ctx = open(os.path.join(input_dir, "context.txt")).read()
    assert "analyze this" in ctx
    assert "EPC contract T&C" in ctx


def test_retry_stage2_relaunches_with_the_stage2_prompt(tmp_path):
    launcher = FakeLauncher()
    c = console(tmp_path, launcher)
    project_id = c.start_project(ProjectRequest(description="x", target="railway"))
    st = c._load_state(project_id); st.stage1_done = True; st.save()
    launcher.argv = None

    out = c.retry_stage(project_id, 2)

    assert out == project_id
    assert launcher.argv is not None and "claude" in launcher.argv[0]
    assert "Stage 2" in launcher.argv[2]        # the rebuilt prompt is for stage 2
    assert c.status(project_id)["stage"] == 2


def test_retry_stage2_blocked_when_stage1_not_done(tmp_path):
    launcher = FakeLauncher()
    c = console(tmp_path, launcher)
    project_id = c.start_project(ProjectRequest(description="x"))
    st = c._load_state(project_id); st.stage1_done = False; st.save()
    launcher.argv = None

    assert c.retry_stage(project_id, 2) is None
    assert launcher.argv is None                # nothing relaunched


def test_retry_clears_the_target_stage_done_flag(tmp_path):
    launcher = FakeLauncher()
    c = console(tmp_path, launcher)
    project_id = c.start_project(ProjectRequest(description="x"))
    st = c._load_state(project_id); st.stage1_done = True; st.stage2_done = True; st.save()

    c.retry_stage(project_id, 2)

    assert c.status(project_id)["stage2_done"] is False   # re-runs so the gate re-evaluates


def test_retry_invalid_stage_returns_none(tmp_path):
    c = console(tmp_path, FakeLauncher())
    project_id = c.start_project(ProjectRequest(description="x"))
    assert c.retry_stage(project_id, 9) is None


def test_uploaded_filenames_are_basename_only_no_traversal(tmp_path):
    import base64, os
    c = console(tmp_path, FakeLauncher())
    b64 = base64.b64encode(b"x").decode()
    project_id = c.start_project(ProjectRequest(description="d",
                                    context_files=[{"name": "../../evil.txt", "content_b64": b64}]))
    assert os.path.exists(os.path.join(str(tmp_path), project_id, "input", "evil.txt"))
    assert not os.path.exists(os.path.join(str(tmp_path), "evil.txt"))


def test_make_prompt_targets_a_dedicated_service_not_the_runner(tmp_path):
    # Spec 1: the built app must deploy to its OWN service, never the runner's own.
    p = make_prompt_stage3(ProjectRequest(description="x", target="railway"), "project-xyz", projects_dir="/runs")
    assert "sf-project-xyz" in p        # per-project dedicated service name
    assert "never" in p.lower()  # explicit don't-clobber warning


def test_status_cost_is_derived_from_the_run_log(tmp_path):
    # Spec 2: live cost comes from the real claude stream, not self-reported state.
    launcher = FakeLauncher()
    c = console(tmp_path, launcher)
    project_id = c.start_project(ProjectRequest(description="guestbook"))
    with open(launcher.log_path, "w") as f:
        f.write('{"type":"result","subtype":"success","total_cost_usd":0.0731}\n')
    assert c.status(project_id)["spent_usd"] == 0.0731


def test_list_runs_returns_launched_runs_for_reconnect(tmp_path):
    # Spec 3: persistence — the server can enumerate runs so the UI reconnects after reload.
    c = console(tmp_path, FakeLauncher())
    ids = []
    for i in range(2):
        c._new_id = lambda i=i: f"project-{i}"
        ids.append(c.start_project(ProjectRequest(description=f"app {i}")))
    listed = {r["project_id"] for r in c.list_projects()}
    assert set(ids) <= listed
    one = [r for r in c.list_projects() if r["project_id"] == "project-0"][0]
    assert one["description"] == "app 0" and "phase" in one


def test_list_runs_includes_distinct_agent_roles_and_updated_timestamp(tmp_path):
    # The projects dashboard (PRD §2.2) renders a per-project agent avatar-stack + last-activity,
    # so each run carries `agents` (distinct roles, first-seen order) and an `updated` epoch.
    c = console(tmp_path, FakeLauncher())
    c._new_id = lambda: "project-0"
    rid = c.start_project(ProjectRequest(description="app"))
    paths = project_paths(str(tmp_path), rid)
    reg = AgentRegistry(paths["agents_db"], clock=lambda: 1)
    reg.spawn("a1", rid, 1, "architect", "claude-opus-4-8", phase="architect")
    reg.spawn("a2", rid, 2, "build", "claude-sonnet-4-6", phase="build")
    reg.spawn("a3", rid, 3, "build", "claude-sonnet-4-6", phase="build")  # dup role collapses

    row = [r for r in c.list_projects() if r["project_id"] == rid][0]
    assert row["agents"] == ["architect", "build"]      # distinct, first-seen order
    assert isinstance(row["updated"], (int, float)) and row["updated"] > 0


def test_summary_round_trips_through_project_crud(tmp_path):
    """The `summary` key is set via rename_project and surfaced by both the batch list_projects
    projection (exercises the _load_states column merge) and the single status() read."""
    c = console(tmp_path, FakeLauncher())
    c._new_id = lambda: "project-0"
    rid = c.start_project(ProjectRequest(description="app"))
    # no summary at creation
    row = [r for r in c.list_projects() if r["project_id"] == rid][0]
    assert row["summary"] is None
    assert c.status(rid)["summary"] is None
    # set it through the write CRUD
    out = c.rename_project(rid, summary="A clean customer-facing blurb.")
    assert out["summary"] == "A clean customer-facing blurb."
    # both read paths reflect it
    row = [r for r in c.list_projects() if r["project_id"] == rid][0]
    assert row["summary"] == "A clean customer-facing blurb."
    assert c.status(rid)["summary"] == "A clean customer-facing blurb."


def test_list_runs_agents_empty_when_none_spawned(tmp_path):
    c = console(tmp_path, FakeLauncher())
    c._new_id = lambda: "project-0"
    rid = c.start_project(ProjectRequest(description="app"))
    row = [r for r in c.list_projects() if r["project_id"] == rid][0]
    assert row["agents"] == []


def test_graph_folds_pipeline_agents_artifacts_blockers_gates(tmp_path):
    from software_factory.db import ProjectStore, db_path
    from software_factory.agents import AgentRegistry
    c = console(tmp_path, FakeLauncher())
    project_id = c.start_project(ProjectRequest(description="guestbook"))
    d = str(tmp_path)
    # an agent, an artifact, a blocker, and an open gate — ALL recorded in project.db (no events)
    AgentRegistry(db_path(d, project_id)).spawn("t1", project_id, None, "build form", "claude-sonnet-4-6", phase="build")
    db = ProjectStore(db_path(d, project_id))
    db.record_artifact("PRD", "PRD.md", kind="prd")
    db.add_blocker("Supabase project not ready", blocks="wait-for-deps")
    db.set_gate("prd", "awaiting")

    g = c.graph(project_id)
    kinds = {n["data"]["kind"] for n in g["nodes"]}
    assert {"orchestrator", "phase", "agent", "artifact", "blocker", "gate"} <= kinds
    phase_labels = {n["data"]["label"] for n in g["nodes"] if n["data"]["kind"] == "phase"}
    assert {"research", "architect", "deploy"} <= phase_labels
    gate_ids = {n["data"]["id"] for n in g["nodes"] if n["data"]["kind"] == "gate"}
    assert "gate:stage1" in gate_ids and "gate:stage2" in gate_ids
    deps_nodes = [n for n in g["nodes"] if n["data"]["kind"] == "deps"]
    assert len(deps_nodes) == 1 and deps_nodes[0]["data"]["id"] == "deps:wait"
    assert any(e["data"]["source"] == "orchestrator" for e in g["edges"])


def test_auto_resume_relaunches_a_dead_incomplete_stage(tmp_path):
    # SPEC §3 zero-touch (retry path): auto_resume_dead_stage returns True + relaunches
    # within the poller's _AUTO_RESUME_MAX cap. Transient crashes self-heal, never reaching
    # 'crashed'. mark_stage_crashed (called by the poller after cap exhaustion) handles the
    # persistent-crash case.
    class FakeProc:
        def __init__(self): self.exit_code = None
        def poll(self): return self.exit_code
    proc = FakeProc(); argvs = []
    def launcher(argv, env=None, log_path=None, cwd=None):
        argvs.append(argv); return proc
    ids = iter(["project-ar"])
    c = Console(str(tmp_path), launch=launcher, new_id=lambda: next(ids))
    rid = c.start_project(ProjectRequest(description="x"))
    st = c._load_state(rid)
    st.stage1_done = True; st.stage2_done = True; st.deps_satisfied = True; st.stage = 3
    st.save()
    proc.exit_code = None
    assert c.auto_resume_dead_stage(rid) is False    # process alive -> not dead, no resume
    proc.exit_code = -9                              # killed mid-stage-3, no verification recorded
    assert c.auto_resume_dead_stage(rid) is True     # host auto-resumes (within cap)
    assert "Stage 3" in argvs[-1][2]
    # Transient recovery: run stays in normal phase (not 'crashed')
    st2 = c._load_state(rid)
    assert st2.phase not in ("crashed", "paused")


def test_mark_stage_crashed_and_resume_project_restarts_stage(tmp_path):
    # SPEC §3 persistent-crash path: after the poller exhausts _AUTO_RESUME_MAX, it calls
    # mark_stage_crashed(). The run lands in 'crashed' for the Recovery bar. resume_project()
    # clears the marker and relaunches — the operator's one action.
    class FakeProc:
        def __init__(self): self.exit_code = None
        def poll(self): return self.exit_code
    proc = FakeProc(); argvs = []
    def launcher(argv, env=None, log_path=None, cwd=None):
        argvs.append(argv); return proc
    ids = iter(["project-pc"])
    c = Console(str(tmp_path), launch=launcher, new_id=lambda: next(ids))
    rid = c.start_project(ProjectRequest(description="x"))
    st = c._load_state(rid)
    st.stage1_done = True; st.stage2_done = True; st.deps_satisfied = True
    st.stage = 3; st.phase = "build"
    st.save()
    proc.exit_code = -9                                        # stage died, process exited
    # mark_stage_crashed — called by poller after retry cap exhausted
    assert c.mark_stage_crashed(rid) is True
    st2 = c._load_state(rid)
    assert st2.phase == "crashed"
    assert st2.crashed_at_node == "build"                     # recorded where it died
    # operator clicks Resume in the Recovery bar → resume_project clears marker + relaunches
    out = c.resume_project(rid)
    assert out == rid
    st3 = c._load_state(rid)
    assert st3.phase != "crashed"                              # no longer crashed
    assert st3.crashed_at_node == ""                          # marker cleared
    assert "Stage 3" in argvs[-1][2]                          # Stage 3 relaunched


def test_status_exposes_paused_at_node_and_crashed_at_node(tmp_path):
    # Regression: Recovery bar gates on status.paused_at_node / status.crashed_at_node;
    # both must appear in the status() dict (even as empty string when not set).
    c = Console(str(tmp_path), launch=lambda *a, **k: type("P", (), {"poll": lambda s: None})(),
                new_id=lambda: "project-rc01")
    rid = c.create_draft(owner="op@test.com")
    st = c.status(rid)
    assert "paused_at_node" in st
    assert "crashed_at_node" in st
    assert st["paused_at_node"] == ""
    assert st["crashed_at_node"] == ""


def test_auto_resume_does_not_fire_at_the_deps_gate_or_when_budget_blocked(tmp_path):
    # A run waiting at the deps gate (stage complete) or stopped for budget is NOT a dead stage.
    class FakeProc:
        def __init__(self): self.exit_code = 0
        def poll(self): return self.exit_code
    ids = iter(["project-ng"])
    c = Console(str(tmp_path), launch=lambda *a, **k: FakeProc(), new_id=lambda: next(ids))
    rid = c.start_project(ProjectRequest(description="x"))
    st = c._load_state(rid)
    st.stage1_done = True; st.stage2_done = True; st.stage = 2   # finished S2, waiting on deps
    st.save()
    assert c.auto_resume_dead_stage(rid) is False
    from software_factory.db import ProjectStore, db_path
    st = c._load_state(rid); st.stage = 3; st.deps_satisfied = True; st.save()
    ProjectStore(db_path(str(tmp_path), rid)).add_blocker("Budget cap reached", blocks="budget")
    assert c.auto_resume_dead_stage(rid) is False    # budget-stopped: waits for the operator


def test_no_launch_path_can_resurrect_a_stopped_run(tmp_path):
    # project-b71e06a3 scar: cancel marked phase='stopped', but the poller's auto-deps + auto-S3
    # path didn't check phase — the canceled run auto-satisfied deps and LAUNCHED Stage 3.
    # Every launch path must refuse terminal runs, and status must surface 'stopped'.
    launcher = FakeLauncher()
    c = console(tmp_path, launcher)
    rid = c.start_project(ProjectRequest(description="x"))
    st = c._load_state(rid)
    st.stage1_done = True; st.stage2_done = True; st.phase = "stopped"
    st.deps_required = ["SUPABASE_URL"]                      # auto-satisfiable (mcp)
    st.save()
    launcher.argv = None
    assert c.maybe_autosatisfy_deps(rid) is False            # terminal: deps never auto-resolve
    st = c._load_state(rid); st.deps_satisfied = True; st.save()
    assert c.start_stage3(rid) is None                       # refused
    assert c.start_stage2(rid) is None                       # refused
    assert c.retry_stage(rid, 3) is None                     # refused
    assert launcher.argv is None                             # nothing launched
    assert c.status(rid)["phase"] == "stopped"               # display tells the truth


def test_auto_resume_never_resurrects_a_canceled_run(tmp_path):
    # phase='stopped' (operator cancel) is terminal — auto-resume must not bring it back.
    class DeadProc:
        def poll(self): return -9
    ids = iter(["project-cx"])
    c = Console(str(tmp_path), launch=lambda *a, **k: DeadProc(), new_id=lambda: next(ids))
    rid = c.start_project(ProjectRequest(description="x"))
    st = c._load_state(rid); st.phase = "stopped"; st.save()
    assert c.auto_resume_dead_stage(rid) is False


def test_budget_kill_is_recoverable_raise_and_resume(tmp_path, monkeypatch):
    # SPEC §4: at the per-project ceiling the poller kills the stage process and records a budget
    # blocker — but the run is RECOVERABLE: raise_budget(ceiling) clears the blocker and the
    # higher per-project ceiling lets the stage relaunch.
    monkeypatch.setenv("SF_COST_CEILING", "10")
    monkeypatch.setenv("SF_STAGE_RESERVE", "0")
    class FakeProc:
        def __init__(self): self.exit_code = None; self.terminated = False
        def poll(self): return self.exit_code
        def terminate(self): self.terminated = True; self.exit_code = -15
    proc = FakeProc()
    ids = iter(["project-bk"])
    c = Console(str(tmp_path), launch=lambda *a, **k: proc, new_id=lambda: next(ids))
    rid = c.start_project(ProjectRequest(description="x"))
    st = c._load_state(rid); st.spent_usd = 11.0; st.save()       # over the $10 ceiling
    assert c.enforce_budget(rid) is True                          # killed
    assert proc.terminated is True
    from software_factory.db import ProjectStore, db_path
    db = ProjectStore(db_path(str(tmp_path), rid))
    open_blockers = [b for b in db.blockers() if not b["cleared"]]
    assert any(b.get("blocks") == "budget" for b in open_blockers)
    # recovery: raise the per-project ceiling -> blocker cleared, persisted override honored
    c.raise_budget(rid, 40.0)
    assert c._load_state(rid).budget_ceiling == 40.0
    assert not [b for b in db.blockers() if not b["cleared"]]
    assert c.enforce_budget(rid) is False                         # under the new ceiling
    st = c._load_state(rid); st.stage1_done = True; st.save()
    assert c.start_stage2(rid) == rid                             # launch-gate honors the override


def test_stop_project_kills_process_and_marks_terminal_stopped(tmp_path):
    # Operator "stop all progress": kill the live stage process + phase=stopped (terminal — the poller
    # won't re-advance/relaunch/re-provision). Idempotent.
    class FakeProc:
        def __init__(self): self.exit_code = None; self.terminated = False
        def poll(self): return self.exit_code
        def terminate(self): self.terminated = True; self.exit_code = -15
        def wait(self, timeout=None): return self.exit_code
        def kill(self): self.exit_code = -9
    proc = FakeProc()
    ids = iter(["project-stop1"])
    c = Console(str(tmp_path), launch=lambda *a, **k: proc, new_id=lambda: next(ids))
    rid = c.start_project(ProjectRequest(description="x"))
    res = c.stop_project(rid)
    assert res == {"project_id": rid, "phase": "stopped", "killed": True}
    assert proc.terminated is True
    state = c._load_state(rid)
    assert state.phase == "stopped" and c._terminal(state) is True   # poller treats it terminal
    # idempotent: already stopped + process already exited → no-op, killed False
    res2 = c.stop_project(rid)
    assert res2["phase"] == "stopped" and res2["killed"] is False


def test_stop_project_without_live_process_still_stops(tmp_path):
    # No tracked process (e.g. console restarted since launch) → can't kill, but phase=stopped still
    # halts the run (the loop can't resume).
    c = Console(str(tmp_path), launch=FakeLauncher(), new_id=lambda: "project-stop2")
    rid = c.start_project(ProjectRequest(description="x"))
    res = c.stop_project(rid)
    assert res["phase"] == "stopped" and res["killed"] is False
    assert c._terminal(c._load_state(rid)) is True


def test_created_by_stamped_at_draft_and_immutable_through_promote(tmp_path):
    # created_by is set ONCE at creation and never mutates — even when owner is reassigned or the draft
    # is promoted. owner stays the reassignable current owner.
    c = Console(str(tmp_path), launch=FakeLauncher(), new_id=lambda: "project-cb1")
    rid = c.create_draft(owner="alice@x.com", name="P")
    st = c._load_state(rid)
    assert st.created_by == "alice@x.com" and st.created_at > 0
    st.owner = "bob@x.com"; st.save()                       # owner reassigned
    c.promote_draft(rid)                                    # _provision_and_launch runs
    after = c._load_state(rid)
    assert after.created_by == "alice@x.com"                # IMMUTABLE
    assert after.owner == "bob@x.com"                       # owner is the reassignable one


def test_created_by_stamped_on_direct_start_project(tmp_path):
    c = Console(str(tmp_path), launch=FakeLauncher(), new_id=lambda: "project-cb3")
    rid = c.start_project(ProjectRequest(description="x", owner="carol@x.com"))
    assert c._load_state(rid).created_by == "carol@x.com"


def test_backfill_created_by_from_owner_is_idempotent_and_surfaced(tmp_path):
    c = Console(str(tmp_path), launch=FakeLauncher(), new_id=lambda: "project-cb4")
    rid = c.start_project(ProjectRequest(description="x", owner="dan@x.com"))
    st = c._load_state(rid); st.created_by = ""; st.created_at = 0.0; st.save()   # simulate legacy row
    assert c.backfill_created_by() == 1
    st2 = c._load_state(rid)
    assert st2.created_by == "dan@x.com" and st2.created_at > 0
    assert c.backfill_created_by() == 0                     # idempotent
    row = next(r for r in c.list_projects() if r["project_id"] == rid)
    assert row["created_by"] == "dan@x.com"                 # surfaced for "which projects did X create"


def test_run_spend_is_per_run_not_cumulative(tmp_path):
    # Per-run budget: each run/project is capped independently. _project_spend reflects ONLY this run's
    # own spend; a prior run's spend does not count against another.
    ids = iter(["project-a", "project-b"])
    c = Console(str(tmp_path), launch=FakeLauncher(), new_id=lambda: next(ids))
    a = c.start_project(ProjectRequest(description="x"))
    st = c._load_state(a); st.spent_usd = 4.0; st.save()
    b = c.start_project(ProjectRequest(description="y"))
    st = c._load_state(b); st.spent_usd = 9.0; st.save()
    assert c._project_spend(a) == 4.0                         # only project-a's spend
    assert c._project_spend(b) == 9.0                         # project-a's $4 does NOT count against project-b


def test_launch_refused_when_this_runs_spend_crosses_ceiling(tmp_path, monkeypatch):
    # Mechanical per-project hard stop: refuse a stage launch when THIS run's spend + a stage reserve
    # would cross SF_COST_CEILING — so the advisory in-prompt budget can't silently blow past it.
    monkeypatch.setenv("SF_COST_CEILING", "10")
    monkeypatch.setenv("SF_STAGE_RESERVE", "5")
    launcher = FakeLauncher()
    c = console(tmp_path, launcher)
    rid = c.start_project(ProjectRequest(description="x"))
    st = c._load_state(rid); st.spent_usd = 8.0; st.stage1_done = True; st.save()  # 8 + 5 reserve > 10
    launcher.argv = None
    assert c.start_stage2(rid) is None                   # refused
    assert launcher.argv is None                          # no process launched
    from software_factory.db import ProjectStore, db_path
    blockers = " ".join(b.get("what", "") for b in ProjectStore(db_path(str(tmp_path), rid)).blockers())
    assert "budget" in blockers.lower()


def test_launch_proceeds_when_under_ceiling(tmp_path, monkeypatch):
    monkeypatch.setenv("SF_COST_CEILING", "30")
    monkeypatch.setenv("SF_STAGE_RESERVE", "5")
    launcher = FakeLauncher()
    c = console(tmp_path, launcher)
    rid = c.start_project(ProjectRequest(description="x"))
    st = c._load_state(rid); st.spent_usd = 2.0; st.stage1_done = True; st.save()
    assert c.start_stage2(rid) == rid                     # well under ceiling -> launches
    assert launcher.argv is not None


def test_next_stage_waits_for_prior_stage_process_to_exit(tmp_path):
    # project-d329e57c scar: detect_stage1_done is mechanical (PRD passes -> poller launches S2)
    # and did NOT wait for the S1 orchestrator PROCESS to exit — two opus orchestrators ran
    # concurrently ~9 min (double burn + S2 reading a workspace S1 was still writing).
    # start_stage2 must refuse while the prior stage's process is alive, then proceed once it exits.
    class FakeProc:
        def __init__(self): self.exit_code = None
        def poll(self): return self.exit_code
    proc = FakeProc()
    launches = []
    def launcher(argv, env=None, log_path=None, cwd=None):
        launches.append(argv); return proc
    ids = iter(["project-ov"])
    c = Console(str(tmp_path), launch=launcher, new_id=lambda: next(ids))
    rid = c.start_project(ProjectRequest(description="x"))
    st = c._load_state(rid); st.stage1_done = True; st.save()
    assert c.start_stage2(rid) is None          # S1 process still alive -> refuse
    assert len(launches) == 1                    # no second claude process spawned
    proc.exit_code = 0                           # S1 exits
    assert c.start_stage2(rid) == rid            # now it launches
    assert len(launches) == 2


def test_deps_auto_satisfy_when_no_human_secret_needed(tmp_path):
    # SPEC §3: if NO required token classifies as 'provide', the host auto-satisfies deps
    # (mock/mcp dispositions apply) — the deps gate must not be a hidden manual pause.
    c = console(tmp_path, FakeLauncher())
    rid = c.start_project(ProjectRequest(description="x"))
    st = c._load_state(rid)
    st.stage2_done = True
    st.deps_required = ["SUPABASE_URL", "NEXTAUTH_SECRET"]   # both classify 'mcp' -> no human
    st.save()
    assert c.maybe_autosatisfy_deps(rid) is True
    assert c._load_state(rid).deps_satisfied is True


def test_deps_do_not_auto_satisfy_when_a_provide_token_is_required(tmp_path):
    # SPEC §3: 'provide' now ONLY happens when the operator explicitly sets it at the gate —
    # and when they do, the run waits for the real secret instead of auto-launching.
    c = console(tmp_path, FakeLauncher())
    rid = c.start_project(ProjectRequest(description="x"))
    st = c._load_state(rid)
    st.stage2_done = True
    st.deps_required = ["PARTNER_SSO_SECRET"]
    st.deps_disposition = {"PARTNER_SSO_SECRET": "provide"}  # operator explicitly requires a human value
    st.save()
    assert c.maybe_autosatisfy_deps(rid) is False
    assert c._load_state(rid).deps_satisfied is False


def test_openrouter_in_runner_env_auto_satisfies_zero_touch(tmp_path, monkeypatch):
    # SPEC §3 zero-touch: OPENROUTER present in the runner env classifies 'env' -> no pause.
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-x")
    c = console(tmp_path, FakeLauncher())
    rid = c.start_project(ProjectRequest(description="x"))
    st = c._load_state(rid)
    st.stage2_done = True
    st.deps_required = ["OPENROUTER_API_KEY"]
    st.save()
    assert c.maybe_autosatisfy_deps(rid) is True
    assert c._load_state(rid).deps_satisfied is True


def test_stage_done_requires_the_orchestrator_process_to_have_finished(tmp_path):
    # SPEC §1: a stage is done only when its artifact gate passes AND the process finished.
    # project-d329e57c scar: the PRD passed while S1 was still alive -> S1+S2 ran concurrently.
    import os
    class FakeProc:
        def __init__(self): self.exit_code = None
        def poll(self): return self.exit_code
    proc = FakeProc()
    ids = iter(["project-sf"])
    c = Console(str(tmp_path), launch=lambda *a, **k: proc, new_id=lambda: next(ids))
    rid = c.start_project(ProjectRequest(description="x"))
    ws = os.path.join(str(tmp_path), rid, "workspace"); os.makedirs(ws, exist_ok=True)
    prd = ("# PRD\n" + "\n".join(f"- https://product{i}.example.com real product" for i in range(3))
           + "\n## Acceptance Criteria\n- works\n## Ticket Seeds\n- t1\n")
    open(os.path.join(ws, "PRD.md"), "w").write(prd)
    assert c.detect_stage1_done(rid) is False                # gate passes but S1 still ALIVE -> not done
    assert c._load_state(rid).stage1_done is False
    proc.exit_code = 0                                       # S1 exits
    assert c.detect_stage1_done(rid) is True                 # gate + finished process -> done


def test_resurfaced_pre_redesign_run_is_not_a_pipeline_run(tmp_path):
    # Budget-bleed scar: an old run dir (PRD.md on disk, but never started by THIS pipeline)
    # must NOT auto-advance. start_project records an "input" artifact in project.db; a resurfaced dir
    # whose project.db is empty (created fresh on load) is_pipeline_project -> False, so the poller skips it.
    import os
    c = console(tmp_path, FakeLauncher())
    # a real run created by start_project has recorded input artifacts:
    rid = c.start_project(ProjectRequest(description="x"))
    assert c.is_pipeline_project(rid) is True
    # a resurfaced old dir: just a PRD on disk, no project.db activity.
    old = os.path.join(str(tmp_path), "project-old")
    os.makedirs(os.path.join(old, "workspace"), exist_ok=True)
    open(os.path.join(old, "workspace", "PRD.md"), "w").write("# PRD")
    assert c.is_pipeline_project("project-old") is False


def test_run_links_surface_repo_and_live_urls(tmp_path):
    # SPEC §6 delivery: repo + live urls projected from the artifacts table for the toolbar,
    # chat narration and the done message.
    from software_factory.db import ProjectStore, db_path
    c = console(tmp_path, FakeLauncher())
    rid = c.start_project(ProjectRequest(description="x"))
    assert c.project_links(rid) == {"repo": None, "live": None}
    db = ProjectStore(db_path(str(tmp_path), rid))
    db.record_artifact("GitHub Repo", "https://github.com/acme/app", kind="repo")
    db.record_artifact("Live URL", "https://sf-run.up.railway.app", kind="deploy")
    links = c.project_links(rid)
    assert links["repo"] == "https://github.com/acme/app"
    assert links["live"] == "https://sf-run.up.railway.app"


def test_stage1_prompt_records_repo_artifact_at_creation(tmp_path):
    p1 = make_prompt_stage1(ProjectRequest(description="x"), "project-r", "/runs")
    assert "GitHub Repo" in p1 and "repo" in p1            # surfaced from the start (SPEC §7)


def test_derive_phases_start_of_run(tmp_path):
    # SPEC §1: the host performs extraction at start_project and records it — extract=done,
    # provision=active, everything later pending. No phase is trust-based.
    c = console(tmp_path, FakeLauncher())
    rid = c.start_project(ProjectRequest(description="x"))
    ph = c.derive_phases(rid)
    assert ph["extract"] == "done"
    assert ph["provision"] == "active"
    assert ph["build"] == "pending" and ph["test"] == "pending"


def test_derive_phases_never_leaves_passed_phases_pending_or_active(tmp_path):
    # project-d329e57c scar: provision painted 'active' during build; extract stuck 'pending'.
    # Once a later phase has activity, earlier phases with activity are done; without -> skipped.
    from software_factory.db import ProjectStore, db_path
    c = console(tmp_path, FakeLauncher())
    rid = c.start_project(ProjectRequest(description="x"))
    db = ProjectStore(db_path(str(tmp_path), rid))
    db.set_phase("research", "done")
    db.set_phase("architect", "active")     # S2 mid-flight; never closed its row
    db.set_phase("build", "active")         # S3 started later (architect forgot to close)
    ph = c.derive_phases(rid)
    assert ph["provision"] == "done"        # has activity, later phases started -> done, NOT active
    assert ph["research"] == "done"
    assert ph["architect"] == "done"        # left 'active' by the agent, but build moved past it
    assert ph["tickets"] == "skipped"       # no recorded activity, process moved past -> skipped
    assert ph["build"] == "active"          # the furthest phase with activity is the live one
    assert ph["deploy"] == "pending"


def test_derive_phases_done_run_and_header(tmp_path):
    from software_factory.db import ProjectStore, db_path
    c = console(tmp_path, FakeLauncher())
    rid = c.start_project(ProjectRequest(description="x"))
    db = ProjectStore(db_path(str(tmp_path), rid))
    db.set_phase("build", "active")
    st = c._load_state(rid); st.phase = "done"; st.save()
    ph = c.derive_phases(rid)
    assert ph["build"] == "done"            # terminal run closes everything with activity
    assert ph["tickets"] == "skipped"
    assert c.status(rid)["phase"] == "done"


def test_status_phase_is_derived_not_stale_provision(tmp_path):
    # The header must reflect the derived current phase, not ProjectState.phase's initial value.
    from software_factory.db import ProjectStore, db_path
    c = console(tmp_path, FakeLauncher())
    rid = c.start_project(ProjectRequest(description="x"))
    ProjectStore(db_path(str(tmp_path), rid)).set_phase("build", "active")
    assert c.status(rid)["phase"] == "build"   # NOT "provision"


def test_graph_resolves_workspace_relative_artifact_paths(tmp_path):
    # Agents run with cwd=workspace and record artifact paths relative to it ("architecture.md",
    # not "workspace/architecture.md"). graph() must resolve those against the workspace dir too,
    # else every real artifact reads "missing/hollow" (the canvas-all-red bug).
    import os
    from software_factory.db import ProjectStore, db_path
    c = console(tmp_path, FakeLauncher())
    rid = c.start_project(ProjectRequest(description="x"))
    ProjectStore(db_path(str(tmp_path), rid)).record_artifact("Architecture", "architecture.md", kind="doc")
    art = lambda: [n["data"] for n in c.graph(rid)["nodes"] if n["data"].get("path") == "architecture.md"][0]
    assert art()["status"] == "missing"                      # not written yet
    ws = os.path.join(str(tmp_path), rid, "workspace"); os.makedirs(ws, exist_ok=True)
    open(os.path.join(ws, "architecture.md"), "w").write("# Arch")
    assert art()["status"] == "created"                      # workspace-relative path now resolves


def test_graph_resolves_project_subdir_relative_artifact_paths(tmp_path):
    # project-1e17ea6a scar (3rd path variant): S1 agents work INSIDE the cloned repo
    # (workspace/<project>/) and record paths relative to it ("PRD.md", "research/x.md").
    # The resolver must try each first-level workspace subdir too — else real artifacts
    # render 'missing' on the canvas.
    import os
    from software_factory.db import ProjectStore, db_path
    c = console(tmp_path, FakeLauncher())
    rid = c.start_project(ProjectRequest(description="x"))
    proj = os.path.join(str(tmp_path), rid, "workspace", "autobuilder-singer")
    os.makedirs(os.path.join(proj, "research"), exist_ok=True)
    open(os.path.join(proj, "PRD.md"), "w").write("# PRD")
    open(os.path.join(proj, "research", "horizon.md"), "w").write("# ctx")
    db = ProjectStore(db_path(str(tmp_path), rid))
    db.record_artifact("PRD", "PRD.md", kind="prd")
    db.record_artifact("Context", "research/horizon.md", kind="doc")
    statuses = {n["data"]["label"]: n["data"]["status"]
                for n in c.graph(rid)["nodes"] if n["data"].get("kind") == "artifact"}
    assert statuses["PRD"] == "created"
    assert statuses["Context"] == "created"


def test_graph_marks_artifacts_missing_until_the_file_really_exists(tmp_path):
    # The "no hollow done" scar at the artifact level: a recorded artifact whose file does not
    # exist is status="missing" (red on the canvas), not a fake green "created".
    import os
    from software_factory.db import ProjectStore, db_path
    c = console(tmp_path, FakeLauncher())
    rid = c.start_project(ProjectRequest(description="x"))
    ProjectStore(db_path(str(tmp_path), rid)).record_artifact("PRD", "workspace/PRD.md", kind="prd")
    art = lambda: [n["data"] for n in c.graph(rid)["nodes"] if n["data"].get("path") == "workspace/PRD.md"][0]
    assert art()["status"] == "missing"                     # recorded but no file -> hollow
    os.makedirs(os.path.join(str(tmp_path), rid, "workspace"), exist_ok=True)
    open(os.path.join(str(tmp_path), rid, "workspace", "PRD.md"), "w").write("a real PRD")
    assert art()["status"] == "created"                     # file now exists -> real


def test_graph_agents_are_projected_from_the_agents_table(tmp_path):
    # Agents appear on the canvas ONLY when recorded in project.db (no planned roster). A recorded
    # agent hangs off its phase, is real=True, and its status comes from the agents table.
    from software_factory.db import db_path
    from software_factory.agents import AgentRegistry
    c = console(tmp_path, FakeLauncher())
    rid = c.start_project(ProjectRequest(description="x"))
    assert not [n for n in c.graph(rid)["nodes"] if n["data"]["kind"] == "agent"]  # nothing recorded yet
    AgentRegistry(db_path(str(tmp_path), rid)).spawn("horizon", rid, None, "HORIZON", "claude-opus-4-8", phase="research")
    g = c.graph(rid)
    hs = [n["data"] for n in g["nodes"] if n["data"]["kind"] == "agent" and n["data"]["label"] == "HORIZON"]
    assert len(hs) == 1 and hs[0]["real"] is True and hs[0]["status"] == "running"
    assert any(e["data"]["source"] == "phase:research" and e["data"]["target"] == "agent:horizon" for e in g["edges"])


def test_graph_agent_status_reflects_outcome(tmp_path):
    from software_factory.db import db_path
    from software_factory.agents import AgentRegistry
    from software_factory.budget import Usage
    c = console(tmp_path, FakeLauncher())
    rid = c.start_project(ProjectRequest(description="x"))
    reg = AgentRegistry(db_path(str(tmp_path), rid))
    reg.spawn("a1", rid, 1, "builder", "claude-sonnet-4-6", phase="build")
    reg.record("a1", outcome="real_diff", usage=Usage(model="claude-sonnet-4-6"), cost_usd=0.1, provenance="7", diff_lines=10)
    a = [n["data"] for n in c.graph(rid)["nodes"] if n["data"]["kind"] == "agent" and n["data"]["label"] == "builder"][0]
    assert a["status"] == "done"


def test_pasted_description_is_persisted_and_input_artifact_is_real(tmp_path):
    # The user pastes context (no file) → it's saved as input/context.txt and the input artifact
    # is a REAL green node, not a hollow placeholder.
    import os
    c = console(tmp_path, FakeLauncher())
    rid = c.start_project(ProjectRequest(description="the full SOW text"))
    assert open(os.path.join(str(tmp_path), rid, "input", "context.txt")).read() == "the full SOW text"
    inp = [n["data"] for n in c.graph(rid)["nodes"] if n["data"]["kind"] == "artifact" and n["data"]["label"] == "input"]
    assert inp and inp[0]["status"] == "created"


def test_url_artifacts_are_links_not_missing(tmp_path):
    from software_factory.db import ProjectStore, db_path
    c = console(tmp_path, FakeLauncher())
    rid = c.start_project(ProjectRequest(description="x"))
    ProjectStore(db_path(str(tmp_path), rid)).record_artifact("GitHub Repo", "https://github.com/a/b", kind="repo")
    repo = [n["data"] for n in c.graph(rid)["nodes"] if n["data"]["label"] == "GitHub Repo"][0]
    assert repo["status"] == "created" and repo["url"] == "https://github.com/a/b"


def test_artifacts_are_children_of_the_agent_that_created_them(tmp_path):
    import os
    from software_factory.db import ProjectStore, db_path
    from software_factory.agents import AgentRegistry
    c = console(tmp_path, FakeLauncher())
    rid = c.start_project(ProjectRequest(description="x"))
    d = str(tmp_path)
    AgentRegistry(db_path(d, rid)).spawn("horizon", rid, None, "HORIZON", "claude-opus-4-8", phase="research")
    os.makedirs(os.path.join(d, rid, "workspace"), exist_ok=True)
    open(os.path.join(d, rid, "workspace", "PRD.md"), "w").write("real")
    ProjectStore(db_path(d, rid)).record_artifact("PRD", "workspace/PRD.md", kind="prd", agent="horizon")
    g = c.graph(rid)
    ids = {n["data"]["id"]: n["data"] for n in g["nodes"]}
    assert "agent:horizon" in ids and ids["agent:horizon"]["label"] == "HORIZON"
    art_id = [n["data"]["id"] for n in g["nodes"] if n["data"].get("path") == "workspace/PRD.md"][0]
    # the PRD artifact's parent edge comes FROM the agent that made it
    assert any(e["data"]["source"] == "agent:horizon" and e["data"]["target"] == art_id for e in g["edges"])
    # and the agent itself hangs off its phase
    assert any(e["data"]["source"] == "phase:research" and e["data"]["target"] == "agent:horizon" for e in g["edges"])


def test_gate_continue_and_artifact(tmp_path):
    from software_factory import gates
    from software_factory.db import ProjectStore, db_path
    c = console(tmp_path, FakeLauncher())
    project_id = c.start_project(ProjectRequest(description="guestbook"))
    d = str(tmp_path)
    ProjectStore(db_path(d, project_id)).set_gate("prd", "awaiting")
    assert gates.pending_gate(d, project_id) == "prd"
    c.continue_project(project_id, "prd")                       # dashboard "Continue"
    assert gates.pending_gate(d, project_id) is None

    # artifact read stays inside the run dir
    import os
    os.makedirs(os.path.join(d, project_id, "workspace"), exist_ok=True)
    open(os.path.join(d, project_id, "workspace", "PRD.md"), "w").write("# PRD\nproblem...")
    assert "PRD" in c.artifact(project_id, "workspace/PRD.md")["content"]
    assert "error" in c.artifact(project_id, "../../etc/passwd")  # traversal rejected


def _model_of(launcher):
    argv = launcher.argv
    return argv[argv.index("--model") + 1]


def test_stage3_done_requires_playwright_pass_and_real_agents(tmp_path):
    # The two NON-NEGOTIABLE Stage-3 gates: (a) done tickets trace to recorded native-Task agents,
    # (b) a PASSING Playwright happy-flow on the live url is recorded. No hollow done.
    # Also mirrors Stages 1/2: done only flips once the Claude Code process has finished.
    from software_factory.db import ProjectStore, db_path
    from software_factory.tickets import TicketStore
    from software_factory.agents import AgentRegistry
    c = console(tmp_path, FakeLauncher())
    rid = c.start_project(ProjectRequest(description="x"))
    dbp = db_path(str(tmp_path), rid)
    db = ProjectStore(dbp)
    ts = TicketStore(dbp)
    reg = AgentRegistry(dbp)

    # Simulate a finished stage process — detect_stage3_done must not flip while Claude is alive.
    c._procs[rid] = type("DeadProc", (), {"poll": lambda self: 0})()

    # A ticket built monolithically (no agent claimed it) -> done with agent=None
    tid = ts.create_ticket("feature", acceptance="a", dod="d", wave=1)
    ts.mark_done(tid, provenance="1", diff_lines=10)
    assert c.detect_stage3_done(rid) is False         # no Playwright pass yet

    # Passing Playwright verification, but the done ticket has no agent -> still not done (gate a)
    db.record_verification("https://sf-x.up.railway.app", True, {"flows": [{"ok": True}]})
    assert c.detect_stage3_done(rid) is False

    # Build it properly: a native Task agent claims THEN completes the ticket (agent retained on done)
    reg.spawn("ag1", rid, tid, "builder", "claude-sonnet-4-6", phase="build")
    ts.claim(tid, "ag1")
    ts.mark_done(tid, provenance="1", diff_lines=10)
    # Built + verified, but QA hasn't approved yet (gate c) -> still not done.
    assert c.detect_stage3_done(rid) is False
    # QA loop closes: deploy -> qa -> approve every ticket.
    ts.mark_deployed(tid); ts.start_qa(tid); ts.qa_approve(tid)
    assert c.detect_stage3_done(rid) is True
    st = c.status(rid)
    assert st["done"] is True and st["deploy_url"] == "https://sf-x.up.railway.app"


def test_detect_stage3_done_waits_for_process_to_finish(tmp_path):
    # Process health is the real indicator; all gates may be green, but if Claude is still
    # running we must NOT flip done prematurely.
    from software_factory.db import ProjectStore, db_path
    from software_factory.tickets import TicketStore
    from software_factory.agents import AgentRegistry
    c = console(tmp_path, FakeLauncher())
    rid = c.start_project(ProjectRequest(description="x"))
    dbp = db_path(str(tmp_path), rid)
    db = ProjectStore(dbp)
    ts = TicketStore(dbp)
    reg = AgentRegistry(dbp)

    tid = ts.create_ticket("feature", acceptance="a", dod="d", wave=1)
    reg.spawn("ag1", rid, tid, "builder", "claude-sonnet-4-6", phase="build")
    ts.claim(tid, "ag1")
    ts.mark_done(tid, provenance="1", diff_lines=10)
    ts.mark_deployed(tid); ts.start_qa(tid); ts.qa_approve(tid)
    db.record_verification("https://sf-x.up.railway.app", True, {"flows": [{"ok": True}]})

    # Simulate a LIVE Claude process
    c._procs[rid] = type("LiveProc", (), {"poll": lambda self: None})()
    assert c.detect_stage3_done(rid) is False

    # Simulate process finishing — now done flips.
    c._procs[rid] = type("DeadProc", (), {"poll": lambda self: 0})()
    assert c.detect_stage3_done(rid) is True


def test_stage3_prompt_is_plan_first_orchestrator_only_with_playwright_gate(tmp_path):
    from software_factory.console import make_prompt_stage3, make_prompt_stage1
    p3 = make_prompt_stage3(ProjectRequest(description="x"), "project-z", "/tmp/r",
                            dispositions={"ADP_CLIENT_ID": "mock", "SUPABASE_URL": "mcp"})
    for needle in ["build-plan.md", "Playwright", "record-verification", "Task sub-agent",
                   "software_factory.db", "sf-project-z", "ORCHESTRATOR-ONLY",
                   # deploy hardening (project-ce47692e gaps) baked into the prompt backstop:
                   "Railway MCP", "generate_domain", "npm audit", "get_logs", "GitHub Repo"]:
        assert needle in p3, needle
    # prompts defer to SKILL.md and carry NO event/ruflo instructions
    for bad in ["events emit", "swarm_init", "agent_spawn ", "ruflo"]:
        assert bad not in p3 and bad not in make_prompt_stage1(ProjectRequest(description="x"), "r", "/t")
    assert "SKILL.md" in make_prompt_stage1(ProjectRequest(description="x"), "r", "/t")


def test_per_stage_models_opus_for_1_and_2_sonnet_for_3(tmp_path):
    # Stages 1 & 2 run on Opus 4.8; Stage 3 on Sonnet. cwd = the workspace.
    import os
    launcher = FakeLauncher()
    c = console(tmp_path, launcher)
    rid = c.start_project(ProjectRequest(description="guestbook"))           # Stage 1
    assert _model_of(launcher) == "claude-opus-4-8"
    assert "--max-turns" not in launcher.argv
    assert launcher.cwd == os.path.join(str(tmp_path), rid, "workspace")

    st = c._load_state(rid); st.stage1_done = True; st.save()
    c.start_stage2(rid)                                              # Stage 2
    assert _model_of(launcher) == "claude-opus-4-8"

    st = c._load_state(rid); st.stage2_done = True; st.deps_satisfied = True; st.save()
    c.start_stage3(rid)                                             # Stage 3
    assert _model_of(launcher) == "claude-sonnet-4-6"


def test_read_log_tails_by_default_but_full_returns_everything(tmp_path):
    import os
    c = console(tmp_path, FakeLauncher())
    rid = c.start_project(ProjectRequest(description="x"))
    big = "L\n" * 30000  # ~60KB of saved log
    with open(os.path.join(str(tmp_path), rid, "project.log"), "w") as f:
        f.write(big)
    assert len(c.read_log(rid)) <= 20000              # feed gets the tail
    assert len(c.read_log(rid, max_bytes=None)) == len(big)  # full saved log is retrievable


def test_default_launch_tees_agent_output_to_the_log_file(tmp_path):
    # Real subprocess: the launcher tees child output to project.log (and to container stdout,
    # which Railway captures — verified live, not here).
    import time
    from software_factory.console import _default_launch
    log = str(tmp_path / "project.log")
    proc = _default_launch(["python3", "-c", "print('hello-from-agent')"], {}, log)
    proc.wait()
    time.sleep(0.3)  # let the pump thread flush
    assert "hello-from-agent" in open(log).read()


def test_run_output_is_captured_to_a_readable_log(tmp_path):
    launcher = FakeLauncher()
    c = console(tmp_path, launcher)
    project_id = c.start_project(ProjectRequest(description="guestbook"))
    # the launcher is told where to capture the run's stdout/stderr
    assert launcher.log_path.endswith("project.log")
    # and read_log surfaces whatever lands there
    import os
    with open(launcher.log_path, "w") as f:
        f.write("provision: checking creds\nhello from claude\n")
    assert "hello from claude" in c.read_log(project_id)


def test_status_reports_workspace_lifecycle(tmp_path):
    import os
    from software_factory import workspace
    launcher = FakeLauncher()
    c = console(tmp_path, launcher)
    project_id = c.start_project(ProjectRequest(description="guestbook"))
    # start_project calls _launch_stage which calls prepare_workspace -> workspace exists immediately
    assert c.status(project_id)["workspace"] == "active"

    # terminal + torn down -> cleaned
    ws = os.path.join(str(tmp_path), project_id, "workspace")
    st = c._load_state(project_id); st.phase = "done"; st.deploy_url = "https://x"; st.save()
    workspace.destroy(ws, projects_dir=str(tmp_path))
    assert c.status(project_id)["workspace"] == "cleaned"


def test_evidence_verifies_the_run_was_really_built_by_the_skill(tmp_path):
    launcher = FakeLauncher()
    c = console(tmp_path, launcher)
    project_id = c.start_project(ProjectRequest(description="guestbook", target="railway"))

    paths = project_paths(str(tmp_path), project_id)
    reg = AgentRegistry(paths["agents_db"], clock=lambda: 1)
    reg.spawn("a1", project_id, 1, "build", "claude-opus-4-8")
    reg.record("a1", outcome="real_diff", cost_usd=0.42, provenance="7", diff_lines=120)
    from software_factory.tickets import TicketStore
    ts = TicketStore(paths["tickets_db"])
    tid = ts.create_ticket("guestbook", acceptance="a", dod="d", wave=1)
    ts.mark_done(tid, provenance="7", diff_lines=120)

    state = c._load_state(project_id)
    state.phase = "done"; state.deploy_url = "https://g.up.railway.app"; state.spent_usd = 0.42
    state.save()

    ev = c.evidence(project_id)
    assert ev["verified"] is True
    assert ev["reasons"] == []
    assert ev["bundle"]["skill"] == "software-factory"


def test_stage_handoff_stage1_done_enables_stage2(tmp_path):
    """Stage 1 events + PRD → detect_stage1_done → start_stage2."""
    import os
    launcher = FakeLauncher()
    c = console(tmp_path, launcher)
    project_id = c.start_project(ProjectRequest(description="guestbook"))

    assert c.detect_stage1_done(project_id) is False

    # Simulate Stage 1 completing: write a real PRD (the mechanical proof — no event needed)
    d = str(tmp_path)
    base = os.path.join(d, project_id)
    ws = os.path.join(base, "workspace")
    os.makedirs(ws, exist_ok=True)
    prd = (
        "# PRD\nhttps://a.com https://b.com https://c.com\n"
        "## Acceptance criteria\nGiven a visitor, when submit, then shown\n"
        "## Ticket seeds\n- seed: form\n"
    )
    with open(os.path.join(ws, "PRD.md"), "w") as f:
        f.write(prd)

    assert c.detect_stage1_done(project_id) is True

    state = c._load_state(project_id)
    assert state.stage1_done is True

    st = c.status(project_id)
    assert st["stage1_done"] is True


def test_stage2_not_done_when_ticket_store_is_empty(tmp_path):
    """Fix #1: artifacts present is NOT enough — if tickets were never persisted to the store,
    Stage 2 is not done (the buildable-tickets gate)."""
    import os
    launcher = FakeLauncher()
    c = console(tmp_path, launcher)
    project_id = c.start_project(ProjectRequest(description="x"))
    d = str(tmp_path); base = os.path.join(d, project_id)
    state = c._load_state(project_id); state.stage1_done = True; state.save()
    ws = os.path.join(base, "workspace"); os.makedirs(ws, exist_ok=True)
    for name, body in [("PRD.md", "# PRD"), ("architecture.md", "# A\n## Required Tokens\n- X_KEY — y\n"),
                       ("architecture.svg", "<svg/>")]:
        with open(os.path.join(ws, name), "w") as f:
            f.write(body)
    # No tickets persisted → not done
    assert c.detect_stage2_done(project_id) is False


def test_stage2_done_and_deps_flow(tmp_path):
    """Stage 2 artifacts + tickets → detect_stage2_done → submit_deps → start_stage3."""
    import os
    from software_factory.tickets import TicketStore
    launcher = FakeLauncher()
    c = console(tmp_path, launcher)
    project_id = c.start_project(ProjectRequest(description="guestbook"))
    d = str(tmp_path)
    base = os.path.join(d, project_id)

    # Mark stage 1 done
    state = c._load_state(project_id)
    state.stage1_done = True
    state.save()

    # Simulate stage 2 completing (artifacts on disk + buildable tickets — no event needed)
    ws = os.path.join(base, "workspace")
    os.makedirs(ws, exist_ok=True)
    with open(os.path.join(ws, "PRD.md"), "w") as f:
        f.write("# PRD content")
    arch_text = (
        "# Architecture\n## Required Tokens\n"
        "- RAILWAY_TOKEN — deploy\n- SUPABASE_URL — storage\n## Data Model\n"
    )
    with open(os.path.join(ws, "architecture.md"), "w") as f:
        f.write(arch_text)
    with open(os.path.join(ws, "architecture.svg"), "w") as f:
        f.write("<svg/>")
    ts = TicketStore(project_paths(d, project_id)["tickets_db"])
    ts.create_ticket("build form", acceptance="a", dod="d", wave=1)

    assert c.detect_stage2_done(project_id) is True
    state = c._load_state(project_id)
    assert state.stage2_done is True
    assert "RAILWAY_TOKEN" in state.deps_required
    assert "SUPABASE_URL" in state.deps_required

    # Deps not satisfied yet
    assert state.deps_satisfied is False
    assert c.start_stage3(project_id) is None

    # Submit deps
    result = c.submit_deps(project_id, {"RAILWAY_TOKEN": "tok1", "SUPABASE_URL": "url1"})
    assert result["satisfied"] is True
    assert result["missing"] == []

    # Status reflects deps
    st = c.status(project_id)
    assert st["stage2_done"] is True
    assert st["deps_satisfied"] is True
    assert "RAILWAY_TOKEN" in st["deps_provided"]


def test_submit_deps_unsatisfied_when_provide_lacks_value(tmp_path):
    c = console(tmp_path, FakeLauncher())
    project_id = c.start_project(ProjectRequest(description="x"))
    state = c._load_state(project_id)
    state.deps_required = ["OPENROUTER_API_KEY"]
    state.save()
    result = c.submit_deps(project_id, {"OPENROUTER_API_KEY": {"disposition": "provide"}})  # no value
    assert result["satisfied"] is False
    assert "OPENROUTER_API_KEY" in result["missing"]


# ---------------------------------------------------------------------------------------
# #107 post-deploy "provide your own key" flow — a user revisiting an already-live project
# replaces a mocked provider dep with their own real value. Zero-touch (SPEC §3) is
# untouched: classify_dep still defaults LLM keys to mock, this is a normal post-deploy
# authed action, not a mid-build pause.
# ---------------------------------------------------------------------------------------

def _deployed_project(c, deps_required=("OPENROUTER_API_KEY",)):
    project_id = c.start_project(ProjectRequest(description="x"))
    state = c._load_state(project_id)
    state.deps_required = list(deps_required)
    state.deploy_url = "https://sf-" + project_id + ".up.railway.app"
    state.save()
    return project_id


def test_provide_deployed_dep_rejects_project_with_no_live_deployment(tmp_path):
    c = console(tmp_path, FakeLauncher())
    project_id = c.start_project(ProjectRequest(description="x"))
    result = c.provide_deployed_dep(project_id, "OPENROUTER_API_KEY", "sk-real")
    assert result == {"ok": False, "detail": "project has no live deployment yet"}


def test_provide_deployed_dep_rejects_unknown_dep_name(tmp_path):
    c = console(tmp_path, FakeLauncher())
    project_id = _deployed_project(c)
    result = c.provide_deployed_dep(project_id, "SOME_OTHER_KEY", "sk-real")
    assert result["ok"] is False and "SOME_OTHER_KEY" in result["detail"]


def test_provide_deployed_dep_rejects_blank_value(tmp_path):
    c = console(tmp_path, FakeLauncher())
    project_id = _deployed_project(c)
    result = c.provide_deployed_dep(project_id, "OPENROUTER_API_KEY", "   ")
    assert result == {"ok": False, "detail": "value required"}


def test_provide_deployed_dep_surfaces_railway_failure_without_touching_state(tmp_path, monkeypatch):
    from software_factory import deploy_db
    monkeypatch.setattr(deploy_db, "set_app_variable",
                        lambda pid, name, value, service_id=None: {"ok": False, "detail": "service not found"})
    c = console(tmp_path, FakeLauncher())
    project_id = _deployed_project(c)
    result = c.provide_deployed_dep(project_id, "OPENROUTER_API_KEY", "sk-real")
    assert result == {"ok": False, "detail": "service not found"}
    # A failed live push must never flip the disposition or mark it provided.
    state = c._load_state(project_id)
    assert state.deps_disposition.get("OPENROUTER_API_KEY") != "provide"
    assert "OPENROUTER_API_KEY" not in (state.deps_provided or [])


def test_provide_deployed_dep_success_flips_disposition_and_stores_vault_entry(tmp_path, monkeypatch):
    from software_factory import deploy_db, vault as vault_module
    monkeypatch.setattr(deploy_db, "set_app_variable",
                        lambda pid, name, value, service_id=None: {"ok": True, "service_id": "svc-app123"})
    monkeypatch.setattr(vault_module, "vault_store", lambda name, secret: "vault-uuid-1")
    c = console(tmp_path, FakeLauncher())
    project_id = _deployed_project(c)
    result = c.provide_deployed_dep(project_id, "OPENROUTER_API_KEY", "sk-real")
    assert result == {"ok": True, "name": "OPENROUTER_API_KEY", "disposition": "provide", "vault_saved": True}
    state = c._load_state(project_id)
    assert state.deps_disposition["OPENROUTER_API_KEY"] == "provide"
    assert "OPENROUTER_API_KEY" in state.deps_provided
    assert state.deps_satisfied is True
    assert state.creds_vault_ids["OPENROUTER_API_KEY"] == "vault-uuid-1"


def test_provide_deployed_dep_succeeds_even_if_vault_store_raises(tmp_path, monkeypatch):
    # The live app already has the real key at this point (Railway push succeeded) — a vault
    # write failure must not make the operator think the key never took effect.
    from software_factory import deploy_db, vault as vault_module
    monkeypatch.setattr(deploy_db, "set_app_variable",
                        lambda pid, name, value, service_id=None: {"ok": True, "service_id": "svc-app123"})
    def _boom(name, secret):
        raise RuntimeError("vault unreachable")
    monkeypatch.setattr(vault_module, "vault_store", _boom)
    c = console(tmp_path, FakeLauncher())
    project_id = _deployed_project(c)
    result = c.provide_deployed_dep(project_id, "OPENROUTER_API_KEY", "sk-real")
    assert result == {"ok": True, "name": "OPENROUTER_API_KEY", "disposition": "provide", "vault_saved": False}
    state = c._load_state(project_id)
    assert state.deps_disposition["OPENROUTER_API_KEY"] == "provide"
    assert "OPENROUTER_API_KEY" not in state.creds_vault_ids


def test_graph_includes_stage_gates_and_deps_node(tmp_path):
    """The graph always includes stage gates and a deps node."""
    c = console(tmp_path, FakeLauncher())
    project_id = c.start_project(ProjectRequest(description="x"))
    g = c.graph(project_id)

    # Stage gates
    gate_nodes = [n for n in g["nodes"] if n["data"]["kind"] == "gate"]
    gate_ids = {n["data"]["id"] for n in gate_nodes}
    assert "gate:stage1" in gate_ids
    assert "gate:stage2" in gate_ids

    # Deps node
    deps_nodes = [n for n in g["nodes"] if n["data"]["kind"] == "deps"]
    assert len(deps_nodes) == 1
    assert deps_nodes[0]["data"]["id"] == "deps:wait"
    assert deps_nodes[0]["data"]["status"] == "pending"

    # When stage1 is done, gate shows passed
    state = c._load_state(project_id)
    state.stage1_done = True
    state.save()
    g2 = c.graph(project_id)
    s1gate = [n for n in g2["nodes"] if n["data"]["id"] == "gate:stage1"][0]
    assert s1gate["data"]["status"] == "passed"


def test_status_includes_stage_fields(tmp_path):
    c = console(tmp_path, FakeLauncher())
    project_id = c.start_project(ProjectRequest(description="x"))
    st = c.status(project_id)
    assert "stage" in st
    assert st["stage"] == 1
    assert st["stage1_done"] is False
    assert st["stage2_done"] is False
    assert st["deps_satisfied"] is False


def test_auto_resume_never_resurrects_a_ghost_run(tmp_path):
    # A project.db created by a mere status query (state lost, no artifacts) must NOT auto-resume:
    # there is no brief to build from — resuming burns spend on an empty prompt
    # (the project-b594a5f4/project-0eb69fdd double-ghost scar).
    launcher = FakeLauncher()
    c = console(tmp_path, launcher)
    c.status("project-ghost")           # creates an empty project.db as a side effect
    assert c.is_pipeline_project("project-ghost") is False
    assert c.auto_resume_dead_stage("project-ghost") is False
    assert launcher.argv is None    # nothing launched


# ---- Per-run model picks (claude runtime): planning = S1/S2, implementation = S3 ----

def _argv_model(argv):
    return argv[argv.index("--model") + 1]


def test_start_run_launches_stage1_on_the_chosen_planning_model(tmp_path):
    launcher = FakeLauncher()
    c = console(tmp_path, launcher)
    rid = c.start_project(ProjectRequest(description="app", planning_model="claude-fable-5",
                                 impl_model="claude-opus-4-8"))
    assert _argv_model(launcher.argv) == "claude-fable-5"
    st = c.status(rid)
    assert st["planning_model"] == "claude-fable-5"
    assert st["impl_model"] == "claude-opus-4-8"


def test_model_defaults_unchanged_when_nothing_picked(tmp_path):
    launcher = FakeLauncher()
    c = console(tmp_path, launcher)
    rid = c.start_project(ProjectRequest(description="app"))
    assert _argv_model(launcher.argv) == "claude-opus-4-8"
    st = c.status(rid)
    assert st["planning_model"] == ""
    assert st["impl_model"] == ""


def test_stage3_uses_the_chosen_impl_model_and_mandates_it_for_subagents(tmp_path):
    # The stage-3 SKILL contract pins sonnet for subagents; an explicit operator pick must
    # override that in-prompt, or the orchestrator would fight its own contract.
    # Uses retry_stage (the operator resume path) to trigger Stage 3 with the impl_model.
    class FakeProc:
        def __init__(self): self.exit_code = None
        def poll(self): return self.exit_code
    proc = FakeProc(); argvs = []
    def launcher(argv, env=None, log_path=None, cwd=None):
        argvs.append(argv); return proc
    ids = iter(["project-im"])
    c = Console(str(tmp_path), launch=launcher, new_id=lambda: next(ids))
    rid = c.start_project(ProjectRequest(description="x", impl_model="claude-opus-4-8"))
    st = c._load_state(rid)
    st.stage1_done = True; st.stage2_done = True; st.deps_satisfied = True; st.stage = 3
    st.phase = "build"  # crashed mid-build
    st.save()
    proc.exit_code = 0   # process finished
    assert c.retry_stage(rid, 3) == rid
    argv = argvs[-1]
    assert _argv_model(argv) == "claude-opus-4-8"
    prompt = argv[2]
    assert "claude-opus-4-8" in prompt and "subagent" in prompt.lower()


def test_unknown_model_picks_are_ignored(tmp_path):
    # Only the operator-offered choices are valid (planning: opus-4-8|fable-5;
    # impl: sonnet-4-6|opus-4-8). Anything else falls back to the defaults.
    launcher = FakeLauncher()
    c = console(tmp_path, launcher)
    rid = c.start_project(ProjectRequest(description="app", planning_model="gpt-5o-mega",
                                 impl_model="claude-haiku-4-5"))
    assert _argv_model(launcher.argv) == "claude-opus-4-8"
    st = c.status(rid)
    assert st["planning_model"] == ""
    assert st["impl_model"] == ""


def test_per_run_model_pick_beats_the_SF_MODEL_env_override(tmp_path, monkeypatch):
    # SF_MODEL is a deploy-wide default knob; an explicit per-project operator pick is more
    # specific and must win (the env var once silently forced wrong models — never again).
    monkeypatch.setenv("SF_MODEL", "claude-sonnet-4-6")
    launcher = FakeLauncher()
    c = console(tmp_path, launcher)
    c.start_project(ProjectRequest(description="app", planning_model="claude-fable-5"))
    assert _argv_model(launcher.argv) == "claude-fable-5"


def test_project_name_is_pinned_and_surfaces_in_status_and_list(tmp_path):
    launcher = FakeLauncher()
    c = console(tmp_path, launcher)
    rid = c.start_project(ProjectRequest(description="a crm for plumbers", name="Acme CRM"))
    assert c.status(rid)["name"] == "Acme CRM"
    assert [r["name"] for r in c.list_projects()] == ["Acme CRM"]


def test_status_carries_the_effective_budget_ceiling(tmp_path, monkeypatch):
    # The cap pill can only reflect a raise if status() exposes the ceiling — the operator
    # raised the cap and the UI showed nothing (state changed invisibly).
    monkeypatch.setenv("SF_COST_CEILING", "30")
    launcher = FakeLauncher()
    c = console(tmp_path, launcher)
    rid = c.start_project(ProjectRequest(description="app"))
    assert c.status(rid)["budget_ceiling"] == 30.0
    c.raise_budget(rid, 55)
    assert c.status(rid)["budget_ceiling"] == 55.0


def test_demo_credentials_surface_from_the_recorded_artifact(tmp_path):
    # SPEC §6 delivery: an app with a sign-in is demo-able only if the seeded demo login
    # reaches the operator — the chat done-message reads it from the demo-creds artifact.
    import os
    from software_factory.db import ProjectStore, db_path
    launcher = FakeLauncher()
    c = console(tmp_path, launcher)
    rid = c.start_project(ProjectRequest(description="app"))
    ws = os.path.join(str(tmp_path), rid)
    with open(os.path.join(ws, "demo_credentials.md"), "w") as f:
        f.write("user: demo@acme.test\npassword: factory-demo-1")
    ProjectStore(db_path(str(tmp_path), rid)).record_artifact(
        "Demo credentials", "demo_credentials.md", kind="demo-creds")
    creds = c.demo_credentials(rid)
    assert "demo@acme.test" in creds and "factory-demo-1" in creds


def test_demo_credentials_none_when_absent(tmp_path):
    launcher = FakeLauncher()
    c = console(tmp_path, launcher)
    rid = c.start_project(ProjectRequest(description="app"))
    assert c.demo_credentials(rid) is None


def test_stage3_prompt_mandates_demo_credentials_recording(tmp_path):
    req = ProjectRequest(description="a crm", target="railway")
    for rt in ("claude", "opencode"):
        p = make_prompt_stage3(req, "project-xyz", projects_dir="/runs", runtime=rt)
        assert "demo_credentials.md" in p, rt
        assert "demo-creds" in p, rt


def test_list_runs_unions_pg_registry_with_local_dirs(tmp_path, monkeypatch):
    # pg mode: a run can exist ONLY in the registry (fresh container, empty volume) —
    # discovery must surface it; local dirs win the dedupe (richer mtime ordering).
    from software_factory import console as console_mod
    launcher = FakeLauncher()
    c = console(tmp_path, launcher)
    rid_local = c.start_project(ProjectRequest(description="local run"))
    monkeypatch.setattr(console_mod.dbshim, "registry_projects",
                        lambda: [{"project_id": rid_local, "created": 1.0},
                                 {"project_id": "project-pgonly", "created": 2.0}])
    ids = [r["project_id"] for r in c.list_projects()]
    assert ids.count(rid_local) == 1            # deduped
    assert "project-pgonly" in ids                  # registry-only run surfaced


# ---------- run ownership (multi-tenant: members see only their own) ----------

def test_owner_stamped_and_list_filters_by_owner(tmp_path):
    launcher = FakeLauncher()
    c = console(tmp_path, launcher)
    # console() fixture mints a single id "project-xyz"; mint distinct ids here
    ids = iter(["project-aaaa1111", "project-bbbb2222", "project-cccc3333"])
    c2 = Console(str(tmp_path), launch=launcher, new_id=lambda: next(ids))
    a = c2.start_project(ProjectRequest(description="a", owner="alice@x.com"))
    b = c2.start_project(ProjectRequest(description="b", owner="bob@x.com"))
    leg = c2.start_project(ProjectRequest(description="legacy"))     # owner ""
    assert c2.project_owner(a) == "alice@x.com"
    assert c2.project_owner(leg) == ""
    allids = {r["project_id"] for r in c2.list_projects()}
    assert {a, b, leg} <= allids                             # admin/internal: all
    assert {r["project_id"] for r in c2.list_projects(owner="alice@x.com")} == {a}
    assert {r["project_id"] for r in c2.list_projects(owner="ALICE@X.COM")} == {a}   # case-insensitive
    assert leg not in {r["project_id"] for r in c2.list_projects(owner="bob@x.com")}  # unowned hidden
    assert c2.status(a)["owner"] == "alice@x.com"


def test_assign_unowned_is_idempotent(tmp_path):
    launcher = FakeLauncher()
    ids = iter(["project-dddd4444", "project-eeee5555"])
    c = Console(str(tmp_path), launch=launcher, new_id=lambda: next(ids))
    owned = c.start_project(ProjectRequest(description="owned", owner="alice@x.com"))
    leg = c.start_project(ProjectRequest(description="legacy"))
    assert c.assign_unowned("admin@x.com") == 1
    assert c.project_owner(leg) == "admin@x.com"
    assert c.project_owner(owned) == "alice@x.com"               # untouched
    assert c.assign_unowned("admin@x.com") == 0              # nothing left


def test_stage_runner_gets_the_runtime_llm_key_injected(tmp_path, monkeypatch):
    # The stage runner (`claude -p`) must authenticate; stage_env_baseline scrubs the console env, so
    # _launch_stage injects the active runtime's key. Without this, Stage 1 dies at auth → run at 0%.
    monkeypatch.delenv("SF_RUNTIME", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    launcher = FakeLauncher()
    c = console(tmp_path, launcher)
    c.start_project(ProjectRequest(description="a guestbook app", target="railway"))   # default claude
    assert "claude" in launcher.argv[0]
    assert launcher.env.get("ANTHROPIC_API_KEY") == "sk-ant-test"   # the runner can authenticate


def test_stage_env_baseline_scrubs_llm_key_so_it_never_leaks_to_a_built_app(monkeypatch):
    # GUARDRAIL: the factory LLM key reaches the RUNNER only via explicit injection; the baseline
    # scrub still excludes it, so any context that does NOT inject (the customer's deployed app env)
    # stays clean — the factory's Anthropic key can never land in a customer deployment.
    from software_factory import env as _env
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    base = _env.stage_env_baseline({})
    assert "ANTHROPIC_API_KEY" not in base and "OPENROUTER_API_KEY" not in base
    # an explicitly-provided key still passes through — that is exactly how the runner receives it
    assert _env.stage_env_baseline({"ANTHROPIC_API_KEY": "x"})["ANTHROPIC_API_KEY"] == "x"


def test_runner_key_is_byok_first_then_platform(tmp_path, monkeypatch):
    # Per-run resolution (NOT platform-hardcoded): a run that brings its OWN key (req.credentials)
    # uses it; the platform key must not overwrite it. (Values live only in the launch env, never
    # persisted — only names land in creds_provided.)
    monkeypatch.delenv("SF_RUNTIME", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-PLATFORM")
    launcher = FakeLauncher()
    c = console(tmp_path, launcher)
    c.start_project(ProjectRequest(description="byok app", target="railway",
                                   credentials={"ANTHROPIC_API_KEY": "sk-ant-BYOK"}))
    assert launcher.env.get("ANTHROPIC_API_KEY") == "sk-ant-BYOK"   # BYOK wins, platform doesn't clobber


# ── BYOK Vault storage ────────────────────────────────────────────────────────

import software_factory.console as _console_mod


def _stub_vault(monkeypatch, store_uuid="vault-uuid-test"):
    """Patch vault functions so tests never hit a real Supabase Vault."""
    stored = {}

    def _fake_store(name, secret):
        stored[name] = secret
        return store_uuid

    def _fake_retrieve(vault_ids):
        # Return a fabricated plaintext based on what was "stored"
        return {k: f"decrypted-{v}" for k, v in vault_ids.items()}

    deleted = []

    def _fake_delete(uuids):
        deleted.extend(uuids)

    monkeypatch.setattr(_console_mod._vault, "vault_store", _fake_store)
    monkeypatch.setattr(_console_mod._vault, "vault_retrieve_many", _fake_retrieve)
    monkeypatch.setattr(_console_mod._vault, "vault_delete_many", _fake_delete)
    return stored, deleted


def test_byok_credentials_stored_in_vault_on_provision(tmp_path, monkeypatch):
    # On project creation with BYOK credentials, each value must be encrypted in Vault and
    # the UUID persisted in state.creds_vault_ids — plaintext never touches disk.
    monkeypatch.delenv("SF_RUNTIME", raising=False)
    stored, _ = _stub_vault(monkeypatch, store_uuid="vault-uuid-tok")
    launcher = FakeLauncher()
    c = console(tmp_path, launcher)
    pid = c.start_project(ProjectRequest(
        description="deploy app", credentials={"RAILWAY_TOKEN": "tok_live"}))
    state = c.status(pid)
    assert state["creds_provided"] == ["RAILWAY_TOKEN"]  # name persisted
    # Vault was called with the plaintext
    assert any("tok_live" in str(v) for v in stored.values())
    # The vault UUID is in state (load directly to verify)
    from software_factory.console import project_paths
    from software_factory.projectstate import ProjectState
    from software_factory.db import ProjectStore
    st = ProjectState.load(pid, ProjectStore(project_paths(str(tmp_path), pid)["db"]))
    assert st.creds_vault_ids.get("RAILWAY_TOKEN") == "vault-uuid-tok"


def test_launch_stage_injects_vault_decrypted_keys(tmp_path, monkeypatch):
    # _launch_stage must retrieve stored BYOK values from Vault and inject them into the
    # stage runner's env. For Stage 1 the env already carries the plaintext (from _provision),
    # so vault_retrieve_many is called but the caller env wins in the merge (correct precedence).
    # Stage 2 tests (below) verify the Vault-only path where env starts empty.
    monkeypatch.delenv("SF_RUNTIME", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-platform")
    vault_retrieve_calls = []

    def _capturing_retrieve(vault_ids):
        vault_retrieve_calls.append(dict(vault_ids))
        return {"RAILWAY_TOKEN": "decrypted-value"}

    _, _ = _stub_vault(monkeypatch)
    monkeypatch.setattr(_console_mod._vault, "vault_retrieve_many", _capturing_retrieve)
    launcher = FakeLauncher()
    c = console(tmp_path, launcher)
    pid = c.start_project(ProjectRequest(
        description="app", credentials={"RAILWAY_TOKEN": "tok_live"}))
    # vault_retrieve_many must have been called during _launch_stage
    assert vault_retrieve_calls, "vault_retrieve_many was never called"
    # The key must be in the runner env (Stage 1: caller env value wins the merge)
    assert "RAILWAY_TOKEN" in launcher.env


def test_stage2_uses_vault_not_os_environ_for_byok_keys(tmp_path, monkeypatch):
    # Stage 2 launch must pull BYOK values from Vault, not from os.environ.
    # This fixes the brittle path where Stage 2 fell back to the console's OS env.
    monkeypatch.delenv("SF_RUNTIME", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-platform")
    monkeypatch.delenv("RAILWAY_TOKEN", raising=False)  # NOT in console's env
    _stub_vault(monkeypatch)
    launcher = FakeLauncher()
    c = console(tmp_path, launcher)
    pid = c.start_project(ProjectRequest(
        description="app", credentials={"RAILWAY_TOKEN": "tok_live"}))
    # Manually wire stage1 done + trigger stage2
    from software_factory.projectstate import ProjectState
    from software_factory.db import ProjectStore
    from software_factory.console import project_paths
    from software_factory.tickets import TicketStore
    from software_factory import artifacts
    import os, shutil
    paths = project_paths(str(tmp_path), pid)
    st = ProjectState.load(pid, ProjectStore(paths["db"]))
    st.stage1_done = True
    st.save()
    # Create artifacts so detect_stage2_done has something to find
    ws = os.path.join(str(tmp_path), pid, "workspace", "stage2")
    os.makedirs(ws, exist_ok=True)
    for f in ["PRD.md", "architecture.md", "architecture.svg"]:
        open(os.path.join(ws, f), "w").write("# stub")
    TicketStore(paths["tickets_db"]).create_ticket(
        title="T", acceptance="AC", dod="DOD", wave=1, description="D")
    st.stage2_done = True
    st.save()
    launcher2 = FakeLauncher()
    c._launch = launcher2
    c.start_stage2(pid)
    # Vault-retrieved key must reach the runner
    assert "RAILWAY_TOKEN" in launcher2.env
    assert launcher2.env["RAILWAY_TOKEN"].startswith("decrypted-")


def test_set_archived_deletes_vault_secrets(tmp_path, monkeypatch):
    # Archiving a project must delete its Vault secrets (encrypted key lifecycle matches run lifecycle).
    monkeypatch.delenv("SF_RUNTIME", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-platform")
    _, deleted = _stub_vault(monkeypatch, store_uuid="vault-uuid-del")
    launcher = FakeLauncher()
    c = console(tmp_path, launcher)
    pid = c.start_project(ProjectRequest(
        description="app", credentials={"RAILWAY_TOKEN": "tok_live"}))
    c.set_archived(pid, True)
    # The vault UUID that was stored must have been queued for deletion
    assert "vault-uuid-del" in deleted


def test_extra_creds_override_vault_stored_values(tmp_path, monkeypatch):
    # When the same key exists in both Vault and extra_creds (Stage 3 gate path),
    # the per-run extra_creds value must win (higher specificity).
    monkeypatch.delenv("SF_RUNTIME", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-platform")
    _stub_vault(monkeypatch, store_uuid="vault-uuid-x")

    override_val = "tok_from_gate"

    def _fake_retrieve_returns_other(vault_ids):
        return {"RAILWAY_TOKEN": "tok_from_vault"}

    monkeypatch.setattr(_console_mod._vault, "vault_retrieve_many", _fake_retrieve_returns_other)

    launcher = FakeLauncher()
    c = console(tmp_path, launcher)
    pid = c.start_project(ProjectRequest(
        description="app", credentials={"RAILWAY_TOKEN": "tok_live"}))

    # Wire to stage3 launch: set all prereqs
    from software_factory.projectstate import ProjectState
    from software_factory.db import ProjectStore
    from software_factory.console import project_paths
    from software_factory.tickets import TicketStore
    import os
    paths = project_paths(str(tmp_path), pid)
    st = ProjectState.load(pid, ProjectStore(paths["db"]))
    st.stage1_done = True
    st.stage2_done = True
    st.deps_satisfied = True
    st.save()
    TicketStore(paths["tickets_db"]).create_ticket(
        title="T", acceptance="AC", dod="DOD", wave=1, description="D")
    launcher3 = FakeLauncher()
    c._launch = launcher3
    c.start_stage3(pid, extra_creds={"RAILWAY_TOKEN": override_val})
    # The explicitly-supplied gate value must win over the vault-retrieved one
    assert launcher3.env.get("RAILWAY_TOKEN") == override_val


# ---------------------------------------------------------------------------------------
# Deploy-DB teardown wiring (the second half of the orphan-leak fix). The console captures
# the provisioned serviceId, reaps it on archive per the A/B policy (DISARMED by default →
# dry-run), and the reaper sweeps ALL runs INCLUDING archived ones (list_projects hides those).
# ---------------------------------------------------------------------------------------

# NOTE: deploy-DB provisioning moved OUT of _launch_stage into the `provision-db` db-CLI verb
# (the stage-3 agent calls it). The verb's persist + salvage behavior is unit-tested in
# tests/unit/test_db.py; the console now only READS state.deploy_db_service_id (the teardown
# handle the verb writes) — proven by the teardown/reaper tests below.

def test_set_archived_reaps_captured_db_when_armed(tmp_path, monkeypatch):
    from software_factory import console as console_mod
    monkeypatch.setenv("SF_DEPLOY_DB_TEARDOWN", "persistent")        # armed, policy B
    c = console(tmp_path, FakeLauncher())
    pid = c.start_project(ProjectRequest(description="x"))
    st = c._load_state(pid); st.deploy_db_service_id = "svc-arch"; st.save()
    torn = []
    monkeypatch.setattr(console_mod.deploy_db, "teardown",
                        lambda service_id, volume_id="", run=None: (torn.append(service_id),
                            {"service_id": service_id, "deleted": True, "already_gone": False,
                             "ok": True, "detail": "", "volume_deleted": False,
                             "volume_already_gone": True})[1])
    assert c.set_archived(pid, True) is True
    assert torn == ["svc-arch"]                                     # archived under B → reap the captured DB


def test_set_archived_fires_teardown_hook_for_runs_with_a_captured_db(tmp_path, monkeypatch):
    # The hook MUST fire on archive (so the disarmed default can dry-run-log a candidate) — whether
    # it actually deletes is the policy gate's job, proven by the deploy_db.reap unit tests.
    from software_factory import console as console_mod
    monkeypatch.delenv("SF_DEPLOY_DB_TEARDOWN", raising=False)       # DISARMED (held)
    c = console(tmp_path, FakeLauncher())
    pid = c.start_project(ProjectRequest(description="x"))
    st = c._load_state(pid); st.deploy_db_service_id = "svc-held"; st.save()
    seen = []
    monkeypatch.setattr(console_mod.deploy_db, "reap",
                        lambda records, **k: (seen.extend(r.service_id for r in records), {"reaped": []})[1])
    c.set_archived(pid, True)
    assert seen == ["svc-held"]                                    # hook fired with the captured id


def test_set_archived_does_not_fire_hook_when_no_db_was_provisioned(tmp_path, monkeypatch):
    from software_factory import console as console_mod
    c = console(tmp_path, FakeLauncher())
    pid = c.start_project(ProjectRequest(description="static site, no db"))   # never provisioned a DB
    called = []
    monkeypatch.setattr(console_mod.deploy_db, "reap", lambda records, **k: called.append(1))
    c.set_archived(pid, True)
    assert called == []                                            # nothing to reap → no reaper call


def test_reap_deploy_dbs_sweeps_archived_runs_that_lists_hide(tmp_path, monkeypatch):
    from software_factory.console import Console
    monkeypatch.delenv("SF_DEPLOY_DB_TEARDOWN", raising=False)       # dry-run preview
    ids = iter(["project-aaaa1111", "project-bbbb2222"])
    c = Console(str(tmp_path), launch=FakeLauncher(), new_id=lambda: next(ids))
    a = c.start_project(ProjectRequest(description="archived one"))
    b = c.start_project(ProjectRequest(description="live demo"))
    sa = c._load_state(a); sa.deploy_db_service_id = "svc-a"; sa.archived = True; sa.save()
    sb = c._load_state(b)
    sb.deploy_db_service_id = "svc-b"; sb.phase = "done"; sb.deploy_url = "https://x"; sb.save()
    report = c.reap_deploy_dbs(dry_run=True)
    assert {w["service_id"] for w in report["would_reap"]} == {"svc-a"}   # archived surfaced + eligible
    assert {k["service_id"] for k in report["kept"]} == {"svc-b"}         # live done kept


# ── #57-field: runtime / model / key_source in status() ─────────────────────────────────────────
def test_status_exposes_runtime_model_key_source_defaults(tmp_path):
    # Default project (claude runtime, no BYOK) → runtime=claude, key_source=TENEXITY
    c = console(tmp_path, FakeLauncher())
    pid = c.start_project(ProjectRequest(description="guestbook", target="railway"))
    st = c.status(pid)
    assert st["runtime"] == "claude"
    assert st["key_source"] == "TENEXITY"
    assert "model" in st   # present; may be empty string (stage default)


def test_status_key_source_byok_when_anthropic_key_provided(tmp_path):
    c = console(tmp_path, FakeLauncher())
    pid = c.start_project(ProjectRequest(description="app",
                                         credentials={"ANTHROPIC_API_KEY": "sk-byok"}))
    st = c.status(pid)
    assert st["runtime"] == "claude"
    assert st["key_source"] == "BYOK"


def test_status_key_source_byok_opencode_uses_openrouter_key(tmp_path):
    c = console(tmp_path, FakeLauncher())
    pid = c.start_project(ProjectRequest(description="app", runtime="opencode",
                                         credentials={"OPENROUTER_API_KEY": "or-byok"}))
    st = c.status(pid)
    assert st["runtime"] == "opencode"
    assert st["key_source"] == "BYOK"


def test_status_key_source_tenexity_when_wrong_key_for_runtime(tmp_path):
    # opencode runtime but user only supplied ANTHROPIC_API_KEY → TENEXITY for opencode runner
    c = console(tmp_path, FakeLauncher())
    pid = c.start_project(ProjectRequest(description="app", runtime="opencode",
                                         credentials={"ANTHROPIC_API_KEY": "sk-byok"}))
    st = c.status(pid)
    assert st["runtime"] == "opencode"
    assert st["key_source"] == "TENEXITY"


def test_status_model_reflects_impl_model_for_claude(tmp_path):
    c = console(tmp_path, FakeLauncher())
    pid = c.start_project(ProjectRequest(description="app", impl_model="claude-sonnet-4-6"))
    st = c.status(pid)
    assert st["runtime"] == "claude"
    assert st["model"] == "claude-sonnet-4-6"


def test_status_model_reflects_opencode_alias(tmp_path):
    c = console(tmp_path, FakeLauncher())
    pid = c.start_project(ProjectRequest(description="app", runtime="opencode", model="glm"))
    st = c.status(pid)
    assert st["runtime"] == "opencode"
    assert st["model"] == "glm"


# ---- #104 watchdog: reap a completed-but-hung claude stage process -----------------------
class _ZombieProc:
    """A claude orchestrator that emitted its terminal `result` then hung at teardown: poll()
    keeps returning None until it's signalled."""
    def __init__(self): self.exit_code = None; self.pid = 4242; self.signals = []
    def poll(self): return self.exit_code
    def terminate(self): self.signals.append("term"); self.exit_code = -15
    def wait(self, timeout=None): return self.exit_code
    def kill(self): self.signals.append("kill"); self.exit_code = -9


def _write_log(c, pid, *events):
    import json, os
    log = os.path.join(c._paths(pid)["base"], "project.log")
    with open(log, "w", encoding="utf-8") as f:
        for ev in events:
            f.write(json.dumps(ev) + "\n")
    return log


def test_reap_completed_zombie_kills_hung_claude_after_grace(tmp_path, monkeypatch):
    # The systemic research-stall (#104): claude emits terminal `result` but the process hangs
    # at remote-MCP teardown, so the live handle pins stage_finished=False forever. The watchdog
    # SIGTERM→SIGKILLs it once the log's been idle past the grace, flipping stage_finished True.
    import os
    monkeypatch.setenv("SF_STAGE_REAP_GRACE_SEC", "1")
    proc = _ZombieProc()
    ids = iter(["project-zb"])
    c = Console(str(tmp_path), launch=lambda *a, **k: proc, new_id=lambda: next(ids))
    rid = c.start_project(ProjectRequest(description="x"))           # runtime defaults to claude
    log = _write_log(c, rid, {"type": "assistant"}, {"type": "result", "total_cost_usd": 1.2})
    os.utime(log, (1, 1))                                            # mtime far in the past -> past grace
    assert c.stage_finished(rid) is False                           # live handle pins it
    assert c.reap_completed_zombie(rid) == 4242                      # reaped, returns the pid
    assert "term" in proc.signals                                   # used the SIGTERM→kill path
    assert c.stage_finished(rid) is True                            # now exited -> existing detection advances


def test_reap_completed_zombie_leaves_an_actively_orchestrating_claude(tmp_path, monkeypatch):
    # Last event is NOT `result` (agent still working) -> never reaped, even past grace. This is
    # what keeps it from racing the §1 double-orchestrator guard.
    import os
    monkeypatch.setenv("SF_STAGE_REAP_GRACE_SEC", "1")
    proc = _ZombieProc()
    ids = iter(["project-ac"])
    c = Console(str(tmp_path), launch=lambda *a, **k: proc, new_id=lambda: next(ids))
    rid = c.start_project(ProjectRequest(description="x"))
    log = _write_log(c, rid, {"type": "result", "total_cost_usd": 1.0}, {"type": "assistant"})
    os.utime(log, (1, 1))
    assert c.reap_completed_zombie(rid) is None
    assert proc.signals == []


def test_reap_completed_zombie_respects_the_grace_window(tmp_path, monkeypatch):
    # A just-completed stage (log fresh) is within grace -> not reaped, giving a clean teardown
    # a chance to exit on its own first.
    monkeypatch.setenv("SF_STAGE_REAP_GRACE_SEC", "600")
    proc = _ZombieProc()
    ids = iter(["project-gw"])
    c = Console(str(tmp_path), launch=lambda *a, **k: proc, new_id=lambda: next(ids))
    rid = c.start_project(ProjectRequest(description="x"))
    _write_log(c, rid, {"type": "result", "total_cost_usd": 1.0})   # fresh mtime, within 600s grace
    assert c.reap_completed_zombie(rid) is None


def test_reap_completed_zombie_default_grace_is_short_not_60s(tmp_path):
    # #105 root-fix: Claude Code has no lazy-MCP-connect or teardown-timeout knob (confirmed
    # against upstream), so every claude+exa stage pays the full hung-teardown cost on every run.
    # The grace exists only to let a clean exit land on its own — it must NOT still default to the
    # original 60s (a minute of pure stall per stage); a few seconds past one poller tick (3s) is
    # plenty. No SF_STAGE_REAP_GRACE_SEC set here — this pins the shipped default, not an override.
    import os
    import time
    proc = _ZombieProc()
    ids = iter(["project-dg"])
    c = Console(str(tmp_path), launch=lambda *a, **k: proc, new_id=lambda: next(ids))
    rid = c.start_project(ProjectRequest(description="x"))
    log = _write_log(c, rid, {"type": "result", "total_cost_usd": 1.0})
    os.utime(log, (time.time() - 10, time.time() - 10))   # idle 10s — past a short default grace
    assert c.reap_completed_zombie(rid) == 4242
    assert "term" in proc.signals


def test_reap_completed_zombie_skips_opencode(tmp_path, monkeypatch):
    # opencode's linger is handled by the step_finish=stop path in stage_finished, not here.
    import os
    monkeypatch.setenv("SF_STAGE_REAP_GRACE_SEC", "1")
    proc = _ZombieProc()
    ids = iter(["project-oc"])
    c = Console(str(tmp_path), launch=lambda *a, **k: proc, new_id=lambda: next(ids))
    rid = c.start_project(ProjectRequest(description="x", runtime="opencode"))
    log = _write_log(c, rid, {"type": "result", "total_cost_usd": 1.0})
    os.utime(log, (1, 1))
    assert c.reap_completed_zombie(rid) is None


# ---------------------------------------------------------------------------------------
# #19 archive / restore / permanent-delete flow
# ---------------------------------------------------------------------------------------

def test_list_projects_include_archived_surfaces_rows_with_flag(tmp_path):
    # Default listing hides archived rows; include_archived=True keeps them, and EVERY row
    # carries an `archived` flag so the dashboard can split active from archived.
    c = console(tmp_path, FakeLauncher())
    ids = iter(["project-a", "project-b"])
    c._new_id = lambda: next(ids)
    live = c.start_project(ProjectRequest(description="live one"))
    arch = c.start_project(ProjectRequest(description="to archive"))
    c.set_archived(arch, True)

    default_ids = {r["project_id"] for r in c.list_projects()}
    assert live in default_ids and arch not in default_ids          # archived hidden by default

    rows = {r["project_id"]: r for r in c.list_projects(include_archived=True)}
    assert live in rows and arch in rows                            # archived now surfaced
    assert rows[arch]["archived"] is True
    assert rows[live]["archived"] is False                          # flag present on every row


def test_archive_then_restore_round_trip(tmp_path):
    # archive → restore → visible again in the default listing.
    c = console(tmp_path, FakeLauncher())
    c._new_id = lambda: "project-r"
    rid = c.start_project(ProjectRequest(description="restore me"))
    assert c.set_archived(rid, True) is True
    assert rid not in {r["project_id"] for r in c.list_projects()}
    assert c.set_archived(rid, False) is False
    assert rid in {r["project_id"] for r in c.list_projects()}      # back in the default listing


def test_delete_project_removes_run_and_is_idempotent(tmp_path, monkeypatch):
    # Permanent delete: the run vanishes from EVERY listing (incl. include_archived), the dir is
    # gone, the registry no longer knows it, and deleting again does not raise.
    import os
    from software_factory.console import project_paths
    c = console(tmp_path, FakeLauncher())
    c._new_id = lambda: "project-d"
    rid = c.start_project(ProjectRequest(description="delete me"))
    base = project_paths(str(tmp_path), rid)["base"]
    assert os.path.isdir(base)

    out = c.delete_project(rid)
    assert out == {"project_id": rid, "deleted": True}
    assert not os.path.isdir(base)                                  # run dir gone
    assert rid not in {r["project_id"] for r in c.list_projects(include_archived=True)}
    assert not c.project_exists(rid)                                # not on disk, not in the registry

    # Idempotent — a second delete (run already gone) must not raise.
    assert c.delete_project(rid) == {"project_id": rid, "deleted": True}
