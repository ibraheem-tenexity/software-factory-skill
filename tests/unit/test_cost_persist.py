"""_cost() must persist live spend to projectstate on recompute, not on cached reads."""
import os
from unittest.mock import patch

from software_factory.console import Console, ProjectRequest
from software_factory.projectstate import ProjectState


class FakeLauncher:
    def __call__(self, argv, env=None, log_path=None, cwd=None):
        return {"pid": 1}


RESULT_LINE = '{"type":"result","subtype":"success","session_id":"s1","total_cost_usd":12.5}\n'
RESULT_LINE_2 = '{"type":"result","subtype":"success","session_id":"s2","total_cost_usd":18.0}\n'


def _make_console(tmp_path):
    ids = iter(["project-abc12345"])
    return Console(str(tmp_path), launch=FakeLauncher(), new_id=lambda: next(ids))


def _write_log(paths, content):
    log_path = os.path.join(paths["base"], "project.log")
    with open(log_path, "w") as f:
        f.write(content)


def test_cost_persists_to_db_on_recompute(tmp_path):
    c = _make_console(tmp_path)
    project_id = c.create_draft(owner="user@test.com", name="Test Project")

    paths = c._paths(project_id)
    _write_log(paths, RESULT_LINE)

    # First call is a recompute — should persist
    cost = c._cost(project_id)
    assert cost == 12.5

    state = c._load_state(project_id)
    assert state.spent_usd == 12.5, f"spent_usd not persisted; got {state.spent_usd}"


def test_cost_cached_read_does_not_write(tmp_path):
    c = _make_console(tmp_path)
    project_id = c.create_draft(owner="user@test.com", name="Test Project")

    paths = c._paths(project_id)
    _write_log(paths, RESULT_LINE)

    # Warm the cache
    c._cost(project_id)

    # Cached read — save must NOT be called
    save_calls = []
    original_save = ProjectState.save

    def tracking_save(self):
        save_calls.append(self.spent_usd)
        original_save(self)

    with patch.object(ProjectState, "save", tracking_save):
        cost = c._cost(project_id)

    assert cost == 12.5
    assert save_calls == [], f"save was called on cached read: {save_calls}"


def test_cost_updates_persisted_value_when_log_grows(tmp_path):
    c = _make_console(tmp_path)
    project_id = c.create_draft(owner="user@test.com", name="Test Project")

    paths = c._paths(project_id)
    _write_log(paths, RESULT_LINE)
    c._cost(project_id)  # first recompute: $12.5

    # Log grows (Stage 2 appended)
    _write_log(paths, RESULT_LINE + RESULT_LINE_2)
    cost = c._cost(project_id)

    assert cost == 30.5  # 12.5 + 18.0
    state = c._load_state(project_id)
    assert state.spent_usd == 30.5


def test_cost_zero_does_not_overwrite_persisted_nonzero(tmp_path):
    c = _make_console(tmp_path)
    project_id = c.create_draft(owner="user@test.com", name="Test Project")

    # Pre-set a persisted value
    state = c._load_state(project_id)
    state.spent_usd = 5.0
    state.save()

    # _cost() with no log should return 0 but NOT overwrite
    cost = c._cost(project_id)
    assert cost == 0.0

    state2 = c._load_state(project_id)
    assert state2.spent_usd == 5.0, "zero _cost() must not overwrite persisted non-zero"
