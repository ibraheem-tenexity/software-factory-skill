"""Pure unit tests for DbConversation (SOF-31/T1.3, rewired to the real agent in T2.1/T2.2) — no
DB, no app-load, no conftest DB round-trips (OOM-safe). Injects a FAKE ConversationStore AND a
FAKE ConciergeAgent (same injectable-dependency pattern established in T1.1/T1.2) so the
turn()/history() contract can be verified without touching Postgres or calling a live model.

Scripted `_SCRIPT`-based behavior (SOF-31's original tests) is gone — the agent rewrite this
ticket scoped out is now in scope here (concierge-agent-spec.md §1, T2.x)."""
import pytest

from software_factory.chat_agent import ConciergeTurn, SuggestedResponse
from software_factory.services.conversation import DbConversation
from software_factory.services.errors import Invalid


class _FakeStore:
    """In-memory stand-in for ConversationStore — same append()/history() shapes (including
    json_blob, which to_provider() needs to render the agent's message list), no DB."""

    def __init__(self):
        self._rows: dict = {}

    def append(self, session_id, role, blocks, *, project_id=None, **kwargs):
        text = blocks[0]["text"] if blocks and blocks[0].get("type") == "text" else ""
        rows = self._rows.setdefault(session_id, [])
        rows.append({"role": role, "input": text, "seq": len(rows), "json_blob": blocks})
        return f"fake-id-{len(rows)}"

    def history(self, session_id):
        return list(self._rows.get(session_id, []))


class _FakeAgent:
    """Injectable stand-in for ConciergeAgent — records every call so tests can assert the
    context/messages ConciergeAgent.run() was actually invoked with."""

    def __init__(self, response="ok", suggested_responses=None):
        self._response = response
        self._suggested = suggested_responses or []
        self.calls = []

    def run(self, context, messages):
        self.calls.append({"context": context, "messages": messages})
        return ConciergeTurn(
            response=self._response,
            suggested_responses=[SuggestedResponse(**s) for s in self._suggested],
        )


def test_first_turn_is_plain_text():
    c = DbConversation(store=_FakeStore(), agent=_FakeAgent(response="hi there"))
    r = c.turn("p1", "I want to automate quoting")
    assert r["response"] == "hi there"
    assert r["suggested_responses"] == []


def test_suggested_responses_pass_through_from_the_agent():
    suggested = [{"response": "Manual data entry", "type": "single select"},
                 {"response": "Approvals", "type": "single select"}]
    c = DbConversation(store=_FakeStore(), agent=_FakeAgent(suggested_responses=suggested))
    r = c.turn("p1", "context")
    assert r["suggested_responses"] == suggested


def test_agent_is_called_with_intake_context():
    agent = _FakeAgent()
    c = DbConversation(store=_FakeStore(), agent=agent)
    c.turn("p1", "hello")
    assert agent.calls[0]["context"] == "intake"


def test_agent_receives_provider_rendered_history_including_the_new_message():
    agent = _FakeAgent()
    c = DbConversation(store=_FakeStore(), agent=agent)
    c.turn("p1", "my message")
    messages = agent.calls[0]["messages"]
    assert any(m.get("role") == "user" for m in messages)


def test_history_is_per_project_and_ordered():
    c = DbConversation(store=_FakeStore(), agent=_FakeAgent())
    c.turn("p1", "hello")
    c.turn("p2", "other")
    assert [t["role"] for t in c.history("p1")] == ["user", "agent"]
    assert len(c.history("p2")) == 2
    assert c.history("nope") == []


def test_empty_message_raises_invalid():
    c = DbConversation(store=_FakeStore(), agent=_FakeAgent())
    with pytest.raises(Invalid):
        c.turn("p1", "   ")


def test_empty_message_never_reaches_the_store_or_agent():
    class _ExplodesIfCalled:
        def append(self, *a, **k): raise AssertionError("must not be called")
        def history(self, *a, **k): raise AssertionError("must not be called")

    class _AgentExplodesIfCalled:
        def run(self, *a, **k): raise AssertionError("must not be called")

    c = DbConversation(store=_ExplodesIfCalled(), agent=_AgentExplodesIfCalled())
    with pytest.raises(Invalid):
        c.turn("p1", "")


def test_different_projects_get_different_session_ids():
    store = _FakeStore()
    c = DbConversation(store=store, agent=_FakeAgent())
    c.turn("p1", "hi")
    c.turn("p2", "hi")
    assert len(store._rows) == 2


def test_history_content_reflects_persisted_input_text():
    c = DbConversation(store=_FakeStore(), agent=_FakeAgent(response="agent reply"))
    c.turn("p1", "my first message")
    rows = c.history("p1")
    assert rows[0]["content"] == "my first message"
    assert rows[1]["content"] == "agent reply"


def test_turn_returns_message_id_and_session_id():
    c = DbConversation(store=_FakeStore(), agent=_FakeAgent())
    r = c.turn("p1", "hello")
    assert r["message_id"]
    assert r["session_id"]


def test_agent_is_lazily_constructed_when_not_injected():
    """DbConversation() with no agent kwarg must not eagerly build a real ConciergeAgent (which
    would try to construct a live chat model) until turn() actually needs it."""
    c = DbConversation(store=_FakeStore())
    assert c._agent is None
