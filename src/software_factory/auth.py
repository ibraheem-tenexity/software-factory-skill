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


# --- Roles & membership ------------------------------------------------------------------
# auth stays dependency-free (env + crypto only) so the suite runs hermetic. The server
# injects a DB-backed user directory at startup via register_user_store(); without it,
# membership/roles fall back to the env lists (SF_AUTH_EMAILS / SF_ADMIN_EMAILS) — the
# bootstrap path that can never lock the env-named admins out.
_member_fn = None   # callable(email)->bool   (is this email allowed to log in?)
_role_fn = None     # callable(email)->str|None  ('admin'|'member'|None)


def register_user_store(member_fn, role_fn) -> None:
    global _member_fn, _role_fn
    _member_fn, _role_fn = member_fn, role_fn


def _env_list(name: str) -> list:
    return [e.strip().lower() for e in os.environ.get(name, "").split(",") if e.strip()]


def role_for(email: str) -> str | None:
    """'admin' | 'member' | None (not allowed). Env SF_ADMIN_EMAILS always wins (bootstrap),
    then the injected DB role, then membership implies 'member'."""
    if not email:
        return None
    if email.lower() in _env_list("SF_ADMIN_EMAILS"):
        return "admin"
    if _role_fn:
        r = _role_fn(email)
        if r in ("admin", "member"):
            return r
    return "member" if _allowed(email) else None


def is_admin(email: str) -> bool:
    return role_for(email) == "admin"


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
    """Allowed to log in: on the env allowlist OR in the injected DB directory (invited
    in-console). Env is the bootstrap that survives an empty/unreachable directory."""
    if not email:
        return False
    if email.lower() in _env_list("SF_AUTH_EMAILS"):
        return True
    return bool(_member_fn and _member_fn(email))


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
    return session_email(token) is not None


def session_email(token: str) -> str | None:
    """The email behind a valid session token, or None if the token is forged, expired,
    or the email is no longer allowed. The identity the server gates ownership on."""
    try:
        b, sig = token.split(".", 1)
        payload = base64.urlsafe_b64decode(b + "=" * (-len(b) % 4)).decode()
        if not hmac.compare_digest(_sign(payload), sig):
            return None
        email, exp = payload.rsplit("|", 1)
        if _allowed(email) and time.time() < int(exp):
            return email
        return None
    except Exception:
        return None
