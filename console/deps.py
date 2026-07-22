"""Auth dependencies — the DI gates every router shares. Behavior unchanged from the monolith."""
import time

from fastapi import Depends, HTTPException, Request

from software_factory import auth
from software_factory.log import get_logger

import console.state as state

logger = get_logger(__name__)

_LAST_ACTIVE_THROTTLE = 60   # seconds — don't write last_active more than once a minute per user


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
            la = u.get("last_active")              # epoch seconds (Decimal from PG) or None
            if la is None or (time.time() - float(la)) > _LAST_ACTIVE_THROTTLE:
                try:
                    state.users.touch_last_active(u["id"])
                except Exception:
                    # activity stamp is best-effort; never fail a request on it — but log why it failed
                    logger.exception("[auth] last_active stamp failed for uid %s (best-effort, ignored)",
                                     u["id"])
            return (u["email"], u["role"], True)
    return (None, None, False)


def require_authed(v: tuple = Depends(viewer)) -> tuple:
    if not v[2]:
        raise HTTPException(status_code=401, detail="unauthorized")
    return v


def _can_see(v: tuple, project_id: str) -> bool:
    """Ownership + tenancy gate enforced on EVERY run-scoped route — filtering the list is not
    enough, a caller could fetch another's run by URL. SOF-221: this gated on role=="admin" ALONE,
    so a non-internal customer org-admin could fetch ANY org's run by id. Now driven by the shared
    `project_visibility` boundary so the list and the per-run gate can't diverge: internal
    staff/service = all; a non-internal org-admin = only their org's runs; a member = own only."""
    if not v[2]:
        return False
    scope = project_visibility(v)
    if scope is None:                      # internal staff / service token = cross-tenant god view
        return True
    owner = (state.console.records.project_owner(project_id) or "").lower() if project_id else ""
    return bool(owner) and owner in scope


def authorize_project(pid: str, v: tuple = Depends(require_authed)) -> tuple:
    """For run-scoped routes carrying {pid}: 404 if the project doesn't exist, 403 if not the owner."""
    if not state.console.project_exists(pid):
        raise HTTPException(status_code=404, detail="project not found")
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


def _org_of(email: str | None) -> str | None:
    """The org_id a user email belongs to, or None (unknown user / no org on file)."""
    u = state.users.get_user((email or "").lower())
    return (u.get("org_id") or None) if u else None


def project_visibility(v: tuple):
    """The set of run-OWNER emails this session may see, or None for the full cross-tenant view.

    THE single run-tenancy boundary (SOF-221) — used by BOTH the `/api/projects` list and the
    per-run `_can_see` gate so the two can't drift (they had: the list showed a role==admin caller
    every org's runs, and the gate let them fetch any run by id). Mirrors `_staff_session`:
      - internal staff / service token → None (operator god-view; unchanged).
      - non-internal org-admin → every member of THEIR org (incl. self). Runs are owner(email)-
        scoped with no org_id column, so a run's org is derived LIVE from its owner's users.org_id
        (owner ∈ the admin's org's members) — no projectstate backfill/migration needed.
      - a member, or an admin with no org on file → only themselves (can't leak).
    """
    email, role, ok = v
    if not ok:
        return set()
    if _staff_session(v):
        return None
    me = (email or "").lower()
    if role == "admin":
        org_id = _org_of(me)
        if org_id:
            emails = {(m.get("email") or "").lower() for m in state.users.list_org_members(org_id)}
            emails.add(me)
            return emails
    return {me}
