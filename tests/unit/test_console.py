"""The operator console: turn a one-line app request into a headless factory run, expose
live status, and surface the deployed URL. The launcher is injected so tests never spawn a
real `claude` process.

This is the harness around the skill — it launches the skill and reads back the skill's own
artifacts; it does not do the building itself.
"""
from software_factory.console import (
    Console, RunRequest, make_prompt, make_prompt_stage1, make_prompt_stage2,
    make_prompt_stage3, run_paths,
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
    ids = iter(["run-xyz"])
    return Console(str(tmp_path), launch=launcher, new_id=lambda: next(ids), extract=extract)


def test_make_prompt_invokes_the_skill_with_run_id_target_and_budget():
    req = RunRequest(description="a guestbook app", context="dark theme", budget=100.0, target="railway")
    p = make_prompt(req, "run-xyz", runs_dir="/runs")
    assert "software-factory" in p          # explicit, deterministic invocation
    assert "run-xyz" in p
    assert "100" in p
    assert "guestbook" in p
    assert "/runs/run-xyz" in p             # tells the orchestrator where to write artifacts
    # Stage 3 prompt carries the deploy target
    p3 = make_prompt_stage3(req, "run-xyz", runs_dir="/runs")
    assert "railway" in p3
    assert "sf-run-xyz" in p3


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


def test_uploaded_pdf_is_extracted_to_markdown_and_composed_into_stage1_input(tmp_path):
    import base64, os
    c = console(tmp_path, FakeLauncher(), extract=lambda path: "# Brief\n\nEPC contract T&C")
    b64 = base64.b64encode(b"%PDF-1.4 ...").decode()
    run_id = c.start_run(RunRequest(description="analyze this",
                                    context_files=[{"name": "brief.pdf", "content_b64": b64}]))
    input_dir = os.path.join(str(tmp_path), run_id, "input")
    # raw PDF is consumed by the conversion; the markdown is what Stage 1 reads
    assert not os.path.exists(os.path.join(input_dir, "brief.pdf"))
    assert "EPC contract T&C" in open(os.path.join(input_dir, "brief.pdf.md")).read()
    # the composed Stage 1 input merges the user prompt and the extracted markdown
    ctx = open(os.path.join(input_dir, "context.txt")).read()
    assert "analyze this" in ctx
    assert "EPC contract T&C" in ctx


def test_retry_stage2_relaunches_with_the_stage2_prompt(tmp_path):
    launcher = FakeLauncher()
    c = console(tmp_path, launcher)
    run_id = c.start_run(RunRequest(description="x", target="railway"))
    st = c._load_state(run_id); st.stage1_done = True; st.save()
    launcher.argv = None

    out = c.retry_stage(run_id, 2)

    assert out == run_id
    assert launcher.argv is not None and "claude" in launcher.argv[0]
    assert "Stage 2" in launcher.argv[2]        # the rebuilt prompt is for stage 2
    assert c.status(run_id)["stage"] == 2


def test_retry_stage2_blocked_when_stage1_not_done(tmp_path):
    launcher = FakeLauncher()
    c = console(tmp_path, launcher)
    run_id = c.start_run(RunRequest(description="x"))
    st = c._load_state(run_id); st.stage1_done = False; st.save()
    launcher.argv = None

    assert c.retry_stage(run_id, 2) is None
    assert launcher.argv is None                # nothing relaunched


def test_retry_clears_the_target_stage_done_flag(tmp_path):
    launcher = FakeLauncher()
    c = console(tmp_path, launcher)
    run_id = c.start_run(RunRequest(description="x"))
    st = c._load_state(run_id); st.stage1_done = True; st.stage2_done = True; st.save()

    c.retry_stage(run_id, 2)

    assert c.status(run_id)["stage2_done"] is False   # re-runs so the gate re-evaluates


def test_retry_invalid_stage_returns_none(tmp_path):
    c = console(tmp_path, FakeLauncher())
    run_id = c.start_run(RunRequest(description="x"))
    assert c.retry_stage(run_id, 9) is None


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
    p = make_prompt_stage3(RunRequest(description="x", target="railway"), "run-xyz", runs_dir="/runs")
    assert "sf-run-xyz" in p           # per-run dedicated service name
    assert "never" in p.lower()  # explicit don't-clobber warning


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
    from software_factory.db import RunDB, db_path
    from software_factory.agents import AgentRegistry
    c = console(tmp_path, FakeLauncher())
    run_id = c.start_run(RunRequest(description="guestbook"))
    d = str(tmp_path)
    # an agent, an artifact, a blocker, and an open gate — ALL recorded in run.db (no events)
    AgentRegistry(db_path(d, run_id)).spawn("t1", run_id, None, "build form", "claude-sonnet-4-6", phase="build")
    db = RunDB(db_path(d, run_id))
    db.record_artifact("PRD", "PRD.md", kind="prd")
    db.add_blocker("Supabase project not ready", blocks="wait-for-deps")
    db.set_gate("prd", "awaiting")

    g = c.graph(run_id)
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
    # SPEC §3 zero-touch: a stage that died mid-flight (OOM/crash — process gone, its gate not
    # passed) is auto-resumed by the host. A human noticing the stall is an intervention.
    class FakeProc:
        def __init__(self): self.exit_code = None
        def poll(self): return self.exit_code
    proc = FakeProc(); argvs = []
    def launcher(argv, env=None, log_path=None, cwd=None):
        argvs.append(argv); return proc
    ids = iter(["run-ar"])
    c = Console(str(tmp_path), launch=launcher, new_id=lambda: next(ids))
    rid = c.start_run(RunRequest(description="x"))
    st = c._load_state(rid)
    st.stage1_done = True; st.stage2_done = True; st.deps_satisfied = True; st.stage = 3
    st.save()
    proc.exit_code = None
    assert c.auto_resume_dead_stage(rid) is False    # process alive -> not dead, no resume
    proc.exit_code = -9                              # killed mid-stage-3, no verification recorded
    assert c.auto_resume_dead_stage(rid) is True     # host resumes stage 3 itself
    assert "Stage 3" in argvs[-1][2]


def test_auto_resume_does_not_fire_at_the_deps_gate_or_when_budget_blocked(tmp_path):
    # A run waiting at the deps gate (stage complete) or stopped for budget is NOT a dead stage.
    class FakeProc:
        def __init__(self): self.exit_code = 0
        def poll(self): return self.exit_code
    ids = iter(["run-ng"])
    c = Console(str(tmp_path), launch=lambda *a, **k: FakeProc(), new_id=lambda: next(ids))
    rid = c.start_run(RunRequest(description="x"))
    st = c._load_state(rid)
    st.stage1_done = True; st.stage2_done = True; st.stage = 2   # finished S2, waiting on deps
    st.save()
    assert c.auto_resume_dead_stage(rid) is False
    from software_factory.db import RunDB, db_path
    st = c._load_state(rid); st.stage = 3; st.deps_satisfied = True; st.save()
    RunDB(db_path(str(tmp_path), rid)).add_blocker("Budget cap reached", blocks="budget")
    assert c.auto_resume_dead_stage(rid) is False    # budget-stopped: waits for the operator


def test_auto_resume_never_resurrects_a_canceled_run(tmp_path):
    # phase='stopped' (operator cancel) is terminal — auto-resume must not bring it back.
    class DeadProc:
        def poll(self): return -9
    ids = iter(["run-cx"])
    c = Console(str(tmp_path), launch=lambda *a, **k: DeadProc(), new_id=lambda: next(ids))
    rid = c.start_run(RunRequest(description="x"))
    st = c._load_state(rid); st.phase = "stopped"; st.save()
    assert c.auto_resume_dead_stage(rid) is False


def test_budget_kill_is_recoverable_raise_and_resume(tmp_path, monkeypatch):
    # SPEC §4: at the per-run ceiling the poller kills the stage process and records a budget
    # blocker — but the run is RECOVERABLE: raise_budget(ceiling) clears the blocker and the
    # higher per-run ceiling lets the stage relaunch.
    monkeypatch.setenv("SF_COST_CEILING", "10")
    monkeypatch.setenv("SF_STAGE_RESERVE", "0")
    class FakeProc:
        def __init__(self): self.exit_code = None; self.terminated = False
        def poll(self): return self.exit_code
        def terminate(self): self.terminated = True; self.exit_code = -15
    proc = FakeProc()
    ids = iter(["run-bk"])
    c = Console(str(tmp_path), launch=lambda *a, **k: proc, new_id=lambda: next(ids))
    rid = c.start_run(RunRequest(description="x"))
    st = c._load_state(rid); st.spent_usd = 11.0; st.save()       # over the $10 ceiling
    assert c.enforce_budget(rid) is True                          # killed
    assert proc.terminated is True
    from software_factory.db import RunDB, db_path
    db = RunDB(db_path(str(tmp_path), rid))
    open_blockers = [b for b in db.blockers() if not b["cleared"]]
    assert any(b.get("blocks") == "budget" for b in open_blockers)
    # recovery: raise the per-run ceiling -> blocker cleared, persisted override honored
    c.raise_budget(rid, 40.0)
    assert c._load_state(rid).budget_ceiling == 40.0
    assert not [b for b in db.blockers() if not b["cleared"]]
    assert c.enforce_budget(rid) is False                         # under the new ceiling
    st = c._load_state(rid); st.stage1_done = True; st.save()
    assert c.start_stage2(rid) == rid                             # launch-gate honors the override


def test_run_spend_is_per_run_not_cumulative(tmp_path):
    # Per-run budget: each run/project is capped independently. _run_spend reflects ONLY this run's
    # own spend; a prior run's spend does not count against another.
    ids = iter(["run-a", "run-b"])
    c = Console(str(tmp_path), launch=FakeLauncher(), new_id=lambda: next(ids))
    a = c.start_run(RunRequest(description="x"))
    st = c._load_state(a); st.spent_usd = 4.0; st.save()
    b = c.start_run(RunRequest(description="y"))
    st = c._load_state(b); st.spent_usd = 9.0; st.save()
    assert c._run_spend(a) == 4.0                         # only run-a's spend
    assert c._run_spend(b) == 9.0                         # run-a's $4 does NOT count against run-b


def test_launch_refused_when_this_runs_spend_crosses_ceiling(tmp_path, monkeypatch):
    # Mechanical per-run hard stop: refuse a stage launch when THIS run's spend + a stage reserve
    # would cross SF_COST_CEILING — so the advisory in-prompt budget can't silently blow past it.
    monkeypatch.setenv("SF_COST_CEILING", "10")
    monkeypatch.setenv("SF_STAGE_RESERVE", "5")
    launcher = FakeLauncher()
    c = console(tmp_path, launcher)
    rid = c.start_run(RunRequest(description="x"))
    st = c._load_state(rid); st.spent_usd = 8.0; st.stage1_done = True; st.save()  # 8 + 5 reserve > 10
    launcher.argv = None
    assert c.start_stage2(rid) is None                   # refused
    assert launcher.argv is None                          # no process launched
    from software_factory.db import RunDB, db_path
    blockers = " ".join(b.get("what", "") for b in RunDB(db_path(str(tmp_path), rid)).blockers())
    assert "budget" in blockers.lower()


def test_launch_proceeds_when_under_ceiling(tmp_path, monkeypatch):
    monkeypatch.setenv("SF_COST_CEILING", "30")
    monkeypatch.setenv("SF_STAGE_RESERVE", "5")
    launcher = FakeLauncher()
    c = console(tmp_path, launcher)
    rid = c.start_run(RunRequest(description="x"))
    st = c._load_state(rid); st.spent_usd = 2.0; st.stage1_done = True; st.save()
    assert c.start_stage2(rid) == rid                     # well under ceiling -> launches
    assert launcher.argv is not None


def test_next_stage_waits_for_prior_stage_process_to_exit(tmp_path):
    # run-d329e57c scar: detect_stage1_done is mechanical (PRD passes -> poller launches S2)
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
    ids = iter(["run-ov"])
    c = Console(str(tmp_path), launch=launcher, new_id=lambda: next(ids))
    rid = c.start_run(RunRequest(description="x"))
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
    rid = c.start_run(RunRequest(description="x"))
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
    rid = c.start_run(RunRequest(description="x"))
    st = c._load_state(rid)
    st.stage2_done = True
    st.deps_required = ["PARTNER_SSO_SECRET"]
    st.deps_disposition = {"PARTNER_SSO_SECRET": "provide"}  # operator explicitly requires a human value
    st.save()
    assert c.maybe_autosatisfy_deps(rid) is False
    assert c._load_state(rid).deps_satisfied is False


def test_stage_done_requires_the_orchestrator_process_to_have_finished(tmp_path):
    # SPEC §1: a stage is done only when its artifact gate passes AND the process finished.
    # run-d329e57c scar: the PRD passed while S1 was still alive -> S1+S2 ran concurrently.
    import os
    class FakeProc:
        def __init__(self): self.exit_code = None
        def poll(self): return self.exit_code
    proc = FakeProc()
    ids = iter(["run-sf"])
    c = Console(str(tmp_path), launch=lambda *a, **k: proc, new_id=lambda: next(ids))
    rid = c.start_run(RunRequest(description="x"))
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
    # must NOT auto-advance. start_run records an "input" artifact in run.db; a resurfaced dir
    # whose run.db is empty (created fresh on load) is_pipeline_run -> False, so the poller skips it.
    import os
    c = console(tmp_path, FakeLauncher())
    # a real run created by start_run has recorded input artifacts:
    rid = c.start_run(RunRequest(description="x"))
    assert c.is_pipeline_run(rid) is True
    # a resurfaced old dir: just a PRD on disk, no run.db activity.
    old = os.path.join(str(tmp_path), "run-old")
    os.makedirs(os.path.join(old, "workspace"), exist_ok=True)
    open(os.path.join(old, "workspace", "PRD.md"), "w").write("# PRD")
    assert c.is_pipeline_run("run-old") is False


def test_run_links_surface_repo_and_live_urls(tmp_path):
    # SPEC §6 delivery: repo + live urls projected from the artifacts table for the toolbar,
    # chat narration and the done message.
    from software_factory.db import RunDB, db_path
    c = console(tmp_path, FakeLauncher())
    rid = c.start_run(RunRequest(description="x"))
    assert c.run_links(rid) == {"repo": None, "live": None}
    db = RunDB(db_path(str(tmp_path), rid))
    db.record_artifact("GitHub Repo", "https://github.com/acme/app", kind="repo")
    db.record_artifact("Live URL", "https://sf-run.up.railway.app", kind="deploy")
    links = c.run_links(rid)
    assert links["repo"] == "https://github.com/acme/app"
    assert links["live"] == "https://sf-run.up.railway.app"


def test_stage1_prompt_records_repo_artifact_at_creation(tmp_path):
    p1 = make_prompt_stage1(RunRequest(description="x"), "run-r", "/runs")
    assert "GitHub Repo" in p1 and "repo" in p1            # surfaced from the start (SPEC §7)


def test_derive_phases_start_of_run(tmp_path):
    # SPEC §1: the host performs extraction at start_run and records it — extract=done,
    # provision=active, everything later pending. No phase is trust-based.
    c = console(tmp_path, FakeLauncher())
    rid = c.start_run(RunRequest(description="x"))
    ph = c.derive_phases(rid)
    assert ph["extract"] == "done"
    assert ph["provision"] == "active"
    assert ph["build"] == "pending" and ph["test"] == "pending"


def test_derive_phases_never_leaves_passed_phases_pending_or_active(tmp_path):
    # run-d329e57c scar: provision painted 'active' during build; extract stuck 'pending'.
    # Once a later phase has activity, earlier phases with activity are done; without -> skipped.
    from software_factory.db import RunDB, db_path
    c = console(tmp_path, FakeLauncher())
    rid = c.start_run(RunRequest(description="x"))
    db = RunDB(db_path(str(tmp_path), rid))
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
    from software_factory.db import RunDB, db_path
    c = console(tmp_path, FakeLauncher())
    rid = c.start_run(RunRequest(description="x"))
    db = RunDB(db_path(str(tmp_path), rid))
    db.set_phase("build", "active")
    st = c._load_state(rid); st.phase = "done"; st.save()
    ph = c.derive_phases(rid)
    assert ph["build"] == "done"            # terminal run closes everything with activity
    assert ph["tickets"] == "skipped"
    assert c.status(rid)["phase"] == "done"


def test_status_phase_is_derived_not_stale_provision(tmp_path):
    # The header must reflect the derived current phase, not RunState.phase's initial value.
    from software_factory.db import RunDB, db_path
    c = console(tmp_path, FakeLauncher())
    rid = c.start_run(RunRequest(description="x"))
    RunDB(db_path(str(tmp_path), rid)).set_phase("build", "active")
    assert c.status(rid)["phase"] == "build"   # NOT "provision"


def test_graph_resolves_workspace_relative_artifact_paths(tmp_path):
    # Agents run with cwd=workspace and record artifact paths relative to it ("architecture.md",
    # not "workspace/architecture.md"). graph() must resolve those against the workspace dir too,
    # else every real artifact reads "missing/hollow" (the canvas-all-red bug).
    import os
    from software_factory.db import RunDB, db_path
    c = console(tmp_path, FakeLauncher())
    rid = c.start_run(RunRequest(description="x"))
    RunDB(db_path(str(tmp_path), rid)).record_artifact("Architecture", "architecture.md", kind="doc")
    art = lambda: [n["data"] for n in c.graph(rid)["nodes"] if n["data"].get("path") == "architecture.md"][0]
    assert art()["status"] == "missing"                      # not written yet
    ws = os.path.join(str(tmp_path), rid, "workspace"); os.makedirs(ws, exist_ok=True)
    open(os.path.join(ws, "architecture.md"), "w").write("# Arch")
    assert art()["status"] == "created"                      # workspace-relative path now resolves


def test_graph_marks_artifacts_missing_until_the_file_really_exists(tmp_path):
    # The "no hollow done" scar at the artifact level: a recorded artifact whose file does not
    # exist is status="missing" (red on the canvas), not a fake green "created".
    import os
    from software_factory.db import RunDB, db_path
    c = console(tmp_path, FakeLauncher())
    rid = c.start_run(RunRequest(description="x"))
    RunDB(db_path(str(tmp_path), rid)).record_artifact("PRD", "workspace/PRD.md", kind="prd")
    art = lambda: [n["data"] for n in c.graph(rid)["nodes"] if n["data"].get("path") == "workspace/PRD.md"][0]
    assert art()["status"] == "missing"                     # recorded but no file -> hollow
    os.makedirs(os.path.join(str(tmp_path), rid, "workspace"), exist_ok=True)
    open(os.path.join(str(tmp_path), rid, "workspace", "PRD.md"), "w").write("a real PRD")
    assert art()["status"] == "created"                     # file now exists -> real


def test_graph_agents_are_projected_from_the_agents_table(tmp_path):
    # Agents appear on the canvas ONLY when recorded in run.db (no planned roster). A recorded
    # agent hangs off its phase, is real=True, and its status comes from the agents table.
    from software_factory.db import db_path
    from software_factory.agents import AgentRegistry
    c = console(tmp_path, FakeLauncher())
    rid = c.start_run(RunRequest(description="x"))
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
    rid = c.start_run(RunRequest(description="x"))
    reg = AgentRegistry(db_path(str(tmp_path), rid))
    reg.spawn("a1", rid, 1, "builder", "claude-sonnet-4-6", phase="build")
    reg.record("a1", outcome="real_diff", usage=Usage(model="claude-sonnet-4-6"), cost_usd=0.1, pr=7, diff_lines=10)
    a = [n["data"] for n in c.graph(rid)["nodes"] if n["data"]["kind"] == "agent" and n["data"]["label"] == "builder"][0]
    assert a["status"] == "done"


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
    from software_factory.db import RunDB, db_path
    c = console(tmp_path, FakeLauncher())
    rid = c.start_run(RunRequest(description="x"))
    RunDB(db_path(str(tmp_path), rid)).record_artifact("GitHub Repo", "https://github.com/a/b", kind="repo")
    repo = [n["data"] for n in c.graph(rid)["nodes"] if n["data"]["label"] == "GitHub Repo"][0]
    assert repo["status"] == "created" and repo["url"] == "https://github.com/a/b"


def test_artifacts_are_children_of_the_agent_that_created_them(tmp_path):
    import os
    from software_factory.db import RunDB, db_path
    from software_factory.agents import AgentRegistry
    c = console(tmp_path, FakeLauncher())
    rid = c.start_run(RunRequest(description="x"))
    d = str(tmp_path)
    AgentRegistry(db_path(d, rid)).spawn("horizon", rid, None, "HORIZON", "claude-opus-4-8", phase="research")
    os.makedirs(os.path.join(d, rid, "workspace"), exist_ok=True)
    open(os.path.join(d, rid, "workspace", "PRD.md"), "w").write("real")
    RunDB(db_path(d, rid)).record_artifact("PRD", "workspace/PRD.md", kind="prd", agent="horizon")
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
    from software_factory.db import RunDB, db_path
    c = console(tmp_path, FakeLauncher())
    run_id = c.start_run(RunRequest(description="guestbook"))
    d = str(tmp_path)
    RunDB(db_path(d, run_id)).set_gate("prd", "awaiting")
    assert gates.pending_gate(d, run_id) == "prd"
    c.continue_run(run_id, "prd")                       # dashboard "Continue"
    assert gates.pending_gate(d, run_id) is None

    # artifact read stays inside the run dir
    import os
    os.makedirs(os.path.join(d, run_id, "workspace"), exist_ok=True)
    open(os.path.join(d, run_id, "workspace", "PRD.md"), "w").write("# PRD\nproblem...")
    assert "PRD" in c.artifact(run_id, "workspace/PRD.md")["content"]
    assert "error" in c.artifact(run_id, "../../etc/passwd")  # traversal rejected


def _model_of(launcher):
    argv = launcher.argv
    return argv[argv.index("--model") + 1]


def test_stage3_done_requires_playwright_pass_and_real_agents(tmp_path):
    # The two NON-NEGOTIABLE Stage-3 gates: (a) done tickets trace to recorded native-Task agents,
    # (b) a PASSING Playwright happy-flow on the live url is recorded. No hollow done.
    from software_factory.db import RunDB, db_path
    from software_factory.tickets import TicketStore
    from software_factory.agents import AgentRegistry
    c = console(tmp_path, FakeLauncher())
    rid = c.start_run(RunRequest(description="x"))
    dbp = db_path(str(tmp_path), rid)
    db = RunDB(dbp)
    ts = TicketStore(dbp)
    reg = AgentRegistry(dbp)

    # A ticket built monolithically (no agent claimed it) -> done with agent=None
    tid = ts.create_ticket("feature", acceptance="a", dod="d", wave=1)
    ts.mark_done(tid, pr=1, diff_lines=10)
    assert c.detect_stage3_done(rid) is False         # no Playwright pass yet

    # Passing Playwright verification, but the done ticket has no agent -> still not done (gate a)
    db.record_verification("https://sf-x.up.railway.app", True, {"flows": [{"ok": True}]})
    assert c.detect_stage3_done(rid) is False

    # Build it properly: a native Task agent claims THEN completes the ticket (agent retained on done)
    reg.spawn("ag1", rid, tid, "builder", "claude-sonnet-4-6", phase="build")
    ts.claim(tid, "ag1")
    ts.mark_done(tid, pr=1, diff_lines=10)
    assert c.detect_stage3_done(rid) is True
    st = c.status(rid)
    assert st["done"] is True and st["deploy_url"] == "https://sf-x.up.railway.app"


def test_stage3_prompt_is_plan_first_orchestrator_only_with_playwright_gate(tmp_path):
    from software_factory.console import make_prompt_stage3, make_prompt_stage1
    p3 = make_prompt_stage3(RunRequest(description="x"), "run-z", "/tmp/r",
                            dispositions={"ADP_CLIENT_ID": "mock", "SUPABASE_URL": "mcp"})
    for needle in ["build-plan.md", "Playwright", "record-verification", "Task sub-agent",
                   "software_factory.db", "sf-run-z", "ORCHESTRATOR-ONLY",
                   # deploy hardening (run-ce47692e gaps) baked into the prompt backstop:
                   "Railway MCP", "generate_domain", "npm audit", "get_logs", "GitHub Repo"]:
        assert needle in p3, needle
    # prompts defer to SKILL.md and carry NO event/ruflo instructions
    for bad in ["events emit", "swarm_init", "agent_spawn ", "ruflo"]:
        assert bad not in p3 and bad not in make_prompt_stage1(RunRequest(description="x"), "r", "/t")
    assert "SKILL.md" in make_prompt_stage1(RunRequest(description="x"), "r", "/t")


def test_per_stage_models_opus_for_1_and_2_sonnet_for_3(tmp_path):
    # Stages 1 & 2 run on Opus 4.8; Stage 3 on Sonnet. Turns are bounded. cwd = the workspace.
    import os
    launcher = FakeLauncher()
    c = console(tmp_path, launcher)
    rid = c.start_run(RunRequest(description="guestbook"))           # Stage 1
    assert _model_of(launcher) == "claude-opus-4-8"
    assert "--max-turns" in launcher.argv
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
    import os
    from software_factory import workspace
    launcher = FakeLauncher()
    c = console(tmp_path, launcher)
    run_id = c.start_run(RunRequest(description="guestbook"))
    # start_run calls _launch_stage which calls prepare_workspace -> workspace exists immediately
    assert c.status(run_id)["workspace"] == "active"

    # terminal + torn down -> cleaned
    ws = os.path.join(str(tmp_path), run_id, "workspace")
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


def test_stage_handoff_stage1_done_enables_stage2(tmp_path):
    """Stage 1 events + PRD → detect_stage1_done → start_stage2."""
    import os
    launcher = FakeLauncher()
    c = console(tmp_path, launcher)
    run_id = c.start_run(RunRequest(description="guestbook"))

    assert c.detect_stage1_done(run_id) is False

    # Simulate Stage 1 completing: write a real PRD (the mechanical proof — no event needed)
    d = str(tmp_path)
    base = os.path.join(d, run_id)
    ws = os.path.join(base, "workspace")
    os.makedirs(ws, exist_ok=True)
    prd = (
        "# PRD\nhttps://a.com https://b.com https://c.com\n"
        "## Acceptance criteria\nGiven a visitor, when submit, then shown\n"
        "## Ticket seeds\n- seed: form\n"
    )
    with open(os.path.join(ws, "PRD.md"), "w") as f:
        f.write(prd)

    assert c.detect_stage1_done(run_id) is True

    state = c._load_state(run_id)
    assert state.stage1_done is True

    st = c.status(run_id)
    assert st["stage1_done"] is True


def test_stage2_not_done_when_ticket_store_is_empty(tmp_path):
    """Fix #1: artifacts present is NOT enough — if tickets were never persisted to the store,
    Stage 2 is not done (the buildable-tickets gate)."""
    import os
    launcher = FakeLauncher()
    c = console(tmp_path, launcher)
    run_id = c.start_run(RunRequest(description="x"))
    d = str(tmp_path); base = os.path.join(d, run_id)
    state = c._load_state(run_id); state.stage1_done = True; state.save()
    ws = os.path.join(base, "workspace"); os.makedirs(ws, exist_ok=True)
    for name, body in [("PRD.md", "# PRD"), ("architecture.md", "# A\n## Required Tokens\n- X_KEY — y\n"),
                       ("architecture.svg", "<svg/>")]:
        with open(os.path.join(ws, name), "w") as f:
            f.write(body)
    # No tickets persisted → not done
    assert c.detect_stage2_done(run_id) is False


def test_stage2_done_and_deps_flow(tmp_path):
    """Stage 2 artifacts + tickets → detect_stage2_done → submit_deps → start_stage3."""
    import os
    from software_factory.tickets import TicketStore
    launcher = FakeLauncher()
    c = console(tmp_path, launcher)
    run_id = c.start_run(RunRequest(description="guestbook"))
    d = str(tmp_path)
    base = os.path.join(d, run_id)

    # Mark stage 1 done
    state = c._load_state(run_id)
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
    ts = TicketStore(run_paths(d, run_id)["tickets_db"])
    ts.create_ticket("build form", acceptance="a", dod="d", wave=1)

    assert c.detect_stage2_done(run_id) is True
    state = c._load_state(run_id)
    assert state.stage2_done is True
    assert "RAILWAY_TOKEN" in state.deps_required
    assert "SUPABASE_URL" in state.deps_required

    # Deps not satisfied yet
    assert state.deps_satisfied is False
    assert c.start_stage3(run_id) is None

    # Submit deps
    result = c.submit_deps(run_id, {"RAILWAY_TOKEN": "tok1", "SUPABASE_URL": "url1"})
    assert result["satisfied"] is True
    assert result["missing"] == []

    # Status reflects deps
    st = c.status(run_id)
    assert st["stage2_done"] is True
    assert st["deps_satisfied"] is True
    assert "RAILWAY_TOKEN" in st["deps_provided"]


def test_submit_deps_dispositions_satisfy_without_values(tmp_path):
    """Mock/MCP/env deps satisfy with no value; only 'provide' needs one. Values never persist."""
    import os
    c = console(tmp_path, FakeLauncher())
    run_id = c.start_run(RunRequest(description="x"))
    state = c._load_state(run_id)
    state.stage1_done = True
    state.stage2_done = True
    state.deps_required = ["SUPABASE_URL", "ADP_CLIENT_ID", "OPENROUTER_API_KEY"]
    state.save()

    # SUPABASE_URL→mcp (default), ADP_CLIENT_ID→mock (default), OPENROUTER→provide w/ value
    result = c.submit_deps(run_id, {
        "SUPABASE_URL": {"disposition": "mcp"},
        "ADP_CLIENT_ID": {"disposition": "mock"},
        "OPENROUTER_API_KEY": {"disposition": "provide", "value": "sk-or-real"},
    })
    assert result["satisfied"] is True
    assert result["missing"] == []
    # Disposition persisted (metadata), but the provided VALUE is NOT on disk (run.db).
    saved = open(os.path.join(str(tmp_path), run_id, "run.db"), "rb").read()
    assert b"sk-or-real" not in saved
    assert c._load_state(run_id).deps_disposition["SUPABASE_URL"] == "mcp"


def test_submit_deps_unsatisfied_when_provide_lacks_value(tmp_path):
    c = console(tmp_path, FakeLauncher())
    run_id = c.start_run(RunRequest(description="x"))
    state = c._load_state(run_id)
    state.deps_required = ["OPENROUTER_API_KEY"]
    state.save()
    result = c.submit_deps(run_id, {"OPENROUTER_API_KEY": {"disposition": "provide"}})  # no value
    assert result["satisfied"] is False
    assert "OPENROUTER_API_KEY" in result["missing"]


def test_graph_includes_stage_gates_and_deps_node(tmp_path):
    """The graph always includes stage gates and a deps node."""
    c = console(tmp_path, FakeLauncher())
    run_id = c.start_run(RunRequest(description="x"))
    g = c.graph(run_id)

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
    state = c._load_state(run_id)
    state.stage1_done = True
    state.save()
    g2 = c.graph(run_id)
    s1gate = [n for n in g2["nodes"] if n["data"]["id"] == "gate:stage1"][0]
    assert s1gate["data"]["status"] == "passed"


def test_status_includes_stage_fields(tmp_path):
    c = console(tmp_path, FakeLauncher())
    run_id = c.start_run(RunRequest(description="x"))
    st = c.status(run_id)
    assert "stage" in st
    assert st["stage"] == 1
    assert st["stage1_done"] is False
    assert st["stage2_done"] is False
    assert st["deps_satisfied"] is False
