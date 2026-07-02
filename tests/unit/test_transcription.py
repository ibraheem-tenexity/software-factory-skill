"""Tests for software_factory.transcription — the OpenAI gpt-4o-transcribe proxy (SOF-14/SOF-75)."""
import base64
from unittest.mock import MagicMock, patch

import pytest

from software_factory.transcription import transcribe_audio, TranscriptionError

_B64 = base64.b64encode(b"fake-audio-bytes").decode()


def _mock_response(json_body, status_ok=True):
    resp = MagicMock()
    resp.json.return_value = json_body
    if not status_ok:
        resp.raise_for_status.side_effect = Exception("500 Server Error")
    return resp


def test_transcribe_audio_raises_without_api_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(TranscriptionError):
        transcribe_audio(_B64, "webm")


def test_transcribe_audio_sends_multipart_request_shape(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    with patch("software_factory.transcription.httpx.post",
              return_value=_mock_response({"text": "hello world"})) as mock_post:
        text = transcribe_audio(_B64, "webm", language="en")
    assert text == "hello world"
    _, kwargs = mock_post.call_args
    assert mock_post.call_args[0][0] == "https://api.openai.com/v1/audio/transcriptions"
    assert kwargs["headers"]["Authorization"] == "Bearer test-key"
    # multipart file upload (decoded bytes), not a JSON body
    assert "json" not in kwargs
    fname, content, ctype = kwargs["files"]["file"]
    assert fname == "audio.webm" and content == b"fake-audio-bytes" and ctype == "audio/webm"
    assert kwargs["data"]["model"] == "gpt-4o-transcribe"
    assert kwargs["data"]["language"] == "en"


def test_transcribe_audio_omits_language_when_not_given(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    with patch("software_factory.transcription.httpx.post",
              return_value=_mock_response({"text": "hi"})) as mock_post:
        transcribe_audio(_B64, "webm")
    assert "language" not in mock_post.call_args.kwargs["data"]


def test_transcribe_audio_raises_on_invalid_base64(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    with pytest.raises(TranscriptionError):
        transcribe_audio("not valid base64!!!", "webm", language="en")


def test_transcribe_audio_raises_on_http_error(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    with patch("software_factory.transcription.httpx.post",
              return_value=_mock_response({}, status_ok=False)):
        with pytest.raises(TranscriptionError):
            transcribe_audio(_B64, "webm")


def test_transcribe_audio_raises_when_no_text_in_response(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    with patch("software_factory.transcription.httpx.post",
              return_value=_mock_response({"usage": {}})):
        with pytest.raises(TranscriptionError):
            transcribe_audio(_B64, "webm")
