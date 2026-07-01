"""Tests for the LangChain Concierge agent (SOF-39/40) — ConciergeTurn/SuggestedResponse
structured output, the context-parameterized agent, and the retry-then-fallback contract.

No live model calls: `create_agent` and the chat model are always mocked/injected. No DB.
These tests exercise ConciergeAgent standalone; test_chat_dock_runner.py and
test_conversation_db.py cover its two callers (/api/chat, /converse).
"""
from unittest.mock import MagicMock, patch

import pytest
from pydantic import ValidationError

from langchain.agents.structured_output import ToolStrategy

from software_factory.chat_agent import (
    CONCIERGE_CONTEXTS,
    ConciergeAgent,
    ConciergeTurn,
    SuggestedResponse,
    _SAFE_FALLBACK_RESPONSE,
)


class _FakeAIMessage:
    """A minimal stand-in for langchain_core.messages.AIMessage — only the attribute
    _extract_usage actually reads."""
    def __init__(self, usage_metadata=None):
        self.usage_metadata = usage_metadata


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

    def test_response_format_is_concierge_turn_via_tool_strategy(self):
        # SOF-58: a bare Pydantic response_format resolves to LangChain's native ProviderStrategy
        # for OpenAI models -- confirmed live, gpt-5.4 under that strategy triplicates its JSON
        # output on effectively every turn. ToolStrategy forces structured output through a
        # function-call argument instead, sidestepping the triplication entirely.
        fake_compiled = MagicMock()
        fake_compiled.invoke.return_value = {"structured_response": ConciergeTurn(response="ok")}
        with patch("langchain.agents.create_agent", return_value=fake_compiled) as mock_create:
            agent = ConciergeAgent(model=MagicMock())
            agent.run("intake", messages=[])
        response_format = mock_create.call_args.kwargs["response_format"]
        assert isinstance(response_format, ToolStrategy)
        assert response_format.schema is ConciergeTurn

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


class TestRunWithUsage:
    """SOF-57: ConciergeAgent.run_with_usage() surfaces real token/cost data alongside the
    ConciergeTurn, without changing run()'s existing single-return contract (still used
    untouched by DbConversation/services/conversation.py)."""

    def test_run_still_returns_only_the_turn(self):
        fake_compiled = MagicMock()
        fake_compiled.invoke.return_value = {"structured_response": ConciergeTurn(response="ok"),
                                             "messages": []}
        with patch("langchain.agents.create_agent", return_value=fake_compiled):
            agent = ConciergeAgent(model=MagicMock())
            turn = agent.run("intake", messages=[])
        assert isinstance(turn, ConciergeTurn) and turn.response == "ok"

    def test_run_with_usage_extracts_tokens_and_computes_real_cost(self):
        ai_msg = _FakeAIMessage(usage_metadata={"input_tokens": 100, "output_tokens": 20, "total_tokens": 120})
        fake_compiled = MagicMock()
        fake_compiled.invoke.return_value = {"structured_response": ConciergeTurn(response="ok"),
                                             "messages": [ai_msg]}
        with patch("langchain.agents.create_agent", return_value=fake_compiled), \
             patch("software_factory.chat_agent.chat_model_label", return_value="gpt-5.4"), \
             patch("software_factory.chat_agent.pricing.openrouter_price",
                   return_value={"input": 0.00001, "output": 0.00003}) as mock_price:
            agent = ConciergeAgent(model=MagicMock())
            turn, usage = agent.run_with_usage("intake", messages=[])
        assert turn.response == "ok"
        assert usage == {"model": "gpt-5.4", "provider": "openai", "input_tokens": 100,
                         "output_tokens": 20, "cost_usd": 100 * 0.00001 + 20 * 0.00003}
        mock_price.assert_called_once_with("openai/gpt-5.4", kind="chat")

    def test_run_with_usage_uses_openrouter_id_verbatim_for_kimi(self):
        ai_msg = _FakeAIMessage(usage_metadata={"input_tokens": 10, "output_tokens": 5})
        fake_compiled = MagicMock()
        fake_compiled.invoke.return_value = {"structured_response": ConciergeTurn(response="ok"),
                                             "messages": [ai_msg]}
        with patch("langchain.agents.create_agent", return_value=fake_compiled), \
             patch("software_factory.chat_agent.chat_model_label",
                   return_value="moonshotai/kimi-k2.7-code"), \
             patch("software_factory.chat_agent.pricing.openrouter_price",
                   return_value={"input": 0.0, "output": 0.0}) as mock_price:
            agent = ConciergeAgent(model=MagicMock())
            _turn, usage = agent.run_with_usage("intake", messages=[])
        assert usage["provider"] == "openrouter"
        mock_price.assert_called_once_with("moonshotai/kimi-k2.7-code", kind="chat")

    def test_run_with_usage_reports_none_cost_when_pricing_lookup_fails(self):
        ai_msg = _FakeAIMessage(usage_metadata={"input_tokens": 10, "output_tokens": 5})
        fake_compiled = MagicMock()
        fake_compiled.invoke.return_value = {"structured_response": ConciergeTurn(response="ok"),
                                             "messages": [ai_msg]}
        with patch("langchain.agents.create_agent", return_value=fake_compiled), \
             patch("software_factory.chat_agent.chat_model_label", return_value="gpt-5.4"), \
             patch("software_factory.chat_agent.pricing.openrouter_price", return_value=None):
            agent = ConciergeAgent(model=MagicMock())
            _turn, usage = agent.run_with_usage("intake", messages=[])
        assert usage["input_tokens"] == 10 and usage["cost_usd"] is None

    def test_run_with_usage_returns_zero_tokens_when_no_message_has_usage_metadata(self):
        fake_compiled = MagicMock()
        fake_compiled.invoke.return_value = {"structured_response": ConciergeTurn(response="ok"),
                                             "messages": [_FakeAIMessage(usage_metadata=None)]}
        with patch("langchain.agents.create_agent", return_value=fake_compiled), \
             patch("software_factory.chat_agent.chat_model_label", return_value="gpt-5.4"):
            agent = ConciergeAgent(model=MagicMock())
            _turn, usage = agent.run_with_usage("intake", messages=[])
        assert usage["input_tokens"] == 0 and usage["output_tokens"] == 0 and usage["cost_usd"] is None

    def test_run_with_usage_falls_back_to_zero_usage_when_both_attempts_fail_with_no_ai_message(self):
        fake_compiled = MagicMock()
        fake_compiled.invoke.return_value = {"structured_response": {"response": ""}, "messages": []}
        with patch("langchain.agents.create_agent", return_value=fake_compiled), \
             patch("software_factory.chat_agent.chat_model_label", return_value="gpt-5.4"):
            agent = ConciergeAgent(model=MagicMock())
            turn, usage = agent.run_with_usage("intake", messages=[])
        assert turn.response == _SAFE_FALLBACK_RESPONSE
        assert usage == {"model": "gpt-5.4", "provider": "openai", "input_tokens": 0,
                         "output_tokens": 0, "cost_usd": None}

    def test_run_with_usage_captures_real_tokens_from_a_failed_structured_output_attempt(self):
        """Live-confirmed (SOF-57 verification): gpt-5.4's native structured-output mode can fail
        StructuredOutputValidationError on a call that still really happened and really cost
        tokens -- create_agent's own exception carries that call's `ai_message`
        (`usage_metadata` included), so a fallback turn must still report the real usage rather
        than 0/null just because the JSON coercion failed on top of it."""
        from langchain.agents.structured_output import StructuredOutputValidationError

        billed_ai_message = _FakeAIMessage(usage_metadata={"input_tokens": 80, "output_tokens": 30})
        fake_compiled = MagicMock()
        fake_compiled.invoke.side_effect = StructuredOutputValidationError(
            "ConciergeTurn", ValueError("bad json"), billed_ai_message)
        with patch("langchain.agents.create_agent", return_value=fake_compiled), \
             patch("software_factory.chat_agent.chat_model_label", return_value="gpt-5.4"), \
             patch("software_factory.chat_agent.pricing.openrouter_price",
                   return_value={"input": 0.00001, "output": 0.00003}):
            agent = ConciergeAgent(model=MagicMock())
            turn, usage = agent.run_with_usage("intake", messages=[])
        assert turn.response == _SAFE_FALLBACK_RESPONSE   # still degrades safely (spec §3)
        assert usage["input_tokens"] == 80 * 2 and usage["output_tokens"] == 30 * 2  # both attempts billed
        assert usage["cost_usd"] == (80 * 2) * 0.00001 + (30 * 2) * 0.00003


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
