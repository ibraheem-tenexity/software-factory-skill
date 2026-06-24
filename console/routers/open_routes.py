"""Open / static routes: the SPA roots (/, /index.html), the gated /admin portal page, /api/health."""
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse

import console.state as state
from console.deps import viewer, _staff_session
from console.poller import _health

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
@router.get("/index.html", response_class=HTMLResponse)
def root(v: tuple = Depends(viewer)):
    # The root serves the Google sign-in page when auth is on and the caller has no session;
    # otherwise the console. (Query strings like /?run=x route here too — FastAPI matches path.)
    # React mode: the SPA gates login itself (reads /api/auth/config + /api/me, renders its own
    # LoginScreen on 401), so serve the bundle to unauthed users too. Legacy mode keeps the
    # server-rendered login page.
    if state._react_enabled():
        return HTMLResponse(state._index_html())
    if not v[2]:
        return HTMLResponse(state._login_html())
    return HTMLResponse(state._index_html())


@router.get("/ArtifactViewer.html", response_class=HTMLResponse)
@router.get("/artifactviewer.html", response_class=HTMLResponse)
def artifact_viewer(v: tuple = Depends(viewer)):
    # Standalone artifact viewer SPA entry (React mode only). Auth-gated: unauthenticated callers
    # bounce to sign-in. Any authed user may open it (ownership is enforced by GET /api/artifacts/{id}).
    if not state._react_enabled():
        raise HTTPException(status_code=404, detail="not found")
    if not v[2]:
        return RedirectResponse("/", status_code=303)
    return HTMLResponse(state._artifact_viewer_html())


@router.get("/admin", response_class=HTMLResponse)
@router.get("/admin.html", response_class=HTMLResponse)
def admin_portal(v: tuple = Depends(viewer)):
    # The Tenexity OS operator portal (separate SPA entry, React mode only) exposes CROSS-TENANT
    # data, so the PAGE is hard-gated server-side (not just the /api/admin/* data): an unauthenticated
    # caller is sent to sign in; a signed-in non-staff user (incl. a customer org-admin) gets 403.
    # Only platform staff (service token, or a human session role==admin AND is_internal==true) get it.
    if not state._react_enabled():
        raise HTTPException(status_code=404, detail="not found")
    if not v[2]:                                   # no session → bounce to sign-in
        return RedirectResponse("/", status_code=303)
    if not _staff_session(v):                      # signed in but not platform staff
        raise HTTPException(status_code=403, detail="forbidden")
    return HTMLResponse(state._admin_html())


@router.get("/api/health")
def health():
    # Health is OPEN (platform probes don't authenticate) and carries no secrets.
    return _health()
