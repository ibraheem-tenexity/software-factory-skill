"""Ephemeral per-run workspace: create -> build inside it -> publish -> destroy.

The destroy is the only destructive op in the whole skill, so it is safety-gated: it refuses
to delete anything that isn't a workspace WE created (sentinel marker) and isn't under the
runs dir. And because proof artifacts live at the run BASE (not inside the workspace),
teardown leaves the evidence intact.
"""
import os

import pytest

from software_factory import workspace


def test_create_makes_the_dir_with_a_sentinel(tmp_path):
    ws = workspace.create(str(tmp_path), "run-1")
    assert os.path.isdir(ws)
    assert ws.endswith(os.path.join("run-1", "workspace"))
    assert workspace.is_ours(ws) is True


def test_destroy_removes_a_workspace_we_created(tmp_path):
    ws = workspace.create(str(tmp_path), "run-1")
    open(os.path.join(ws, "app.py"), "w").write("print('hi')")
    workspace.destroy(ws, runs_dir=str(tmp_path))
    assert not os.path.exists(ws)


def test_destroy_refuses_a_dir_without_the_sentinel(tmp_path):
    # Looks like a workspace but we didn't create it -> never delete.
    rogue = tmp_path / "run-x" / "workspace"
    rogue.mkdir(parents=True)
    (rogue / "precious.txt").write_text("do not delete")
    with pytest.raises(Exception):
        workspace.destroy(str(rogue), runs_dir=str(tmp_path))
    assert rogue.exists()


def test_destroy_refuses_a_path_outside_runs_dir(tmp_path):
    ws = workspace.create(str(tmp_path), "run-1")
    other_runs = tmp_path / "somewhere_else"
    other_runs.mkdir()
    with pytest.raises(Exception):
        workspace.destroy(ws, runs_dir=str(other_runs))
    assert os.path.exists(ws)  # untouched


def test_proof_artifacts_at_the_base_survive_teardown(tmp_path):
    # agents.db / tickets.db / runstate live at the BASE, beside the workspace, not inside it.
    base = tmp_path / "run-1"
    ws = workspace.create(str(tmp_path), "run-1")
    (base / "agents.db").write_text("evidence")
    workspace.destroy(ws, runs_dir=str(tmp_path))
    assert not os.path.exists(ws)
    assert (base / "agents.db").exists()  # proof survives
