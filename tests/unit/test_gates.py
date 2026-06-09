"""Review gates, backed by the per-run datastore (gates table). A gate marked `awaiting`
blocks await_gate until it becomes `cleared` (the dashboard Continue button clears it).
Sleep is injected so the blocking poll is testable offline.
"""
from software_factory import gates
from software_factory.db import RunDB, db_path


def test_clear_gate_and_pending_reflects_it(tmp_path):
    d = str(tmp_path)
    RunDB(db_path(d, "run-1")).set_gate("prd", "awaiting")
    assert gates.pending_gate(d, "run-1") == "prd"   # awaiting, not yet cleared
    gates.clear_gate(d, "run-1", "prd")
    assert gates.pending_gate(d, "run-1") is None      # cleared
    assert gates.is_cleared(d, "run-1", "prd")


def test_await_returns_immediately_when_already_cleared(tmp_path):
    d = str(tmp_path)
    gates.clear_gate(d, "run-1", "prd")
    slept = []
    assert gates.await_gate(d, "run-1", "prd", sleep=lambda s: slept.append(s)) is True
    assert slept == []  # no waiting needed


def test_await_blocks_until_gate_is_cleared(tmp_path):
    d = str(tmp_path)
    calls = {"n": 0}

    def sleep(_):
        calls["n"] += 1
        if calls["n"] == 1:
            assert gates.pending_gate(d, "run-1") == "prd"   # it marked the pause
        if calls["n"] == 2:                                  # human clicks Continue after 2 polls
            gates.clear_gate(d, "run-1", "prd")

    assert gates.await_gate(d, "run-1", "prd", interval=1, max_wait=100, sleep=sleep) is True
    assert calls["n"] == 2
    assert gates.is_cleared(d, "run-1", "prd")


def test_await_times_out_if_never_cleared(tmp_path):
    d = str(tmp_path)
    assert gates.await_gate(d, "run-1", "prd", interval=1, max_wait=3, sleep=lambda s: None) is False
