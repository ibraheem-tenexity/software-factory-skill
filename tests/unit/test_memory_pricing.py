"""SOF-32: memory/pricing.py — live OpenRouter pricing lookup, mocked httpx (no live network,
no DB). ACTUALLY RUN via a standalone python -c script bypassing pytest/conftest (this repo's
conftest bootstraps a real Postgres connection at collection time for every test file,
unconditionally — the memory-track's hard DB-connection constraint covers this file too, even
though its own content never touches a DB). Transcript in the PR description.
"""
from unittest.mock import MagicMock, patch

from software_factory.memory import pricing


def _fake_response(data):
    resp = MagicMock()
    resp.json.return_value = {"data": data}
    resp.raise_for_status.return_value = None
    return resp


def test_openrouter_price_parses_real_catalog_shape():
    pricing._cache.clear()
    resp = _fake_response([{"id": "anthropic/claude-haiku-4.5",
                            "pricing": {"prompt": "0.000001", "completion": "0.000005"}}])
    with patch("httpx.get", return_value=resp):
        price = pricing.openrouter_price("anthropic/claude-haiku-4.5", kind="chat")
    assert price == {"input": 0.000001, "output": 0.000005}


def test_openrouter_price_caches_after_first_fetch():
    pricing._cache.clear()
    resp = _fake_response([{"id": "m", "pricing": {"prompt": "0.1", "completion": "0.2"}}])
    with patch("httpx.get", return_value=resp) as m:
        pricing.openrouter_price("m", kind="chat")
        pricing.openrouter_price("m", kind="chat")
    assert m.call_count == 1


def test_openrouter_price_returns_none_on_network_failure_never_fabricates():
    pricing._cache.clear()
    with patch("httpx.get", side_effect=Exception("network down")):
        assert pricing.openrouter_price("anthropic/claude-haiku-4.5", kind="chat") is None


def test_openrouter_price_returns_none_for_unknown_model():
    pricing._cache.clear()
    resp = _fake_response([{"id": "some/other-model", "pricing": {"prompt": "0.1", "completion": "0"}}])
    with patch("httpx.get", return_value=resp):
        assert pricing.openrouter_price("nonexistent/model", kind="chat") is None


def test_openrouter_price_embedding_kind_hits_the_embeddings_catalog_url():
    pricing._cache.clear()
    resp = _fake_response([{"id": "google/gemini-embedding-2",
                            "pricing": {"prompt": "0.0000002", "completion": "0"}}])
    with patch("httpx.get", return_value=resp) as m:
        price = pricing.openrouter_price("google/gemini-embedding-2", kind="embedding")
    assert price == {"input": 0.0000002, "output": 0.0}
    assert m.call_args[0][0] == pricing._EMBEDDING_MODELS_URL
