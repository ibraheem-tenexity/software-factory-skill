"""Tests for chat_agent — model selection, the concierge system prompt + override cache, and
check_and_notify (the pipeline-stage-transition notifier, extracted from the removed
ChatAgentRunner in SOF-35).

SOF-35: the OpenAI Agents SDK runtime (`Agent`/`Runner`) and its 14 tools (`make_tools`,
`ChatAgentRunner`) are removed — no ported behavior, see concierge-agent-spec.md §1. Tests for
the removed tools/runner are deleted, not adapted; the LangChain rebuild (T2.1/T2.2) ships with
its own tests against the new architecture.
"""
from unittest.mock import MagicMock, patch

import pytest

from software_factory.chat_agent import (
    CONCIERGE_INSTRUCTIONS,
    check_and_notify,
    reset_concierge_prompt_cache,
    resolve_concierge_instructions,
)


@pytest.fixture(autouse=True)
def _reset_concierge_prompt_cache():
    reset_concierge_prompt_cache()
    yield
    reset_concierge_prompt_cache()


@pytest.fixture
def mock_console():
    c = MagicMock()
    c.status = MagicMock(return_value={
        "project_id": "project-test123", "phase": "research", "stage": 1,
        "stage1_done": False, "stage2_done": False,
        "deps_required": [], "deps_satisfied": False,
        "spent_usd": 1.23, "status": "running",
    })
    return c


class TestConciergePrompt:
    def test_concierge_instructions_exist(self):
        assert "Factory Concierge" in CONCIERGE_INSTRUCTIONS or len(CONCIERGE_INSTRUCTIONS) > 100

    def test_concierge_prompt_db_override_wins(self):
        store = MagicMock()
        store.get.return_value = {"prompt": "EDITED concierge prompt"}
        with patch("software_factory.agent_prompts.PromptStore", return_value=store):
            assert resolve_concierge_instructions() == "EDITED concierge prompt"

    def test_concierge_prompt_falls_back_without_override(self):
        store = MagicMock()
        store.get.return_value = None
        with patch("software_factory.agent_prompts.PromptStore", return_value=store):
            assert resolve_concierge_instructions() == CONCIERGE_INSTRUCTIONS

    def test_concierge_prompt_db_failure_does_not_break_resolution(self):
        store = MagicMock()
        store.get.side_effect = RuntimeError("database unavailable")
        with patch("software_factory.agent_prompts.PromptStore", return_value=store):
            assert resolve_concierge_instructions() == CONCIERGE_INSTRUCTIONS

    def test_concierge_prompt_cache_avoids_repeated_db_reads(self):
        store = MagicMock()
        store.get.return_value = {"prompt": "CACHED concierge prompt"}
        with patch("software_factory.agent_prompts.PromptStore", return_value=store):
            assert resolve_concierge_instructions() == "CACHED concierge prompt"
            assert resolve_concierge_instructions() == "CACHED concierge prompt"
        store.get.assert_called_once()


class TestCheckAndNotify:
    def test_check_and_notify_stage1_done(self, mock_console):
        mock_console.status.return_value = {
            "project_id": "project-test123", "phase": "architect", "stage": 2,
            "stage1_done": True, "stage2_done": False,
            "deps_required": [], "deps_satisfied": False,
            "spent_usd": 2.0, "status": "running",
        }
        msgs = check_and_notify(mock_console, "project-test123", prev_stage=1)
        assert any(m.msg_type == "status_update" for m in msgs)

    def test_check_and_notify_deps_needed(self, mock_console):
        mock_console.status.return_value = {
            "project_id": "project-test123", "phase": "tickets", "stage": 2,
            "stage1_done": True, "stage2_done": True,
            "deps_required": ["RAILWAY_TOKEN"], "deps_satisfied": False,
            "spent_usd": 3.0, "status": "running",
        }
        msgs = check_and_notify(mock_console, "project-test123", prev_stage=2)
        assert any(m.msg_type == "dep_request" for m in msgs)

    def test_check_and_notify_complete(self, mock_console):
        mock_console.status.return_value = {
            "project_id": "project-test123", "phase": "done", "stage": 3,
            "stage1_done": True, "stage2_done": True,
            "deps_required": [], "deps_satisfied": True,
            "spent_usd": 8.0, "done": True,
            "deploy_url": "https://sf-test123.up.railway.app",
        }
        msgs = check_and_notify(mock_console, "project-test123", prev_stage=3)
        assert any(m.msg_type == "complete" for m in msgs)
        complete_msg = next(m for m in msgs if m.msg_type == "complete")
        assert "sf-test123" in complete_msg.content
        assert complete_msg.metadata["url"] == "https://sf-test123.up.railway.app"


class TestModelPickThreading:
    """The UI's runtime/model/name picks now ride into create_draft (the server passes the chat
    body's picks when minting the interview draft); promote_draft reads them from the draft state.

    Unrelated to the OpenAI-Agents-SDK rip-out — kept unchanged."""

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
