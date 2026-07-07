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

import logging
import os
import time
from typing import Callable

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "google/gemini-embedding-2"
# SOF-84: this model's native output is 3072-dim, not 1024 — confirmed live. Nothing here
# truncates it (no `dimensions=` param passed), so DIMENSIONS must track the real output shape;
# the pgvector columns are `halfvec(3072)` to match (plain `vector` caps HNSW indexing at 2000).
DIMENSIONS = 3072
_OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

# OpenRouter/most embedding providers cap items per request well under typical corpus sizes —
# split larger inputs into sub-batches rather than assume the provider accepts an unbounded list.
_BATCH_SIZE = 96
_MAX_RETRIES = 3
_BACKOFF_SECONDS = 2.0


class EmbeddingRetriesExhausted(RuntimeError):
    """OpenRouter kept returning empty embedding data after all retries (SOF-84)."""


def _default_client():
    from openai import OpenAI
    return OpenAI(base_url=_OPENROUTER_BASE_URL, api_key=os.environ["OPENROUTER_API_KEY"])


def embed_texts(
    texts: list[str], *, model: str = DEFAULT_MODEL, client=None,
    sleep: Callable[[float], None] = time.sleep,
) -> list[list[float]]:
    """Dense embedding for each string in `texts`, in order. Returns one `Vector(DIMENSIONS)`-shaped
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
            # encoding_format="float" is explicit on purpose (SOF-84): the openai SDK defaults
            # this to "base64" when omitted, which some OpenRouter-routed providers for this
            # model can't fulfill — they 200 with an empty `data` array instead of erroring.
            # Forcing "float" removes that round-trip and its failure mode entirely.
            resp = client.embeddings.create(model=model, input=batch, encoding_format="float")
        except RateLimitError as exc:
            last_err = exc
            sleep(_BACKOFF_SECONDS * (2 ** attempt))
            continue
        if not resp.data:
            detail = (
                f"attempt={attempt + 1}/{_MAX_RETRIES} model={model} batch_size={len(batch)} "
                f"resp_model={getattr(resp, 'model', None)!r} extra={getattr(resp, 'model_extra', None)!r}"
            )
            logger.warning("embed_texts: empty embedding data from OpenRouter (%s)", detail)
            last_err = EmbeddingRetriesExhausted(f"No embedding data received after retries: {detail}")
            sleep(_BACKOFF_SECONDS * (2 ** attempt))
            continue
        # Provider returns items possibly out of request order; `index` is authoritative.
        ordered = sorted(resp.data, key=lambda d: d.index)
        return [list(item.embedding) for item in ordered]
    raise last_err
