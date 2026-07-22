"""SOF-32: live OpenRouter pricing lookup — real published $/token, never fabricated.

Ingestion cost (SOF-27/memory/cost.py) must reflect what a model call actually cost. Rather
than hardcode a $/token figure (which drifts as providers change pricing) or guess, this module
fetches OpenRouter's own public, unauthenticated pricing catalog at call time. Chat/completion
models live in GET /api/v1/models; embedding models are NOT listed there — they live in a
separate GET /api/v1/embeddings/models (confirmed by hitting both live). Neither call needs an
API key and neither costs money — it's metadata, not a model invocation.

Cached in-process only (never persisted to disk/DB) so a long-running console process doesn't
re-fetch on every ingest call, but also never serves stale pricing across a restart.
"""
from __future__ import annotations

import httpx

from ..log import get_logger

logger = get_logger(__name__)

_MODELS_URL = "https://openrouter.ai/api/v1/models"
_EMBEDDING_MODELS_URL = "https://openrouter.ai/api/v1/embeddings/models"

_cache: dict[str, dict] = {}


def _fetch_catalog(url: str) -> list[dict]:
    resp = httpx.get(url, timeout=15)
    resp.raise_for_status()
    return resp.json().get("data", [])


def openrouter_price(model: str, kind: str = "chat") -> dict | None:
    """{"input": $/token, "output": $/token} for `model`, or None if it can't be determined
    (network failure, or the model isn't in the catalog `kind` implies). `kind` is "chat" for
    completion/summarization models (GET /models) or "embedding" for embedding models (GET
    /embeddings/models) — they're different catalogs on OpenRouter, not different fields of
    one. Never raises — a pricing-lookup failure must not crash the ingestion it's costing."""
    cache_key = f"{kind}:{model}"
    if cache_key in _cache:
        return _cache[cache_key]
    url = _EMBEDDING_MODELS_URL if kind == "embedding" else _MODELS_URL
    try:
        catalog = _fetch_catalog(url)
    except Exception:
        logger.exception("[pricing] OpenRouter %s catalog fetch failed for model %s — "
                         "pricing unavailable, caller falls back", kind, model)
        return None
    for entry in catalog:
        if entry.get("id") == model:
            pricing = entry.get("pricing") or {}
            try:
                price = {"input": float(pricing.get("prompt", 0) or 0),
                        "output": float(pricing.get("completion", 0) or 0)}
            except (TypeError, ValueError):
                logger.exception("[pricing] OpenRouter returned unparseable pricing for model %s "
                                 "(%s) — pricing unavailable, caller falls back", model, kind)
                return None
            _cache[cache_key] = price
            return price
    return None
