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
    c.start_project = MagicMock(return_value="project-test123")
    c.status = MagicMock(return_value={
        "project_id": "project-test123", "phase": "research", "stage": 1,
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
    c._projects_dir = "/tmp/test-runs"
    return c


@pytest.fixture
def mock_users():
    u = MagicMock()
    u.org_for_user = MagicMock(return_value=None)
    u.create_org = MagicMock(return_value="org-abcd1234")
    u.get_org = MagicMock(return_value={"id": "org-abcd1234", "name": "Acme Industrial Supply"})
    u.update_org = MagicMock()
    u.set_profile = MagicMock()
    return u


class TestMakeTools:
    def test_tools_are_the_locked_13(self, mock_console):
        names = {t.name for t in make_tools(mock_console)}
        assert names == {
            "get_company_profile", "set_company_profile", "set_connected_systems",
            "set_project_basics", "set_project_scope", "attach_project_materials",
            "request_materials", "get_intake_state", "validate_intake_complete",
            "hand_off_to_factory", "check_status", "request_dep_input", "get_result",
        }
        # retired tools are gone
        assert "record_brief_section" not in names and "start_pipeline" not in names

    def test_hand_off_to_factory_promotes_the_active_draft(self, mock_console):
        mock_console.promote_draft = MagicMock(return_value="project-test123")
        tools = make_tools(mock_console, draft_id=lambda: "project-test123",
                           interview=lambda: "USER: build a guestbook")
        h = next(t for t in tools if t.name == "hand_off_to_factory")
        result = asyncio.get_event_loop().run_until_complete(h.on_invoke_tool(None, json.dumps({})))
        mock_console.promote_draft.assert_called_once()
        assert mock_console.promote_draft.call_args[0][0] == "project-test123"
        assert mock_console.promote_draft.call_args.kwargs["interview_md"].startswith("USER:")
        assert "project-test123" in result

    def test_set_project_basics_writes_draft(self, mock_console):
        mock_console.set_draft_project = MagicMock(return_value={"name": "Quote-to-Epicor", "goal": "g"})
        tools = make_tools(mock_console, draft_id=lambda: "project-test123")
        t = next(t for t in tools if t.name == "set_project_basics")
        asyncio.get_event_loop().run_until_complete(
            t.on_invoke_tool(None, json.dumps({"name": "Quote-to-Epicor", "goal": "g"})))
        mock_console.set_draft_project.assert_called_once_with("project-test123", name="Quote-to-Epicor", goal="g")

    def test_set_project_scope_writes_draft(self, mock_console):
        mock_console.set_draft_project = MagicMock(return_value={"scope": ["Inventory"]})
        tools = make_tools(mock_console, draft_id=lambda: "project-test123")
        t = next(t for t in tools if t.name == "set_project_scope")
        asyncio.get_event_loop().run_until_complete(
            t.on_invoke_tool(None, json.dumps({"scope": ["Inventory"]})))
        mock_console.set_draft_project.assert_called_once_with("project-test123", scope=["Inventory"])

    def test_get_company_profile_reads_org(self, mock_console, mock_users):
        mock_users.org_for_user = MagicMock(return_value={"id": "org-1", "name": "Acme"})
        tools = make_tools(mock_console, users=mock_users, owner=lambda: "op@x.ai")
        t = next(t for t in tools if t.name == "get_company_profile")
        result = asyncio.get_event_loop().run_until_complete(t.on_invoke_tool(None, "{}"))
        assert json.loads(result)["org"]["name"] == "Acme"

    def test_set_company_profile_creates_org_when_none(self, mock_console, mock_users):
        tools = make_tools(mock_console, users=mock_users, owner=lambda: "op@x.ai")
        t = next(t for t in tools if t.name == "set_company_profile")
        asyncio.get_event_loop().run_until_complete(t.on_invoke_tool(None, json.dumps({
            "name": "Acme Industrial Supply", "industry": "Industrial Distribution",
            "headcount": "51–200", "role": "Operations"})))
        mock_users.create_org.assert_called_once()
        # role flows into the user profile (designation)
        assert mock_users.set_profile.call_args.kwargs["designation"] == "Operations"

    def test_set_connected_systems_requires_org(self, mock_console, mock_users):
        mock_users.org_for_user = MagicMock(return_value=None)
        tools = make_tools(mock_console, users=mock_users, owner=lambda: "op@x.ai")
        t = next(t for t in tools if t.name == "set_connected_systems")
        result = asyncio.get_event_loop().run_until_complete(
            t.on_invoke_tool(None, json.dumps({"ids": ["epicor"]})))
        assert "error" in json.loads(result)

    def test_get_intake_state_is_readonly_snapshot(self, mock_console, mock_users):
        mock_users.org_for_user = MagicMock(return_value={"id": "org-1", "name": "Acme"})
        mock_console.draft_project = MagicMock(return_value={"name": "P", "goal": "g", "scope": []})
        tools = make_tools(mock_console, users=mock_users, owner=lambda: "op@x.ai",
                           draft_id=lambda: "project-test123")
        t = next(t for t in tools if t.name == "get_intake_state")
        out = json.loads(asyncio.get_event_loop().run_until_complete(t.on_invoke_tool(None, "{}")))
        assert out["company"]["name"] == "Acme" and out["project"]["name"] == "P"

    def test_check_status_calls_console(self, mock_console):
        tools = make_tools(mock_console)
        check = next(t for t in tools if t.name == "check_status")
        result = asyncio.get_event_loop().run_until_complete(
            check.on_invoke_tool(None, json.dumps({"project_id": "project-test123"}))
        )
        mock_console.status.assert_called_once_with("project-test123")
        parsed = json.loads(result)
        assert parsed["phase"] == "research"

    def test_request_dep_input_returns_structured(self, mock_console):
        tools = make_tools(mock_console)
        req_dep = next(t for t in tools if t.name == "request_dep_input")
        result = asyncio.get_event_loop().run_until_complete(
            req_dep.on_invoke_tool(None, json.dumps({
                "project_id": "project-test123",
                "dep_names": ["RAILWAY_TOKEN"],
            }))
        )
        parsed = json.loads(result)
        assert parsed["type"] == "dep_request"
        assert "RAILWAY_TOKEN" in parsed["dep_names"]


class TestChatToolOwnership:
    """Run-scoped chat tools must enforce the same ownership rules as the HTTP layer."""

    def test_member_cannot_check_status_of_foreign_run(self, mock_console):
        mock_console.project_owner = MagicMock(return_value="other@example.com")
        tools = make_tools(mock_console, viewer=lambda: ("user@example.com", "member"))
        check = next(t for t in tools if t.name == "check_status")
        result = asyncio.get_event_loop().run_until_complete(
            check.on_invoke_tool(None, json.dumps({"project_id": "project-test123"}))
        )
        parsed = json.loads(result)
        assert parsed.get("error") == "forbidden"
        mock_console.status.assert_not_called()

    def test_member_can_check_status_of_own_run(self, mock_console):
        mock_console.project_owner = MagicMock(return_value="user@example.com")
        tools = make_tools(mock_console, viewer=lambda: ("user@example.com", "member"))
        check = next(t for t in tools if t.name == "check_status")
        result = asyncio.get_event_loop().run_until_complete(
            check.on_invoke_tool(None, json.dumps({"project_id": "project-test123"}))
        )
        parsed = json.loads(result)
        assert "error" not in parsed
        mock_console.status.assert_called_once_with("project-test123")

    def test_admin_bypasses_ownership_check(self, mock_console):
        mock_console.project_owner = MagicMock(return_value="other@example.com")
        tools = make_tools(mock_console, viewer=lambda: ("admin@example.com", "admin"))
        get = next(t for t in tools if t.name == "get_result")
        result = asyncio.get_event_loop().run_until_complete(
            get.on_invoke_tool(None, json.dumps({"project_id": "project-test123"}))
        )
        parsed = json.loads(result)
        assert parsed.get("error") != "forbidden"
        mock_console.evidence.assert_called_once_with("project-test123")


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

    def test_multiple_message_items_collapse_to_one_bubble(self, mock_console):
        """Regression: the SDK can emit >1 MessageOutputItem per turn (model chatty / pausing
        around tool calls). They must collapse into ONE assistant bubble, not render as two
        questions in a row."""
        from agents.items import MessageOutputItem
        from openai.types.responses import ResponseOutputMessage, ResponseOutputText

        def _msg(mid, txt):
            raw = ResponseOutputMessage(
                id=mid, content=[ResponseOutputText(annotations=[], text=txt, type="output_text")],
                role="assistant", status="completed", type="message")
            return MessageOutputItem(agent=MagicMock(), raw_item=raw)

        items = [_msg("m1", "Got it. Any existing assets?"), _msg("m2", "And any risks?")]
        runner = ChatAgentRunner(mock_console)
        with patch("agents.Runner.run", new=AsyncMock(return_value=_fake_run_result(items))):
            rid, msgs = asyncio.get_event_loop().run_until_complete(
                runner.handle_message("project-abcd1234", "university success office", [], [])
            )
        text_msgs = [m for m in msgs if m.msg_type == "text"]
        assert len(text_msgs) == 1
        assert "existing assets" in text_msgs[0].content and "risks" in text_msgs[0].content

    def test_hand_off_tool_call_emits_pipeline_started(self, mock_console):
        from agents.items import ToolCallItem
        from openai.types.responses import ResponseFunctionToolCall

        raw = ResponseFunctionToolCall(
            arguments=json.dumps({}),
            call_id="c1", name="hand_off_to_factory", type="function_call",
        )
        item = ToolCallItem(agent=MagicMock(), raw_item=raw)

        runner = ChatAgentRunner(mock_console)
        with patch("agents.Runner.run", new=AsyncMock(return_value=_fake_run_result([item]))):
            rid, msgs = asyncio.get_event_loop().run_until_complete(
                # the server mints the draft id and passes it in; promotion keeps that same id
                runner.handle_message("project-abcd1234", "build a guestbook", [], [])
            )
        assert rid == "project-abcd1234"
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
                runner.handle_message("project-test123", "here are deps", [], [])
            )
        dep_msg = next(m for m in msgs if m.msg_type == "dep_request")
        assert "RAILWAY_TOKEN" in dep_msg.metadata["dep_names"]

    def test_handle_message_stashes_attachments_before_running(self, mock_console):
        """Files must be available to the tools during the agent run, since
        hand_off_to_factory fires inside Runner.run."""
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

    def test_tool_call_malformed_args_degrades_not_crashes(self, mock_console):
        """A malformed tool call (request_dep_input with no dep_names) degrades instead of raising.
        OpenAI validates args server-side so this never fired there, but a ChatCompletions-compat
        proxy (Kimi via OpenRouter) can emit malformed arguments — crashing would 500 the chat."""
        from agents.items import ToolCallItem
        from openai.types.responses import ResponseFunctionToolCall

        raw = ResponseFunctionToolCall(
            arguments=json.dumps({}),  # missing required dep_names
            call_id="c3", name="request_dep_input", type="function_call",
        )
        item = ToolCallItem(agent=MagicMock(), raw_item=raw)

        runner = ChatAgentRunner(mock_console)
        with patch("agents.Runner.run", new=AsyncMock(return_value=_fake_run_result([item]))):
            _, msgs = asyncio.get_event_loop().run_until_complete(
                runner.handle_message("project-abcd1234", "deps", [], [])
            )
        assert all(m.msg_type != "dep_request" for m in msgs)


class TestChatAgentRunner:
    def test_init_creates_agent(self, mock_console):
        runner = ChatAgentRunner(mock_console)
        assert runner._agent is not None
        assert runner._console is mock_console

    def test_concierge_instructions_exist(self):
        assert "Factory Concierge" in CONCIERGE_INSTRUCTIONS or len(CONCIERGE_INSTRUCTIONS) > 100

    def test_check_and_notify_stage1_done(self, mock_console):
        mock_console.status.return_value = {
            "project_id": "project-test123", "phase": "architect", "stage": 2,
            "stage1_done": True, "stage2_done": False,
            "deps_required": [], "deps_satisfied": False,
            "spent_usd": 2.0, "status": "running",
        }
        runner = ChatAgentRunner(mock_console)
        msgs = runner.check_and_notify("project-test123", prev_stage=1)
        assert any(m.msg_type == "status_update" for m in msgs)

    def test_check_and_notify_deps_needed(self, mock_console):
        mock_console.status.return_value = {
            "project_id": "project-test123", "phase": "tickets", "stage": 2,
            "stage1_done": True, "stage2_done": True,
            "deps_required": ["RAILWAY_TOKEN"], "deps_satisfied": False,
            "spent_usd": 3.0, "status": "running",
        }
        runner = ChatAgentRunner(mock_console)
        msgs = runner.check_and_notify("project-test123", prev_stage=2)
        assert any(m.msg_type == "dep_request" for m in msgs)

    def test_check_and_notify_complete(self, mock_console):
        mock_console.status.return_value = {
            "project_id": "project-test123", "phase": "done", "stage": 3,
            "stage1_done": True, "stage2_done": True,
            "deps_required": [], "deps_satisfied": True,
            "spent_usd": 8.0, "done": True,
            "deploy_url": "https://sf-test123.up.railway.app",
        }
        runner = ChatAgentRunner(mock_console)
        msgs = runner.check_and_notify("project-test123", prev_stage=3)
        assert any(m.msg_type == "complete" for m in msgs)
        complete_msg = next(m for m in msgs if m.msg_type == "complete")
        assert "sf-test123" in complete_msg.content
        assert complete_msg.metadata["url"] == "https://sf-test123.up.railway.app"


class TestModelPickThreading:
    """The UI's runtime/model/name picks now ride into create_draft (the server passes the chat
    body's picks when minting the interview draft); promote_draft reads them from the draft state."""

    def _real_console(self, tmp_path):
        from software_factory.console import Console
        ids = iter([f"project-{i:08x}" for i in range(1, 9)])
        return Console(str(tmp_path), launch=lambda *a, **k: {"pid": 1}, new_id=lambda: next(ids))

    def test_create_draft_threads_model_picks_and_name(self, tmp_path):
        c = self._real_console(tmp_path)
        rid = c.create_draft(owner="op@x.ai", name="Acme CRM",
                             planning_model="claude-fable-5", impl_model="claude-opus-4-8")
        st = c._load_state(rid)
        assert st.name == "Acme CRM"
        assert st.planning_model == "claude-fable-5"
        assert st.impl_model == "claude-opus-4-8"

    def test_promote_preserves_draft_runtime(self, tmp_path):
        c = self._real_console(tmp_path)
        rid = c.create_draft(owner="op@x.ai", runtime="opencode")
        c.update_draft_brief(rid, {"goals": "a cargo screening prototype for ground handlers"})
        c.promote_draft(rid, description="cargo screening")
        assert c._load_state(rid).runtime == "opencode"
