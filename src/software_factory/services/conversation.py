"""DB-backed Concierge conversation service — see `DbConversation` below.

`SF_CONVERSATION_DB` is retired (the operator declared it permanent-on): `DbConversation` is now
unconditionally the conversation service, backed by `ConversationStore`.
"""
import logging
import uuid

from software_factory import dbshim
from software_factory.constants import CONCIERGE_SAFE_FALLBACK
from software_factory.data_transfer_objects.chat_agent import ConciergeTurn
from software_factory.recipes.store import RecipeStore
from software_factory.tagged_reply import parse_tagged_reply

logger = logging.getLogger(__name__)

# SOF-137: the first-turn context is baked into the system prompt and re-sent EVERY turn (the
# cached agent instance reuses it for the whole conversation) — unlike fetch_document_markdown's
# one-shot 500k-token ceiling (concierge_tools._MAX_FULL_DOCUMENT_TOKENS), inlining anywhere near
# that size here would overflow the chat model's context on every turn, forever, for that
# project. A dedicated, much smaller budget: per-doc AND a running total across all documents —
# over-budget documents fall back to summary + search/fetch tools, same as an oversized single doc.
_INLINE_CONTEXT_PER_DOC_TOKENS = 20_000
_INLINE_CONTEXT_TOTAL_TOKENS = 40_000


def _onboarding_session_id(project_id: str) -> str:
    """Deterministic session_id for the one onboarding conversation per project. uuid5 over a
    fixed standard namespace needs no private magic constant and is stable across deployments."""
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, f"onboarding:{project_id}"))


def _document_context_rows(project_id: str) -> list[dict]:
    """blob_id/name/summary_md/status for every ingested document in this project (SOF-137: the
    full-doc-context first-turn block needs the display name doc_summary rows alone don't carry).
    A blobs+doc_summary join, mirroring MemoryStore.assumptions()'s pattern — raw SQL rather than
    MemoryStore because this module is CORE and must not import console.*, and MemoryStore has no
    combined name+summary read."""
    conn = dbshim.connect(".")
    try:
        rows = conn.execute(
            "SELECT b.id AS blob_id, b.name AS document_name, ds.summary_md, ds.status "
            "FROM blobs b JOIN doc_summary ds ON ds.blob_id = b.id "
            "WHERE ds.scope = 'project' AND ds.scope_id = ?",
            (project_id,),
        ).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]


def _build_first_turn_context(console, project_id: str, users=None) -> str:
    """SOF-62: the server-assembled project-context block for the Concierge's first turn — the
    owning company's profile, the user's own project input, the selected recipe, every document
    summary, and existing per-document assumptions. Pushed into the system prompt (see
    default_prompt.build_system_prompt), never a fake user message, so the first reply already
    accounts for everything on file with no tool call required. Missing pieces (no company profile,
    no selected recipe, no documents yet) are stated as such, never silently omitted, so the agent
    doesn't have to guess whether a section was skipped or is genuinely empty."""
    from software_factory.memory.store import MemoryStore

    state = console._load_state(project_id)
    sections = []

    # The company that owns this project — everything captured on the org profile at signup, so the
    # Concierge leads with company context and never re-asks what the org record already answers.
    org = None
    if users is not None and getattr(state, "owner", ""):
        try:
            org = users.org_for_user(state.owner)
        except Exception:
            org = None
    if org:
        sub_focus = ", ".join(org.get("sub_focus") or []) or "(none listed)"
        systems = ", ".join(org.get("connected_systems") or []) or "(none listed)"
        company_text = (
            f"- Company: {org.get('name') or '(unnamed)'}\n"
            f"- Industry: {org.get('industry') or '(not provided)'}\n"
            f"- Focus areas: {sub_focus}\n"
            f"- Headcount: {org.get('headcount') or '(not provided)'}\n"
            f"- Revenue: {org.get('revenue') or '(not provided)'}\n"
            f"- Location: {org.get('location') or '(not provided)'}\n"
            f"- Website: {org.get('website') or '(not provided)'}\n"
            f"- Connected systems: {systems}"
        )
    else:
        company_text = "(no company profile on file for this project's owner)"
    sections.append(f"### The company\n{company_text}")

    sections.append(
        "### The user's own input\n"
        f"- Project name: {state.name or '(untitled)'}\n"
        f"- Goal: {state.goal or '(not given yet)'}\n"
        f"- Scope: {', '.join(state.scope) if state.scope else '(not given yet)'}\n"
        f"- Description: {state.description or '(not composed yet)'}"
    )

    # A picked repo-backed recipe is the ONLY external framing — its body_md
    # is the frame the interview/brief are built on. No recipe → the user's own words alone. No
    # brief-matches-recipe validator exists; the framing sentence is the prompt doing the work.
    recipe_body = state.recipe_id and RecipeStore().body(state.recipe_id)
    if recipe_body:
        r = RecipeStore().get(state.recipe_id)
        sections.append(f"### Recipe: {r['name']} (this project builds FROM this recipe)\n"
                        f"{recipe_body}")

    # SOF-137: the FULL document text, not just its summary, unless it would blow the dedicated
    # inline-context budget above (per-doc AND running total across all documents) — under budget,
    # the agent never has to call a tool just to read what it was already given.
    from software_factory.memory.ingest import estimate_tokens

    doc_rows = _document_context_rows(project_id)
    if doc_rows:
        doc_sections = []
        inline_budget_used = 0
        for row in doc_rows:
            name = row["document_name"]
            if row["status"] != "ready":
                doc_sections.append(f"**{name}** (not ready yet — status: {row['status']})")
                continue
            full_text = MemoryStore().get_document_markdown(row["blob_id"])
            tokens = estimate_tokens(full_text) if full_text else None
            fits = (full_text and tokens <= _INLINE_CONTEXT_PER_DOC_TOKENS
                    and inline_budget_used + tokens <= _INLINE_CONTEXT_TOTAL_TOKENS)
            if fits:
                inline_budget_used += tokens
                doc_sections.append(f"**{name}** (full text below)\n{full_text}")
            else:
                doc_sections.append(
                    f"**{name}** (too large for full text here — use search_document_summaries, "
                    "fetch_document_markdown, or get_from_project_memory for exact passages)\n"
                    f"{row['summary_md'] or '(summary pending)'}")
        summary_text = "\n\n".join(doc_sections)
    else:
        summary_text = "(no documents uploaded yet)"
    sections.append(f"### Documents\n{summary_text}")

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
    """Durable onboarding Concierge over ConversationStore and the LangChain ChatAgent.

    One cached agent is bound per project. Conversation rows preserve user, agent, and real tool
    messages for replay; readiness is not persisted. The response reports factual `handed_off`
    state from the project phase so agent-triggered promotion can drive UI navigation."""

    def __init__(self, users=None, store=None, agent=None, console=None):
        if store is not None:
            self._store = store
        else:
            from software_factory.conversation_store import ConversationStore
            self._store = ConversationStore(users=users)
        self._agent = agent      # injectable ChatAgent (tests); used for every project when set
        self._console = console  # needed to bind the per-project tool belt
        self._users = users      # org profile lookup for the first-turn company context
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
                    first_turn_context = _build_first_turn_context(self._console, project_id, self._users)
            self._agents[project_id] = ChatAgent(
                context="intake", tools=tools, first_turn_context=first_turn_context,
                use_tagged_output=True)
        return self._agents[project_id]

    def history(self, project_id: str) -> list[dict]:
        """The full transcript for a project (oldest first). Empty if none yet."""
        rows = self._store.history(_onboarding_session_id(project_id))
        return [{"role": r["role"], "content": r["input"] or "", "choices": []} for r in rows]

    def _persist_turn(self, session_id: str, project_id: str, sent_len: int,
                      final_messages: list, turn: ConciergeTurn, usage: dict) -> dict:
        """Shared by `turn()` and `turn_stream()` (SOF-154): append everything the run produced —
        tool calls, tool results, the final reply — to the conversation, then return the
        ConciergeTurn dict `{response, suggested_responses, message_id, session_id, handed_off}`.
        `handed_off` is the actual post-turn project phase, not agent-generated readiness state.
        `final_messages` is the full message list (input + produced); `sent_len` is how many of
        those were the input we sent, so only the newly-produced tail gets persisted here."""
        suggested = [sr.model_dump() for sr in turn.suggested_responses]
        new_msgs = final_messages[sent_len:]
        message_id = None
        for m in new_msgs:
            mtype = getattr(m, "type", "")
            if mtype == "ai":
                tool_calls = getattr(m, "tool_calls", None) or []
                if not tool_calls:
                    # The terminal, tag-formatted reply — its RAW content (still carrying <say>/
                    # <option> tags) is never persisted as its own row; the parsed, clean `turn`
                    # below is the one and only row recorded for it.
                    continue
                blocks = [{"type": "tool_use", "id": tc.get("id") or "", "name": tc.get("name") or "",
                          "input": tc.get("args") or {}} for tc in tool_calls]
                message_id = self._store.append(session_id, "agent", blocks, project_id=project_id)
            elif mtype == "tool":
                content_text = m.content if isinstance(m.content, str) else str(m.content)
                message_id = self._store.append(
                    session_id, "tool",
                    [{"type": "tool_result", "tool_use_id": getattr(m, "tool_call_id", "") or "",
                      "is_error": False, "content": [{"type": "text", "text": content_text}]}],
                    project_id=project_id, tool_name=getattr(m, "name", None),
                    tool_call_id=getattr(m, "tool_call_id", None))
        # The user-facing reply — recorded once, with usage on this final row.
        message_id = self._store.append(
            session_id, "agent",
            [{"type": "text", "text": turn.response, "suggested_responses": suggested}],
            project_id=project_id,
            model=usage.get("model"), provider=usage.get("provider"),
            input_tokens=usage.get("input_tokens", 0), output_tokens=usage.get("output_tokens", 0),
            cost_usd=usage.get("cost_usd") or 0.0,
        )
        return {"response": turn.response, "suggested_responses": suggested,
                "message_id": message_id, "session_id": session_id,
                "handed_off": bool(self._console and not self._console.is_draft(project_id))}

    async def turn(self, project_id: str, message: str) -> dict:
        """One Concierge turn. Non-empty message = the user's turn (recorded, agent replies).
        EMPTY message = "the agent opens": no user row is written — the agent simply speaks next
        from its system prompt (which carries the first-turn project context) + history. That is
        the whole interview mechanism: the screen is a chat box, the LLM asks because that's what
        LLMs do. Returns a ConciergeTurn dict: {response, suggested_responses, message_id,
        session_id, handed_off}."""
        text = (message or "").strip()
        session_id = _onboarding_session_id(project_id)
        # Checked BEFORE appending this message: an empty history means this call IS turn one —
        # that's the signal _get_agent uses to bake the first-turn context block into the system
        # prompt (SOF-62). Checking after the append below would always see >=1 row.
        is_first_turn = not self._store.history(session_id)

        if text:
            self._store.append(session_id, "user", [{"type": "text", "text": text}],
                              project_id=project_id)

        from software_factory.conversation_provider import to_provider
        rows = self._store.history(session_id)
        messages = to_provider(rows, "openai")   # OpenRouter (Kimi) also uses the OpenAI shape

        agent = self._get_agent(project_id, is_first_turn=is_first_turn)
        result = await agent.run(messages)
        # SOF-154: ToolStrategy(ConciergeTurn) is off for this agent (use_tagged_output=True) — there
        # is no more `result["structured_response"]`. Reconstruct from the terminal AI message's
        # plain, tag-formatted content instead (see tagged_reply.py) — the ReAct loop only stops once
        # the model emits a no-tool-call message, so that's always the last message in the result.
        final_messages = result.get("messages") or []
        final_content = ""
        if final_messages:
            last = final_messages[-1]
            final_content = last.content if isinstance(getattr(last, "content", None), str) else ""
        turn = parse_tagged_reply(final_content)
        usage = getattr(agent, "last_usage", None) or {}
        return self._persist_turn(session_id, project_id, len(messages), final_messages, turn, usage)

    async def turn_stream(self, project_id: str, message: str):
        """SOF-154: the streaming sibling of `turn()` — same recording/reply contract, but the
        final reply streams token-by-token instead of landing all at once. Yields the SAME
        `working`/`token`/`option` event dicts `ChatAgent.astream_turn()` produces, then a final
        `{"type": "done", **turn()'s return dict}` once persistence completes (mirrors `turn()`'s
        single commit-point — persistence happens AFTER the stream is exhausted, not per-token, so
        the SOF-90 tool-trace ordering invariant is unchanged, just delayed to stream-end) or
        `{"type": "error", "detail": ...}` on a genuine mid-stream failure."""
        text = (message or "").strip()
        session_id = _onboarding_session_id(project_id)
        is_first_turn = not self._store.history(session_id)

        if text:
            self._store.append(session_id, "user", [{"type": "text", "text": text}],
                              project_id=project_id)

        from software_factory.conversation_provider import to_provider
        rows = self._store.history(session_id)
        messages = to_provider(rows, "openai")

        agent = self._get_agent(project_id, is_first_turn=is_first_turn)
        try:
            async for ev in agent.astream_turn(messages):
                yield ev
        except Exception:
            logger.exception("[conversation] turn_stream mid-stream failure, project=%s", project_id)
            yield {"type": "error", "detail": CONCIERGE_SAFE_FALLBACK}
            return

        final_messages = getattr(agent, "last_messages", None) or list(messages)
        turn = getattr(agent, "last_turn", None) or ConciergeTurn(
            response=CONCIERGE_SAFE_FALLBACK, suggested_responses=[])
        usage = getattr(agent, "last_usage", None) or {}
        result = self._persist_turn(session_id, project_id, len(messages), final_messages, turn, usage)
        yield {"type": "done", **result}
