"""Tests for ChatDockRunner (SOF-39/40 follow-up) — the /api/chat restoration after SOF-35's
rip-out left state._chat_runner permanently None. No live model calls (ConciergeAgent is
injected as a fake), no DB (console is a MagicMock)."""
import asyncio
import json

from unittest.mock import MagicMock

from software_factory.chat_agent import ChatDockRunner, ConciergeTurn, SuggestedResponse, _context_for_project


_FAKE_USAGE = {"model": "fake-model", "provider": "fake", "input_tokens": 42, "output_tokens": 7,
              "cost_usd": 0.0021}


class _FakeAgent:
    def __init__(self, response="ok", suggested_responses=None, error=None, usage=None):
        self._response = response
        self._suggested = suggested_responses or []
        self._error = error
        self._usage = usage if usage is not None else _FAKE_USAGE
        self.calls = []

    def run(self, context, messages):
        self.calls.append({"context": context, "messages": list(messages)})
        if self._error:
            raise self._error
        return ConciergeTurn(response=self._response,
                             suggested_responses=[SuggestedResponse(**s) for s in self._suggested])

    def run_with_usage(self, context, messages):
        return self.run(context, messages), self._usage


def _collect(agen):
    async def _run():
        return [line async for line in agen]
    return asyncio.run(_run())


def _mock_console(phase="build"):
    c = MagicMock()
    c.status = MagicMock(return_value={"phase": phase})
    return c


def test_context_for_project_maps_done_to_overview():
    assert _context_for_project(_mock_console(phase="done"), "p1") == "overview"


def test_context_for_project_defaults_to_build_for_unknown_phase():
    assert _context_for_project(_mock_console(phase="stage2"), "p1") == "build"
    assert _context_for_project(_mock_console(phase=""), "p1") == "build"


def test_context_for_project_defaults_to_build_on_console_error():
    console = MagicMock()
    console.status = MagicMock(side_effect=RuntimeError("no such project"))
    assert _context_for_project(console, "nonexistent") == "build"


def test_handle_message_streamed_yields_one_done_event():
    agent = _FakeAgent(response="hello from the dock")
    runner = ChatDockRunner(_mock_console(), agent=agent)
    lines = _collect(runner.handle_message_streamed("p1", "hi", [], []))
    assert len(lines) == 1
    evt = json.loads(lines[0])
    assert evt["type"] == "done"
    assert evt["project_id"] == "p1"
    assert evt["messages"][0]["role"] == "assistant"
    assert evt["messages"][0]["content"] == "hello from the dock"


def test_handle_message_streamed_carries_real_usage_in_the_done_event():
    agent = _FakeAgent(response="hello", usage={"model": "gpt-5.4", "provider": "openai",
                                                "input_tokens": 123, "output_tokens": 45,
                                                "cost_usd": 0.0067})
    runner = ChatDockRunner(_mock_console(), agent=agent)
    lines = _collect(runner.handle_message_streamed("p1", "hi", [], []))
    evt = json.loads(lines[0])
    assert evt["usage"] == {"model": "gpt-5.4", "provider": "openai",
                           "input_tokens": 123, "output_tokens": 45, "cost_usd": 0.0067}


def test_handle_message_streamed_infers_context_from_phase():
    agent = _FakeAgent()
    runner = ChatDockRunner(_mock_console(phase="done"), agent=agent)
    _collect(runner.handle_message_streamed("p1", "hi", [], []))
    assert agent.calls[0]["context"] == "overview"


def test_handle_message_streamed_uses_build_context_when_no_project_id():
    agent = _FakeAgent()
    runner = ChatDockRunner(_mock_console(), agent=agent)
    _collect(runner.handle_message_streamed(None, "hi", [], []))
    assert agent.calls[0]["context"] == "build"


def test_conversation_history_accumulates_across_turns():
    agent = _FakeAgent(response="reply")
    runner = ChatDockRunner(_mock_console(), agent=agent)
    _collect(runner.handle_message_streamed("p1", "first", [], []))
    _collect(runner.handle_message_streamed("p1", "second", [], []))
    second_call_messages = agent.calls[1]["messages"]
    contents = [m["content"] for m in second_call_messages]
    assert "first" in contents
    assert "reply" in contents   # the agent's own prior reply is in its own history
    assert "second" in contents


def test_different_projects_get_isolated_history():
    agent = _FakeAgent()
    runner = ChatDockRunner(_mock_console(), agent=agent)
    _collect(runner.handle_message_streamed("p1", "hello p1", [], []))
    _collect(runner.handle_message_streamed("p2", "hello p2", [], []))
    p2_messages = agent.calls[1]["messages"]
    assert not any("hello p1" in m["content"] for m in p2_messages)


def test_attached_files_are_noted_in_the_message_content():
    agent = _FakeAgent()
    runner = ChatDockRunner(_mock_console(), agent=agent)
    _collect(runner.handle_message_streamed("p1", "see attached", [{"name": "spec.pdf"}], []))
    sent = agent.calls[0]["messages"][0]["content"]
    assert "spec.pdf" in sent


def test_agent_error_yields_error_event_not_a_crash():
    agent = _FakeAgent(error=ConnectionError("upstream down"))
    runner = ChatDockRunner(_mock_console(), agent=agent)
    lines = _collect(runner.handle_message_streamed("p1", "hi", [], []))
    assert len(lines) == 1
    evt = json.loads(lines[0])
    assert evt["type"] == "error"
    assert "upstream down" in evt["detail"]


def test_agent_is_lazily_constructed_when_not_injected():
    runner = ChatDockRunner(_mock_console())
    assert runner._agent is None
