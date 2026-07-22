"""SOF-62: the first-turn project-context block (services/conversation.py) and the once-per-project
injection wiring in DbConversation. Written fresh against the current API; NOT built on test_conversation_db.py,
which fails at import post-c97c7eb (filed separately as SOF-67).

No DB, no network: dbshim.connect and MemoryStore are patched throughout.
"""
import asyncio
from unittest.mock import MagicMock, patch

from software_factory.services.conversation import (
    DbConversation,
    _build_first_turn_context,
)


def _state(name="Acme", goal="Automate quoting", scope=None, description="desc"):
    s = MagicMock()
    s.name, s.goal, s.scope, s.description = name, goal, scope or [], description
    s.recipe_id = ""
    return s


class TestBuildFirstTurnContext:
    def test_assembles_user_and_document_context_without_a_retired_sow_section(self):
        console = MagicMock()
        console._load_state.return_value = _state()
        with patch("software_factory.services.conversation._document_context_rows", return_value=[]), \
             patch("software_factory.memory.store.MemoryStore") as MS:
            MS.return_value.assumptions.return_value = [
                {"fact": "Uses Epicor", "document_name": "doc.pdf"}]
            block = _build_first_turn_context(console, "proj-1")

        assert "### The user's own input" in block
        assert "Acme" in block and "Automate quoting" in block
        assert "### Statement of Work" not in block
        assert "### Documents" in block and "no documents uploaded yet" in block
        assert "### Existing per-document assumptions" in block
        assert "Uses Epicor (from doc.pdf)" in block

    def test_missing_pieces_are_stated_not_silently_dropped(self):
        console = MagicMock()
        console._load_state.return_value = _state(name="")
        with patch("software_factory.services.conversation._document_context_rows", return_value=[]), \
             patch("software_factory.memory.store.MemoryStore") as MS:
            MS.return_value.assumptions.return_value = []
            block = _build_first_turn_context(console, "proj-1")

        assert "no documents uploaded yet" in block
        assert "no per-document assumptions" in block


class TestFirstTurnInjectionWiring:
    """Exercises DbConversation.turn() end to end with a fake store + fake ChatAgent class,
    same injectable-dependency pattern as the rest of this test suite."""

    def _run(self, conv, project_id, message):
        return asyncio.run(conv.turn(project_id, message))

    def test_first_turn_bakes_context_into_agent_construction(self):
        console = MagicMock()
        console._load_state.return_value = _state()
        store = _FakeStore()
        constructed = []

        class FakeChatAgent:
            def __init__(self, context, tools, model=None, first_turn_context=None):
                constructed.append(first_turn_context)
                self.last_usage = {}

            async def run(self, messages):
                from software_factory.data_transfer_objects.chat_agent import ConciergeTurn
                return ConciergeTurn(response="hi", suggested_responses=[])

        with patch("software_factory.chat_agent.ChatAgent", FakeChatAgent), \
             patch("software_factory.concierge_tools.build_project_tools", return_value=[]), \
             patch("software_factory.services.conversation._build_first_turn_context",
                   return_value="CTX-BLOCK") as builder:
            conv = DbConversation(store=store, console=console)
            self._run(conv, "proj-1", "hello")

        builder.assert_called_once_with(console, "proj-1")
        assert constructed == ["CTX-BLOCK"]

    def test_second_turn_reuses_the_cached_agent_without_rebuilding_context(self):
        console = MagicMock()
        console._load_state.return_value = _state()
        store = _FakeStore()
        constructed = []

        class FakeChatAgent:
            def __init__(self, context, tools, model=None, first_turn_context=None):
                constructed.append(first_turn_context)
                self.last_usage = {}

            async def run(self, messages):
                from software_factory.data_transfer_objects.chat_agent import ConciergeTurn
                return ConciergeTurn(response="hi", suggested_responses=[])

        with patch("software_factory.chat_agent.ChatAgent", FakeChatAgent), \
             patch("software_factory.concierge_tools.build_project_tools", return_value=[]), \
             patch("software_factory.services.conversation._build_first_turn_context",
                   return_value="CTX-BLOCK") as builder:
            conv = DbConversation(store=store, console=console)
            self._run(conv, "proj-1", "first message")
            self._run(conv, "proj-1", "second message")

        # Exactly one agent construction (one call to the context builder), for the WHOLE
        # conversation — the second turn must not re-inject or rebuild it.
        builder.assert_called_once()
        assert constructed == ["CTX-BLOCK"]

    def test_injected_agent_bypasses_first_turn_context_entirely(self):
        """When an agent is injected directly (tests / non-project contexts), _get_agent must
        never call the context builder at all — this is the pre-existing test-injection seam."""
        console = MagicMock()
        store = _FakeStore()

        class FakeAgent:
            last_usage = {}

            async def run(self, messages):
                from software_factory.data_transfer_objects.chat_agent import ConciergeTurn
                return ConciergeTurn(response="hi", suggested_responses=[])

        with patch("software_factory.services.conversation._build_first_turn_context") as builder:
            conv = DbConversation(store=store, console=console, agent=FakeAgent())
            self._run(conv, "proj-1", "hello")

        builder.assert_not_called()


class _FakeStore:
    """Minimal in-memory ConversationStore stand-in — append()/history() shapes only, no DB."""

    def __init__(self):
        self._rows: dict = {}

    def append(self, session_id, role, blocks, *, project_id=None, **kwargs):
        text = blocks[0]["text"] if blocks and blocks[0].get("type") == "text" else ""
        rows = self._rows.setdefault(session_id, [])
        rows.append({"role": role, "input": text, "seq": len(rows), "json_blob": blocks})
        return f"fake-id-{len(rows)}"

    def history(self, session_id):
        return list(self._rows.get(session_id, []))
