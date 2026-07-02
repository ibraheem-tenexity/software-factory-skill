"""DB-backed Concierge conversation service — see `DbConversation` below.

`SF_CONVERSATION_DB` is retired (the operator declared it permanent-on): `DbConversation` is now
unconditionally the conversation service, backed by `ConversationStore`. The in-memory mock
(`Conversation`, scripted turns for a keyless demo) and its tests are removed with it.
"""
import uuid

from software_factory.services.errors import Invalid
from software_factory import dbshim


def _onboarding_session_id(project_id: str) -> str:
    """Deterministic session_id for the (exactly one) onboarding conversation per project —
    concierge-conversation-store.md §2. uuid5 over a fixed, standard namespace so this needs no
    magic constant of its own and is stable across processes/deployments."""
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, f"onboarding:{project_id}"))


def _matching_sow_bodies(project_name: str) -> list[dict]:
    """SOW row(s) whose free-text `project` matches this project's name (SOF-62). No user-facing
    "choose an SOW" mechanism exists yet — sow.project is free-text, staff-authored (Tenexity OS
    §3.4b) — so name-match is the nearest-term linkage; a real `sow_id` on the draft is a separate,
    later fix. Case-insensitive (a staff-typed sow.project differing only in case shouldn't
    silently miss — the sharpest edge of the known name-match gap, per review) but still an exact
    match otherwise. Read via dbshim like MemoryStore does — sow is a global table, not
    project-scoped storage, so this is a plain query, not a MemoryStore method."""
    name = (project_name or "").strip()
    if not name:
        return []
    conn = dbshim.connect(".")
    try:
        rows = conn.execute(
            "SELECT title, body FROM sow WHERE lower(project) = lower(?) AND body IS NOT NULL",
            (name,),
        ).fetchall()
    finally:
        conn.close()
    return [{"title": r["title"], "body": r["body"]} for r in rows]


def _build_first_turn_context(console, project_id: str) -> str:
    """SOF-62: the server-assembled project-context block for the Concierge's first turn — the
    user's own project input, the matching SOW body, every document summary, and existing
    per-document assumptions. Pushed into the system prompt (see default_prompt.build_system_prompt),
    never a fake user message, so the first reply already accounts for everything on file with no
    tool call required. Missing pieces (no SOW match, no documents yet) are stated as such, never
    silently omitted, so the agent doesn't have to guess whether a section was skipped or is
    genuinely empty."""
    from software_factory.memory.store import MemoryStore

    state = console._load_state(project_id)
    sections = []

    sections.append(
        "### The user's own input\n"
        f"- Project name: {state.name or '(untitled)'}\n"
        f"- Goal: {state.goal or '(not given yet)'}\n"
        f"- Scope: {', '.join(state.scope) if state.scope else '(not given yet)'}\n"
        f"- Description: {state.description or '(not composed yet)'}"
    )

    sow_rows = _matching_sow_bodies(state.name)
    if sow_rows:
        sow_text = "\n\n".join(f"**{r['title']}**\n{r['body']}" for r in sow_rows)
    else:
        sow_text = "(no SOW on file matching this project's name)"
    sections.append(f"### Statement of Work\n{sow_text}")

    summaries = MemoryStore().list_doc_summaries("project", project_id)
    if summaries:
        summary_text = "\n\n".join(
            f"- {row['summary_md'] or '(summary pending — status: ' + row['status'] + ')'}"
            for row in summaries.values()
        )
    else:
        summary_text = "(no documents uploaded yet)"
    sections.append(f"### Document summaries\n{summary_text}")

    assumptions = MemoryStore().assumptions("project", project_id)
    if assumptions:
        assumption_text = "\n".join(
            f"- {a['fact']} (from {a['document_name']})" for a in assumptions
        )
    else:
        assumption_text = "(no per-document assumptions extracted yet)"
    sections.append(f"### Existing per-document assumptions\n{assumption_text}")

    return "\n\n".join(sections)


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

    def _get_agent(self, project_id: str, is_first_turn: bool = False):
        # self._agents is IN-PROCESS ONLY. After a restart, an in-flight conversation's first
        # unanswered turn post-restart sees non-empty history (is_first_turn=False), so the
        # context block is NOT reconstructed — by design, not a gap: the discussed context already
        # lives in the persisted conversation history the agent replays every turn regardless.
        # Do not "fix" this into always-injecting on cache-miss; that would double the context on
        # every restart of a long-running conversation instead of relying on history.
        if self._agent is not None:
            return self._agent
        if project_id not in self._agents:
            from software_factory.chat_agent import ChatAgent
            tools = []
            first_turn_context = None
            if self._console is not None:
                from software_factory.concierge_tools import build_project_tools
                tools = build_project_tools(self._console, project_id)
                if is_first_turn:
                    first_turn_context = _build_first_turn_context(self._console, project_id)
            self._agents[project_id] = ChatAgent(
                context="intake", tools=tools, first_turn_context=first_turn_context)
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
        # Checked BEFORE appending this message: an empty history means this call IS turn one —
        # that's the signal _get_agent uses to bake the first-turn context block into the system
        # prompt (SOF-62). Checking after the append below would always see >=1 row.
        is_first_turn = not self._store.history(session_id)

        self._store.append(session_id, "user", [{"type": "text", "text": text}],
                          project_id=project_id)

        from software_factory.conversation_provider import to_provider
        rows = self._store.history(session_id)
        messages = to_provider(rows, "openai")   # OpenRouter (Kimi) also uses the OpenAI shape

        agent = self._get_agent(project_id, is_first_turn=is_first_turn)
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
