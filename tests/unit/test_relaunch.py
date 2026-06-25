"""Tests for POST /api/projects/{pid}/relaunch and Console.relaunch_project.

AC:
  1. relaunch on stopped/done → new project_id, source untouched, full pipeline from stage 1
  2. Spec fields carried over: description, brief, scope, runtime, models, budget_ceiling,
     creds_vault_ids, deploy_target; relaunched_from lineage set
  3. Input materials (input/) copied to new project; source input/ unchanged
  4. relaunch on non-stopped/non-done → ValueError (409 from the route)
  5. No double-orchestrator: new_id != source_id; source _procs untouched
  6. restart_pipeline tool routes stopped runs to relaunch (new project_id in response)
"""
import os

import pytest

from software_factory.console import Console, ProjectRequest


class FakeLauncher:
    def __call__(self, argv, env=None, log_path=None, cwd=None):
        return {"pid": 1234}


@pytest.fixture(autouse=True)
def _mock_check_mcp(monkeypatch):
    from software_factory import console as _cm
    monkeypatch.setattr(_cm, "check_mcp", lambda path: [])


def _make_console(tmp_path, ids):
    it = iter(ids)
    return Console(str(tmp_path), launch=FakeLauncher(), new_id=lambda: next(it))


# ── 1. Basic relaunch: stopped → new run, source untouched ───────────────────

def test_relaunch_stopped_returns_new_project_id(tmp_path):
    c = _make_console(tmp_path, ["project-src01", "project-new01"])
    src = c.start_project(ProjectRequest(description="original app"))
    c.stop_project(src)
    assert c._load_state(src).phase == "stopped"

    new_id = c.relaunch_project(src)

    assert new_id == "project-new01"
    assert new_id != src
    # source remains stopped
    assert c._load_state(src).phase == "stopped"
    # new run is live (not stopped/draft)
    new_state = c._load_state(new_id)
    assert new_state.phase not in ("stopped", "draft")


def test_relaunch_done_also_works(tmp_path):
    c = _make_console(tmp_path, ["project-src02", "project-new02"])
    src = c.start_project(ProjectRequest(description="done app"))
    st = c._load_state(src)
    st.phase = "done"; st.save()

    new_id = c.relaunch_project(src)
    assert new_id == "project-new02"
    assert c._load_state(src).phase == "done"


# ── 2. Spec fields carried over ───────────────────────────────────────────────

def test_relaunch_carries_spec_fields(tmp_path):
    c = _make_console(tmp_path, ["project-spec1", "project-spec2"])
    src = c.start_project(ProjectRequest(
        description="spec test", runtime="claude",
        planning_model="claude-opus-4-8", impl_model="claude-sonnet-4-6",
        target="railway",
    ))
    src_st = c._load_state(src)
    src_st.phase = "stopped"
    src_st.budget_ceiling = 42.0
    src_st.creds_vault_ids = {"RAILWAY_TOKEN": "vault-uuid-xyz"}
    src_st.scope = ["Quoting / RFQ", "Inventory"]
    src_st.brief = {"goals": "build an ERP"}
    src_st.save()

    new_id = c.relaunch_project(src)
    ns = c._load_state(new_id)

    assert ns.description == "spec test"
    assert ns.runtime == "claude"
    assert ns.planning_model == "claude-opus-4-8"
    assert ns.impl_model == "claude-sonnet-4-6"
    assert ns.deploy_target == "railway"
    assert ns.budget_ceiling == 42.0
    assert ns.creds_vault_ids == {"RAILWAY_TOKEN": "vault-uuid-xyz"}
    assert ns.scope == ["Quoting / RFQ", "Inventory"]
    assert ns.brief == {"goals": "build an ERP"}
    assert ns.relaunched_from == src
    assert ns.spent_usd == 0.0
    assert ns.stage1_done is False
    assert ns.stage2_done is False


# ── 3. Input materials copied; source unchanged ───────────────────────────────

def test_relaunch_copies_input_materials(tmp_path):
    c = _make_console(tmp_path, ["project-mat1", "project-mat2"])
    src = c.start_project(ProjectRequest(description="materials test"))
    # Simulate a file in input/ (markdown after conversion)
    src_input = os.path.join(str(tmp_path), src, "input")
    os.makedirs(src_input, exist_ok=True)
    (open(os.path.join(src_input, "spec.md"), "w")).write("# Spec\nsome content")

    st = c._load_state(src); st.phase = "stopped"; st.save()
    new_id = c.relaunch_project(src)

    new_input = os.path.join(str(tmp_path), new_id, "input")
    # File was copied to new run's input/
    assert os.path.isfile(os.path.join(new_input, "spec.md"))
    # Source file still intact
    assert os.path.isfile(os.path.join(src_input, "spec.md"))
    # Files are independent copies (not the same inode)
    assert os.stat(os.path.join(src_input, "spec.md")).st_ino != \
           os.stat(os.path.join(new_input, "spec.md")).st_ino


def test_relaunch_works_without_input_dir(tmp_path):
    c = _make_console(tmp_path, ["project-noin1", "project-noin2"])
    src = c.start_project(ProjectRequest(description="no input"))
    st = c._load_state(src); st.phase = "stopped"; st.save()
    new_id = c.relaunch_project(src)
    # No error — missing input/ is handled gracefully
    assert new_id == "project-noin2"


# ── 4. Relaunch blocked on non-terminal phases ────────────────────────────────

def test_relaunch_raises_on_running_project(tmp_path):
    c = _make_console(tmp_path, ["project-live1"])
    src = c.start_project(ProjectRequest(description="live"))
    st = c._load_state(src); st.phase = "build"; st.save()

    with pytest.raises(ValueError, match="stopped or done"):
        c.relaunch_project(src)


def test_relaunch_raises_on_draft(tmp_path):
    c = _make_console(tmp_path, ["project-drf1"])
    src = c.create_draft(owner="u@x.com")
    with pytest.raises(ValueError, match="stopped or done"):
        c.relaunch_project(src)


# ── 5. Race safety: new id != source, no _procs bleed ────────────────────────

def test_relaunch_new_id_has_fresh_proc_registry(tmp_path):
    c = _make_console(tmp_path, ["project-race1", "project-race2"])
    src = c.start_project(ProjectRequest(description="race"))
    st = c._load_state(src); st.phase = "stopped"; st.save()

    new_id = c.relaunch_project(src)

    # Source's _procs entry (if any) is the FakeLauncher dict, which has no .poll → not alive
    assert not c._stage_process_alive(src)
    # New run is not double-orchestrating the source
    assert new_id != src
