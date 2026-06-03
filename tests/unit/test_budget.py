"""Budget is the guardrail that bites: real token usage -> USD, hard cutoff at the ceiling.

Scars these tests defend against (from the last run):
- spend was estimated from char counts, not real tokens
- there was no ceiling, so runaway loops billed ~$700 invisibly
"""
import pytest

from software_factory.budget import Budget, BudgetExceeded, Usage


# A model whose prices are round numbers so cost math is obvious in the test.
TEST_PRICES = {
    "test-model": {
        "input": 10.0 / 1_000_000,     # $10 / Mtok
        "cached": 1.0 / 1_000_000,     # $1  / Mtok  (cheaper than input)
        "output": 50.0 / 1_000_000,    # $50 / Mtok
    }
}


def make_budget(ceiling=100.0, spent=0.0):
    return Budget(ceiling_usd=ceiling, prices=TEST_PRICES, spent_usd=spent)


def test_charge_computes_cost_from_real_tokens_not_estimates():
    b = make_budget()
    # 1M input + 1M output = $10 + $50 = $60. reasoning tokens bill as output.
    cost = b.charge(Usage("test-model", input_tokens=1_000_000, output_tokens=1_000_000))
    assert cost == pytest.approx(60.0)
    assert b.spent() == pytest.approx(60.0)


def test_cached_tokens_are_cheaper_than_input():
    cached = make_budget().charge(Usage("test-model", cached_tokens=1_000_000))
    fresh = make_budget().charge(Usage("test-model", input_tokens=1_000_000))
    assert cached < fresh
    assert cached == pytest.approx(1.0)


def test_reasoning_tokens_bill_as_output():
    b = make_budget()
    cost = b.charge(Usage("test-model", reasoning_tokens=1_000_000))
    assert cost == pytest.approx(50.0)


def test_spent_and_remaining_track_running_total():
    b = make_budget(ceiling=100.0)
    b.charge(Usage("test-model", output_tokens=1_000_000))  # $50
    assert b.spent() == pytest.approx(50.0)
    assert b.remaining() == pytest.approx(50.0)


def test_raises_budget_exceeded_when_spend_hits_ceiling():
    b = make_budget(ceiling=100.0, spent=80.0)
    # This charge ($50) crosses $100 -> hard cutoff.
    with pytest.raises(BudgetExceeded) as exc:
        b.charge(Usage("test-model", output_tokens=1_000_000))
    # The crossing charge is still recorded so the end-of-run report is honest.
    assert b.spent() == pytest.approx(130.0)
    assert exc.value.spent == pytest.approx(130.0)
    assert exc.value.ceiling == pytest.approx(100.0)


def test_cutoff_fires_exactly_at_ceiling_not_only_above():
    b = make_budget(ceiling=100.0, spent=50.0)
    # Lands exactly on $100 -> the spec says stop "the moment spend hits $100".
    with pytest.raises(BudgetExceeded):
        b.charge(Usage("test-model", output_tokens=1_000_000))  # +$50 -> $100


def test_unknown_model_is_an_error_not_a_silent_zero():
    # A model we have no price for must not bill as free — that hides spend.
    b = make_budget()
    with pytest.raises(KeyError):
        b.charge(Usage("mystery-model", output_tokens=1_000))
