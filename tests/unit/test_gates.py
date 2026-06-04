"""Review gates: at key phases (after PRD, after architecture+infra, before deploy) the run
PAUSES — emits awaiting_review and blocks until a human clicks Continue in the dashboard (which
writes the gate's .ok file). Sleep is injected so the blocking poll is testable offline.
"""
from software_factory import gates, events


def test_clear_gate_creates_ok_and_pending_reflects_it(tmp_path):
    d = str(tmp_path)
    events.emit(d, "run-1", "awaiting_review", {"gate": "prd"})
    assert gates.pending_gate(d, "run-1") == "prd"   # awaiting, not yet cleared
    gates.clear_gate(d, "run-1", "prd")
    assert gates.pending_gate(d, "run-1") is None     # cleared


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
        if calls["n"] == 2:                      # human clicks Continue after 2 polls
            gates.clear_gate(d, "run-1", "prd")
    assert gates.await_gate(d, "run-1", "prd", interval=1, max_wait=100, sleep=sleep) is True
    assert calls["n"] == 2
    # it announced the pause
    assert any(e["type"] == "awaiting_review" and e["payload"]["gate"] == "prd"
               for e in events.read_events(d, "run-1"))


def test_await_times_out_if_never_cleared(tmp_path):
    d = str(tmp_path)
    assert gates.await_gate(d, "run-1", "prd", interval=1, max_wait=3, sleep=lambda s: None) is False
