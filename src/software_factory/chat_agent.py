"""Factory Concierge = system prompt + a LangChain agent + real tools, and nothing else
(concierge-agent-spec.md §2). https://docs.langchain.com/oss/python/langchain/agents

Everything else lives where it belongs: the output-contract data classes in
`data_transfer_objects/concierge.py`, the prompts + operator-override cache in `default_prompt.py`,
the model/context constants in `constants.py`, and the tool belt in `concierge_tools.py`.
"""
from __future__ import annotations

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

# Model type → chat model class. Kimi (Moonshot) speaks the OpenAI wire protocol, so it's the same
# client class with a different base_url/key — the map is the single place that knowledge lives.
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


class ChatAgent:
    """One context-parameterized LangChain agent (spec §2/§4.6). `_agent` is exactly what
    `create_agent` returns; `run` feeds it the conversation history and returns a ConciergeTurn.

    `context` sets the focus (same identity everywhere). `tools`/`model` are injectable — pass a
    per-project belt from `concierge_tools.build_project_tools`, or a fake model in tests.
    """

    def __init__(self, context: str = "intake", tools: list | None = None, model=None):
        self._agent = create_agent(
            model or choose_chat_model(),
            tools or [],
            system_prompt=build_system_prompt(context),
            response_format=ToolStrategy(ConciergeTurn),
        )

    async def run(self, messages: list) -> ConciergeTurn:
        """Run the agent over the conversation history and return the terminal ConciergeTurn.
        One retry, then a safe fallback — a bad generation never 500s the turn (spec §3)."""
        for _ in range(2):
            try:
                result = await self._agent.ainvoke({"messages": messages})
                return result["structured_response"]
            except Exception:
                continue
        return ConciergeTurn(response=CONCIERGE_SAFE_FALLBACK, suggested_responses=[])
