"""Light console auth — Google sign-in + an HMAC-signed session cookie.

Identity is Google OAuth / GIS: the browser gets a Google ID token and POSTs it to /api/auth/google.
We verify it (signature against Google's rotating JWKS, exp, aud, iss — via the google-auth library,
never hand-decoded) and mint our OWN HMAC-signed session cookie. We do NOT use Supabase Auth / GoTrue;
the cookie is independent of where Postgres lives.

Who is allowed lives entirely in the database (`public.users`, status invited/active/disabled) — there
is no env allowlist. The cookie carries only the user id and a token_version; the ROLE is resolved per
request from the DB so a demotion/disable takes effect on the next request, not at cookie expiry. The
caller (the console's `viewer` dependency) does that per-request status + token_version revocation check.

Enabled only when SF_GOOGLE_CLIENT_ID is set; absent → console stays open so local dev and the hermetic
test suite run unchanged. Machine/admin callers authenticate with the X-SF-Service-Token header instead.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time

SESSION_TTL = 8 * 3600       # 8h — short-lived; SF_SESSION_SECRET rotation is the global-logout lever
COOKIE = "sf_session"
SERVICE_HEADER = "X-SF-Service-Token"
_BOOT_SECRET = secrets.token_hex(32)


class AuthError(Exception):
    """Google ID token failed validation (bad signature/aud/iss/exp, or unverified email)."""


def enabled() -> bool:
    return bool(os.environ.get("SF_GOOGLE_CLIENT_ID"))


def client_id() -> str:
    return os.environ.get("SF_GOOGLE_CLIENT_ID", "")


# --- Google ID token validation ----------------------------------------------------------
def verify_google_id_token(token: str) -> dict:
    """Verify a GIS ID token and return its claims ('sub', 'email', …). Raises AuthError on any
    failure. verify_oauth2_token checks the signature against Google's JWKS (with key rotation),
    plus exp, aud and iss in one call — do not decode the JWT by hand."""
    if not token:
        raise AuthError("no token")
    from google.auth.transport import requests as google_requests
    from google.oauth2 import id_token as google_id_token
    try:
        info = google_id_token.verify_oauth2_token(
            token, google_requests.Request(), audience=client_id())
    except Exception as e:                       # bad signature / aud / iss / exp / unreachable JWKS
        raise AuthError(str(e))
    if str(info.get("email_verified")).lower() != "true":
        raise AuthError("email not verified")
    # If the GIS front-end sets a nonce, verify it here as replay protection:
    #   if info.get("nonce") != expected_nonce: raise AuthError("nonce mismatch")
    return info


# --- HMAC session cookie -----------------------------------------------------------------
# A signed cookie is integrity-protected, NOT encrypted: the payload is readable by the user, so it
# holds no secrets — only the user id and token_version, both covered by the signature. Expiry lives
# inside the signed payload so it cannot be extended by editing the cookie.
def _secret() -> bytes:
    # SF_SESSION_SECRET is the signing key; rotating it is the global logout. Falls back to the
    # legacy SF_AUTH_SECRET (so an existing prod secret keeps sessions alive across the cutover),
    # then a per-boot random (dev/test: sessions simply don't survive a restart).
    return (os.environ.get("SF_SESSION_SECRET") or os.environ.get("SF_AUTH_SECRET")
            or _BOOT_SECRET).encode()


def _b64u_encode(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def _b64u_decode(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def sign_session(user_id: str, token_version: int, ttl_seconds: int = SESSION_TTL) -> str:
    payload = {"uid": str(user_id), "tv": int(token_version), "exp": int(time.time()) + ttl_seconds}
    raw = _b64u_encode(json.dumps(payload, separators=(",", ":")).encode())
    sig = hmac.new(_secret(), raw.encode(), hashlib.sha256).digest()
    return f"{raw}.{_b64u_encode(sig)}"


def verify_session(cookie: str) -> dict | None:
    """Return the signed payload {uid, tv, exp} if the signature is valid and unexpired, else None.
    The caller STILL must check status + token_version against the DB (per-request revocation)."""
    if not cookie:
        return None
    try:
        raw, sig = cookie.rsplit(".", 1)
    except ValueError:
        return None
    try:
        expected = hmac.new(_secret(), raw.encode(), hashlib.sha256).digest()
        if not hmac.compare_digest(expected, _b64u_decode(sig)):   # constant-time, never ==
            return None
        payload = json.loads(_b64u_decode(raw))
    except Exception:
        return None
    if int(payload.get("exp", 0)) < int(time.time()):
        return None
    return payload


# --- Service token -----------------------------------------------------------------------
def service_token_ok(value) -> bool:
    """Machine-caller credential: header == SF_SERVICE_TOKEN env (babysitter sessions, scripts, CI).
    Compared constant-time. Env unset = feature off, never a bypass.

    BLAST RADIUS: this is a single static bearer secret with broad (admin-equivalent) authority —
    anything that can read SF_SERVICE_TOKEN or observe the header is effectively admin. Keep it long,
    random, and rotateable (env only, never hardcoded).
    TODO: as soon as there is more than one machine caller, move to per-client tokens (a table of
    hashed tokens, or distinct env vars per caller) rather than this one shared secret.
    """
    expected = os.environ.get("SF_SERVICE_TOKEN", "")
    if not expected or not value:
        return False
    return hmac.compare_digest(str(value), expected)
