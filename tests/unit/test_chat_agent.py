"""Tests for chat_agent — model selection and draft model-pick threading.

SOF-35: the OpenAI Agents SDK runtime (`Agent`/`Runner`) and its 14 tools (`make_tools`,
`ChatAgentRunner`) are removed — no ported behavior. Tests for
the removed tools/runner are deleted, not adapted; the LangChain rebuild (T2.1/T2.2) ships with
its own tests against the new architecture. The concierge system prompt + override cache now
live in `default_prompt.py` (see test_default_prompt_sof62.py) and `check_and_notify` no longer
exists in the codebase.
"""
from unittest.mock import MagicMock

import pytest


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
        c.promote_draft(rid, description="cargo screening")
        assert c._load_state(rid).runtime == "opencode"
