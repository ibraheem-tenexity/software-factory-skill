"""The structured onboarding brief: coverage, the 'enough to proceed' heuristic, and the
prompt-block rendering injected into Stage 1."""
from software_factory.brief import (
    BRIEF_SECTIONS, REQUIRED_SECTIONS,
    coverage, enough, brief_to_prompt_block, compose_description,
)


def test_compose_description_appends_scope_line():
    assert compose_description("Build a quoting tool.", ["Quoting / RFQ", "Pricing & approvals"]) == (
        "Build a quoting tool.\n\nScope of work: Quoting / RFQ, Pricing & approvals.")


def test_compose_description_handles_empty_scope_and_empty_goal():
    assert compose_description("Just a goal.", []) == "Just a goal."
    assert compose_description("Just a goal.", None) == "Just a goal."
    assert compose_description("", ["Inventory"]) == "Scope of work: Inventory."
    assert compose_description("  ", []) == ""


def test_required_sections_are_a_subset_of_all_sections():
    assert set(REQUIRED_SECTIONS).issubset(set(BRIEF_SECTIONS))


def test_coverage_needs_more_than_a_trivial_answer():
    cov = coverage({"goals": "x", "success_metrics": "Reduce screening time by 40% vs the manual flow"})
    assert cov["goals"] is False            # too short
    assert cov["success_metrics"] is True
    assert cov["constraints"] is False      # absent


def test_enough_only_when_required_sections_covered():
    empty_ok, missing = enough({})
    assert empty_ok is False
    assert set(missing) == set(REQUIRED_SECTIONS)

    partial = {
        "goals": "A cargo screening prototype for ground handlers to log screening events.",
        "success_metrics": "A stakeholder cannot distinguish it from the hand-built demo.",
    }
    ok, missing = enough(partial)
    assert ok is False
    assert "definition_of_done" in missing

    full = dict(partial, definition_of_done="All V1 screens deployed and browser-verified.")
    ok, missing = enough(full)
    assert ok is True and missing == []


def test_prompt_block_is_empty_when_brief_is_empty():
    assert brief_to_prompt_block({}) == ""
    assert brief_to_prompt_block({"goals": ""}) == ""


def test_prompt_block_renders_filled_sections_in_order():
    block = brief_to_prompt_block({
        "definition_of_done": "Deployed + verified.",
        "goals": "Cargo screening demo.",
    })
    assert "PROJECT BRIEF" in block
    assert "## Context & Goals" in block and "Cargo screening demo." in block
    assert "## Definition of Done" in block
    # goals (earlier in BRIEF_SECTIONS) renders before definition_of_done regardless of input order
    assert block.index("## Context & Goals") < block.index("## Definition of Done")
