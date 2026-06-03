"""Run state must survive a crash or a /loop re-entry: load -> work -> save -> resume.

The backend is pluggable (local JSON here; ruflo MCP in a real run) so the same
resume contract is unit-testable without any live dependency.
"""
from software_factory.runstate import RunState, JsonFileStore


def store(tmp_path):
    return JsonFileStore(str(tmp_path))


def test_fresh_run_starts_at_provision_with_zero_spend(tmp_path):
    s = RunState.load("run-1", store(tmp_path))
    assert s.phase == "provision"
    assert s.spent_usd == 0.0
    assert s.repo_url is None
    assert s.deploy_url is None


def test_loading_an_unknown_run_is_fresh_not_an_error(tmp_path):
    s = RunState.load("never-seen", store(tmp_path))
    assert s.run_id == "never-seen"
    assert s.phase == "provision"


def test_save_then_load_resumes_exactly_where_it_left_off(tmp_path):
    st = store(tmp_path)
    s = RunState.load("run-2", st)
    s.phase = "build"
    s.spent_usd = 42.5
    s.repo_url = "https://github.com/acme/guestbook"
    s.save()

    # Simulate a crash + /loop re-entry: brand-new object, same backend.
    resumed = RunState.load("run-2", store(tmp_path))
    assert resumed.phase == "build"
    assert resumed.spent_usd == 42.5
    assert resumed.repo_url == "https://github.com/acme/guestbook"


def test_runs_are_isolated_by_id(tmp_path):
    st = store(tmp_path)
    a = RunState.load("a", st)
    a.phase = "deploy"
    a.save()
    b = RunState.load("b", store(tmp_path))
    assert b.phase == "provision"  # 'a' did not leak into 'b'
