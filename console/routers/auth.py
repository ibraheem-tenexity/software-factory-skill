"""Auth exchange + identity/team routes: /api/auth/config, /api/auth/google, /api/me, /api/users."""
from fastapi import APIRouter, Depends, HTTPException
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


@router.post("/api/auth/password")
def password_login(body: PasswordLoginIn):
    # Email+password sign-in. Reuses the SHIPPED session model: authenticate_password applies the same
    # users-table allowlist + 'active' lifecycle gate as Google (a disabled/invited user can't get in),
    # constant-time verifies the scrypt hash, then we mint the SAME uid+token_version cookie. Generic
    # 401 for every failure (bad email, bad password, no password set, disabled) — never leak which.
    u = state.users.authenticate_password(body.email or "", body.password or "")
    if not u:
        raise HTTPException(status_code=401, detail="invalid credentials")
    token = auth.sign_session(u["id"], int(u["token_version"]))
    resp = JSONResponse({"ok": True})
    resp.set_cookie(auth.COOKIE, token, max_age=auth.SESSION_TTL, path="/",
                    httponly=True, secure=True, samesite="lax")
    return resp
