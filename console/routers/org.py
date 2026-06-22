"""Organization + Org Admin (PRD §2.3): company profile, knowledge base, team & access, usage & billing."""
import base64

from fastapi import APIRouter, Depends, HTTPException

from software_factory import storage, billing

import console.state as state
from console.deps import require_authed, require_admin
from console.schemas import (OrgIn, OrgPatchIn, OrgDocIn, OrgDocPatchIn, OrgDocUseIn, OrgMemberIn,
                             OrgMemberPatchIn, OrgBillingIn)

router = APIRouter()


# ── Organization (onboarding front door) ──────────────────────────────────────────────────────
# The onboarding screen reads GET /api/org on load: no org on file → first-time path; an org →
# returning path. POST creates the org + links the current user; PATCH is the Manage editor.
@router.get("/api/org")
def get_org(v: tuple = Depends(require_authed)):
    return {"org": state.users.org_for_user(v[0]) if v[0] else None}


@router.post("/api/org")
def create_org(body: OrgIn, v: tuple = Depends(require_authed)):
    if not (body.name or "").strip():
        raise HTTPException(status_code=400, detail="name required")
    oid = state.users.create_org(
        body.name, industry=body.industry, sub_focus=body.sub_focus,
        headcount=body.headcount, revenue=body.revenue, location=body.location,
        website=body.website, connected_systems=body.connected_systems, by=v[0] or "")
    if v[0]:
        state.users.set_profile(v[0], org_id=oid, designation=body.designation,
                          role_description=body.role_description)
    return {"org": state.users.get_org(oid)}


@router.patch("/api/org")
def patch_org(body: OrgPatchIn, v: tuple = Depends(require_authed)):
    org = state.users.org_for_user(v[0]) if v[0] else None
    if not org:
        raise HTTPException(status_code=404, detail="no org on file")
    fields = {k: val for k, val in body.model_dump().items() if val is not None}
    state.users.update_org(org["id"], **fields)
    return {"org": state.users.get_org(org["id"])}


# ── Org admin helpers ─────────────────────────────────────────────────────────────────────────
def _caller_org(v: tuple) -> dict:
    """The org on file for the session, or 404 (mirrors PATCH /api/org)."""
    org = state.users.org_for_user(v[0]) if v[0] else None
    if not org:
        raise HTTPException(status_code=404, detail="no org on file")
    return org


def _members_payload(org_id: str, me: str) -> dict:
    return {"members": [
        {"email": m["email"], "role": m["role"], "designation": m.get("designation"),
         "you": m["email"] == me}
        for m in state.users.list_org_members(org_id)]}


def _org_doc_or_404(doc_id: int, org_id: str) -> dict:
    b = state.blobs.get_blob(doc_id)
    if not b or b["scope"] != "org" or b["scope_id"] != org_id:
        raise HTTPException(status_code=404, detail="doc not found")
    return b


# Knowledge base ----------------------------------------------------------------------------------
@router.get("/api/org/docs")
def org_docs(v: tuple = Depends(require_authed)):
    return {"docs": state.blobs.list_org_docs(_caller_org(v)["id"])}


@router.post("/api/org/docs")
def org_doc_upload(body: OrgDocIn, v: tuple = Depends(require_admin)):
    org = _caller_org(v)
    if not (body.name or "").strip():
        raise HTTPException(status_code=400, detail="name required")
    try:
        raw = base64.b64decode(body.data_b64 or "", validate=True)
    except Exception:
        raise HTTPException(status_code=400, detail="data_b64 must be valid base64")
    scope_id = f"org/{org['id']}"
    key = f"kb/{body.name}"
    storage.put(scope_id, key, raw)
    bid = state.blobs.record("org", org["id"], f"{scope_id}/{key}", name=body.name, tag=body.tag,
                       kind=state._doc_kind(body.name), content_type=body.content_type,
                       size_bytes=len(raw), sha256=storage.sha256(raw))
    doc = next((d for d in state.blobs.list_org_docs(org["id"]) if d["id"] == bid), None)
    return {"doc": doc}


@router.post("/api/org/docs/{doc_id}/use")
def org_doc_use(doc_id: int, body: OrgDocUseIn, v: tuple = Depends(require_authed)):
    org = _caller_org(v)
    _org_doc_or_404(doc_id, org["id"])
    if not (body.project_id or "").strip():
        raise HTTPException(status_code=400, detail="project_id required")
    return {"used_count": state.blobs.record_use(doc_id, body.project_id)}


@router.patch("/api/org/docs/{doc_id}")
def org_doc_update(doc_id: int, body: OrgDocPatchIn, v: tuple = Depends(require_admin)):
    org = _caller_org(v)
    _org_doc_or_404(doc_id, org["id"])
    state.blobs.update(doc_id, name=body.name, tag=body.tag)
    doc = next((d for d in state.blobs.list_org_docs(org["id"]) if d["id"] == doc_id), None)
    return {"doc": doc}


@router.delete("/api/org/docs/{doc_id}")
def org_doc_delete(doc_id: int, v: tuple = Depends(require_admin)):
    org = _caller_org(v)
    _org_doc_or_404(doc_id, org["id"])
    state.blobs.delete(doc_id)
    return {"ok": True}


# Team & access -----------------------------------------------------------------------------------
@router.get("/api/org/members")
def org_members(v: tuple = Depends(require_authed)):
    return _members_payload(_caller_org(v)["id"], (v[0] or "").lower())


@router.post("/api/org/members")
def org_member_invite(body: OrgMemberIn, v: tuple = Depends(require_admin)):
    org = _caller_org(v)
    if not (body.email or "").strip():
        raise HTTPException(status_code=400, detail="email required")
    state.users.invite_member(body.email, org["id"], role=body.role or "member",
                        designation=body.designation, by=v[0] or "")
    return _members_payload(org["id"], (v[0] or "").lower())


@router.patch("/api/org/members/{email}")
def org_member_update(email: str, body: OrgMemberPatchIn, v: tuple = Depends(require_admin)):
    org = _caller_org(v)
    member = state.users.get_user(email)
    if not member or member.get("org_id") != org["id"]:
        raise HTTPException(status_code=404, detail="member not found")
    if body.role in ("admin", "member"):
        state.users.upsert(email, body.role, by=v[0] or "")
    if body.designation is not None:
        state.users.set_profile(email, designation=body.designation)
    return _members_payload(org["id"], (v[0] or "").lower())


@router.delete("/api/org/members/{email}")
def org_member_remove(email: str, v: tuple = Depends(require_admin)):
    org = _caller_org(v)
    member = state.users.get_user(email)
    if not member or member.get("org_id") != org["id"]:
        raise HTTPException(status_code=404, detail="member not found")
    state.users.remove(email)
    return _members_payload(org["id"], (v[0] or "").lower())


# Usage & billing ---------------------------------------------------------------------------------
@router.get("/api/org/usage")
def org_usage(v: tuple = Depends(require_authed)):
    org = _caller_org(v)
    member_emails = {m["email"].lower() for m in state.users.list_org_members(org["id"])}
    runs = [r for r in state.console.list_projects(owner=None)
            if (r.get("owner") or "").lower() in member_emails]
    return billing.summarize(org, runs)


@router.patch("/api/org/billing")
def org_billing(body: OrgBillingIn, v: tuple = Depends(require_admin)):
    org = _caller_org(v)
    fields = {k: val for k, val in body.model_dump().items() if val is not None}
    if fields:
        state.users.update_org(org["id"], **fields)
    org = state.users.get_org(org["id"])
    return {"plan": org["plan"], "monthly_budget_cap": org["monthly_budget_cap"]}
