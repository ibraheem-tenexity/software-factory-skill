"""LIVE smoke of embed_texts against the real OpenRouter embeddings endpoint.

Spends real (tiny) money on one real API call. Opt-in only.

Run explicitly:
    SF_LIVE=1 OPENROUTER_API_KEY=... pytest -m live tests/integration/test_memory_embed_live.py

Skips silently unless SF_LIVE=1 and OPENROUTER_API_KEY is set. NOT executed in this sandbox —
the memory-track's hard constraint plus this test's own real-network/real-spend nature both
argue for deferring it to a real opt-in run, not exercising it here.
"""
import os

import pytest

from software_factory.memory.embed import DIMENSIONS, embed_texts

pytestmark = pytest.mark.live

_SKIP = os.environ.get("SF_LIVE") != "1" or not os.environ.get("OPENROUTER_API_KEY")
_SKIP_REASON = "set SF_LIVE=1 and OPENROUTER_API_KEY to run the live embedding smoke"


@pytest.mark.skipif(_SKIP, reason=_SKIP_REASON)
def test_embed_texts_against_real_openrouter():
    out = embed_texts(["the quick brown fox jumps over the lazy dog"])
    assert len(out) == 1
    assert len(out[0]) == DIMENSIONS
    assert any(v != 0.0 for v in out[0])
