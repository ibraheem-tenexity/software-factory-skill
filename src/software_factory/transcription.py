"""Speech-to-text: proxies dictation audio to OpenRouter's Whisper Large v3 (SOF-14).

OpenRouter exposes a dedicated (non-chat-completions) transcription endpoint: JSON body with
base64 audio, not the OpenAI SDK's multipart file-upload shape. Confirmed against the OpenRouter
docs (guides/overview/multimodal/stt, api-reference/transcriptions/create-audio-transcriptions)
before building — see SOF-14.
"""
import os

import httpx

_ENDPOINT = "https://openrouter.ai/api/v1/audio/transcriptions"
_MODEL = "openai/whisper-large-v3"


class TranscriptionError(Exception):
    """OpenRouter transcription call failed (missing key, upstream error, bad audio, etc.)."""


def transcribe_audio(data_b64: str, fmt: str, language: str | None = None) -> str:
    """Send base64-encoded dictation audio to OpenRouter Whisper Large v3; return the transcript.
    Raises TranscriptionError with a user-facing message on any failure."""
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        raise TranscriptionError("OPENROUTER_API_KEY is not set — dictation unavailable")

    body = {"model": _MODEL, "input_audio": {"data": data_b64, "format": fmt}}
    if language:
        body["language"] = language

    try:
        resp = httpx.post(
            _ENDPOINT,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json=body,
            timeout=60,
        )
        resp.raise_for_status()
    except Exception as exc:
        raise TranscriptionError(f"Transcription failed: {exc}") from exc

    text = resp.json().get("text")
    if text is None:
        raise TranscriptionError("Transcription response had no 'text' field")
    return text
