"""Auth exchange + identity/team routes: /api/auth/config, /api/auth/google, /api/me, /api/users."""
import json
import os

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse

from software_factory import auth

import console.state as state
from console.deps import require_authed, require_admin
from console.schemas import UserMgmtIn, GoogleLoginIn, PasswordLoginIn

router = APIRouter()


# ── Identity + team ─────────────────────────────────────────────────────────────────────────
@router.get("/api/me")
def me(v: tuple = Depends(require_authed)):
    return {"email": v[0], "role": v[1], "auth": auth.enabled()}


@router.get("/api/users")
def list_users(v: tuple = Depends(require_admin)):
    return {"users": state.users.list_users()}


@router.post("/api/users")
def manage_users(body: UserMgmtIn, v: tuple = Depends(require_admin)):
    email = (body.email or "").strip().lower()
    role = body.role
    if not email or role not in ("admin", "member", "remove"):
        raise HTTPException(status_code=400, detail="email + role (admin|member|remove) required")
    if role == "remove":
        state.users.remove(email)
    else:
        state.users.upsert(email, role, by=v[0] or "admin")
    return {"users": state.users.list_users()}


# ── Auth exchange ───────────────────────────────────────────────────────────────────────────
@router.get("/api/auth/config")
def auth_config():
    # Public (no session): the React SPA reads this on boot to know whether auth is on and to get
    # the Google OAuth web client id for the sign-in button. client_id is already public (it's
    # embedded in the GIS button); enabled carries no secret.
    return {"enabled": auth.enabled(), "client_id": auth.client_id()}


@router.post("/api/auth/google")
def google_login(body: GoogleLoginIn):
    # The login exchange is the ONLY route reachable without a session.
    # Verify the Google ID token (signature/JWKS, exp, aud, iss), resolve it to an allowed user
    # (invited→active on first sign-in), then mint a uid+token_version cookie. Role is NOT in the cookie.
    try:
        claims = auth.verify_google_id_token(body.credential or "")
    except auth.AuthError:
        raise HTTPException(status_code=403, detail="not authorized")
    u = state.users.authenticate(claims.get("sub"), claims.get("email", ""))
    if not u:
        raise HTTPException(status_code=403, detail="not authorized")
    token = auth.sign_session(u["id"], int(u["token_version"]))
    resp = JSONResponse({"ok": True})
    resp.set_cookie(auth.COOKIE, token, max_age=auth.SESSION_TTL, path="/",
                    httponly=True, secure=True, samesite="lax")
    return resp


def _client_ip(request: Request) -> str:
    # NON-SPOOFABLE client IP for the throttle key. The LEFTMOST X-Forwarded-For hop is
    # client-controlled (a client can prefill its own XFF; the proxy only appends) — keying on it lets
    # an attacker rotate a forged leftmost per request and evade the per-IP counter. So we trust only
    # what OUR proxy appended:
    #   1) X-Envoy-External-Address — Railway's Envoy edge sets this to the real external client; the
    #      client cannot set it through the proxy. Preferred when present.
    #   2) Else X-Forwarded-For indexed from the RIGHT by the trusted-proxy-hop count: the entry the
    #      outermost trusted proxy appended is the real client; everything to its left is forgeable and
    #      ignored. SF_TRUSTED_PROXY_HOPS (default 1 = single Railway edge) tunes this with no redeploy.
    #   3) Else the direct socket peer (local/dev, no proxy).
    envoy = request.headers.get("x-envoy-external-address")
    if envoy:
        return envoy.strip()
    xff = request.headers.get("x-forwarded-for")
    if xff:
        parts = [p.strip() for p in xff.split(",") if p.strip()]
        hops = max(1, int(os.environ.get("SF_TRUSTED_PROXY_HOPS", "1")))
        if len(parts) >= hops:
            return parts[-hops]          # appended by the outermost trusted proxy = the real client
    return request.client.host if request.client else "?"


@router.post("/api/auth/password")
def password_login(body: PasswordLoginIn, request: Request):
    # Email+password sign-in. Reuses the SHIPPED session model: authenticate_password applies the same
    # users-table allowlist + 'active' lifecycle gate as Google (a disabled/invited user can't get in),
    # constant-time verifies the scrypt hash, then we mint the SAME uid+token_version cookie. Generic
    # 401 for every failure (bad email, bad password, no password set, disabled) — never leak which.
    email = (body.email or "").strip().lower()
    ip = _client_ip(request)
    # Login-source audit + empirical IP-resolution check: one structured line per attempt with the
    # resolved IP and the raw upstream headers, so we can confirm prod resolves the REAL external
    # client (not a 10.x proxy hop) and tune SF_TRUSTED_PROXY_HOPS if Railway's XFF semantics differ.
    print(json.dumps({"evt": "auth_password", "ip": ip,
                      "envoy": request.headers.get("x-envoy-external-address"),
                      "xff": request.headers.get("x-forwarded-for")}), flush=True)
    keys = [f"email:{email}", f"ip:{ip}"]
    # Brute-force/DoS guard: checked BEFORE the (deliberately slow) scrypt verify, so a throttled
    # attempt never pays the hash cost. Generic message — no Retry-After value leak about which key.
    wait = state.login_throttle.retry_after(keys)
    if wait:
        resp = JSONResponse({"detail": "too many attempts"}, status_code=429)
        resp.headers["Retry-After"] = str(wait)
        return resp
    u = state.users.authenticate_password(email, body.password or "")
    if not u:
        state.login_throttle.record_failure(keys)
        raise HTTPException(status_code=401, detail="invalid credentials")
    state.login_throttle.reset(keys)            # good login → wipe this user/IP's failure counters
    token = auth.sign_session(u["id"], int(u["token_version"]))
    resp = JSONResponse({"ok": True})
    resp.set_cookie(auth.COOKIE, token, max_age=auth.SESSION_TTL, path="/",
                    httponly=True, secure=True, samesite="lax")
    return resp
