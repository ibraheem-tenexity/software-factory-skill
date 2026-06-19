"""Concierge model selection (gpt-4o vs Kimi via OpenRouter) and the malformed-tool-args
degradation path — a ChatCompletions-compat proxy can emit arguments OpenAI never would."""
import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock, AsyncMock, patch

from openai.types.responses import ResponseFunctionToolCall

from software_factory.chat_agent import ChatAgentRunner, select_chat_model


def test_default_is_gpt4o_when_openai_key_present(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-x")
    monkeypatch.delenv("SF_CHAT_MODEL", raising=False)
    assert select_chat_model() == "gpt-4o"


def test_kimi_when_only_openrouter_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("SF_CHAT_MODEL", raising=False)
    monkeypatch.setenv("OPENROUTER_API_KEY", "or-x")
    m = select_chat_model()
    assert m != "gpt-4o" and m.model == "moonshotai/kimi-k2.7-code"


def test_sf_chat_model_kimi_forces_kimi_even_with_openai_key(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-x")
    monkeypatch.setenv("OPENROUTER_API_KEY", "or-x")
    monkeypatch.setenv("SF_CHAT_MODEL", "kimi")
    assert select_chat_model().model == "moonshotai/kimi-k2.7-code"


def test_sf_chat_model_gpt4o_is_the_rollback(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "or-x")
    monkeypatch.setenv("SF_CHAT_MODEL", "gpt-4o")
    assert select_chat_model() == "gpt-4o"


def _runner():
    return ChatAgentRunner(MagicMock(_runs_dir="/tmp/x"))


def _fake_result(items):
    return SimpleNamespace(new_items=items, final_output="ok")


def _tool_call_item(agent, name, arguments):
    from agents.items import ToolCallItem
    raw = ResponseFunctionToolCall(
        name=name, arguments=arguments, call_id="c1", type="function_call")
    return ToolCallItem(agent=agent, raw_item=raw)


def test_malformed_tool_arguments_degrade_to_text_not_crash(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-x")
    runner = _runner()
    bad = _tool_call_item(runner._agent, "request_dep_input", "NOT VALID JSON {")
    with patch("agents.Runner.run", new=AsyncMock(return_value=_fake_result([bad]))):
        run_id, msgs = asyncio.get_event_loop().run_until_complete(
            runner.handle_message(None, "hi", [], []))
    # no dep_request emitted, no exception — final_output text is the fallback reply
    assert all(m.msg_type != "dep_request" for m in msgs)
    assert any(m.msg_type == "text" for m in msgs)


def test_missing_dep_names_key_degrades(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-x")
    runner = _runner()
    bad = _tool_call_item(runner._agent, "request_dep_input", "{}")
    with patch("agents.Runner.run", new=AsyncMock(return_value=_fake_result([bad]))):
        _, msgs = asyncio.get_event_loop().run_until_complete(
            runner.handle_message(None, "hi", [], []))
    assert all(m.msg_type != "dep_request" for m in msgs)


def test_wellformed_tool_call_still_fires(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-x")
    runner = _runner()
    good = _tool_call_item(runner._agent, "request_dep_input",
                           '{"run_id": "run-1", "dep_names": ["RAILWAY_TOKEN"]}')
    with patch("agents.Runner.run", new=AsyncMock(return_value=_fake_result([good]))):
        _, msgs = asyncio.get_event_loop().run_until_complete(
            runner.handle_message("run-1", "hi", [], []))
    dep = next(m for m in msgs if m.msg_type == "dep_request")
    assert dep.metadata["dep_names"] == ["RAILWAY_TOKEN"]


def test_hand_off_to_factory_promotes_draft(monkeypatch):
    # hand_off_to_factory promotes the interview draft (runtime/picks already on the draft from
    # create_draft); it no longer calls start_run with a fresh RunRequest.
    import json
    from unittest.mock import MagicMock
    from software_factory.chat_agent import make_tools
    monkeypatch.setenv("OPENAI_API_KEY", "sk-x")
    captured = {}
    mock_console = MagicMock()
    mock_console.promote_draft = lambda rid, **kw: captured.update(rid=rid) or "run-x"
    tools = make_tools(mock_console, draft_id=lambda: "run-draft01")
    hand = next(t for t in tools if t.name == "hand_off_to_factory")
    asyncio.get_event_loop().run_until_complete(
        hand.on_invoke_tool(None, json.dumps({})))
    assert captured["rid"] == "run-draft01"
