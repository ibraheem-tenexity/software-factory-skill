"""Organization + Org Admin business logic (PRD §2.3): company profile, knowledge base, team &
access, usage & billing.

This is the orchestration the `console/routers/org.py` handlers used to inline — validation, base64
decode, storage I/O, the DB writes, and read-back composition. The router is now thin: it runs the
auth dependency, extracts the caller email, and calls one method here. Failures are signalled with the
domain errors in `errors.py` (mapped to HTTP by console/app.py). Auth gating (admin-only routes) stays
in the router as a FastAPI dependency — that's a transport concern, not business logic.
"""
from __future__ import annotations

import base64

from software_factory import storage, billing
from .errors import Invalid, NotFound
from .files import doc_kind


class OrgService:
    def __init__(self, users, blobs, console):
        self.users = users
        self.blobs = blobs
        self.console = console

    # ── organization profile ────────────────────────────────────────────────────────────────
    def get_org(self, email: str) -> dict | None:
        return self.users.org_for_user(email) if email else None

    def create_org(self, body, by: str) -> dict:
        if not (body.name or "").strip():
            raise Invalid("name required")
        oid = self.users.create_org(
            body.name, industry=body.industry, sub_focus=body.sub_focus,
            headcount=body.headcount, revenue=body.revenue, location=body.location,
            website=body.website, connected_systems=body.connected_systems, by=by or "")
        if by:
            self.users.set_profile(by, org_id=oid, designation=body.designation,
                                   role_description=body.role_description)
        return self.users.get_org(oid)

    def patch_org(self, email: str, body) -> dict:
        org = self._require_org(email)
        fields = {k: val for k, val in body.model_dump().items() if val is not None}
        self.users.update_org(org["id"], **fields)
        return self.users.get_org(org["id"])

    # ── helpers ─────────────────────────────────────────────────────────────────────────────
    def _require_org(self, email: str) -> dict:
        """The org on file for the session, or 404 (mirrors PATCH /api/org)."""
        org = self.users.org_for_user(email) if email else None
        if not org:
            raise NotFound("no org on file")
        return org

    def _members_payload(self, org_id: str, me: str) -> dict:
        return {"members": [
            {"email": m["email"], "role": m["role"], "designation": m.get("designation"),
             "you": m["email"] == me}
            for m in self.users.list_org_members(org_id)]}

    def _org_doc_or_404(self, doc_id: int, org_id: str) -> dict:
        b = self.blobs.get_blob(doc_id)
        if not b or b["scope"] != "org" or b["scope_id"] != org_id:
            raise NotFound("doc not found")
        return b

    # ── knowledge base ──────────────────────────────────────────────────────────────────────
    def list_docs(self, email: str) -> list[dict]:
        return self.blobs.list_org_docs(self._require_org(email)["id"])

    def upload_doc(self, email: str, body) -> dict | None:
        org = self._require_org(email)
        if not (body.name or "").strip():
            raise Invalid("name required")
        try:
            raw = base64.b64decode(body.data_b64 or "", validate=True)
        except Exception:
            raise Invalid("data_b64 must be valid base64")
        scope_id = f"org/{org['id']}"
        key = f"kb/{body.name}"
        storage.put(scope_id, key, raw)
        bid = self.blobs.record("org", org["id"], f"{scope_id}/{key}", name=body.name, tag=body.tag,
                                kind=doc_kind(body.name), content_type=body.content_type,
                                size_bytes=len(raw), sha256=storage.sha256(raw))
        return next((d for d in self.blobs.list_org_docs(org["id"]) if d["id"] == bid), None)

    def record_doc_use(self, email: str, doc_id: int, project_id: str) -> int:
        org = self._require_org(email)
        self._org_doc_or_404(doc_id, org["id"])
        if not (project_id or "").strip():
            raise Invalid("project_id required")
        return self.blobs.record_use(doc_id, project_id)

    def update_doc(self, email: str, doc_id: int, name, tag) -> dict | None:
        org = self._require_org(email)
        self._org_doc_or_404(doc_id, org["id"])
        self.blobs.update(doc_id, name=name, tag=tag)
        return next((d for d in self.blobs.list_org_docs(org["id"]) if d["id"] == doc_id), None)

    def delete_doc(self, email: str, doc_id: int) -> None:
        org = self._require_org(email)
        self._org_doc_or_404(doc_id, org["id"])
        self.blobs.delete(doc_id)

    # ── team & access ───────────────────────────────────────────────────────────────────────
    def members(self, email: str, me: str) -> dict:
        return self._members_payload(self._require_org(email)["id"], me)

    def invite_member(self, email: str, body, me: str, by: str) -> dict:
        org = self._require_org(email)
        if not (body.email or "").strip():
            raise Invalid("email required")
        self.users.invite_member(body.email, org["id"], role=body.role or "member",
                                 designation=body.designation, by=by or "")
        return self._members_payload(org["id"], me)

    def update_member(self, email: str, target: str, body, me: str, by: str) -> dict:
        org = self._require_org(email)
        member = self.users.get_user(target)
        if not member or member.get("org_id") != org["id"]:
            raise NotFound("member not found")
        if body.role in ("admin", "member"):
            self.users.upsert(target, body.role, by=by or "")
        if body.designation is not None:
            self.users.set_profile(target, designation=body.designation)
        return self._members_payload(org["id"], me)

    def remove_member(self, email: str, target: str, me: str) -> dict:
        org = self._require_org(email)
        member = self.users.get_user(target)
        if not member or member.get("org_id") != org["id"]:
            raise NotFound("member not found")
        self.users.remove(target)
        return self._members_payload(org["id"], me)

    # ── usage & billing ─────────────────────────────────────────────────────────────────────
    def usage(self, email: str) -> dict:
        org = self._require_org(email)
        member_emails = {m["email"].lower() for m in self.users.list_org_members(org["id"])}
        runs = [r for r in self.console.list_projects(owner=None)
                if (r.get("owner") or "").lower() in member_emails]
        return billing.summarize(org, runs)

    def update_billing(self, email: str, body) -> dict:
        org = self._require_org(email)
        fields = {k: val for k, val in body.model_dump().items() if val is not None}
        if fields:
            self.users.update_org(org["id"], **fields)
        org = self.users.get_org(org["id"])
        return {"plan": org["plan"], "monthly_budget_cap": org["monthly_budget_cap"]}
