"""SOF-29: dense embeddings via OpenRouter (T3.1's embedding layer).

Reuses the `openai` SDK already in the dependency tree (langchain-openai pulls it in
transitively — SOF-46 dropped the openai-agents package that used to; `pip show
langchain-openai` confirms `openai` is still one of its own dependencies) pointed at
OpenRouter's OpenAI-compatible embeddings endpoint. Dense only —
OpenRouter's embeddings API never returns a sparse/learned-sparse vector (see
docs/project-memory-concierge/project-memory-stack-2026.md); the sparse/keyword channel is
Postgres tsvector, generated at the DB level (chunk.fts), not here.
"""
from __future__ import annotations

import os
import time
from typing import Callable

DEFAULT_MODEL = "google/gemini-embedding-2"
DIMENSIONS = 1024
_OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

# OpenRouter/most embedding providers cap items per request well under typical corpus sizes —
# split larger inputs into sub-batches rather than assume the provider accepts an unbounded list.
_BATCH_SIZE = 96
_MAX_RETRIES = 3
_BACKOFF_SECONDS = 2.0


def _default_client():
    from openai import OpenAI
    return OpenAI(base_url=_OPENROUTER_BASE_URL, api_key=os.environ["OPENROUTER_API_KEY"])


def embed_texts(
    texts: list[str], *, model: str = DEFAULT_MODEL, client=None,
    sleep: Callable[[float], None] = time.sleep,
) -> list[list[float]]:
    """Dense embedding for each string in `texts`, in order. Returns one `Vector(1024)`-shaped
    list[float] per input. Empty input returns []. `client` is injectable for tests (a stub
    embedder — see tests/unit/test_memory_embed.py) so this never makes a live network call
    unless the caller wants it to.
    """
    if not texts:
        return []
    client = client or _default_client()
    out: list[list[float]] = []
    for start in range(0, len(texts), _BATCH_SIZE):
        batch = texts[start:start + _BATCH_SIZE]
        out.extend(_embed_batch_with_retry(client, model, batch, sleep))
    return out


def _embed_batch_with_retry(client, model: str, batch: list[str],
                            sleep: Callable[[float], None]) -> list[list[float]]:
    from openai import RateLimitError

    last_err: Exception | None = None
    for attempt in range(_MAX_RETRIES):
        try:
            resp = client.embeddings.create(model=model, input=batch)
            # Provider returns items possibly out of request order; `index` is authoritative.
            ordered = sorted(resp.data, key=lambda d: d.index)
            return [list(item.embedding) for item in ordered]
        except RateLimitError as exc:
            last_err = exc
            sleep(_BACKOFF_SECONDS * (2 ** attempt))
    raise last_err
