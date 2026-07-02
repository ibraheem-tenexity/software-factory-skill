"""In-memory mock Concierge conversation — stands in until the real LangChain agent ships (see
docs/concierge-agent-spec.md). Returns deterministic scripted turns so the frontend conversation
loop (plain-text vs up-to-4-choice questions → hand off) can be built and demoed without a model
key.

Framework-free (only `time` + `errors.py`); one in-memory transcript per project_id; resets on
restart — expected for the mock. `DbConversation` below (SOF-31/T1.3) is the durable swap: same
`turn()`/`history()` contract, backed by `ConversationStore` instead of an in-memory dict.
`console/state.py::reset()` picks one or the other behind `SF_CONVERSATION_DB` — this mock class
and its own tests (`tests/unit/test_conversation.py`) are untouched, unconditionally hermetic.
"""
import time
import uuid

from software_factory.services.errors import Invalid

# Scripted agent turns, walked by the count of prior agent turns. Each entry is (message, choices);
# `choices` empty ⇒ a plain-text turn, otherwise ≤4 single-select options. The real agent decides
# text-vs-choices per turn; the mock just cycles a representative script (text → choices → choices).
_SCRIPT: list[tuple[str, list[str]]] = [
    ("Thanks — that's a solid start. In one line, what's the single most important outcome this "
     "project has to deliver?", []),
    ("Which part of the workflow is the biggest bottleneck today?",
     ["Manual data entry / re-keying", "Approvals & sign-off", "Reporting & visibility", "Something else"]),
    ("Who are the primary users of what we build?",
     ["Internal ops team", "Sales / quoting", "External customers", "Management"]),
]
_HANDOFF = ("I have enough to draft the brief. Hand off to the factory whenever you're ready — or keep "
            "adding detail and I'll fold it in.", [])


class Conversation:
    """Mock conversation service: one in-memory transcript per project."""

    def __init__(self):
        self._store: dict = {}  # project_id → list[{role, content, choices}]

    def history(self, project_id: str) -> list[dict]:
        """The full transcript for a project (oldest first). Empty if none yet."""
        return list(self._store.get(project_id, []))

    def turn(self, project_id: str, message: str) -> dict:
        """Record the user's message and return the (mock) agent's next turn:
        {"message": str, "choices": list[str] (≤4), "done": bool}. `done` = the agent has no more
        questions and is inviting hand-off. Raises `Invalid` on an empty message."""
        text = (message or "").strip()
        if not text:
            raise Invalid("message is empty")
        turns = self._store.setdefault(project_id, [])
        turns.append({"role": "user", "content": text, "choices": []})

        prior_agent_turns = sum(1 for t in turns if t["role"] == "agent")
        done = prior_agent_turns >= len(_SCRIPT)
        reply, choices = _HANDOFF if done else _SCRIPT[prior_agent_turns]
        turns.append({"role": "agent", "content": reply, "choices": list(choices), "ts": _now()})
        return {"message": reply, "choices": list(choices), "done": done}


def _now() -> float:
    return time.time()


def _onboarding_session_id(project_id: str) -> str:
    """Deterministic session_id for the (exactly one) onboarding conversation per project —
    concierge-conversation-store.md §2. uuid5 over a fixed, standard namespace so this needs no
    magic constant of its own and is stable across processes/deployments."""
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, f"onboarding:{project_id}"))


class DbConversation:
    """DB-backed Concierge conversation (SOF-31/T1.3) — the SAME turn()/history() contract as the
    mock above, now durable via ConversationStore. Storage-only swap per the ticket's own scope:
    the scripted `_SCRIPT` reply logic is preserved verbatim (not coupled to the agent rewrite —
    that's T2.x), just re-homed to read "how many prior agent turns" from persisted history
    instead of an in-memory list.

    `choices`/`done` were never a persisted concept even in the mock — they're recomputed fresh
    from script position on every `turn()` call. `history()` keeps that: it reports an empty
    `choices` list per row (the existing test contract only asserts `role` values from
    `history()`, never `choices`/`content`, so this is a safe, surgical simplification)."""

    def __init__(self, users=None, store=None, agent=None, console=None):
        if store is not None:
            self._store = store
        else:
            from software_factory.conversation_store import ConversationStore
            self._store = ConversationStore(users=users)
        self._agent = agent      # injectable ChatAgent (tests); used for every project when set
        self._console = console  # needed to bind the per-project tool belt
        self._agents: dict = {}  # project_id → ChatAgent (tools bind project_id at construction)

    def _get_agent(self, project_id: str):
        if self._agent is not None:
            return self._agent
        if project_id not in self._agents:
            from software_factory.chat_agent import ChatAgent
            tools = []
            if self._console is not None:
                from software_factory.concierge_tools import build_project_tools
                tools = build_project_tools(self._console, project_id)
            self._agents[project_id] = ChatAgent(context="intake", tools=tools)
        return self._agents[project_id]

    def history(self, project_id: str) -> list[dict]:
        """The full transcript for a project (oldest first). Empty if none yet."""
        rows = self._store.history(_onboarding_session_id(project_id))
        return [{"role": r["role"], "content": r["input"] or "", "choices": []} for r in rows]

    async def turn(self, project_id: str, message: str) -> dict:
        """Record the user's message, run it through the real LangChain ChatAgent ("intake"
        context, per-project tool belt), and return a ConciergeTurn dict: {response,
        suggested_responses, message_id, session_id}. Raises `Invalid` on an empty message —
        persists nothing on that path, matching the mock."""
        text = (message or "").strip()
        if not text:
            raise Invalid("message is empty")
        session_id = _onboarding_session_id(project_id)

        self._store.append(session_id, "user", [{"type": "text", "text": text}],
                          project_id=project_id)

        from software_factory.conversation_provider import to_provider
        rows = self._store.history(session_id)
        messages = to_provider(rows, "openai")   # OpenRouter (Kimi) also uses the OpenAI shape

        agent = self._get_agent(project_id)
        turn = await agent.run(messages)
        usage = getattr(agent, "last_usage", None) or {}

        suggested = [sr.model_dump() for sr in turn.suggested_responses]
        block = {"type": "text", "text": turn.response, "suggested_responses": suggested}
        message_id = self._store.append(
            session_id, "agent", [block], project_id=project_id,
            model=usage.get("model"), provider=usage.get("provider"),
            input_tokens=usage.get("input_tokens", 0), output_tokens=usage.get("output_tokens", 0),
            cost_usd=usage.get("cost_usd", 0.0),
        )

        return {"response": turn.response, "suggested_responses": suggested,
                "message_id": message_id, "session_id": session_id}
