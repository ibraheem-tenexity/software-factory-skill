"""Factory Concierge = a database-backed system prompt + a LangChain agent + real tools.

Everything else lives where it belongs: output DTOs in `data_transfer_objects/chat_agent.py`,
DB prompt resolution and context composition in `default_prompt.py`, model/context constants in
`constants.py`, and the tool belt in `concierge_tools.py`.
"""
from __future__ import annotations

import logging
import os

from langchain.agents import create_agent
from langchain.agents.structured_output import ToolStrategy
from langchain_openai import ChatOpenAI

from software_factory.constants import (
    CONCIERGE_DEFAULT_MODEL,
    CONCIERGE_KIMI_MODEL,
    CONCIERGE_SAFE_FALLBACK,
    OPENROUTER_BASE_URL,
)
from software_factory.data_transfer_objects.chat_agent import ConciergeTurn
from software_factory.default_prompt import build_system_prompt
from software_factory.tagged_reply import TaggedReplyParser

# Model type → chat model class. Kimi (Moonshot) speaks the OpenAI wire protocol, so it's the same
# client class with a different base_url/key — the map is the single place that knowledge lives.
logger = logging.getLogger(__name__)

CHAT_MODEL_CLASSES: dict[str, type[ChatOpenAI]] = {"openai": ChatOpenAI, "kimi": ChatOpenAI}


def _use_kimi() -> bool:
    choice = os.environ.get("SF_CHAT_MODEL", "").strip().lower()
    if choice:
        return "kimi" in choice
    # No explicit choice: use Kimi only if OpenAI isn't configured but OpenRouter is.
    return not os.environ.get("OPENAI_API_KEY") and bool(os.environ.get("OPENROUTER_API_KEY"))


def _concierge_model_id() -> str | None:
    """The CONCIERGE row's `model_id` from the system_agents store, or None if the row/model is
    missing (or the DB can't be reached). Function-local import: SystemAgentStore touches the DB, so
    importing it at module load would couple this module to a live connection."""
    try:
        from software_factory.system_agents import SystemAgentStore
        row = SystemAgentStore().get("CONCIERGE")
        return row["model_id"] if row and row.get("model_id") else None
    except Exception:
        return None


def choose_chat_model() -> ChatOpenAI:
    """Return a ready chat model instance. Prefers the CONCIERGE row's configured `model_id`; falls
    back to the env logic (`_use_kimi()` / CONCIERGE_DEFAULT_MODEL) when the row/model is missing.
    A `moonshotai/…` id routes through Kimi/OpenRouter; any other id is a plain OpenAI model."""
    model_id = _concierge_model_id()
    if model_id:
        if model_id.startswith("moonshotai/"):
            return CHAT_MODEL_CLASSES["kimi"](
                model=model_id,
                base_url=OPENROUTER_BASE_URL,
                api_key=os.environ.get("OPENROUTER_API_KEY", ""),
            )
        return CHAT_MODEL_CLASSES["openai"](model=model_id)
    if _use_kimi():
        return CHAT_MODEL_CLASSES["kimi"](
            model=CONCIERGE_KIMI_MODEL,
            base_url=OPENROUTER_BASE_URL,
            api_key=os.environ.get("OPENROUTER_API_KEY", ""),
        )
    return CHAT_MODEL_CLASSES["openai"](model=os.environ.get("SF_CHAT_MODEL") or CONCIERGE_DEFAULT_MODEL)


def chat_model_label() -> str:
    """The model-id string the Concierge is currently configured to use — a display label for
    Tenexity OS + the model registry. Builds no client; mirrors choose_chat_model()'s selection."""
    model_id = _concierge_model_id()
    if model_id:
        return model_id
    if _use_kimi():
        return CONCIERGE_KIMI_MODEL
    return os.environ.get("SF_CHAT_MODEL") or CONCIERGE_DEFAULT_MODEL


def _extract_usage(messages: list) -> dict:
    """Real token counts from the newest AIMessage carrying `usage_metadata`, priced via the live
    OpenRouter catalog (SOF-57 ledger). cost_usd is None — never a fabricated 0 — when pricing is
    unavailable."""
    model = chat_model_label()
    provider = "openrouter" if "/" in model else "openai"
    for m in reversed(messages):
        um = getattr(m, "usage_metadata", None)
        if um:
            input_tokens = um.get("input_tokens") or 0
            output_tokens = um.get("output_tokens") or 0
            cost = None
            try:
                from software_factory.memory import pricing
                lookup_id = model if provider == "openrouter" else f"openai/{model}"
                price = pricing.openrouter_price(lookup_id, kind="chat")
                if price is not None:
                    cost = input_tokens * price["input"] + output_tokens * price["output"]
            except Exception:
                cost = None
            return {"model": model, "provider": provider, "input_tokens": input_tokens,
                    "output_tokens": output_tokens, "cost_usd": cost}
    return {"model": model, "provider": provider, "input_tokens": 0, "output_tokens": 0,
            "cost_usd": None}


class ChatAgent:
    """One context-parameterized LangChain agent. `_agent` is exactly what
    `create_agent` returns; `run` feeds it the conversation history and returns a ConciergeTurn.

    `context` sets the focus (same identity everywhere). `tools`/`model` are injectable — pass a
    per-project belt from `concierge_tools.build_project_tools`, or a fake model in tests.
    `first_turn_context` (SOF-62) is baked into the system prompt at construction — see
    `default_prompt.build_system_prompt`'s docstring for why this is construction-time, not per-run.
    """

    def __init__(self, context: str = "intake", tools: list | None = None, model=None,
                 first_turn_context: str | None = None, use_tagged_output: bool = False):
        """`use_tagged_output` (SOF-154): drop the forced `ToolStrategy(ConciergeTurn)` structured
        output entirely and let the final turn stream as plain content instead, formatted per the
        `<say>`/`<option>` tag contract (`tagged_reply.py`) the `context`'s prompt framing must
        already instruct — today that's ONLY `default_prompt._CONTEXT_FRAMING["intake"]`. This is a
        construction-time choice (`response_format` is bound once, at `create_agent`), so a caller
        that wants the old one-shot structured-JSON behavior (the dock) simply never passes it."""
        self.last_usage: dict = {}   # set by run()/astream_turn(): {model, provider, tokens, cost_usd}
        self._use_tagged_output = use_tagged_output
        kwargs: dict = {}
        if not use_tagged_output:
            kwargs["response_format"] = ToolStrategy(ConciergeTurn)
        self._agent = create_agent(
            model or choose_chat_model(),
            tools or [],
            system_prompt=build_system_prompt(context, first_turn_context),
            **kwargs,
        )

    async def run(self, messages: list) -> dict:
        """Run the agent over the history array and return the RAW result — `messages` (everything
        the run produced: tool calls, tool results, replies) plus `structured_response`. No "turn"
        abstraction: the caller appends the produced messages to its array and that's it.
        One retry, then a safe fallback — a bad generation never 500s the request.
        Side effect: `self.last_usage` carries this run's real model/token/cost usage."""
        for attempt in range(2):
            try:
                result = await self._agent.ainvoke({"messages": messages})
                self.last_usage = _extract_usage(result.get("messages") or [])
                return result
            except Exception:
                logger.exception("[chat_agent] run attempt %s failed", attempt + 1)
                continue
        return {"messages": [],
                "structured_response": ConciergeTurn(response=CONCIERGE_SAFE_FALLBACK, suggested_responses=[])}

    async def astream_turn(self, messages: list):
        """SOF-154: stream the final tagged reply. Requires `use_tagged_output=True` at
        construction (there is no forced structured_response to stream field-by-field otherwise).

        Yields event dicts as they occur:
          - `{"type": "working"}` — the model is mid-tool-call this turn (real tool_call_chunks
            seen); emitted once per model turn that calls a tool, never carries prose.
          - `{"type": "token", "text": ...}` / `{"type": "option", "option_type", "text"}` — from
            `TaggedReplyParser`, fed the final turn's plain-content deltas.

        After the stream is exhausted, sets `self.last_turn` (the reconstructed `ConciergeTurn`),
        `self.last_messages` (the full message list — same shape `run()`'s `result["messages"]`
        carries, for the caller's existing persistence walk), and `self.last_usage`.

        Retry semantics mirror `run()`: one silent retry, but ONLY while `started` is still False
        (nothing has reached the caller yet) — once a real `working`/`token`/`option` event has been
        yielded, a subsequent failure is NOT retried here. It propagates as a raised exception so the
        caller (already mid-stream to its own client) surfaces its own error event instead of this
        method silently redoing work the user has partially seen."""
        if not self._use_tagged_output:
            raise RuntimeError("astream_turn requires ChatAgent(use_tagged_output=True)")
        for attempt in range(2):
            parser = TaggedReplyParser()
            started = False
            in_tool_call_streak = False
            result_messages = list(messages)
            try:
                async for ev in self._agent.astream_events({"messages": messages}, version="v2"):
                    name = ev.get("event")
                    if name == "on_chat_model_stream":
                        chunk = ev["data"]["chunk"]
                        if getattr(chunk, "tool_call_chunks", None):
                            if not in_tool_call_streak:
                                in_tool_call_streak = True
                                started = True
                                yield {"type": "working"}
                            continue
                        in_tool_call_streak = False
                        text = chunk.content if isinstance(chunk.content, str) else ""
                        if text:
                            events = parser.feed(text)
                            if events:
                                started = True
                            for out in events:
                                yield out
                    elif name == "on_chain_end" and ev.get("name") == "LangGraph":
                        output = ev.get("data", {}).get("output") or {}
                        if isinstance(output, dict) and output.get("messages"):
                            result_messages = output["messages"]
            except Exception:
                if started:
                    raise
                logger.exception("[chat_agent] astream_turn attempt %s failed", attempt + 1)
                continue
            for out in parser.finish():
                yield out
            self.last_messages = result_messages
            self.last_usage = _extract_usage(result_messages)
            self.last_turn = parser.reconstruct()
            return
        self.last_messages = []
        self.last_usage = {}
        self.last_turn = ConciergeTurn(response=CONCIERGE_SAFE_FALLBACK, suggested_responses=[])
