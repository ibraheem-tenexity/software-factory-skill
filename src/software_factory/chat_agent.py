"""Factory Concierge — model selection, system prompt, and the LangChain agent (T2.1/T2.2).

SOF-35: the OpenAI Agents SDK runtime (`Agent`/`Runner`) and its 14 tools (`make_tools`) are
removed — they didn't work reliably and were not being fixed (see
docs/project-memory-concierge/concierge-agent-spec.md §1). Model selection, the system prompt,
and its operator-override cache are unchanged and are reused by `ConciergeAgent` below.

SOF-39/40: `ConciergeAgent` is the replacement — one context-parameterized LangChain agent
(system prompt + empty/extensible tool belt) whose terminal turn is coerced to `ConciergeTurn`.
Both surfaces now delegate to it: `/converse` (onboarding) via `DbConversation`
(`services/conversation.py`), `/api/chat` (the persistent in-project dock) via `ChatDockRunner`
below, assigned to `state._chat_runner`. Persistence stays where it was pre-rip-out —
`DbConversation` uses `ConversationStore`, `ChatDockRunner` still uses `chat.jsonl`/`ChatStore`
(folding `/api/chat` onto the conversation table is T1.4, a deliberate later follow-up, not
pulled forward here). The tool belt is empty for both, so neither surface can yet take actions
(hand off, request creds, etc.) via chat — that returns once real tools are bound (spec §5).

Uses `langchain.agents.create_agent` (LangChain/LangGraph 1.x) — NOT the deprecated
`langgraph.prebuilt.create_react_agent` the original design note assumed; the installed version
in this repo warns `create_react_agent` is deprecated in favor of `create_agent`, which has an
equivalent `response_format=<PydanticModel>` structured-output parameter and an empty-`tools`
no-loop mode, so there's no capability gap — just a newer import path.
"""
from __future__ import annotations

import asyncio
import json
import os
import time
from typing import Callable, Literal

from pydantic import BaseModel, Field, ValidationError

from software_factory.chat_store import ChatMessage
from software_factory.console import Console


_DEFAULT_OPENAI_CHAT_MODEL = "gpt-5.4"   # concierge default (was gpt-4o); SF_CHAT_MODEL overrides it
_KIMI_MODEL = "moonshotai/kimi-k2.7-code"
_CONCIERGE_PROMPT_CACHE_TTL_SECONDS = 60.0


def _use_kimi(choice: str) -> bool:
    return choice == "kimi" or (
        not choice and not os.environ.get("OPENAI_API_KEY") and os.environ.get("OPENROUTER_API_KEY")
    )


def select_chat_model():
    """Concierge model: gpt-5.4 (OpenAI) or Kimi K2.7 Code via OpenRouter's OpenAI-compatible API.

    SF_CHAT_MODEL=kimi forces Kimi; unset picks gpt-5.4 when OPENAI_API_KEY exists, else Kimi when only
    OPENROUTER_API_KEY does. Any OTHER SF_CHAT_MODEL value is passed through verbatim as the OpenAI
    model id — so it's the no-redeploy rollback lever for the OpenAI model too (e.g. set it back to a
    known-good id if gpt-5.4 is ever rejected), alongside the Kimi rollback."""
    choice = os.environ.get("SF_CHAT_MODEL", "").strip().lower()
    if _use_kimi(choice):
        from agents import OpenAIChatCompletionsModel, set_tracing_disabled
        from openai import AsyncOpenAI

        from . import langfuse_tracing
        if not langfuse_tracing.enabled():
            # Without Langfuse the SDK's default tracing would try (and fail) to reach OpenAI.
            # With Langfuse on, the OpenInference instrumentor replaces that exporter, so we
            # KEEP tracing enabled to capture the Kimi path in Langfuse too.
            set_tracing_disabled(True)
        client = AsyncOpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=os.environ.get("OPENROUTER_API_KEY", ""),
        )
        return OpenAIChatCompletionsModel(model=_KIMI_MODEL, openai_client=client)
    return choice or _DEFAULT_OPENAI_CHAT_MODEL


def chat_model_label() -> str:
    """Display id of the live concierge model (no client constructed) — for the OS Agents card."""
    choice = os.environ.get("SF_CHAT_MODEL", "").strip().lower()
    if _use_kimi(choice):
        return _KIMI_MODEL
    return choice or _DEFAULT_OPENAI_CHAT_MODEL


CONCIERGE_INSTRUCTIONS = """\
You are the Factory Concierge for the Software Factory onboarding. You guide the user through a short \
intake — their company (first-time users only) and THIS project — PERSISTING each answer as you go \
with your tools, then hand off to the build factory. Ask EXACTLY ONE question per turn and WAIT for \
the answer before moving on (never stack two questions in one message).

## First, who am I talking to
Call **get_company_profile** at the start. If it returns an org, this is a RETURNING user — their \
company context is on file and REUSED; do NOT re-ask it, go straight to the project. If it returns \
null, this is a FIRST-TIME user — set up the company first, then the project.

## Company setup (first-time only)
Gather and persist with **set_company_profile** (industry + what the company does, company name, \
headcount, annual revenue, the user's role). Optionally call **set_connected_systems** with the ids \
of systems they use (epicor | sap | netsuite | qb | sf | site) — optional, it lets the factory pull \
real SKUs/customers/pricing. One question per turn; persist as each answer comes in.

## The project (always)
- Project name + what they're building (the outcome/goal) → **set_project_basics**.
- Which parts of the business it touches (the scope of work) → **set_project_scope**.
- Materials: a walkthrough video or documents are the highest-signal input. Files the user attaches \
  arrive with their message and are saved automatically — acknowledge them with \
  **attach_project_materials**. If a specific high-value material is missing, ask for it with \
  **request_materials**.

## Persisting + proceeding
Persist every answer immediately via the matching set_* tool — never just hold it in the chat. Use \
**get_intake_state** to see what's captured and **validate_intake_complete** to gauge readiness. The \
USER decides when to proceed and the on-screen checklist owns completion, so don't badger — when they \
are ready (or say "just build it"), confirm in one short line and call **hand_off_to_factory**, which \
promotes the draft into a real run and launches the build.

## After handoff
Stay on. Use **check_status** to report progress naturally; **request_dep_input** when the build needs \
credentials (NEVER ask the user to paste tokens as chat text); **get_result** to share the deployment \
URL(s) when it's done — a project may ship more than one deliverable.

## Style
Concise — 1-3 sentences per turn, ONE question, specific not generic. A short "got it — <next>" is ideal.
"""


class _ConciergePromptCache:
    def __init__(self, default_prompt: str, ttl_seconds: float,
                 clock: Callable[[], float] = time.monotonic):
        self._default_prompt = default_prompt
        self._ttl_seconds = ttl_seconds
        self._clock = clock
        self._prompt = default_prompt
        self._expires_at = 0.0

    def get(self) -> str:
        now = self._clock()
        if now < self._expires_at:
            return self._prompt
        try:
            from software_factory.agent_prompts import PromptStore, override_key
            row = PromptStore().get(override_key("CONCIERGE"))
            self._prompt = row["prompt"] if row and row.get("prompt") else self._default_prompt
        except Exception:
            # Keep the last known good prompt; if none has loaded, that is the code default.
            pass
        self._expires_at = now + self._ttl_seconds
        return self._prompt

    def reset(self) -> None:
        self._prompt = self._default_prompt
        self._expires_at = 0.0


_CONCIERGE_PROMPT_CACHE = _ConciergePromptCache(
    CONCIERGE_INSTRUCTIONS, _CONCIERGE_PROMPT_CACHE_TTL_SECONDS)


def resolve_concierge_instructions() -> str:
    """Effective concierge prompt: DB override with a short cache, default constant on miss/error."""
    return _CONCIERGE_PROMPT_CACHE.get()


def reset_concierge_prompt_cache() -> None:
    """Test/maintenance hook: force the next prompt resolve to hit PromptStore."""
    _CONCIERGE_PROMPT_CACHE.reset()


def check_and_notify(console: Console, project_id: str, prev_stage: int = 0) -> list[ChatMessage]:
    """Check pipeline status and generate notification messages for stage transitions.

    Extracted from the removed ChatAgentRunner (SOF-35): pure Console-status logic with no
    dependency on the agent runtime, so it survives the OpenAI-Agents-SDK rip-out unchanged."""
    status = console.status(project_id)
    msgs: list[ChatMessage] = []
    now = time.time()

    if status.get("stage1_done") and prev_stage < 2:
        msgs.append(ChatMessage(
            role="system",
            content="Research complete — Design & Architecture stage starting.",
            msg_type="status_update", ts=now,
            metadata={"project_id": project_id, "stage": 2},
        ))

    if status.get("stage2_done") and prev_stage < 3:
        deps = status.get("deps_required", [])
        if deps and not status.get("deps_satisfied"):
            msgs.append(ChatMessage(
                role="assistant",
                content="The architecture requires these credentials to proceed. "
                        "Please provide them in the secure fields below.",
                msg_type="dep_request", ts=now,
                metadata={"project_id": project_id, "dep_names": deps},
            ))
        else:
            msgs.append(ChatMessage(
                role="system",
                content="Design complete — Build stage starting.",
                msg_type="status_update", ts=now,
                metadata={"project_id": project_id, "stage": 3},
            ))

    if status.get("done"):
        url = status.get("deploy_url", "")
        spent = status.get("spent_usd", 0)
        msgs.append(ChatMessage(
            role="assistant",
            content=f"Build complete! Deployed to {url} — total cost ${spent:.2f}.",
            msg_type="complete", ts=now,
            metadata={"project_id": project_id, "url": url, "spent_usd": spent},
        ))

    return msgs


# ── T2.2: the structured-output contract (concierge-agent-spec.md §3) ─────────────────────────
# This is what drives the UI: suggested_responses empty => a plain-text turn; non-empty => the
# FE renders selectable options, `type` deciding radio (single) vs checkbox (multi). No `choices`/
# `done` -- the shape IS the state.

class SuggestedResponse(BaseModel):
    response: str = Field(min_length=1)
    type: Literal["single select", "multi select"]


class ConciergeTurn(BaseModel):
    response: str = Field(min_length=1)   # required, non-empty -- the assistant's utterance
    suggested_responses: list[SuggestedResponse] = Field(default_factory=list)


# A bad generation must never 500 the turn (spec §3) -- this is what ConciergeAgent.run returns
# after one retry still fails to produce a valid ConciergeTurn.
_SAFE_FALLBACK_RESPONSE = "Sorry, I didn't quite catch that -- could you say it again?"


# ── T2.1: one context-parameterized LangChain agent ────────────────────────────────────────────
# Product spec Principle 2 / §4.6: ONE assistant, same identity/voice everywhere; only its focus
# (`context`) changes. Deliberately minimal -- system prompt + agent loop + a tool belt that
# starts empty. No multi-agent graphs, no chains-of-chains.
CONCIERGE_CONTEXTS = ("intake", "overview", "build", "docs", "ingesting")


def _build_chat_model():
    """LangChain chat model honoring the SAME SF_CHAT_MODEL env selection as select_chat_model()
    (OpenAI gpt-5.4 default, or Kimi K2.7 Code via OpenRouter's OpenAI-compatible endpoint) -- the
    model choice logic is identical, only the returned object type differs (a LangChain
    BaseChatModel here, vs the OpenAI-Agents-SDK model wrapper select_chat_model() returns)."""
    from langchain_openai import ChatOpenAI

    choice = os.environ.get("SF_CHAT_MODEL", "").strip().lower()
    if _use_kimi(choice):
        return ChatOpenAI(
            model=_KIMI_MODEL,
            base_url="https://openrouter.ai/api/v1",
            api_key=os.environ.get("OPENROUTER_API_KEY", ""),
        )
    return ChatOpenAI(model=choice or _DEFAULT_OPENAI_CHAT_MODEL)


class ConciergeAgent:
    """One LangChain agent, reused across all five contexts (spec §4.6) -- only the system
    prompt's focus changes, never the identity/voice. Tool belt starts empty (spec §5); real
    tools are bound later, one at a time, only when backed by a working service.

    `model`/`tools` are injectable for testing (a fake chat model, no live API calls)."""

    def __init__(self, model=None, tools=None):
        self._model = model if model is not None else _build_chat_model()
        self._tools = list(tools) if tools else []

    def _compiled_agent_for(self, context: str):
        if context not in CONCIERGE_CONTEXTS:
            raise ValueError(f"unknown concierge context: {context!r} (expected one of {CONCIERGE_CONTEXTS})")
        from langchain.agents import create_agent
        from langchain.agents.structured_output import ToolStrategy
        system_prompt = f"{resolve_concierge_instructions()}\n\n## Current focus: {context}"
        # SOF-58: a bare Pydantic response_format resolves to LangChain's native ProviderStrategy
        # for OpenAI models -- confirmed live, gpt-5.4 under that strategy returns the SAME valid
        # JSON object concatenated 2-3x in one completion, which chokes create_agent's own
        # json.loads("Extra data: line 2 column 1...") on effectively every turn. ToolStrategy
        # forces structured output through a function-call argument (OpenAI's own tool-calling
        # schema validation) instead of raw native JSON text, sidestepping the triplication.
        return create_agent(self._model, self._tools, system_prompt=system_prompt,
                            response_format=ToolStrategy(ConciergeTurn))

    def run(self, context: str, messages: list) -> ConciergeTurn:
        """`messages`: a LangChain-shaped message list (the conversation-store's to_provider()
        output, T1.2). Returns a validated ConciergeTurn -- never raises on a structured-output
        failure: retries once, then falls back to a safe {response, suggested_responses: []}
        rather than 500ing the turn (spec §3).

        EXCEPTION SCOPE (confirmed against the installed LangChain 1.3.11 source, not assumed):
        `langchain.agents.create_agent`'s structured-output coercion raises
        `langchain.agents.structured_output.StructuredOutputError` (base class covering both its
        `StructuredOutputValidationError` and `MultipleStructuredOutputsError` subclasses) when the
        model's tool-calling strategy produces a malformed/ambiguous structured response. Caught
        alongside pydantic's own ValidationError (a direct `ConciergeTurn.model_validate` failure)
        and this method's own "no structured_response" ValueError guard."""
        from langchain.agents.structured_output import StructuredOutputError
        agent = self._compiled_agent_for(context)
        for _attempt in range(2):
            try:
                result = agent.invoke({"messages": messages})
                structured = result.get("structured_response")
                if isinstance(structured, ConciergeTurn):
                    return structured
                if structured is None:
                    raise ValueError("agent returned no structured_response")
                return ConciergeTurn.model_validate(structured)
            except (ValidationError, ValueError, StructuredOutputError):
                continue
        return ConciergeTurn(response=_SAFE_FALLBACK_RESPONSE, suggested_responses=[])


# Phase -> context inference for the persistent dock (no per-screen signal exists in ChatIn
# today, so this is the coarsest reasonable proxy for "what is the user looking at"). Operator
# call: infer from phase, "build" as the fallback for anything not explicitly mapped (draft/
# unknown/pre-build phases included) — refine later if a real per-screen signal is threaded in.
_PHASE_CONTEXT = {"done": "overview"}


def _context_for_project(console: Console, project_id: str) -> str:
    try:
        phase = (console.status(project_id).get("phase") or "").lower()
    except Exception:
        return "build"
    return _PHASE_CONTEXT.get(phase, "build")


class ChatDockRunner:
    """Serves `/api/chat` (the persistent, in-project concierge dock) via `ConciergeAgent` — the
    restored replacement for the removed OpenAI-Agents-SDK `ChatAgentRunner` (SOF-35). Only
    `handle_message_streamed` is implemented; the route (`console/routers/chat.py`) never called
    the old class's non-streaming `handle_message`.

    Persistence stays on `chat.jsonl`/`ChatStore` — the route itself appends after streaming
    completes, unchanged from the pre-rip-out contract. Folding `/api/chat` onto the conversation
    table is T1.4, a deliberate later follow-up, not pulled forward here.

    History is kept in an in-memory per-process dict, matching the removed `ChatAgentRunner`'s
    own behavior (a restart loses in-flight context same as before — not a new regression).

    Tool belt is empty (spec §5), so this cannot yet hand off / request creds / take any action
    via chat — pure conversation, same as `DbConversation`, until real tools are bound later."""

    def __init__(self, console: Console, users=None, agent=None):
        self._console = console
        self._agent = agent
        self._conversations: dict[str, list] = {}

    def _get_agent(self):
        if self._agent is None:
            self._agent = ConciergeAgent()
        return self._agent

    async def handle_message_streamed(
        self, project_id: str | None, user_msg: str,
        files: list, images: list,
        runtime: str = "", planning_model: str = "",
        impl_model: str = "", project_name: str = "",
        gated: bool = False, owner: str = "", role: str = "member",
    ):
        """Async generator yielding NDJSON lines. `ConciergeAgent.run()` is a single blocking call
        (no real token-by-token stream), so this yields exactly one `done` event with the full
        reply rather than fabricating `delta` events — an honest simplification, not a silent
        pretense of streaming that isn't happening."""
        content = user_msg or ""
        if files:
            content += "\n" + "\n".join(f"[Attached file: {f.get('name', 'file')}]" for f in files)
        if images:
            content += "\n" + "\n".join(f"[Attached image: {i.get('name', 'image')}]" for i in images)

        conv_key = project_id or "__new__"
        history = self._conversations.setdefault(conv_key, [])
        history.append({"role": "user", "content": content})

        context = _context_for_project(self._console, project_id) if project_id else "build"
        try:
            turn = await asyncio.to_thread(self._get_agent().run, context, list(history))
        except Exception as e:
            yield json.dumps({"type": "error", "detail": str(e)}) + "\n"
            return

        history.append({"role": "assistant", "content": turn.response})

        now = time.time()
        messages = [{"role": "assistant", "content": turn.response, "msg_type": "text",
                    "ts": now, "metadata": {}}]
        yield json.dumps({"type": "done", "project_id": project_id, "messages": messages}) + "\n"
