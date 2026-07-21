"""Organization + Org Admin (PRD §2.3): company profile, knowledge base, team & access, usage &
billing. Thin HTTP layer — each handler runs its auth dependency, extracts the caller email, and
delegates to `state.org_service`; validation/orchestration live there (raising domain errors that
console/app.py maps to HTTP). Admin-only gating stays here as a FastAPI dependency (transport)."""
from fastapi import APIRouter, Depends, HTTPException

import console.state as state
from console.deps import require_authed, require_admin
from console.schemas import (OrgIn, OrgPatchIn, OrgDocIn, OrgDocPatchIn, OrgDocUseIn, OrgMemberIn,
                             OrgMemberPatchIn, OrgBillingIn, SecretCreateIn, SecretRotateIn,
                             OrgDiscoveryIn)
from software_factory import storage
from software_factory.ingestion import discovery
from software_factory.ingestion.discovery import DiscoveryError

router = APIRouter()


def _org_id_or_404(email: str) -> str:
    """Mirrors OrgService._require_org — the discovery routes need only the id, and discovery
    itself stays out of org_service (an ingestion-owned job, not org profile/KB policy)."""
    org = state.users.org_for_user(email) if email else None
    if not org:
        raise HTTPException(status_code=404, detail="no org on file")
    return org["id"]


# ── Organization (onboarding front door) ──────────────────────────────────────────────────────
# The onboarding screen reads GET /api/org on load: no org on file → first-time path; an org →
# returning path. POST creates the org + links the current user; PATCH is the Manage editor.
@router.get("/api/org")
def get_org(v: tuple = Depends(require_authed)):
    return {"org": state.org_service.get_org(v[0])}


@router.post("/api/org")
def create_org(body: OrgIn, v: tuple = Depends(require_authed)):
    return {"org": state.org_service.create_org(body, by=v[0] or "")}


@router.patch("/api/org")
def patch_org(body: OrgPatchIn, v: tuple = Depends(require_authed)):
    return {"org": state.org_service.patch_org(v[0], body)}


# Knowledge base ----------------------------------------------------------------------------------
@router.get("/api/org/docs")
def org_docs(v: tuple = Depends(require_authed)):
    return {"docs": state.org_service.list_docs(v[0])}


@router.post("/api/org/docs")
def org_doc_upload(body: OrgDocIn, v: tuple = Depends(require_admin)):
    return {"doc": state.org_service.upload_doc(v[0], body)}


@router.post("/api/org/docs/{doc_id}/use")
def org_doc_use(doc_id: int, body: OrgDocUseIn, v: tuple = Depends(require_authed)):
    return {"used_count": state.org_service.record_doc_use(v[0], doc_id, body.project_id)}


@router.patch("/api/org/docs/{doc_id}")
def org_doc_update(doc_id: int, body: OrgDocPatchIn, v: tuple = Depends(require_admin)):
    return {"doc": state.org_service.update_doc(v[0], doc_id, body.name, body.tag)}


@router.delete("/api/org/docs/{doc_id}")
def org_doc_delete(doc_id: int, v: tuple = Depends(require_admin)):
    state.org_service.delete_doc(v[0], doc_id)
    return {"ok": True}


@router.get("/api/org/docs/{doc_id}/content")
def org_doc_content(doc_id: int, v: tuple = Depends(require_authed)):
    """Raw text for the standalone Artifact Viewer (`?blob=<id>`) — the KB upload/CRUD routes
    above only ever handled metadata; this is the first thing that reads a doc's bytes back out
    of storage. Same scope check as `OrgService._org_doc_or_404`."""
    org_id = _org_id_or_404(v[0])
    blob = state.blobs.get_blob(doc_id)
    if not blob or blob["scope"] != "org" or blob["scope_id"] != org_id:
        raise HTTPException(status_code=404, detail="doc not found")
    raw = storage.get_by_path(blob["storage_key"])
    return {"content": raw.decode("utf-8", errors="replace")}


# Codebase discovery (CBT-6/7) ---------------------------------------------------------------------
@router.post("/api/org/discovery")
def start_discovery(body: OrgDiscoveryIn, v: tuple = Depends(require_admin)):
    try:
        return discovery.start(_org_id_or_404(v[0]), body.repo_url, body.pat_secret)
    except DiscoveryError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/api/org/discovery")
def discovery_status(v: tuple = Depends(require_admin)):
    return discovery.status(_org_id_or_404(v[0]))


# Team & access -----------------------------------------------------------------------------------
@router.get("/api/org/members")
def org_members(v: tuple = Depends(require_authed)):
    return state.org_service.members(v[0], (v[0] or "").lower())


@router.post("/api/org/members")
def org_member_invite(body: OrgMemberIn, v: tuple = Depends(require_admin)):
    return state.org_service.invite_member(v[0], body, me=(v[0] or "").lower(), by=v[0] or "")


@router.patch("/api/org/members/{email}")
def org_member_update(email: str, body: OrgMemberPatchIn, v: tuple = Depends(require_admin)):
    return state.org_service.update_member(v[0], email, body, me=(v[0] or "").lower(), by=v[0] or "")


@router.delete("/api/org/members/{email}")
def org_member_remove(email: str, v: tuple = Depends(require_admin)):
    return state.org_service.remove_member(v[0], email, me=(v[0] or "").lower())


# Usage & billing ---------------------------------------------------------------------------------
@router.get("/api/org/usage")
def org_usage(v: tuple = Depends(require_authed)):
    return state.org_service.usage(v[0])


@router.patch("/api/org/billing")
def org_billing(body: OrgBillingIn, v: tuple = Depends(require_admin)):
    return state.org_service.update_billing(v[0], body)


# Secrets vault -----------------------------------------------------------------------------------
@router.get("/api/org/secrets")
def list_secrets(v: tuple = Depends(require_admin)):
    return {"secrets": state.secrets_svc.list(v[0])}


@router.post("/api/org/secrets", status_code=201)
def create_secret(body: SecretCreateIn, v: tuple = Depends(require_admin)):
    return {"secret": state.secrets_svc.create(v[0], body.name, body.value, body.kind)}


@router.patch("/api/org/secrets/{name}")
def rotate_secret(name: str, body: SecretRotateIn, v: tuple = Depends(require_admin)):
    return {"secret": state.secrets_svc.rotate(v[0], name, body.value)}


@router.delete("/api/org/secrets/{name}", status_code=204)
def delete_secret(name: str, v: tuple = Depends(require_admin)):
    state.secrets_svc.delete(v[0], name)


@router.get("/api/org/secrets/{name}/ref")
def secret_ref(name: str, v: tuple = Depends(require_authed)):
    return state.secrets_svc.get_ref(v[0], name)
