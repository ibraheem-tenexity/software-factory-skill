"""Light console auth — Google sign-in, allowlisted operators, env-gated.

Disabled (both env vars absent) = console stays open: local dev and every existing
test run unchanged. Enabled = every route except the login flow requires a valid
HMAC-signed session cookie.
"""
import time

import pytest

from software_factory import auth


@pytest.fixture()
def enabled(monkeypatch):
    monkeypatch.setenv("SF_GOOGLE_CLIENT_ID", "cid-123.apps.googleusercontent.com")
    monkeypatch.setenv("SF_AUTH_EMAILS", "ibraheem@tenexity.ai, second@tenexity.ai")
    monkeypatch.setenv("SF_AUTH_SECRET", "test-secret")


def test_disabled_without_env(monkeypatch):
    monkeypatch.delenv("SF_GOOGLE_CLIENT_ID", raising=False)
    monkeypatch.delenv("SF_AUTH_EMAILS", raising=False)
    assert auth.enabled() is False


def test_enabled_with_both_vars(enabled):
    assert auth.enabled() is True


def _claims(**over):
    c = {"aud": "cid-123.apps.googleusercontent.com", "email": "ibraheem@tenexity.ai",
         "email_verified": "true"}
    c.update(over)
    return c


def test_login_accepts_allowlisted_verified_google_token(enabled, monkeypatch):
    monkeypatch.setattr(auth, "_fetch_claims", lambda tok: _claims())
    token = auth.login("goog-id-token")
    assert token and auth.session_valid(token)


def test_login_rejects_wrong_audience(enabled, monkeypatch):
    # A valid Google token minted for ANOTHER app must not open our console.
    monkeypatch.setattr(auth, "_fetch_claims", lambda tok: _claims(aud="other-app"))
    assert auth.login("tok") is None


def test_login_rejects_non_allowlisted_email(enabled, monkeypatch):
    monkeypatch.setattr(auth, "_fetch_claims", lambda tok: _claims(email="evil@example.com"))
    assert auth.login("tok") is None


def test_login_rejects_unverified_email(enabled, monkeypatch):
    monkeypatch.setattr(auth, "_fetch_claims", lambda tok: _claims(email_verified="false"))
    assert auth.login("tok") is None


def test_login_rejects_when_google_validation_fails(enabled, monkeypatch):
    def boom(tok):
        raise RuntimeError("tokeninfo unreachable")
    monkeypatch.setattr(auth, "_fetch_claims", boom)
    assert auth.login("tok") is None


def test_tampered_session_is_invalid(enabled, monkeypatch):
    monkeypatch.setattr(auth, "_fetch_claims", lambda tok: _claims())
    token = auth.login("tok")
    assert auth.session_valid(token + "x") is False
    assert auth.session_valid("garbage") is False
    assert auth.session_valid("") is False


def test_expired_session_is_invalid(enabled, monkeypatch):
    monkeypatch.setattr(auth, "_fetch_claims", lambda tok: _claims())
    real_time = time.time
    monkeypatch.setattr(auth.time, "time", lambda: real_time() - auth.SESSION_TTL - 60)
    token = auth.login("tok")  # minted in the "past"
    monkeypatch.setattr(auth.time, "time", real_time)
    assert auth.session_valid(token) is False


def test_session_dies_when_email_leaves_the_allowlist(enabled, monkeypatch):
    monkeypatch.setattr(auth, "_fetch_claims", lambda tok: _claims())
    token = auth.login("tok")
    monkeypatch.setenv("SF_AUTH_EMAILS", "someone-else@tenexity.ai")
    assert auth.session_valid(token) is False
