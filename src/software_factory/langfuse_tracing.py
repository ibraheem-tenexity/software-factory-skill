"""Langfuse env-gate check for the concierge chat agent.

SOF-35: `setup_langfuse()` (which instrumented the OpenAI Agents SDK's `Agent`/`Runner` via
`OpenAIAgentsInstrumentor` for the now-removed `ChatAgentRunner`) is removed — it has no caller
left and no equivalent for the OpenAI Agents SDK primitives it targeted once they're gone. The
LangChain rebuild (T2.1) will need its own tracing setup (e.g. an OpenInference LangChain
instrumentor) if Langfuse tracing is still wanted for the new agent — that's new code, not a
port of this.

`enabled()` survives: `select_chat_model()` (chat_agent.py) still uses it to decide whether to
disable the OpenAI Agents SDK's own tracing for the Kimi/OpenRouter model-selection path, which
is unrelated to the concierge's tool-calling framework.
"""
from __future__ import annotations

import os


def enabled() -> bool:
    return bool(os.environ.get("LANGFUSE_PUBLIC_KEY") and os.environ.get("LANGFUSE_SECRET_KEY"))
