"""SOF-27: charge console-side ingestion spend (embedding/summarization/extraction) to the
project's ledger, so the poller's existing stop-at-ceiling budget brake counts it.

Ingestion never runs as a stage process, so its cost never appears in project.log — the source
Console._cost() parses. Recording it into ProjectState.ingestion_spent_usd (a separate
accumulator from spent_usd) makes it visible to Console._project_spend(), which both
Console.enforce_budget() (run unconditionally every poller tick, not gated on a live stage
process) and Console._launch_stage()'s per-run ceiling refusal already read.
"""
from __future__ import annotations

from ..budget import PRICES
from ..log import get_logger

logger = get_logger(__name__)


def _cost_of(model: str, input_tokens: int, output_tokens: int) -> float:
    """Fallback USD cost from budget.PRICES when the caller has no authoritative cost from the
    provider. KeyError on an unpriced model is intentional (mirrors Budget.cost_of) — an
    un-priced call must never bill as free. Add the model's rate to budget.PRICES first."""
    rate = PRICES[model]
    return input_tokens * rate["input"] + output_tokens * rate["output"]


def record_ingestion_cost(
    console, project_id: str, *, model: str, provider: str,
    input_tokens: int = 0, output_tokens: int = 0, usd: float | None = None,
) -> float:
    """Record one ingestion LLM/embedding call's cost against `project_id`'s ledger.

    Pass an authoritative `usd` when the provider's own response reports cost (preferred —
    mirrors streamlog.py's "authoritative when the API reports it" philosophy); otherwise it's
    computed from `budget.PRICES[model]`. Returns the recorded delta (USD).

    Also emits a Langfuse generation span when Langfuse is configured (env-gated, no-op
    otherwise) — this is a plain manual span, not the OpenAI-Agents auto-instrumentor in
    langfuse_tracing.py, because ingestion calls are raw `openai` SDK calls to OpenRouter, not
    Agents-SDK runs.
    """
    delta = usd if usd is not None else _cost_of(model, input_tokens, output_tokens)
    state = console._load_state(project_id)
    state.ingestion_spent_usd = (state.ingestion_spent_usd or 0.0) + delta
    state.save()
    _emit_langfuse_span(project_id, model, provider, input_tokens, output_tokens, delta)
    return delta


def _emit_langfuse_span(project_id: str, model: str, provider: str,
                        input_tokens: int, output_tokens: int, usd: float) -> None:
    from .. import langfuse_tracing
    if not langfuse_tracing.enabled():
        return
    try:
        from langfuse import get_client
        client = get_client()
        with client.start_as_current_generation(
            name="memory-ingestion",
            model=model,
            metadata={"project_id": project_id, "provider": provider},
            usage_details={"input": input_tokens, "output": output_tokens},
            cost_details={"total": usd},
        ):
            pass
    except Exception:
        logger.debug("[memory.cost] Langfuse span failed — ingestion cost still recorded",
                     exc_info=True)
