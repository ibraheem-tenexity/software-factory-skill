"""Langfuse tracing for the concierge chat agent (OpenAI Agents SDK).

Wires the OpenInference instrumentor → Langfuse over OpenTelemetry, per
https://langfuse.com/integrations/frameworks/openai-agents. Every concierge turn
(Agent run, tool calls, model generations) is exported as a Langfuse trace.

Env-gated like the old exporter: a no-op unless LANGFUSE_PUBLIC_KEY +
LANGFUSE_SECRET_KEY are set, so local/test runs and Langfuse-less deployments are
unaffected. Host comes from LANGFUSE_BASE_URL (or LANGFUSE_HOST), read by the
Langfuse client itself.

This is the LIVE-agent counterpart to the removed log-parsing exporter (#103) —
different surface (the running concierge, not build-stage project.log) and
different mechanism (OpenTelemetry spans, not manual ingestion POSTs).
"""
from __future__ import annotations

import os

from .log import get_logger

logger = get_logger(__name__)

_instrumented = False


def enabled() -> bool:
    return bool(os.environ.get("LANGFUSE_PUBLIC_KEY") and os.environ.get("LANGFUSE_SECRET_KEY"))


def setup_langfuse():
    """Instrument the OpenAI Agents SDK so concierge runs export to Langfuse.

    Returns the Langfuse client (for an explicit flush) or None when disabled /
    the packages are absent. Idempotent — instrumentation is applied once even if
    a ChatAgentRunner is constructed per request.

    OpenAIAgentsInstrumentor().instrument() installs its OpenTelemetry processor as
    the SDK's EXCLUSIVE trace processor, which replaces the default OpenAI backend
    exporter — so spans go only to Langfuse and nothing tries to reach OpenAI's
    tracing endpoint (the reason the Kimi/OpenRouter path otherwise disables
    tracing; see select_chat_model in chat_agent.py).
    """
    global _instrumented
    if not enabled():
        return None
    try:
        from langfuse import get_client
        from openinference.instrumentation.openai_agents import OpenAIAgentsInstrumentor
    except ImportError:
        logger.warning("[langfuse] keys set but tracing packages are missing — concierge tracing off")
        return None
    client = get_client()  # reads LANGFUSE_* env; sets up the OTel exporter to Langfuse
    if not _instrumented:
        OpenAIAgentsInstrumentor().instrument()
        _instrumented = True
        host = os.environ.get("LANGFUSE_BASE_URL") or os.environ.get("LANGFUSE_HOST") \
            or "https://cloud.langfuse.com"
        logger.info("[langfuse] concierge tracing instrumented → %s", host)
    return client
