"""Pure unit tests for the mock Concierge conversation service — no DB, no app-load, no conftest DB
round-trips (OOM-safe). Verifies the FE contract: each turn is plain text OR ≤4 choices, and the
agent eventually invites hand-off."""
import pytest

from software_factory.services.conversation import Conversation
from software_factory.services.errors import Invalid


def test_first_turn_is_plain_text():
    c = Conversation()
    r = c.turn("p1", "I want to automate quoting")
    assert r["message"]
    assert r["choices"] == []
    assert r["done"] is False


def test_a_later_turn_offers_choices():
    c = Conversation()
    c.turn("p1", "context")
    r = c.turn("p1", "faster quoting")
    assert 1 <= len(r["choices"]) <= 4
    assert r["done"] is False


def test_choices_never_exceed_four():
    c = Conversation()
    for msg in ("a", "b", "c"):
        assert len(c.turn("p1", msg)["choices"]) <= 4


def test_runs_out_of_questions_then_invites_handoff():
    c = Conversation()
    r = None
    for msg in ("a", "b", "c", "d"):
        r = c.turn("p1", msg)
    assert r["done"] is True
    assert r["choices"] == []


def test_history_is_per_project_and_ordered():
    c = Conversation()
    c.turn("p1", "hello")
    c.turn("p2", "other")
    assert [t["role"] for t in c.history("p1")] == ["user", "agent"]
    assert len(c.history("p2")) == 2
    assert c.history("nope") == []


def test_empty_message_raises_invalid():
    c = Conversation()
    with pytest.raises(Invalid):
        c.turn("p1", "   ")
