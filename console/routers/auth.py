"""Auth exchange + identity/team routes: /api/auth/config, /api/auth/google, /api/me, /api/users."""
import json

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse

from software_factory import auth

import console.state as state
from console.deps import require_authed, require_staff
from console.schemas import UserMgmtIn, GoogleLoginIn, PasswordLoginIn

router = APIRouter()


# ── Identity + team ─────────────────────────────────────────────────────────────────────────
@router.get("/api/me")
def me(v: tuple = Depends(require_authed)):
    # email/role come from the per-request viewer; name + is_internal come from the user row so the
    # AccountMenu can show "name · email · role" + the OPERATOR/staff badge. name falls back to email
    # when unset. Service-token / auth-disabled sessions have no user row (email=None) → admin operator.
    email, role, _ = v
    u = state.users.get_user(email) if email else None
    name = (u.get("name") if u else None) or email
    is_internal = bool(u.get("is_internal")) if u else (role == "admin")
    return {"email": email, "role": role, "name": name, "is_internal": is_internal, "auth": auth.enabled()}


# SOF-221: the GLOBAL cross-org user directory + allowlist management. These were gated on
# require_admin (role=="admin" alone), so a non-internal customer org-admin could enumerate EVERY
# org's users (GET) and upsert/remove ANY user globally (POST — a privilege-escalation vector).
# Same root cause as the projects leak: role-only gate ignoring is_internal. Locked to require_staff
# (internal operators only). No frontend consumer — the customer team screen uses the org-scoped
# /api/org/members (see api.ts: "NOT /api/users (that's the global cross-org dir)").
@router.get("/api/users")
def list_users(v: tuple = Depends(require_staff)):
    return {"users": state.users.list_users()}


@router.post("/api/users")
def manage_users(body: UserMgmtIn, v: tuple = Depends(require_staff)):
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
    # NON-SPOOFABLE client IP for the throttle key, canonicalized for Railway's edge (verified
    # empirically on prod 2026-06-23):
    #   1) X-Envoy-External-Address — defensive first-check. Railway's current edge does NOT set it
    #      (always null here), so this is harmless dead weight today; it auto-wins if a future edge
    #      sets a real client address.
    #   2) Else X-Forwarded-For LEFTMOST entry (parts[0]). Railway's edge STRIPS any client-supplied
    #      XFF and PREPENDS the real client IP, so the leftmost is the real, non-forgeable client AND
    #      is independent of how many internal hops Railway adds (the rightmost entries are ROTATING
    #      Railway-internal addresses — unstable, useless as a throttle key). ⚠️ This non-forgeability
    #      RELIES on Railway's edge stripping inbound XFF; re-verify if the edge/ingress/routing changes.
    #   3) Else the direct socket peer (local/dev, no proxy).
    envoy = request.headers.get("x-envoy-external-address")
    if envoy:
        return envoy.strip()
    xff = request.headers.get("x-forwarded-for")
    if xff:
        parts = [p.strip() for p in xff.split(",") if p.strip()]
        if parts:
            return parts[0]              # leftmost = real client (edge-set, hop-count-independent)
    return request.client.host if request.client else "?"


@router.post("/api/auth/password")
def password_login(body: PasswordLoginIn, request: Request):
    # Email+password sign-in. Reuses the SHIPPED session model: authenticate_password applies the same
    # users-table allowlist + 'active' lifecycle gate as Google (a disabled/invited user can't get in),
    # constant-time verifies the scrypt hash, then we mint the SAME uid+token_version cookie. Generic
    # 401 for every failure (bad email, bad password, no password set, disabled) — never leak which.
    email = (body.email or "").strip().lower()
    ip = _client_ip(request)
    # Login-source audit + IP-resolution check: one structured line per attempt with the resolved IP
    # and the raw upstream headers, so we can confirm prod keeps resolving the REAL external client
    # (the edge-set leftmost XFF, not a rotating internal hop) if Railway's edge behavior changes.
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


@router.post("/api/auth/logout")
def logout():
    # Sign out = clear the session cookie. UNGATED on purpose: it must succeed idempotently even with
    # an expired/absent/invalid cookie (the user just wants out). Overwrite with an empty, immediately
    # expired cookie carrying the SAME flags+path so the browser actually drops it. The FE redirects
    # after. (This clears the cookie; bumping token_version is the server-side revoke lever for "log
    # out everywhere" — not needed for a normal sign-out.)
    resp = JSONResponse({"ok": True})
    resp.set_cookie(auth.COOKIE, "", max_age=0, path="/",
                    httponly=True, secure=True, samesite="lax")
    return resp
