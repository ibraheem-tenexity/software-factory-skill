"""Tests for software_factory.transcription — the OpenRouter Whisper Large v3 proxy (SOF-14)."""
from unittest.mock import MagicMock, patch

import pytest

from software_factory.transcription import transcribe_audio, TranscriptionError


def _mock_response(json_body, status_ok=True):
    resp = MagicMock()
    resp.json.return_value = json_body
    if not status_ok:
        resp.raise_for_status.side_effect = Exception("500 Server Error")
    return resp


def test_transcribe_audio_raises_without_api_key(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    with pytest.raises(TranscriptionError):
        transcribe_audio("AAAA", "webm")


def test_transcribe_audio_sends_correct_request_shape(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    with patch("software_factory.transcription.httpx.post",
              return_value=_mock_response({"text": "hello world"})) as mock_post:
        text = transcribe_audio("AAAA", "webm", language="en")
    assert text == "hello world"
    _, kwargs = mock_post.call_args
    assert mock_post.call_args[0][0] == "https://openrouter.ai/api/v1/audio/transcriptions"
    assert kwargs["headers"]["Authorization"] == "Bearer test-key"
    assert kwargs["json"]["model"] == "openai/whisper-large-v3"
    assert kwargs["json"]["input_audio"] == {"data": "AAAA", "format": "webm"}
    assert kwargs["json"]["language"] == "en"


def test_transcribe_audio_omits_language_when_not_given(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    with patch("software_factory.transcription.httpx.post",
              return_value=_mock_response({"text": "hi"})) as mock_post:
        transcribe_audio("AAAA", "webm")
    assert "language" not in mock_post.call_args.kwargs["json"]


def test_transcribe_audio_raises_on_http_error(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    with patch("software_factory.transcription.httpx.post",
              return_value=_mock_response({}, status_ok=False)):
        with pytest.raises(TranscriptionError):
            transcribe_audio("AAAA", "webm")


def test_transcribe_audio_raises_when_no_text_in_response(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    with patch("software_factory.transcription.httpx.post",
              return_value=_mock_response({"usage": {}})):
        with pytest.raises(TranscriptionError):
            transcribe_audio("AAAA", "webm")
