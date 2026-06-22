"""Auth dependencies — the DI gates every router shares. Behavior unchanged from the monolith."""
from fastapi import Depends, HTTPException, Request

from software_factory import auth

import console.state as state


def viewer(request: Request) -> tuple:
    """(email, role, ok). ok = authorized to use the API at all. Auth disabled (local/dev) or a valid
    service token = full admin access. A session cookie is verified (HMAC signature + expiry), then the
    user is loaded from the DB and the role resolved PER REQUEST — rejecting a disabled user or a stale
    token_version. Role is NOT carried in the cookie, so a demotion/revoke takes effect on the next request."""
    if not auth.enabled():
        return (None, "admin", True)
    if auth.service_token_ok(request.headers.get(auth.SERVICE_HEADER)):
        return (None, "admin", True)
    payload = auth.verify_session(request.cookies.get(auth.COOKIE))
    if payload:
        u = state.users.get_by_id(payload.get("uid"))
        if u and u["status"] == "active" and int(u["token_version"]) == int(payload.get("tv", -1)):
            return (u["email"], u["role"], True)
    return (None, None, False)


def require_authed(v: tuple = Depends(viewer)) -> tuple:
    if not v[2]:
        raise HTTPException(status_code=401, detail="unauthorized")
    return v


def _can_see(v: tuple, project_id: str) -> bool:
    """Ownership gate enforced on EVERY run-scoped route — filtering the list is not enough,
    a member could fetch another's run by URL. Admin/service = all; member = own only."""
    email, role, ok = v
    if not ok:
        return False
    if role == "admin":
        return True
    return bool(project_id) and state.console.project_owner(project_id) == (email or "").lower()


def authorize_project(pid: str, v: tuple = Depends(require_authed)) -> tuple:
    """For run-scoped routes carrying {pid}: 403 unless admin/service or the run's owner."""
    if not _can_see(v, pid):
        raise HTTPException(status_code=403, detail="forbidden")
    return v


def require_admin(v: tuple = Depends(require_authed)) -> tuple:
    if v[1] != "admin":
        raise HTTPException(status_code=403, detail="admin only")
    return v


def _staff_session(v: tuple) -> bool:
    """May this session reach Tenexity OS (cross-tenant data + the operator portal)? Service token /
    auth-disabled (viewer email=None, role=admin) → yes (bots/CI). A HUMAN session must be BOTH
    role==admin AND is_internal==true — a customer org-admin or any non-staff member never qualifies."""
    email, role, ok = v
    if not ok:
        return False
    if email is None and role == "admin":          # service token or auth disabled = platform access
        return True
    u = state.users.get_user((email or "").lower())
    return bool(role == "admin" and u and u.get("is_internal") in (1, True))


def require_staff(v: tuple = Depends(require_authed)) -> tuple:
    """Tenexity OS API gate (§3): platform staff ONLY — cross-tenant data. See `_staff_session`."""
    if not _staff_session(v):
        raise HTTPException(status_code=403, detail="staff only")
    return v
