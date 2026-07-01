"""Langfuse env-gate check for the concierge chat agent.

SOF-35: `setup_langfuse()` (which instrumented the OpenAI Agents SDK's `Agent`/`Runner` via
`OpenAIAgentsInstrumentor` for the now-removed `ChatAgentRunner`) is removed — it has no caller
left and no equivalent for the OpenAI Agents SDK primitives it targeted once they're gone. The
LangChain rebuild (T2.1) will need its own tracing setup (e.g. an OpenInference LangChain
instrumentor) if Langfuse tracing is still wanted for the new agent — that's new code, not a
port of this.

`enabled()` survives: `memory/cost.py` still uses it to gate ingestion cost recording. SOF-46:
`select_chat_model()` (chat_agent.py), this module's other caller and the last importer of
`agents`/`openinference-instrumentation-openai-agents` anywhere in this repo, is removed —
superseded by `_build_chat_model()`, which never needed Langfuse-gated tracing-disable logic
(the OpenAI Agents SDK's own tracing, which this was working around, doesn't exist on the
LangChain path at all).
"""
from __future__ import annotations

import os


def enabled() -> bool:
    return bool(os.environ.get("LANGFUSE_PUBLIC_KEY") and os.environ.get("LANGFUSE_SECRET_KEY"))
