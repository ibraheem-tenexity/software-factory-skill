"""ProjectStore — the run datastore that backs ProjectState and the canvas projection."""
from software_factory.db import ProjectStore, db_path
from software_factory.projectstate import ProjectState


def test_flat_run_id_isolation_in_one_shared_db(tmp_path):
    # Postgres shares ONE set of canvas tables across runs (flat schema); prove the project_id scoping
    # by pointing two RunDBs at different run ids (incl. the gates composite PK, where both runs use
    # the same gate name).
    dbf = str(tmp_path / "project-shared")
    a = ProjectStore(dbf); a._project_id = "project-aaaaaaaa"
    b = ProjectStore(dbf); b._project_id = "project-bbbbbbbb"
    a.set_phase("research", "done"); a.set_gate("stage1", "passed"); a.add_blocker("x")
    b.set_phase("research", "active"); b.set_gate("stage1", "failed")
    assert a.phase_status()["research"] == "done"      # each run sees only its own rows
    assert b.phase_status()["research"] == "active"
    assert a.gate_status()["stage1"] == "passed"        # same gate name, isolated per run
    assert b.gate_status()["stage1"] == "failed"
    assert len(a.blockers()) == 1 and len(b.blockers()) == 0


def test_runstate_round_trips_through_run_db(tmp_path):
    db = ProjectStore(str(tmp_path / "project-1"))
    st = ProjectState.load("project-1", db)
    st.phase = "research"
    st.stage = 2
    st.deps_required = ["OPENROUTER_API_KEY"]
    st.save()
    again = ProjectState.load("project-1", ProjectStore(str(tmp_path / "project-1")))
    assert again.phase == "research"
    assert again.stage == 2
    assert again.deps_required == ["OPENROUTER_API_KEY"]


def test_phases_artifacts_blockers_gates_project(tmp_path):
    db = ProjectStore(str(tmp_path / "project-1"))
    db.set_phase("research", "active")
    db.set_phase("research", "done")          # last write wins per name
    db.record_artifact("PRD", "workspace/PRD.md", kind="prd", agent="HORIZON")
    db.add_blocker("MCP down", blocks="mcp")
    db.set_gate("stage1", "passed")

    assert db.phase_status()["research"] == "done"
    arts = db.artifacts()
    assert len(arts) == 1 and arts[0]["title"] == "PRD" and arts[0]["agent"] == "HORIZON"
    assert db.blockers()[0]["what"] == "MCP down" and db.blockers()[0]["cleared"] == 0
    db.clear_blocker("MCP down")
    assert db.blockers()[0]["cleared"] == 1
    assert db.gate_status()["stage1"] == "passed"


def test_verification_gate(tmp_path):
    db = ProjectStore(str(tmp_path / "project-1"))
    assert db.has_passing_verification() is False
    db.record_verification("https://app", False, {"flows": [{"ok": False}]})
    assert db.has_passing_verification() is False        # a failing run doesn't count
    db.record_verification("https://app", True, {"flows": [{"ok": True}]})
    assert db.has_passing_verification() is True


def test_cli_writes_to_run_db(tmp_path):
    from software_factory.db import main
    runs = str(tmp_path)
    assert main(["set-phase", runs, "project-0ddd55fe", "build"]) == 0
    assert main(["record-artifact", runs, "project-0ddd55fe", "Build Plan", "build-plan.md", "plan"]) == 0
    db = ProjectStore(db_path(runs, "project-0ddd55fe"))
    assert db.phase_status()["build"] == "active"
    assert any(a["title"] == "Build Plan" and a["kind"] == "plan" for a in db.artifacts())


def test_cli_spawn_and_finish_agent(tmp_path):
    from software_factory.db import main
    from software_factory.agents import AgentRegistry
    runs = str(tmp_path)
    assert main(["spawn-agent", runs, "project-abc12345", "t7", "builder", "claude-sonnet-4-6", "build", "7"]) == 0
    assert main(["finish-agent", runs, "project-abc12345", "t7", "real_diff", "0.12", "9", "40"]) == 0
    rec = AgentRegistry(db_path(runs, "project-abc12345")).get("t7")
    assert rec.role == "builder" and rec.phase == "build" and rec.ticket_id == 7
    assert rec.status == "done" and rec.provenance == "9" and rec.diff_lines == 40


def test_cli_rejects_malformed_run_id_without_touching_db(tmp_path):
    """Wrong arg order lands junk in the project_id slot. The CLI must reject it
    (exit non-zero) BEFORE constructing ProjectStore — no db file, no pg schema, created."""
    from software_factory.db import main
    runs = str(tmp_path)
    # the real incident: `db set-phase architect active /data/runs project-0ddd55fe`
    for bad in ("active", "/data/runs", "architecture.md", "architect", "real_diff"):
        assert main(["set-phase", runs, bad, "active"]) == 2
    # nothing was created in the runs dir for any of those bad ids
    import os
    assert os.listdir(runs) == []


def test_cli_accepts_correctly_ordered_call(tmp_path):
    from software_factory.db import main
    runs = str(tmp_path)
    assert main(["set-phase", runs, "project-0ddd55fe", "research", "active"]) == 0
    db = ProjectStore(db_path(runs, "project-0ddd55fe"))
    assert db.phase_status()["research"] == "active"
