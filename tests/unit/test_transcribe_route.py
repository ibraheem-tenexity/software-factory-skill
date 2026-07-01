"""Tests for POST /api/transcribe — the Dictate mic button's backend proxy (SOF-14).
No live OpenRouter call: software_factory.transcription.transcribe_audio is mocked throughout."""
import importlib
import os
import sys

import pytest
from fastapi.testclient import TestClient


def _load_app(tmp_path, monkeypatch):
    monkeypatch.setenv("SF_PROJECTS_DIR", str(tmp_path))
    monkeypatch.setenv("SF_RUNS_DIR", str(tmp_path))
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setenv("SF_GOOGLE_CLIENT_ID", "cid-123.apps.googleusercontent.com")
    monkeypatch.setenv("SF_SESSION_SECRET", "test-secret")
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
    import console.app as app_mod
    importlib.reload(app_mod)
    return app_mod


@pytest.fixture()
def auth_mod(tmp_path, monkeypatch):
    mod = _load_app(tmp_path, monkeypatch)
    mod.users.upsert("user@tenexity.ai", "member")
    return mod


@pytest.fixture()
def auth_client(auth_mod):
    return TestClient(auth_mod.app, base_url="https://testserver")


def _login(mod, client, monkeypatch, email="user@tenexity.ai"):
    from software_factory import auth as a
    monkeypatch.setattr(a, "verify_google_id_token",
                        lambda tok: {"sub": "sub-" + email, "email": email, "email_verified": True})
    return client.post("/api/auth/google", json={"credential": "t"})


def test_transcribe_requires_auth(auth_client):
    r = auth_client.post("/api/transcribe", json={"audio_base64": "AAAA", "format": "webm"})
    assert r.status_code == 401


def test_transcribe_503_when_no_key(auth_mod, auth_client, monkeypatch):
    _login(auth_mod, auth_client, monkeypatch)
    # _load_app already delenv's OPENROUTER_API_KEY — this is the default state.
    r = auth_client.post("/api/transcribe", json={"audio_base64": "AAAA", "format": "webm"})
    assert r.status_code == 503


def test_transcribe_400_when_audio_missing(auth_mod, auth_client, monkeypatch):
    _login(auth_mod, auth_client, monkeypatch)
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    r = auth_client.post("/api/transcribe", json={"audio_base64": "", "format": "webm"})
    assert r.status_code == 400


def test_transcribe_returns_text_on_success(auth_mod, auth_client, monkeypatch):
    _login(auth_mod, auth_client, monkeypatch)
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    import console.routers.chat as chat_mod
    monkeypatch.setattr(chat_mod, "transcribe_audio",
                        lambda data_b64, fmt, language=None: "hello from whisper")
    r = auth_client.post("/api/transcribe", json={"audio_base64": "AAAA", "format": "webm"})
    assert r.status_code == 200
    assert r.json() == {"text": "hello from whisper"}


def test_transcribe_502_on_upstream_failure(auth_mod, auth_client, monkeypatch):
    _login(auth_mod, auth_client, monkeypatch)
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    import console.routers.chat as chat_mod
    from software_factory.transcription import TranscriptionError

    def _boom(data_b64, fmt, language=None):
        raise TranscriptionError("upstream exploded")
    monkeypatch.setattr(chat_mod, "transcribe_audio", _boom)
    r = auth_client.post("/api/transcribe", json={"audio_base64": "AAAA", "format": "webm"})
    assert r.status_code == 502
