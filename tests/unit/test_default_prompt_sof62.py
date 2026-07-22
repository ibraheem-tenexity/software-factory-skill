"""SOF-62: build_system_prompt's optional first_turn_context parameter.

The Concierge base prompt is database-only. These historical unit cases therefore require a
configured CONCIERGE row; no code fallback is implied. The first-turn project context is appended
to the system prompt, never represented as a fake user message.
"""
import pytest

from software_factory.default_prompt import build_system_prompt


def test_no_first_turn_context_is_unchanged_from_before_sof62():
    prompt = build_system_prompt("intake")
    assert "## Project context" not in prompt


def test_first_turn_context_is_appended_under_its_own_heading():
    prompt = build_system_prompt("intake", first_turn_context="THE CONTEXT BLOCK")
    assert "## Project context" in prompt
    assert "THE CONTEXT BLOCK" in prompt
    # Appears after the base instructions + framing, not spliced into the middle of them.
    assert prompt.index("## Project context") > prompt.index("## Right now")


def test_empty_string_first_turn_context_is_not_appended():
    prompt = build_system_prompt("intake", first_turn_context="")
    assert "## Project context" not in prompt


def test_unknown_context_still_raises_even_with_first_turn_context_set():
    with pytest.raises(ValueError, match="unknown concierge context"):
        build_system_prompt("not-a-real-context", first_turn_context="whatever")


def test_reading_materials_and_analysis_sections_present():
    prompt = build_system_prompt("intake")
    assert "fetch_document_markdown" in prompt
    assert "search_document_summaries" in prompt
    assert "finalize_product_brief" in prompt
    assert "read_product_brief" in prompt
    assert "hand_off_to_factory" in prompt
