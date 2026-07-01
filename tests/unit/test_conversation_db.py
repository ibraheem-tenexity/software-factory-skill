"""Pure unit tests for DbConversation (SOF-31/T1.3) — no DB, no app-load, no conftest DB round-trips
(OOM-safe). Injects a FAKE ConversationStore (same seam ConversationStore itself uses for its own
repo/users, per the injectable-dependency pattern established in T1.1/T1.2) so the turn()/history()
contract can be verified without touching Postgres. Mirrors test_conversation.py's cases 1:1 — the
same FE contract must hold for both the mock and the DB-backed swap."""
import pytest

from software_factory.services.conversation import DbConversation, _SCRIPT
from software_factory.services.errors import Invalid


class _FakeStore:
    """In-memory stand-in for ConversationStore — same append()/history() shapes, no DB."""

    def __init__(self):
        self._rows: dict = {}

    def append(self, session_id, role, blocks, *, project_id=None, **kwargs):
        text = blocks[0]["text"] if blocks and blocks[0].get("type") == "text" else ""
        rows = self._rows.setdefault(session_id, [])
        rows.append({"role": role, "input": text, "seq": len(rows)})
        return "fake-id"

    def history(self, session_id):
        return list(self._rows.get(session_id, []))


def test_first_turn_is_plain_text():
    c = DbConversation(store=_FakeStore())
    r = c.turn("p1", "I want to automate quoting")
    assert r["message"]
    assert r["choices"] == []
    assert r["done"] is False


def test_a_later_turn_offers_choices():
    c = DbConversation(store=_FakeStore())
    c.turn("p1", "context")
    r = c.turn("p1", "faster quoting")
    assert 1 <= len(r["choices"]) <= 4
    assert r["done"] is False


def test_choices_never_exceed_four():
    c = DbConversation(store=_FakeStore())
    for msg in ("a", "b", "c"):
        assert len(c.turn("p1", msg)["choices"]) <= 4


def test_runs_out_of_questions_then_invites_handoff():
    c = DbConversation(store=_FakeStore())
    r = None
    for msg in ("a", "b", "c", "d"):
        r = c.turn("p1", msg)
    assert r["done"] is True
    assert r["choices"] == []


def test_history_is_per_project_and_ordered():
    c = DbConversation(store=_FakeStore())
    c.turn("p1", "hello")
    c.turn("p2", "other")
    assert [t["role"] for t in c.history("p1")] == ["user", "agent"]
    assert len(c.history("p2")) == 2
    assert c.history("nope") == []


def test_empty_message_raises_invalid():
    c = DbConversation(store=_FakeStore())
    with pytest.raises(Invalid):
        c.turn("p1", "   ")


def test_empty_message_never_reaches_the_store():
    class _ExplodesIfCalled:
        def append(self, *a, **k): raise AssertionError("must not be called")
        def history(self, *a, **k): raise AssertionError("must not be called")

    c = DbConversation(store=_ExplodesIfCalled())
    with pytest.raises(Invalid):
        c.turn("p1", "")


def test_different_projects_get_different_session_ids():
    store = _FakeStore()
    c = DbConversation(store=store)
    c.turn("p1", "hi")
    c.turn("p2", "hi")
    assert len(store._rows) == 2


def test_history_content_reflects_persisted_input_text():
    c = DbConversation(store=_FakeStore())
    c.turn("p1", "my first message")
    rows = c.history("p1")
    assert rows[0]["content"] == "my first message"
    assert rows[1]["content"] == _SCRIPT[0][0]
