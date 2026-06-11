"""Run state must survive a crash or a /loop re-entry: load -> work -> save -> resume.

The backend is pluggable (local JSON here; the per-run run.db in a real run) so the same
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


def test_proof_marker_is_stamped_and_persists(tmp_path):
    # At provision the orchestrator stamps WHICH skill drove the run — the run's receipt.
    st = store(tmp_path)
    s = RunState.load("run-proof", st)
    assert s.skill is None  # not yet stamped
    s.skill = "software-factory"
    s.skill_version = "0.0.1"
    s.description = "guestbook web app"
    s.deploy_target = "railway"
    s.save()

    resumed = RunState.load("run-proof", store(tmp_path))
    assert resumed.skill == "software-factory"
    assert resumed.skill_version == "0.0.1"
    assert resumed.description == "guestbook web app"
    assert resumed.deploy_target == "railway"


def test_runs_are_isolated_by_id(tmp_path):
    st = store(tmp_path)
    a = RunState.load("a", st)
    a.phase = "deploy"
    a.save()
    b = RunState.load("b", store(tmp_path))
    assert b.phase == "provision"  # 'a' did not leak into 'b'


def test_per_run_model_picks_persist_across_reload(tmp_path):
    # Operator-picked models (planning = S1/S2 orchestrators, impl = S3) are pinned at
    # start_run and must survive crashes/retries like every other run-scoped decision.
    st = store(tmp_path)
    s = RunState.load("run-m", st)
    s.planning_model = "claude-fable-5"
    s.impl_model = "claude-opus-4-8"
    s.save()
    resumed = RunState.load("run-m", store(tmp_path))
    assert resumed.planning_model == "claude-fable-5"
    assert resumed.impl_model == "claude-opus-4-8"
