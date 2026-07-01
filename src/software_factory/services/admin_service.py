"""Tenexity OS operator-portal business logic (PRD §3) — CROSS-TENANT.

The `console/routers/admin_os.py` handlers used to inline the cross-tenant aggregation, the fat
invite orchestration, and the staff-admin lockout guards. This service owns all of that; the router
runs the `require_staff` gate and calls one method here. Framework-free — raises the domain errors in
`errors.py` (mapped to HTTP by console/app.py), never FastAPI's HTTPException.
"""
from __future__ import annotations

import datetime
import os

from software_factory import tenexity_os
from software_factory.agent_prompts import override_key
from software_factory.users import TENEXITY_ORG_ID
from .errors import Invalid, NotFound, Conflict, Unprocessable


def _midnight_epoch() -> float:
    now = datetime.datetime.now()
    return now.replace(hour=0, minute=0, second=0, microsecond=0).timestamp()


class AdminService:
    def __init__(self, console, users, agent_store, tool_store, prompts, sow_store):
        self.console = console
        self.users = users
        self.agent_store = agent_store
        self.tool_store = tool_store
        self.prompts = prompts
        self.sow_store = sow_store

    # ── cross-tenant context + dashboards ─────────────────────────────────────────────
    def _context(self):
        """Shared cross-tenant reads: all projects, all orgs, members-by-org, owner→org-name map."""
        runs = self.console.list_projects(owner=None)
        orgs = self.users.list_orgs()
        members_by_org = {o["id"]: self.users.list_org_members(o["id"]) for o in orgs}
        o2o = tenexity_os.owner_to_org(orgs, members_by_org)
        return runs, orgs, members_by_org, o2o

    def overview(self) -> dict:
        runs, orgs, _members, o2o = self._context()
        rollups = tenexity_os.agent_rollups()
        roster = tenexity_os.agent_roster(self.agent_store.all(), rollups, self.prompts.all())
        return tenexity_os.overview(orgs, runs, rollups, tenexity_os.agents_active_count(),
                                    tenexity_os.today_burn(_midnight_epoch()), roster, o2o)

    def clients(self) -> dict:
        runs, orgs, members_by_org, _o2o = self._context()
        return {"clients": tenexity_os.client_rows(orgs, runs, members_by_org,
                                                   tenexity_os.open_tickets_by_project())}

    def projects(self, mode: str = "all") -> dict:
        runs, _orgs, _members, o2o = self._context()
        return {"projects": tenexity_os.project_rows(runs, o2o, tenexity_os.ticket_counts_by_project(),
                                                     mode=mode)}

    def set_demo(self, pid: str, is_demo: bool) -> dict:
        return {"project_id": pid, "is_demo": self.console.set_demo(pid, is_demo)}

    # ── agents ─────────────────────────────────────────────────────────────────────────
    def agents(self) -> dict:
        # The 4 REAL orchestrators (STAGE-1/2/3 + CONCIERGE) have BOTH a registry row AND a richer live
        # card. Render each ONCE: the live card wins for those callsigns; the roster contributes only
        # OTHER (custom) agents → no dupes.
        live = tenexity_os.live_agent_cards()
        live_cs = {c["callsign"] for c in live}
        roster = tenexity_os.agent_roster(self.agent_store.all(), tenexity_os.agent_rollups(),
                                          self.prompts.all())
        return {"agents": [r for r in roster if r["callsign"] not in live_cs] + live}

    def sync_agents(self) -> dict:
        agents = self.agent_store.sync_real_agents()
        return {"synced": len(agents), "agents": agents}

    def agent(self, callsign: str, runtime: str = "claude") -> dict:
        live = tenexity_os.live_agent_detail(callsign, runtime)
        if live:
            ov = self.prompts.get(override_key(callsign, live.get("runtime")))
            if ov:
                live = {**live, "prompt": ov["prompt"], "version": ov["version"], "is_default": False,
                        "overridden": True, "updated_by": ov["updated_by"], "updated_at": ov["updated_at"]}
            else:
                live = {**live, "version": 0, "is_default": True, "overridden": False}
            return {**live, "tools": [t for t in self.tool_store.all() if t["status"] == "connected"],
                    "activity": []}
        cs = callsign.upper()
        card = next((a for a in tenexity_os.agent_roster(self.agent_store.all(), tenexity_os.agent_rollups(),
                                                         self.prompts.all()) if a["callsign"] == cs), None)
        if not card:
            raise NotFound("unknown agent")
        p = self.prompts.get(cs)
        return {**card, "prompt": p["prompt"] if p else "",
                "prompt_applied": False,
                "tools": [t for t in self.tool_store.all() if t["status"] == "connected"],
                "activity": []}

    def create_agent(self, body) -> dict:
        cs = (body.callsign or "").strip().upper()
        if not cs or not (body.name or "").strip():
            raise Invalid("callsign + name required")
        if self.agent_store.get(cs):
            raise Conflict("callsign exists")
        return {"agent": self.agent_store.create(cs, body.name, role=body.role, model=body.model,
                                                 cost_tier=body.cost_tier, descr=body.descr)}

    def update_agent(self, callsign: str, body) -> dict:
        cs = callsign.upper()
        if not self.agent_store.get(cs):
            raise NotFound("unknown agent")
        fields = {k: val for k, val in body.model_dump().items() if val is not None}
        return {"agent": self.agent_store.update(cs, fields)}

    def delete_agent(self, callsign: str) -> dict:
        cs = callsign.upper()
        if tenexity_os.is_editable_orchestrator(cs):
            raise Conflict("structural agent — required by the pipeline")
        if not self.agent_store.get(cs):
            raise NotFound("unknown agent")
        self.agent_store.delete(cs)
        return {"ok": True}

    def _stage_runtime(self, cs: str, runtime: str | None) -> str | None:
        """Validate + normalize the runtime for a prompt write/revert: required (claude|opencode) for
        stage skills, ignored for the concierge."""
        if not cs.startswith("STAGE-"):
            return None
        if runtime not in ("claude", "opencode"):
            raise Invalid("runtime (claude|opencode) required for stage skills")
        return runtime

    def set_prompt(self, callsign: str, body, by: str) -> dict:
        cs = callsign.upper()
        if tenexity_os.is_editable_orchestrator(cs):
            rt = self._stage_runtime(cs, body.runtime)
            row = self.prompts.set(override_key(cs, rt), body.prompt or "", by=by or "")
            return {"callsign": cs, "runtime": rt, "version": row["version"],
                    "updated_by": row["updated_by"], "updated_at": row["updated_at"],
                    "applied": True, "is_default": False}
        row = self.prompts.set(cs, body.prompt or "", by=by or "")
        return {"callsign": row["callsign"], "prompt": row["prompt"], "version": row["version"],
                "updated_by": row["updated_by"], "updated_at": row["updated_at"],
                "applied": False}

    def revert_prompt(self, callsign: str, runtime: str | None = None) -> dict:
        cs = callsign.upper()
        if not tenexity_os.is_editable_orchestrator(cs):
            raise NotFound("no editable override for this agent")
        rt = self._stage_runtime(cs, runtime)
        self.prompts.delete(override_key(cs, rt))
        return {"callsign": cs, "runtime": rt, "version": 0, "is_default": True}

    # ── tools / MCP registry ─────────────────────────────────────────────────────────
    def tools(self) -> dict:
        return {"tools": [{**t, "used": None} for t in self.tool_store.all()]}

    def create_tool(self, body) -> dict:
        if not (body.name or "").strip():
            raise Invalid("name required")
        return {"tool": self.tool_store.create(body.name, type=body.type, provider=body.provider,
                                               scope=body.scope, auth=body.auth, status=body.status)}

    def update_tool(self, tool_id: int, body) -> dict:
        fields = {k: val for k, val in body.model_dump().items() if val is not None}
        tool = self.tool_store.update(tool_id, fields)
        if not tool:
            raise NotFound("unknown tool")
        return {"tool": tool}

    def delete_tool(self, tool_id: int) -> dict:
        self.tool_store.delete(tool_id)
        return {"ok": True}

    # ── clients / tenants (admin-scoped org CRUD) ──────────────────────────────────────
    def create_client(self, body, by: str) -> dict:
        if not (body.name or "").strip():
            raise Invalid("name required")
        oid = self.users.create_org(body.name, industry=body.industry, website=body.website, by=by or "")
        return {"client": self.users.get_org(oid)}

    def update_client(self, org_id: str, body) -> dict:
        if not self.users.get_org(org_id):
            raise NotFound("unknown org")
        fields = {k: val for k, val in body.model_dump().items() if val is not None}
        self.users.update_org(org_id, **fields)
        return {"client": self.users.get_org(org_id)}

    def delete_client(self, org_id: str) -> dict:
        if not self.users.get_org(org_id):
            raise NotFound("unknown org")
        self.users.delete_org(org_id)
        return {"ok": True}

    # ── invites / allow-list ───────────────────────────────────────────────────────────
    def _access_rows(self) -> dict:
        out = []
        for u in self.users.list_users():
            staff = u.get("is_internal") in (1, True)
            org = self.users.get_org(u["org_id"]) if u.get("org_id") else None
            out.append({"email": u["email"], "type": "Tenexity" if staff else "New org",
                        "org": "Tenexity" if staff else (org["name"] if org else None),
                        "role": u["role"], "status": u.get("status") or "active",
                        "name": u.get("name"), "designation": u.get("designation"),
                        "sign_in_method": u.get("sign_in_method"), "last_active": u.get("last_active"),
                        "invited_by": u.get("invited_by")})
        return {"users": out}

    def access(self) -> dict:
        return self._access_rows()

    def invite(self, body, by: str) -> dict:
        email = (body.email or "").strip().lower()
        if not email:
            raise Invalid("email required")
        method = body.method or "google"
        if method == "password" and not (body.password or ""):
            raise Invalid("password required when method is 'password'")
        role = body.role if body.role in ("admin", "member") else None
        if body.access_type == "tenexity":
            self.users.upsert(email, role or "member", by=by)   # staff default member unless role given
            self.users.set_profile(email, is_internal=True, org_id=TENEXITY_ORG_ID,
                                   name=body.name, designation=body.designation, sign_in_method=method)
        else:
            if not (body.org_name or "").strip():
                raise Invalid("org_name required for a new org")
            oid = self.users.create_org(body.org_name, by=by)
            self.users.invite_member(email, oid, role=role or "admin", by=by)  # org default admin
            self.users.set_profile(email, name=body.name, designation=body.designation,
                                   sign_in_method=method)
        if method == "password":
            self.users.set_password(email, body.password)
            self.users.set_status(email, "active")
        else:
            self.users.set_status(email, "invited")
        return self._access_rows()

    def access_update(self, email: str, body, caller: str) -> dict:
        em = (email or "").strip().lower()
        u = self.users.get_user(em)
        if not u:
            raise NotFound("unknown user")

        def _is_staff_admin(role, internal, status):
            return role == "admin" and internal in (1, True) and (status or "active") != "disabled"
        cur_role, cur_internal, cur_status = u["role"], u.get("is_internal"), (u.get("status") or "active")
        new_role = body.role if body.role in ("admin", "member") else cur_role
        new_internal = body.is_internal if body.is_internal is not None else cur_internal
        new_status = body.status if body.status in ("active", "invited", "disabled") else cur_status
        was = _is_staff_admin(cur_role, cur_internal, cur_status)
        will = _is_staff_admin(new_role, new_internal, new_status)

        if was and not will:
            if em == (caller or "").lower():
                raise Conflict("cannot remove your own staff-admin access")
            others = [x for x in self.users.list_users()
                      if (x["email"] or "").lower() != em
                      and _is_staff_admin(x["role"], x.get("is_internal"), x.get("status"))]
            if not others:
                raise Conflict("cannot remove the last Tenexity staff admin")

        if body.role in ("admin", "member"):
            self.users.upsert(em, body.role, by=caller or "")
        if body.is_internal is not None:
            self.users.set_profile(em, is_internal=body.is_internal)
        if body.status == "disabled":
            self.users.disable(em)
        elif body.status in ("active", "invited"):
            self.users.set_status(em, body.status)
        return self._access_rows()

    def access_resend(self, email: str) -> dict:
        em = (email or "").strip().lower()
        u = self.users.get_user(em)
        if not u:
            raise NotFound("unknown user")
        if (u.get("status") or "active") != "invited":
            raise Conflict(f"user is '{u.get('status', 'active')}' — only invited users can be resent")
        base = (os.environ.get("SF_APP_URL") or "").rstrip("/")
        return {"email": em, "status": "invited", "link": f"{base}/" if base else "/"}

    def access_revoke(self, email: str) -> dict:
        self.users.disable((email or "").strip().lower())
        return self._access_rows()

    # ── SOW (Statement of Work) CRUD ────────────────────────────────────────────────────
    def sow_list(self) -> dict:
        return {"sows": self.sow_store.list_all()}

    def sow_get(self, sow_id: int) -> dict:
        row = self.sow_store.get(sow_id)
        if not row:
            raise NotFound("sow not found")
        return row

    def sow_create(self, body) -> dict:
        try:
            return self.sow_store.create(
                body.title,
                org=body.org, project=body.project, value=body.value,
                file=body.file, version=body.version, status=body.status, body=body.body,
            )
        except ValueError as e:
            raise Unprocessable(str(e))

    def sow_update(self, sow_id: int, body) -> dict:
        if not self.sow_store.get(sow_id):
            raise NotFound("sow not found")
        try:
            return self.sow_store.update(sow_id, body.model_dump(exclude_none=True))
        except ValueError as e:
            raise Unprocessable(str(e))
