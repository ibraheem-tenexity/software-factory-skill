"""OpenCode --format json cost parsing, written against the REAL captured fixture
(tests/fixtures/opencode-run.jsonl — a live kimi-k2.6 spike run, schema ground truth)."""
import json
import os

from software_factory.constants import PRICES
from software_factory.streamlog import OPENCODE_FALLBACK_MODEL, cost_usd

FIXTURE = os.path.join(os.path.dirname(__file__), "..", "fixtures", "opencode-run.jsonl")


def _fixture_text() -> str:
    with open(FIXTURE) as f:
        return f.read()


def test_fixture_cost_is_the_sum_of_step_finish_costs():
    text = _fixture_text()
    expected = sum(
        json.loads(line)["part"]["cost"]
        for line in text.splitlines()
        if line.strip() and json.loads(line).get("type") == "step_finish"
    )
    assert expected > 0, "fixture must contain real non-zero costs (spike abort criterion)"
    assert cost_usd(text) == round(expected, 6)


def test_costless_step_finish_prices_tokens_at_kimi_rate_not_claude_default():
    # cost absent -> tokens priced via the kimi entry; reasoning bills as output.
    ev = {"type": "step_finish", "part": {"type": "step-finish",
          "tokens": {"input": 1_000_000, "output": 500_000, "reasoning": 500_000,
                     "cache": {"read": 1_000_000, "write": 0}}}}
    rate = PRICES[OPENCODE_FALLBACK_MODEL]
    expected = round(1_000_000 * rate["input"] + 1_000_000 * rate["cached"]
                     + 1_000_000 * rate["output"], 6)
    got = cost_usd(json.dumps(ev))
    assert got == expected
    # and it must NOT be the silent claude-sonnet default rate
    sonnet = PRICES["claude-sonnet-4-6"]
    not_expected = round(1_000_000 * sonnet["input"] + 1_000_000 * sonnet["cached"]
                         + 1_000_000 * sonnet["output"], 6)
    assert got != not_expected


def test_opencode_events_do_not_feed_the_claude_tail_estimate():
    # tool_use/text/step_start events carry no `message.usage`; only step_finish counts.
    text = _fixture_text()
    non_finish = "\n".join(l for l in text.splitlines()
                           if l.strip() and json.loads(l).get("type") != "step_finish")
    assert cost_usd(non_finish) == 0.0


def test_claude_result_lines_still_parse_alongside_opencode_lines():
    # one parser, both vocabularies (a single run never mixes, but the parser must not care)
    mixed = "\n".join([
        json.dumps({"type": "result", "total_cost_usd": 1.5}),
        json.dumps({"type": "step_finish", "part": {"type": "step-finish", "cost": 0.25}}),
    ])
    assert cost_usd(mixed) == 1.75


def test_kimi_price_entry_exists_and_matches_openrouter_list():
    rate = PRICES["openrouter/moonshotai/kimi-k2.7-code"]
    assert rate["input"] == 0.75 / 1_000_000
    assert rate["cached"] == 0.375 / 1_000_000
    assert rate["output"] == 3.50 / 1_000_000


def test_garbage_and_interrupted_tool_events_are_ignored():
    # the fixture contains a real aborted `unknown` tool event (status=error, interrupted)
    text = _fixture_text() + "\nnot json\n{\"broken\""
    assert cost_usd(text) > 0  # still parses; junk contributes nothing
