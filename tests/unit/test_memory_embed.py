"""SOF-29: embed.py — request/response shape against a stub client. No live network, no DB."""
import httpx
import pytest

from software_factory.memory.embed import DIMENSIONS, EmbeddingRetriesExhausted, embed_texts


def _rate_limit_error():
    from openai import RateLimitError
    req = httpx.Request("POST", "https://openrouter.ai/api/v1/embeddings")
    return RateLimitError("slow down", response=httpx.Response(429, request=req), body=None)


class _Item:
    def __init__(self, index, embedding):
        self.index = index
        self.embedding = embedding


class _Resp:
    def __init__(self, data):
        self.data = data


class _StubEmbeddings:
    def __init__(self, vector_for):
        self.vector_for = vector_for
        self.calls = []

    def create(self, *, model, input, encoding_format=None):
        self.calls.append({"model": model, "input": list(input), "encoding_format": encoding_format})
        # Return out of order deliberately — index must be respected, not list position.
        items = [_Item(i, self.vector_for(text)) for i, text in enumerate(input)]
        return _Resp(list(reversed(items)))


class _StubClient:
    def __init__(self, vector_for=lambda text: [0.0] * DIMENSIONS):
        self.embeddings = _StubEmbeddings(vector_for)


def test_embed_texts_returns_one_vector_per_input_in_request_order():
    client = _StubClient(vector_for=lambda text: [float(len(text))] * DIMENSIONS)
    out = embed_texts(["a", "bb", "ccc"], client=client)
    assert len(out) == 3
    assert out[0] == [1.0] * DIMENSIONS
    assert out[1] == [2.0] * DIMENSIONS
    assert out[2] == [3.0] * DIMENSIONS


def test_embed_texts_empty_input_returns_empty_list_without_calling_the_client():
    client = _StubClient()
    assert embed_texts([], client=client) == []
    assert client.embeddings.calls == []


def test_embed_texts_uses_the_default_model_unless_overridden():
    client = _StubClient()
    embed_texts(["x"], client=client)
    assert client.embeddings.calls[0]["model"] == "google/gemini-embedding-2"
    embed_texts(["x"], client=client, model="qwen/qwen3-embedding")
    assert client.embeddings.calls[1]["model"] == "qwen/qwen3-embedding"


def test_embed_texts_splits_into_batches_above_the_batch_size():
    client = _StubClient()
    texts = [f"t{i}" for i in range(150)]  # > _BATCH_SIZE (96)
    out = embed_texts(texts, client=client)
    assert len(out) == 150
    assert len(client.embeddings.calls) == 2
    assert len(client.embeddings.calls[0]["input"]) == 96
    assert len(client.embeddings.calls[1]["input"]) == 54


def test_embed_texts_requests_float_encoding_not_the_sdks_implicit_base64_default():
    # SOF-84: the openai SDK defaults encoding_format to "base64" when omitted, which some
    # OpenRouter-routed providers for this model can't fulfill (200 + empty `data`). We must
    # always ask for "float" explicitly.
    client = _StubClient()
    embed_texts(["x"], client=client)
    assert client.embeddings.calls[0]["encoding_format"] == "float"


def test_embed_texts_retries_on_rate_limit_then_succeeds():
    attempts = {"n": 0}
    client = _StubClient()
    real_create = client.embeddings.create

    def flaky_create(*, model, input, encoding_format=None):
        attempts["n"] += 1
        if attempts["n"] == 1:
            raise _rate_limit_error()
        return real_create(model=model, input=input, encoding_format=encoding_format)

    client.embeddings.create = flaky_create
    sleeps = []
    out = embed_texts(["x"], client=client, sleep=sleeps.append)
    assert len(out) == 1
    assert attempts["n"] == 2
    assert sleeps == [2.0]  # one backoff before the successful retry


def test_embed_texts_raises_after_exhausting_retries():
    from openai import RateLimitError

    client = _StubClient()
    client.embeddings.create = lambda **kw: (_ for _ in ()).throw(_rate_limit_error())
    with pytest.raises(RateLimitError):
        embed_texts(["x"], client=client, sleep=lambda s: None)


def test_embed_texts_retries_on_empty_embedding_data_then_succeeds():
    attempts = {"n": 0}
    client = _StubClient()
    real_create = client.embeddings.create

    def flaky_create(*, model, input, encoding_format=None):
        attempts["n"] += 1
        if attempts["n"] == 1:
            return _Resp([])  # OpenRouter 200-with-empty-data case (SOF-84)
        return real_create(model=model, input=input, encoding_format=encoding_format)

    client.embeddings.create = flaky_create
    sleeps = []
    out = embed_texts(["x"], client=client, sleep=sleeps.append)
    assert len(out) == 1
    assert attempts["n"] == 2
    assert sleeps == [2.0]


def test_embed_texts_raises_with_diagnostic_detail_after_exhausting_retries_on_empty_data():
    client = _StubClient()
    client.embeddings.create = lambda **kw: _Resp([])
    with pytest.raises(EmbeddingRetriesExhausted, match="No embedding data received"):
        embed_texts(["x"], client=client, sleep=lambda s: None)
