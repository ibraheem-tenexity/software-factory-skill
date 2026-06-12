"""Light console auth — Google sign-in, allowlisted operators, env-gated.

Enabled only when BOTH are set (either absent -> console stays open, so local dev and
the existing test suite run unchanged):
  SF_GOOGLE_CLIENT_ID — the Google OAuth web client id the sign-in button uses
  SF_AUTH_EMAILS      — comma-separated operator allowlist

Flow: the login page's Google button posts the GIS ID token to /api/auth/google; the
server validates it via Google's tokeninfo endpoint (one HTTPS call — no crypto deps,
Google checks the signature), then checks audience + verified email + allowlist and
issues an HMAC-signed session cookie. The signing secret is per-boot random unless
SF_AUTH_SECRET is set (set it so sessions survive restarts).
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
import urllib.parse
import urllib.request

SESSION_TTL = 30 * 24 * 3600  # 30 days
COOKIE = "sf_session"
_BOOT_SECRET = secrets.token_hex(32)


def enabled() -> bool:
    return bool(os.environ.get("SF_GOOGLE_CLIENT_ID") and os.environ.get("SF_AUTH_EMAILS"))


def client_id() -> str:
    return os.environ.get("SF_GOOGLE_CLIENT_ID", "")


SERVICE_HEADER = "X-SF-Service-Token"


def service_token_ok(value) -> bool:
    """Machine-caller credential: header == SF_SERVICE_TOKEN env (babysitter sessions,
    scripts, CI). Env unset = feature off, never a bypass."""
    expected = os.environ.get("SF_SERVICE_TOKEN", "")
    if not expected or not value:
        return False
    return hmac.compare_digest(str(value), expected)


def _secret() -> bytes:
    return (os.environ.get("SF_AUTH_SECRET") or _BOOT_SECRET).encode()


def _allowed(email: str) -> bool:
    allow = [e.strip().lower() for e in os.environ.get("SF_AUTH_EMAILS", "").split(",")
             if e.strip()]
    return bool(email) and email.lower() in allow


def _fetch_claims(id_token: str) -> dict:
    url = ("https://oauth2.googleapis.com/tokeninfo?id_token="
           + urllib.parse.quote(id_token, safe=""))
    with urllib.request.urlopen(url, timeout=10) as r:
        return json.load(r)


def login(id_token: str) -> str | None:
    """Validate a Google ID token; return a session token, or None if rejected."""
    try:
        claims = _fetch_claims(id_token)
    except Exception:
        return None  # invalid token / tokeninfo unreachable — reject, never crash
    if claims.get("aud") != client_id():
        return None  # a valid Google token minted for ANOTHER app must not open the console
    if str(claims.get("email_verified")).lower() != "true":
        return None
    email = claims.get("email", "")
    if not _allowed(email):
        return None
    payload = f"{email}|{int(time.time()) + SESSION_TTL}"
    b = base64.urlsafe_b64encode(payload.encode()).decode().rstrip("=")
    return f"{b}.{_sign(payload)}"


def _sign(payload: str) -> str:
    return hmac.new(_secret(), payload.encode(), hashlib.sha256).hexdigest()


def session_valid(token: str) -> bool:
    """Constant-time HMAC check + expiry + the email must STILL be allowlisted."""
    try:
        b, sig = token.split(".", 1)
        payload = base64.urlsafe_b64decode(b + "=" * (-len(b) % 4)).decode()
        if not hmac.compare_digest(_sign(payload), sig):
            return False
        email, exp = payload.rsplit("|", 1)
        return _allowed(email) and time.time() < int(exp)
    except Exception:
        return False
