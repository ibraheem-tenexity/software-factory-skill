"""Open / static routes: the SPA roots (/, /index.html), the gated /admin portal page, /api/health."""
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse

import console.state as state
from console.deps import viewer, _staff_session
from software_factory.workers.supervisor import _health

router = APIRouter()
_SPA_HTML_HEADERS = {"Cache-Control": "no-cache, max-age=0, must-revalidate"}


@router.get("/", response_class=HTMLResponse)
@router.get("/index.html", response_class=HTMLResponse)
def root(v: tuple = Depends(viewer)):
    # The React SPA gates login itself (reads /api/auth/config + /api/me, renders its own
    # LoginScreen on 401), so serve the bundle to everyone — authed or not. (Query strings like
    # /?run=x route here too — FastAPI matches path.)
    return HTMLResponse(state._index_html(), headers=_SPA_HTML_HEADERS)


@router.get("/ArtifactViewer.html", response_class=HTMLResponse)
@router.get("/artifactviewer.html", response_class=HTMLResponse)
def artifact_viewer(v: tuple = Depends(viewer)):
    # Standalone artifact viewer SPA entry. Auth-gated: unauthenticated callers bounce to sign-in.
    # Any authed user may open it (ownership is enforced by GET /api/artifacts/{id}).
    if not v[2]:
        return RedirectResponse("/", status_code=303)
    return HTMLResponse(state._artifact_viewer_html(), headers=_SPA_HTML_HEADERS)


@router.get("/admin", response_class=HTMLResponse)
@router.get("/admin.html", response_class=HTMLResponse)
def admin_portal(v: tuple = Depends(viewer)):
    # The Tenexity OS operator portal (separate SPA entry, React mode only) exposes CROSS-TENANT
    # data, so the PAGE is hard-gated server-side (not just the /api/admin/* data): an unauthenticated
    # caller is sent to sign in; a signed-in non-staff user (incl. a customer org-admin) gets 403.
    # Only platform staff (service token, or a human session role==admin AND is_internal==true) get it.
    if not v[2]:                                   # no session → bounce to sign-in
        return RedirectResponse("/", status_code=303)
    if not _staff_session(v):                      # signed in but not platform staff
        raise HTTPException(status_code=403, detail="forbidden")
    return HTMLResponse(state._admin_html(), headers=_SPA_HTML_HEADERS)


@router.get("/api/health")
def health():
    # Health is OPEN (platform probes don't authenticate) and carries no secrets.
    return _health()


@router.get("/api/version")
def version():
    # OPEN (no secrets): the running build's git SHA, so a deploy can be verified against the
    # expected commit — stops link-drift false-negative verifies (TEN-151 / KNOWN_ISSUES #87).
    from software_factory.version import version_info
    return version_info()
