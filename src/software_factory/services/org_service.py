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

from software_factory import notify, storage
from ..memory.ingest import maybe_ingest_async
from .errors import Invalid, NotFound
from .files import doc_kind

def summarize(org: dict | None, runs: list[dict]) -> dict:
    """Roll the org's runs into the Usage & billing payload.

    `org` is the organization record (for `plan`/`monthly_budget_cap`), or None.
    `runs` are that org's runs (already owner-filtered to org members) as returned by
    `Console.list_projects`. A run is "active" (building now) when it is neither budget-stopped,
    held, nor already shipped (has a deploy_url)."""
    org = org or {}
    by_project = [
        {"project_id": r["project_id"],
         "name": r.get("name") or r["project_id"],
         "spent_usd": round(r.get("spent_usd") or 0.0, 2)}
        for r in runs
    ]
    by_project.sort(key=lambda p: p["spent_usd"], reverse=True)
    active = sum(1 for r in runs
                 if not r.get("budget_stopped") and not r.get("held") and not r.get("deploy_url"))
    return {
        "plan": org.get("plan"),
        "monthly_budget_cap": org.get("monthly_budget_cap"),
        "spent": round(sum(p["spent_usd"] for p in by_project), 2),
        "active_projects": active,
        "total_projects": len(runs),
        "by_project": by_project,
    }



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
        count = self.blobs.record_use(doc_id, project_id)
        # SOF-32: org docs ingest lazily, on import into a project (not at KB-upload time) —
        # idempotent via content_sha256 dedup in ingest_blob, so re-importing an already-ready
        # doc into a second project is a safe no-op, not a re-ingest.
        maybe_ingest_async(doc_id, self.console)
        return count

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
        invitee = (body.email or "").strip()
        if not invitee:
            raise Invalid("email required")
        self.users.invite_member(invitee, org["id"], role=body.role or "member",
                                 designation=body.designation, by=by or "")
        # SOF-140: tell the invitee they were invited. Fire-and-forget — send_invite never raises,
        # and an email failure must NOT fail the invite (the member row is already created). The
        # UI reads invite_email_sent and says so honestly rather than pretending. No invite token /
        # link: auth is Google/password on the invited email, so signing in with it IS acceptance.
        payload = self._members_payload(org["id"], me)
        payload["invite_email_sent"] = notify.send_invite(
            invitee, org_name=org.get("name") or "Software Factory", inviter=by or me)
        return payload

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
        return summarize(org, runs)

    def update_billing(self, email: str, body) -> dict:
        org = self._require_org(email)
        fields = {k: val for k, val in body.model_dump().items() if val is not None}
        if fields:
            self.users.update_org(org["id"], **fields)
        org = self.users.get_org(org["id"])
        return {"plan": org["plan"], "monthly_budget_cap": org["monthly_budget_cap"]}
