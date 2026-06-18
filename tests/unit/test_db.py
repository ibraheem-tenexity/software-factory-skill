"""RunDB — the single per-run datastore that backs RunState and the canvas projection."""
from software_factory.db import RunDB, db_path
from software_factory.runstate import RunState


def test_runstate_round_trips_through_run_db(tmp_path):
    db = RunDB(str(tmp_path / "run.db"))
    st = RunState.load("run-1", db)
    st.phase = "research"
    st.stage = 2
    st.deps_required = ["OPENROUTER_API_KEY"]
    st.save()
    again = RunState.load("run-1", RunDB(str(tmp_path / "run.db")))
    assert again.phase == "research"
    assert again.stage == 2
    assert again.deps_required == ["OPENROUTER_API_KEY"]


def test_phases_artifacts_blockers_gates_project(tmp_path):
    db = RunDB(str(tmp_path / "run.db"))
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
    db = RunDB(str(tmp_path / "run.db"))
    assert db.has_passing_verification() is False
    db.record_verification("https://app", False, {"flows": [{"ok": False}]})
    assert db.has_passing_verification() is False        # a failing run doesn't count
    db.record_verification("https://app", True, {"flows": [{"ok": True}]})
    assert db.has_passing_verification() is True


def test_cli_writes_to_run_db(tmp_path):
    from software_factory.db import main
    runs = str(tmp_path)
    assert main(["set-phase", runs, "run-0ddd55fe", "build"]) == 0
    assert main(["record-artifact", runs, "run-0ddd55fe", "Build Plan", "build-plan.md", "plan"]) == 0
    db = RunDB(db_path(runs, "run-0ddd55fe"))
    assert db.phase_status()["build"] == "active"
    assert any(a["title"] == "Build Plan" and a["kind"] == "plan" for a in db.artifacts())


def test_cli_spawn_and_finish_agent(tmp_path):
    from software_factory.db import main
    from software_factory.agents import AgentRegistry
    runs = str(tmp_path)
    assert main(["spawn-agent", runs, "run-abc12345", "t7", "builder", "claude-sonnet-4-6", "build", "7"]) == 0
    assert main(["finish-agent", runs, "run-abc12345", "t7", "real_diff", "0.12", "9", "40"]) == 0
    rec = AgentRegistry(db_path(runs, "run-abc12345")).get("t7")
    assert rec.role == "builder" and rec.phase == "build" and rec.ticket_id == 7
    assert rec.status == "done" and rec.provenance == "9" and rec.diff_lines == 40


def test_cli_rejects_malformed_run_id_without_touching_db(tmp_path):
    """Wrong arg order lands junk in the run_id slot. The CLI must reject it
    (exit non-zero) BEFORE constructing RunDB — no db file, no pg schema, created."""
    from software_factory.db import main
    runs = str(tmp_path)
    # the real incident: `db set-phase architect active /data/runs run-0ddd55fe`
    for bad in ("active", "/data/runs", "architecture.md", "architect", "real_diff"):
        assert main(["set-phase", runs, bad, "active"]) == 2
    # nothing was created in the runs dir for any of those bad ids
    import os
    assert os.listdir(runs) == []


def test_cli_accepts_correctly_ordered_call(tmp_path):
    from software_factory.db import main
    runs = str(tmp_path)
    assert main(["set-phase", runs, "run-0ddd55fe", "research", "active"]) == 0
    db = RunDB(db_path(runs, "run-0ddd55fe"))
    assert db.phase_status()["research"] == "active"
