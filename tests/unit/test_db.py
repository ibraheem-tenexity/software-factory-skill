"""ProjectStore — the run datastore that backs ProjectState and the canvas projection."""
from software_factory.db import ProjectStore, db_path, project_id_from_path
from software_factory.projectstate import ProjectState
import pytest


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


def test_name_and_summary_persist_in_columns_not_json(tmp_path):
    """`name` and `summary` are stored in their own projectstate COLUMNS, never duplicated into the
    JSON `data` blob, and round-trip back through ProjectState.load (read merges the columns)."""
    import json
    db = ProjectStore(str(tmp_path / "project-1"))
    st = ProjectState.load("project-1", db)
    st.name = "Quote-to-Epicor"
    st.summary = "Automates **RFQ** quoting against Epicor."
    st.description = "goal prose"
    st.save()
    # raw row: name/summary live in the columns and are absent from the blob; other fields stay in it.
    from software_factory import dbshim
    conn = dbshim.connect(str(tmp_path / "project-1"))
    try:
        row = conn.execute(
            "SELECT data, name, summary FROM projectstate WHERE project_id = ?", ("project-1",)
        ).fetchone()
    finally:
        conn.close()
    blob = json.loads(row["data"])
    assert "name" not in blob and "summary" not in blob
    assert blob["description"] == "goal prose"
    assert row["name"] == "Quote-to-Epicor"
    assert row["summary"] == "Automates **RFQ** quoting against Epicor."
    # a fresh load merges the columns back onto the dataclass
    again = ProjectState.load("project-1", ProjectStore(str(tmp_path / "project-1")))
    assert again.name == "Quote-to-Epicor"
    assert again.summary == "Automates **RFQ** quoting against Epicor."
    assert again.description == "goal prose"


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


def test_cli_writes_to_run_db(tmp_path, monkeypatch):
    from software_factory.db import main
    runs = str(tmp_path)
    monkeypatch.chdir(tmp_path)
    (tmp_path / "build-plan.md").write_text("# plan")
    assert main(["set-phase", runs, "project-0ddd55fe", "build"]) == 0
    assert main(["record-artifact", runs, "project-0ddd55fe", "Build Plan", "build-plan.md", "plan"]) == 0
    db = ProjectStore(db_path(runs, "project-0ddd55fe"))
    assert db.phase_status()["build"] == "active"
    assert any(a["title"] == "Build Plan" and a["kind"] == "plan" for a in db.artifacts())


def test_record_artifact_rejects_missing_file(tmp_path, monkeypatch):
    from software_factory.db import main
    runs = str(tmp_path)
    monkeypatch.chdir(tmp_path)
    rc = main(["record-artifact", runs, "project-0ddd55fe", "Demo credentials", "demo_credentials.md", "demo-creds"])
    assert rc == 1
    db = ProjectStore(db_path(runs, "project-0ddd55fe"))
    assert not any(a["kind"] == "demo-creds" for a in db.artifacts())


def test_record_artifact_allows_url_without_file(tmp_path, monkeypatch):
    from software_factory.db import main
    runs = str(tmp_path)
    monkeypatch.chdir(tmp_path)
    rc = main(["record-artifact", runs, "project-0ddd55fe", "GitHub Repo", "https://github.com/acme/app", "repo"])
    assert rc == 0
    db = ProjectStore(db_path(runs, "project-0ddd55fe"))
    assert any(a["kind"] == "repo" for a in db.artifacts())


def test_cli_spawn_and_finish_agent(tmp_path):
    from software_factory.db import main
    from software_factory.runtime_agents import AgentRegistry
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


def test_project_id_from_path_uses_directory_name():
    assert project_id_from_path("/data/runs/project-0362f961f0984e75") == "project-0362f961f0984e75"
    assert project_id_from_path("/data/runs/project-0362f961f0984e75/") == "project-0362f961f0984e75"
    assert project_id_from_path("/tmp/pytest/run") == "run"  # generic directory id still accepted


def test_project_id_from_path_derives_from_parent_when_given_db_file():
    """Agents sometimes hand-construct TicketStore('/.../<run>/project.db'); the guard must use
    the run directory, not the filename, as project_id."""
    assert project_id_from_path("/data/runs/project-0362f961f0984e75/project.db") == "project-0362f961f0984e75"


def test_project_id_from_path_rejects_file_like_without_valid_parent():
    with pytest.raises(ValueError, match="could not derive a valid project_id"):
        project_id_from_path("/data/runs/project.db")
    with pytest.raises(ValueError, match="could not derive a valid project_id"):
        project_id_from_path("/data/runs/junk-id/project.db")

# ── provision-db verb (moved out of Console._launch_stage; the stage-3 agent calls it) ──────────
# The verb wraps deploy_db.provision and persists the teardown handle onto ProjectState + records
# the artifact on success; on failure it salvages any partial serviceId and exits non-zero.

def test_provision_db_verb_persists_service_id_and_records_artifact(tmp_path, monkeypatch):
    import os
    from software_factory.db import main
    from software_factory import deploy_db as dd
    runs = str(tmp_path); pid = "project-aaaa1111"
    # The agent's cwd is the workspace; the verb resolves context/ from cwd.
    ws = tmp_path / pid / "workspace"; (ws / "context").mkdir(parents=True)
    monkeypatch.chdir(ws)
    monkeypatch.setattr(dd, "provision",
                        lambda project_id, ctx: {"service_id": "svc-xyz", "volume_id": "vol-9",
                                                 "DATABASE_URL": "postgres://x",
                                                 "provider": "railway-postgres", "service": "Postgres-XX"})
    assert main(["provision-db", runs, pid]) == 0
    st = ProjectState.load(pid, ProjectStore(db_path(runs, pid)))
    assert st.deploy_db_service_id == "svc-xyz"          # durable teardown handle persisted
    assert st.deploy_db_volume_id == "vol-9"             # volume handle persisted when present
    arts = ProjectStore(db_path(runs, pid)).artifacts()
    assert any(a["title"] == "Deploy DB" and a["kind"] == "deploy-db"
               and a["path"] == "context/" + dd.DEPLOY_DB_FILE for a in arts)


# ── provision-repo verb (SOF-22) — one canonical repo per project, whichever stage calls it ──
# first: both stage-1 and stage-3 call the SAME verb; only the first caller actually creates a
# repo (and records it), so two independent SKILL-driven creation paths can never leave two
# real repos + two duplicate "GitHub Repo" artifact rows for one project.

def test_provision_repo_verb_creates_persists_and_records_once(tmp_path, monkeypatch):
    from software_factory.db import main
    from software_factory import repo as repo_mod
    runs = str(tmp_path); pid = "project-aaaa1111bbbb2222"
    ws = tmp_path / pid / "workspace"; ws.mkdir(parents=True)
    monkeypatch.chdir(ws)
    calls = []
    monkeypatch.setattr(repo_mod.GitHub, "create_repo",
                        lambda self, name, private=True: calls.append(name) or f"https://github.com/acme/{name}")
    assert main(["provision-repo", runs, pid, "quote-follow-up"]) == 0
    assert calls == ["quote-follow-up-aaaa1111"]           # host-computed <slug>-<8hex>, agent never picks the suffix
    st = ProjectState.load(pid, ProjectStore(db_path(runs, pid)))
    assert st.repo_url == "https://github.com/acme/quote-follow-up-aaaa1111"
    arts = ProjectStore(db_path(runs, pid)).artifacts()
    assert sum(1 for a in arts if a["kind"] == "repo") == 1
    assert arts[0]["title"] == "GitHub Repo" and arts[0]["path"] == st.repo_url


def test_provision_repo_verb_is_idempotent_second_caller_reuses_no_duplicate(tmp_path, monkeypatch):
    """Simulates the real bug: stage-1 provisions, then stage-3 (a different workspace, same
    project) calls the SAME verb. It must reuse stage-1's repo — no second create_repo call,
    no second artifact row — and clone it into its own (fresh) cwd."""
    from software_factory.db import main
    from software_factory import repo as repo_mod
    runs = str(tmp_path); pid = "project-cccc3333dddd4444"
    stage1_ws = tmp_path / pid / "stage1-workspace"; stage1_ws.mkdir(parents=True)
    stage3_ws = tmp_path / pid / "stage3-workspace"; stage3_ws.mkdir(parents=True)

    create_calls, clone_calls = [], []
    monkeypatch.setattr(repo_mod.GitHub, "create_repo",
                        lambda self, name, private=True: create_calls.append(name) or f"https://github.com/acme/{name}")
    monkeypatch.setattr(repo_mod.GitHub, "clone_repo", lambda self, url: clone_calls.append(url))

    monkeypatch.chdir(stage1_ws)
    assert main(["provision-repo", runs, pid, "quote-follow-up"]) == 0
    assert len(create_calls) == 1
    assert clone_calls == []          # first call: create_repo's own --clone covers it, no separate clone needed

    monkeypatch.chdir(stage3_ws)
    # stage-3 might pick a different slug (it doesn't matter — repo_url is already set, so the
    # slug is ignored and the EXISTING repo is reused, not a second one under this new name).
    assert main(["provision-repo", runs, pid, "sf-project"]) == 0
    assert len(create_calls) == 1                          # still just the one repo — no second create_repo call
    assert clone_calls == ["https://github.com/acme/quote-follow-up-cccc3333"]  # cloned into stage-3's fresh workspace

    st = ProjectState.load(pid, ProjectStore(db_path(runs, pid)))
    assert st.repo_url == "https://github.com/acme/quote-follow-up-cccc3333"
    arts = ProjectStore(db_path(runs, pid)).artifacts()
    assert sum(1 for a in arts if a["kind"] == "repo") == 1     # still exactly one "GitHub Repo" artifact


def test_provision_repo_verb_reuse_skips_clone_when_already_checked_out(tmp_path, monkeypatch):
    """A retry within the SAME workspace (repo already cloned there) must not re-clone.

    SOF-44: `gh repo clone <url>` (like create_repo's own --clone) clones into a NEW
    ./<repo-name>/ subdirectory of cwd, never into cwd itself — so the fixture puts .git under
    that subdirectory, not directly under the workspace root (the old, buggy assumption this
    ticket fixed)."""
    from software_factory.db import main
    from software_factory import repo as repo_mod
    runs = str(tmp_path); pid = "project-eeee5555ffff6666"
    ws = tmp_path / pid / "workspace"
    (ws / "already-here-eeee5555" / ".git").mkdir(parents=True)
    monkeypatch.chdir(ws)
    clone_calls = []
    monkeypatch.setattr(repo_mod.GitHub, "clone_repo", lambda self, url: clone_calls.append(url))
    st = ProjectState.load(pid, ProjectStore(db_path(runs, pid)))
    st.repo_url = "https://github.com/acme/already-here-eeee5555"
    st.save()
    assert main(["provision-repo", runs, pid, "irrelevant"]) == 0
    assert clone_calls == []


def test_provision_repo_verb_reuse_reclones_when_not_actually_checked_out(tmp_path, monkeypatch):
    """SOF-44 regression: before this fix, checking os.path.isdir(".git") in cwd was ALWAYS
    False after a real clone (which lands in ./<repo-name>/, not cwd) — so this exact scenario
    (freshly entered workspace, repo NOT yet cloned here) must still trigger a clone. Proves the
    fix didn't flip the check backwards (e.g. skipping every clone unconditionally)."""
    from software_factory.db import main
    from software_factory import repo as repo_mod
    runs = str(tmp_path); pid = "project-11112222333344"
    ws = tmp_path / pid / "fresh-workspace"; ws.mkdir(parents=True)
    monkeypatch.chdir(ws)
    clone_calls = []
    monkeypatch.setattr(repo_mod.GitHub, "clone_repo", lambda self, url: clone_calls.append(url))
    st = ProjectState.load(pid, ProjectStore(db_path(runs, pid)))
    st.repo_url = "https://github.com/acme/not-here-yet-11112222"
    st.save()
    assert main(["provision-repo", runs, pid, "irrelevant"]) == 0
    assert clone_calls == ["https://github.com/acme/not-here-yet-11112222"]


def test_provision_repo_verb_exits_nonzero_when_create_repo_fails(tmp_path, monkeypatch):
    from software_factory.db import main
    from software_factory import repo as repo_mod
    runs = str(tmp_path); pid = "project-11119999aaaa8888"
    ws = tmp_path / pid / "workspace"; ws.mkdir(parents=True)
    monkeypatch.chdir(ws)
    monkeypatch.setattr(repo_mod.GitHub, "create_repo", lambda self, name, private=True: "")
    assert main(["provision-repo", runs, pid, "quote-follow-up"]) == 1
    st = ProjectState.load(pid, ProjectStore(db_path(runs, pid)))
    assert not st.repo_url
    assert ProjectStore(db_path(runs, pid)).artifacts() == []


def test_provision_db_verb_salvages_partial_service_id_and_exits_nonzero(tmp_path, monkeypatch):
    """provision() writes the serviceId to disk then raises (e.g. variables read timed out): the
    verb salvages that partial id onto state (so the reaper can tear it down) and exits non-zero
    so the agent add-blockers + STOPs — no artifact, no DB-less deploy."""
    import os
    from software_factory.db import main
    from software_factory import deploy_db as dd
    runs = str(tmp_path); pid = "project-bbbb2222"
    ws = tmp_path / pid / "workspace"; (ws / "context").mkdir(parents=True)
    monkeypatch.chdir(ws)

    def provision_writes_id_then_raises(project_id, ctx):
        dd.write_file(ctx, {"service_id": "svc-salvage", "service": "Postgres-SL",
                            "provider": "railway-postgres", "project_id": project_id})
        raise RuntimeError("variables read timed out")
    monkeypatch.setattr(dd, "provision", provision_writes_id_then_raises)

    assert main(["provision-db", runs, pid]) == 1        # non-zero → agent stops
    st = ProjectState.load(pid, ProjectStore(db_path(runs, pid)))
    assert st.deploy_db_service_id == "svc-salvage"      # partial id salvaged for the reaper
    arts = ProjectStore(db_path(runs, pid)).artifacts()
    assert not any(a["title"] == "Deploy DB" for a in arts)   # no artifact on failure
