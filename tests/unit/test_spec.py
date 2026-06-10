"""SPEC.md is the contract (operator directive): it must exist and stay in sync with the
constants the code actually uses — a cheap drift check, not a prose test."""
import os

SPEC = os.path.join(os.path.dirname(__file__), "..", "..", "SPEC.md")


def _spec():
    with open(SPEC) as f:
        return f.read()


def test_spec_exists():
    assert os.path.isfile(SPEC)


def test_spec_names_the_phase_pipeline_and_states():
    s = _spec()
    from software_factory.console import PIPELINE
    for phase in PIPELINE:
        assert phase in s, f"SPEC.md missing phase {phase}"
    for state in ("pending", "active", "done", "skipped"):
        assert state in s


def test_spec_names_the_agent_outcomes_used_by_code():
    s = _spec()
    from software_factory.agents import _STATUS_FOR
    for outcome in _STATUS_FOR:
        assert outcome in s, f"SPEC.md missing outcome {outcome}"
    assert "unreported" in s          # the host's orphan-finalize outcome


def test_spec_names_the_budget_knobs():
    s = _spec()
    for knob in ("SF_COST_CEILING", "budget_ceiling", "/retry"):
        assert knob in s
