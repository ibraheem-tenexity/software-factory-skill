"""Tests for chat_agent — OpenAI Agents SDK concierge wrapping Console."""
import asyncio
import json
import os
from unittest.mock import MagicMock, AsyncMock, patch

import pytest

from software_factory.chat_agent import ChatAgentRunner, make_tools, CONCIERGE_INSTRUCTIONS
from software_factory.chat_store import ChatMessage


@pytest.fixture
def mock_console():
    c = MagicMock()
    c.start_run = MagicMock(return_value="run-test123")
    c.status = MagicMock(return_value={
        "run_id": "run-test123", "phase": "research", "stage": 1,
        "stage1_done": False, "stage2_done": False,
        "deps_required": [], "deps_satisfied": False,
        "spent_usd": 1.23, "status": "running",
    })
    c.stage2_artifacts = MagicMock(return_value={
        "deps_required": ["RAILWAY_TOKEN", "SUPABASE_URL"],
        "deps_provided": [], "missing": ["RAILWAY_TOKEN", "SUPABASE_URL"],
        "satisfied": False,
    })
    c.submit_deps = MagicMock(return_value={
        "deps_provided": ["RAILWAY_TOKEN"], "deps_required": ["RAILWAY_TOKEN"],
        "missing": [], "satisfied": True,
    })
    c.evidence = MagicMock(return_value={
        "url": "https://sf-test123.up.railway.app",
        "artifacts": ["PRD.md", "architecture.md"],
    })
    c._runs_dir = "/tmp/test-runs"
    return c


class TestMakeTools:
    def test_tools_are_created(self, mock_console):
        tools = make_tools(mock_console)
        names = {t.name for t in tools}
        assert "start_pipeline" in names
        assert "check_status" in names
        assert "get_required_deps" in names
        assert "request_dep_input" in names
        assert "get_result" in names

    def test_start_pipeline_calls_console(self, mock_console):
        tools = make_tools(mock_console)
        start = next(t for t in tools if t.name == "start_pipeline")
        inp = json.dumps({"description": "Build a guestbook", "context": "NextJS app",
                          "budget": 50, "target": "railway"})
        result = asyncio.get_event_loop().run_until_complete(
            start.on_invoke_tool(None, inp)
        )
        mock_console.start_run.assert_called_once()
        req = mock_console.start_run.call_args[0][0]
        assert req.description == "Build a guestbook"
        assert req.context == "NextJS app"
        assert req.budget == 50
        assert "run-test123" in result

    def test_check_status_calls_console(self, mock_console):
        tools = make_tools(mock_console)
        check = next(t for t in tools if t.name == "check_status")
        result = asyncio.get_event_loop().run_until_complete(
            check.on_invoke_tool(None, json.dumps({"run_id": "run-test123"}))
        )
        mock_console.status.assert_called_once_with("run-test123")
        parsed = json.loads(result)
        assert parsed["phase"] == "research"

    def test_get_required_deps_calls_console(self, mock_console):
        tools = make_tools(mock_console)
        deps = next(t for t in tools if t.name == "get_required_deps")
        result = asyncio.get_event_loop().run_until_complete(
            deps.on_invoke_tool(None, json.dumps({"run_id": "run-test123"}))
        )
        mock_console.stage2_artifacts.assert_called_once_with("run-test123")
        parsed = json.loads(result)
        assert "RAILWAY_TOKEN" in parsed["deps_required"]

    def test_request_dep_input_returns_structured(self, mock_console):
        tools = make_tools(mock_console)
        req_dep = next(t for t in tools if t.name == "request_dep_input")
        result = asyncio.get_event_loop().run_until_complete(
            req_dep.on_invoke_tool(None, json.dumps({
                "run_id": "run-test123",
                "dep_names": ["RAILWAY_TOKEN"],
            }))
        )
        parsed = json.loads(result)
        assert parsed["type"] == "dep_request"
        assert "RAILWAY_TOKEN" in parsed["dep_names"]


def _fake_run_result(new_items, final_output=None):
    r = MagicMock()
    r.new_items = new_items
    r.final_output = final_output
    return r


class TestHandleMessage:
    """handle_message must parse the real OpenAI Agents SDK item shapes.

    raw_item is a pydantic model (ResponseOutputMessage / ResponseFunctionToolCall),
    not a dict — fields are attributes, not .get() keys.
    """

    def test_message_output_item_is_parsed(self, mock_console):
        from agents.items import MessageOutputItem
        from openai.types.responses import ResponseOutputMessage, ResponseOutputText

        raw = ResponseOutputMessage(
            id="m1",
            content=[ResponseOutputText(annotations=[], text="Hello, what shall we build?",
                                        type="output_text")],
            role="assistant", status="completed", type="message",
        )
        item = MessageOutputItem(agent=MagicMock(), raw_item=raw)

        runner = ChatAgentRunner(mock_console)
        with patch("agents.Runner.run", new=AsyncMock(return_value=_fake_run_result([item]))):
            rid, msgs = asyncio.get_event_loop().run_until_complete(
                runner.handle_message(None, "hi", [], [])
            )
        assert any(m.msg_type == "text" and "what shall we build" in m.content for m in msgs)

    def test_start_pipeline_tool_call_is_parsed(self, mock_console):
        from agents.items import ToolCallItem
        from openai.types.responses import ResponseFunctionToolCall

        raw = ResponseFunctionToolCall(
            arguments=json.dumps({"description": "Build a guestbook"}),
            call_id="c1", name="start_pipeline", type="function_call",
        )
        item = ToolCallItem(agent=MagicMock(), raw_item=raw)

        runner = ChatAgentRunner(mock_console)
        with patch("agents.Runner.run", new=AsyncMock(return_value=_fake_run_result([item]))):
            rid, msgs = asyncio.get_event_loop().run_until_complete(
                runner.handle_message(None, "build a guestbook", [], [])
            )
        assert rid is not None
        assert any(m.msg_type == "pipeline_started" for m in msgs)

    def test_request_dep_input_tool_call_is_parsed(self, mock_console):
        from agents.items import ToolCallItem
        from openai.types.responses import ResponseFunctionToolCall

        raw = ResponseFunctionToolCall(
            arguments=json.dumps({"dep_names": ["RAILWAY_TOKEN"]}),
            call_id="c2", name="request_dep_input", type="function_call",
        )
        item = ToolCallItem(agent=MagicMock(), raw_item=raw)

        runner = ChatAgentRunner(mock_console)
        with patch("agents.Runner.run", new=AsyncMock(return_value=_fake_run_result([item]))):
            rid, msgs = asyncio.get_event_loop().run_until_complete(
                runner.handle_message("run-test123", "here are deps", [], [])
            )
        dep_msg = next(m for m in msgs if m.msg_type == "dep_request")
        assert "RAILWAY_TOKEN" in dep_msg.metadata["dep_names"]

    def test_start_pipeline_tool_includes_attachments(self, mock_console):
        """The start_pipeline tool threads pending attachments into the RunRequest —
        so an attached PDF is not dropped at the chat layer."""
        files = [{"name": "proposal.pdf", "content_b64": "JVBERi0="}]
        tools = make_tools(mock_console, attachments=lambda: files)
        start = next(t for t in tools if t.name == "start_pipeline")
        asyncio.get_event_loop().run_until_complete(
            start.on_invoke_tool(None, json.dumps({"description": "Build from this"}))
        )
        req = mock_console.start_run.call_args[0][0]
        assert req.context_files == files

    def test_handle_message_stashes_attachments_before_running(self, mock_console):
        """Files must be available to the tools during the agent run, since
        start_pipeline fires inside Runner.run."""
        files = [{"name": "proposal.pdf", "content_b64": "JVBERi0="}]
        runner = ChatAgentRunner(mock_console)
        seen = {}

        async def fake_run(agent, input):
            seen["pending"] = list(runner._pending_files)
            return _fake_run_result([])

        with patch("agents.Runner.run", new=fake_run):
            asyncio.get_event_loop().run_until_complete(
                runner.handle_message(None, "build from this", files, [])
            )
        assert seen["pending"] == files

    def test_tool_call_missing_required_arg_degrades_not_crashes(self, mock_console):
        """A schema-violating tool call (missing required 'description') degrades to a plain
        text reply instead of raising. OpenAI validates args server-side so this never fired
        there, but a ChatCompletions-compat proxy (Kimi via OpenRouter) can emit malformed
        arguments — crashing here would 500 the chat endpoint."""
        from agents.items import ToolCallItem
        from openai.types.responses import ResponseFunctionToolCall

        raw = ResponseFunctionToolCall(
            arguments=json.dumps({}),  # missing required 'description'
            call_id="c3", name="start_pipeline", type="function_call",
        )
        item = ToolCallItem(agent=MagicMock(), raw_item=raw)

        runner = ChatAgentRunner(mock_console)
        with patch("agents.Runner.run", new=AsyncMock(return_value=_fake_run_result([item]))):
            _, msgs = asyncio.get_event_loop().run_until_complete(
                runner.handle_message(None, "build", [], [])
            )
        assert all(m.msg_type != "pipeline_started" for m in msgs)


class TestChatAgentRunner:
    def test_init_creates_agent(self, mock_console):
        runner = ChatAgentRunner(mock_console)
        assert runner._agent is not None
        assert runner._console is mock_console

    def test_concierge_instructions_exist(self):
        assert "Factory Concierge" in CONCIERGE_INSTRUCTIONS or len(CONCIERGE_INSTRUCTIONS) > 100

    def test_check_and_notify_stage1_done(self, mock_console):
        mock_console.status.return_value = {
            "run_id": "run-test123", "phase": "architect", "stage": 2,
            "stage1_done": True, "stage2_done": False,
            "deps_required": [], "deps_satisfied": False,
            "spent_usd": 2.0, "status": "running",
        }
        runner = ChatAgentRunner(mock_console)
        msgs = runner.check_and_notify("run-test123", prev_stage=1)
        assert any(m.msg_type == "status_update" for m in msgs)

    def test_check_and_notify_deps_needed(self, mock_console):
        mock_console.status.return_value = {
            "run_id": "run-test123", "phase": "tickets", "stage": 2,
            "stage1_done": True, "stage2_done": True,
            "deps_required": ["RAILWAY_TOKEN"], "deps_satisfied": False,
            "spent_usd": 3.0, "status": "running",
        }
        runner = ChatAgentRunner(mock_console)
        msgs = runner.check_and_notify("run-test123", prev_stage=2)
        assert any(m.msg_type == "dep_request" for m in msgs)

    def test_check_and_notify_complete(self, mock_console):
        mock_console.status.return_value = {
            "run_id": "run-test123", "phase": "done", "stage": 3,
            "stage1_done": True, "stage2_done": True,
            "deps_required": [], "deps_satisfied": True,
            "spent_usd": 8.0, "done": True,
            "deploy_url": "https://sf-test123.up.railway.app",
        }
        runner = ChatAgentRunner(mock_console)
        msgs = runner.check_and_notify("run-test123", prev_stage=3)
        assert any(m.msg_type == "complete" for m in msgs)
        complete_msg = next(m for m in msgs if m.msg_type == "complete")
        assert "sf-test123" in complete_msg.content
        assert complete_msg.metadata["url"] == "https://sf-test123.up.railway.app"


class TestModelPickThreading:
    def test_start_pipeline_threads_model_picks_into_runrequest(self, mock_console):
        """The UI's planning/impl model picks ride the chat body (like runtime) and must
        reach the RunRequest, or the pick silently evaporates at the chat layer."""
        tools = make_tools(mock_console,
                           models=lambda: ("claude-fable-5", "claude-opus-4-8"))
        start = next(t for t in tools if t.name == "start_pipeline")
        asyncio.get_event_loop().run_until_complete(
            start.on_invoke_tool(None, json.dumps({"description": "Build it"}))
        )
        req = mock_console.start_run.call_args[0][0]
        assert req.planning_model == "claude-fable-5"
        assert req.impl_model == "claude-opus-4-8"
