"""Speech-to-text: proxies dictation audio to OpenAI's gpt-4o-transcribe (SOF-14, SOF-75).

SOF-75: switched from OpenRouter Whisper Large v3 to OpenAI `gpt-4o-transcribe` — it handles the
short clips onboarding produces with markedly less tail-garble/hallucination. This is OpenAI's
transcription endpoint, which takes a MULTIPART file upload (not a base64 JSON body), so the
FE-supplied base64 is decoded to bytes and sent as a file part. `OPENAI_API_KEY` is required
(set in prod); a missing key raises TranscriptionError, which the caller surfaces as a graceful
"dictation unavailable" rather than a crash.
"""
import base64
import os

import httpx

from .log import get_logger

logger = get_logger(__name__)

_ENDPOINT = "https://api.openai.com/v1/audio/transcriptions"
_MODEL = "gpt-4o-transcribe"


class TranscriptionError(Exception):
    """Transcription call failed (missing key, upstream error, bad audio, etc.)."""


def transcribe_audio(data_b64: str, fmt: str, language: str | None = None) -> str:
    """Send base64-encoded dictation audio to OpenAI gpt-4o-transcribe; return the transcript.
    Raises TranscriptionError with a user-facing message on any failure."""
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise TranscriptionError("OPENAI_API_KEY is not set — dictation unavailable")

    try:
        audio = base64.b64decode(data_b64)
    except Exception as exc:
        logger.exception("[transcription] base64 decode failed — audio payload unusable")
        raise TranscriptionError(f"invalid audio data: {exc}") from exc

    files = {"file": (f"audio.{fmt}", audio, f"audio/{fmt}")}
    data = {"model": _MODEL}
    if language:
        data["language"] = language

    try:
        resp = httpx.post(
            _ENDPOINT,
            headers={"Authorization": f"Bearer {api_key}"},
            files=files,
            data=data,
            timeout=60,
        )
        resp.raise_for_status()
    except Exception as exc:
        logger.exception("[transcription] gpt-4o-transcribe call failed — dictation unavailable")
        raise TranscriptionError(f"Transcription failed: {exc}") from exc

    text = resp.json().get("text")
    if text is None:
        raise TranscriptionError("Transcription response had no 'text' field")
    return text
