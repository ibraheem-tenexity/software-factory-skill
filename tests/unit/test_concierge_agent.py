"""Tests for the LangChain Concierge agent (SOF-39/40) — ConciergeTurn/SuggestedResponse
structured output, the context-parameterized agent, and the retry-then-fallback contract.

No live model calls: `create_agent` and the chat model are always mocked/injected. No DB.
These tests exercise ConciergeAgent standalone; test_chat_dock_runner.py and
test_conversation_db.py cover its two callers (/api/chat, /converse).
"""
from unittest.mock import MagicMock, patch

import pytest
from pydantic import ValidationError

from software_factory.chat_agent import (
    CONCIERGE_CONTEXTS,
    ConciergeAgent,
    ConciergeTurn,
    SuggestedResponse,
    _SAFE_FALLBACK_RESPONSE,
)


class TestConciergeTurnContract:
    def test_response_is_required_and_non_empty(self):
        with pytest.raises(ValidationError):
            ConciergeTurn(response="")

    def test_suggested_responses_default_empty(self):
        t = ConciergeTurn(response="hi")
        assert t.suggested_responses == []

    def test_suggested_response_type_enum_enforced(self):
        with pytest.raises(ValidationError):
            SuggestedResponse(response="yes", type="checkbox")  # not a valid literal

    def test_valid_single_and_multi_select_types(self):
        SuggestedResponse(response="yes", type="single select")
        SuggestedResponse(response="yes", type="multi select")


class TestConciergeAgentConstruction:
    def test_default_tool_belt_is_empty(self):
        agent = ConciergeAgent(model=MagicMock())
        assert agent._tools == []

    def test_unknown_context_raises(self):
        agent = ConciergeAgent(model=MagicMock())
        with pytest.raises(ValueError, match="unknown concierge context"):
            agent.run("not-a-real-context", messages=[])

    @pytest.mark.parametrize("context", CONCIERGE_CONTEXTS)
    def test_all_five_contexts_accepted(self, context):
        fake_compiled = MagicMock()
        fake_compiled.invoke.return_value = {
            "structured_response": ConciergeTurn(response="ok")
        }
        with patch("langchain.agents.create_agent", return_value=fake_compiled):
            agent = ConciergeAgent(model=MagicMock())
            turn = agent.run(context, messages=[])
        assert turn.response == "ok"

    def test_system_prompt_carries_the_context(self):
        fake_compiled = MagicMock()
        fake_compiled.invoke.return_value = {"structured_response": ConciergeTurn(response="ok")}
        with patch("langchain.agents.create_agent", return_value=fake_compiled) as mock_create:
            agent = ConciergeAgent(model=MagicMock())
            agent.run("overview", messages=[])
        assert "Current focus: overview" in mock_create.call_args.kwargs["system_prompt"]

    def test_response_format_is_concierge_turn(self):
        fake_compiled = MagicMock()
        fake_compiled.invoke.return_value = {"structured_response": ConciergeTurn(response="ok")}
        with patch("langchain.agents.create_agent", return_value=fake_compiled) as mock_create:
            agent = ConciergeAgent(model=MagicMock())
            agent.run("intake", messages=[])
        assert mock_create.call_args.kwargs["response_format"] is ConciergeTurn

    def test_tools_passed_through_to_create_agent(self):
        fake_compiled = MagicMock()
        fake_compiled.invoke.return_value = {"structured_response": ConciergeTurn(response="ok")}
        fake_tool = MagicMock(name="a_tool")
        with patch("langchain.agents.create_agent", return_value=fake_compiled) as mock_create:
            agent = ConciergeAgent(model=MagicMock(), tools=[fake_tool])
            agent.run("intake", messages=[])
        assert mock_create.call_args.args[1] == [fake_tool]


class TestConciergeAgentRetryAndFallback:
    def test_valid_pydantic_instance_returned_directly(self):
        fake_compiled = MagicMock()
        want = ConciergeTurn(response="direct hit", suggested_responses=[])
        fake_compiled.invoke.return_value = {"structured_response": want}
        with patch("langchain.agents.create_agent", return_value=fake_compiled):
            agent = ConciergeAgent(model=MagicMock())
            turn = agent.run("intake", messages=[])
        assert turn is want
        assert fake_compiled.invoke.call_count == 1

    def test_valid_dict_is_coerced_to_concierge_turn(self):
        fake_compiled = MagicMock()
        fake_compiled.invoke.return_value = {
            "structured_response": {"response": "from a dict", "suggested_responses": []}
        }
        with patch("langchain.agents.create_agent", return_value=fake_compiled):
            agent = ConciergeAgent(model=MagicMock())
            turn = agent.run("intake", messages=[])
        assert isinstance(turn, ConciergeTurn) and turn.response == "from a dict"

    def test_missing_structured_response_retries_once_then_falls_back(self):
        fake_compiled = MagicMock()
        fake_compiled.invoke.return_value = {"structured_response": None}
        with patch("langchain.agents.create_agent", return_value=fake_compiled):
            agent = ConciergeAgent(model=MagicMock())
            turn = agent.run("intake", messages=[])
        assert turn.response == _SAFE_FALLBACK_RESPONSE
        assert turn.suggested_responses == []
        assert fake_compiled.invoke.call_count == 2   # one retry, per spec

    def test_invalid_shape_first_attempt_recovers_on_retry(self):
        fake_compiled = MagicMock()
        fake_compiled.invoke.side_effect = [
            {"structured_response": {"response": ""}},          # invalid: empty response
            {"structured_response": {"response": "recovered"}},  # valid on retry
        ]
        with patch("langchain.agents.create_agent", return_value=fake_compiled):
            agent = ConciergeAgent(model=MagicMock())
            turn = agent.run("intake", messages=[])
        assert turn.response == "recovered"
        assert fake_compiled.invoke.call_count == 2

    def test_both_attempts_invalid_falls_back_without_raising(self):
        fake_compiled = MagicMock()
        fake_compiled.invoke.return_value = {"structured_response": {"response": ""}}
        with patch("langchain.agents.create_agent", return_value=fake_compiled):
            agent = ConciergeAgent(model=MagicMock())
            turn = agent.run("intake", messages=[])  # must not raise
        assert turn.response == _SAFE_FALLBACK_RESPONSE
        assert fake_compiled.invoke.call_count == 2

    def test_transport_error_is_not_swallowed(self):
        """A genuine API/transport failure is a different failure class than a malformed
        structured output — it must propagate, not be silently masked as a safe fallback."""
        fake_compiled = MagicMock()
        fake_compiled.invoke.side_effect = ConnectionError("upstream unreachable")
        with patch("langchain.agents.create_agent", return_value=fake_compiled):
            agent = ConciergeAgent(model=MagicMock())
            with pytest.raises(ConnectionError):
                agent.run("intake", messages=[])


class TestBuildChatModel:
    def test_default_openai_model_when_key_present(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-x")
        monkeypatch.delenv("SF_CHAT_MODEL", raising=False)
        fake_chat_openai = MagicMock()
        with patch("langchain_openai.ChatOpenAI", fake_chat_openai):
            from software_factory.chat_agent import _build_chat_model
            _build_chat_model()
        fake_chat_openai.assert_called_once_with(model="gpt-5.4")

    def test_kimi_via_openrouter_when_only_openrouter_key(self, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("SF_CHAT_MODEL", raising=False)
        monkeypatch.setenv("OPENROUTER_API_KEY", "or-x")
        fake_chat_openai = MagicMock()
        with patch("langchain_openai.ChatOpenAI", fake_chat_openai):
            from software_factory.chat_agent import _build_chat_model
            _build_chat_model()
        _, kwargs = fake_chat_openai.call_args
        assert kwargs["model"] == "moonshotai/kimi-k2.7-code"
        assert kwargs["base_url"] == "https://openrouter.ai/api/v1"
