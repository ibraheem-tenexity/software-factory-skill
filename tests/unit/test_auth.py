"""Console auth — Google ID-token verification + the HMAC-signed uid/token_version session cookie.

Disabled (SF_GOOGLE_CLIENT_ID absent) = console stays open: local dev and every existing test run
unchanged. Enabled = every route except the login flow requires a valid session cookie, and the
allowlist + role live entirely in the DB (see test_users.py), not in env.
"""
import time

import pytest

from software_factory import auth


@pytest.fixture()
def enabled(monkeypatch):
    monkeypatch.setenv("SF_GOOGLE_CLIENT_ID", "cid-123.apps.googleusercontent.com")
    monkeypatch.setenv("SF_SESSION_SECRET", "test-secret")
    monkeypatch.delenv("SF_AUTH_SECRET", raising=False)


def test_disabled_without_client_id(monkeypatch):
    monkeypatch.delenv("SF_GOOGLE_CLIENT_ID", raising=False)
    assert auth.enabled() is False


def test_enabled_with_client_id(enabled):
    assert auth.enabled() is True


# ---------- Google ID token verification (via google-auth) ----------

def _patch_verify(monkeypatch, claims=None, exc=None):
    from google.oauth2 import id_token as gid

    def fake(token, request, audience=None):
        if exc:
            raise exc
        return claims
    monkeypatch.setattr(gid, "verify_oauth2_token", fake)


def test_verify_returns_claims_for_verified_email(enabled, monkeypatch):
    _patch_verify(monkeypatch, {"sub": "g-123", "email": "ibraheem@tenexity.ai", "email_verified": True})
    info = auth.verify_google_id_token("goog-id-token")
    assert info["sub"] == "g-123" and info["email"] == "ibraheem@tenexity.ai"


def test_verify_rejects_unverified_email(enabled, monkeypatch):
    _patch_verify(monkeypatch, {"sub": "g-1", "email": "x@t.ai", "email_verified": False})
    with pytest.raises(auth.AuthError):
        auth.verify_google_id_token("tok")


def test_verify_rejects_invalid_token(enabled, monkeypatch):
    # verify_oauth2_token raises on bad signature/aud/iss/exp — we surface that as AuthError.
    _patch_verify(monkeypatch, exc=ValueError("Token has wrong audience"))
    with pytest.raises(auth.AuthError):
        auth.verify_google_id_token("tok")


def test_verify_rejects_empty_token(enabled):
    with pytest.raises(auth.AuthError):
        auth.verify_google_id_token("")


# ---------- the HMAC session cookie (carries only uid + token_version) ----------

def test_session_roundtrip(enabled):
    tok = auth.sign_session("user-uuid-1", 7)
    payload = auth.verify_session(tok)
    assert payload and payload["uid"] == "user-uuid-1" and payload["tv"] == 7


def test_tampered_and_garbage_sessions_are_invalid(enabled):
    tok = auth.sign_session("u", 0)
    assert auth.verify_session(tok + "x") is None       # mutated signature
    assert auth.verify_session("garbage") is None        # no separator
    assert auth.verify_session("a.b.c") is None          # not our format
    assert auth.verify_session("") is None
    assert auth.verify_session(None) is None


def test_expired_session_is_invalid(enabled, monkeypatch):
    real_time = time.time
    monkeypatch.setattr(auth.time, "time", lambda: real_time() - auth.SESSION_TTL - 60)
    tok = auth.sign_session("u", 0)                       # minted in the "past"
    monkeypatch.setattr(auth.time, "time", real_time)
    assert auth.verify_session(tok) is None              # expiry is inside the signed payload


def test_secret_rotation_invalidates_all_sessions(enabled, monkeypatch):
    tok = auth.sign_session("u", 0)
    assert auth.verify_session(tok) is not None
    monkeypatch.setenv("SF_SESSION_SECRET", "rotated-secret")   # the global-logout lever
    assert auth.verify_session(tok) is None


def test_role_is_not_in_the_cookie(enabled):
    # Authorization is resolved per-request from the DB; the cookie must not carry the role.
    import base64
    import json
    tok = auth.sign_session("u", 3)
    raw = tok.rsplit(".", 1)[0]
    payload = json.loads(base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4)))
    assert set(payload) == {"uid", "tv", "exp"}


def test_service_token_constant_time_check(monkeypatch):
    monkeypatch.setenv("SF_SERVICE_TOKEN", "s3cr3t-long-random")
    assert auth.service_token_ok("s3cr3t-long-random") is True
    assert auth.service_token_ok("wrong") is False
    assert auth.service_token_ok(None) is False
    monkeypatch.delenv("SF_SERVICE_TOKEN", raising=False)
    assert auth.service_token_ok("anything") is False    # unset env = feature off, never a bypass
