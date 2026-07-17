"""Tenexity OS operator-portal business logic (PRD §3) — CROSS-TENANT.

The `console/routers/admin_os.py` handlers used to inline the cross-tenant aggregation, the fat
invite orchestration, and the staff-admin lockout guards. This service owns all of that; the router
runs the `require_staff` gate and calls one method here. Framework-free — raises the domain errors in
`errors.py` (mapped to HTTP by console/app.py), never FastAPI's HTTPException.
"""
from __future__ import annotations

import base64
import datetime
import json
import logging
import os

from software_factory import notify, tenexity_os
from software_factory.users import TENEXITY_ORG_ID
from .errors import Invalid, NotFound, Conflict, Unprocessable
from .org_service import CONSOLE_URL


def _midnight_epoch() -> float:
    now = datetime.datetime.now()
    return now.replace(hour=0, minute=0, second=0, microsecond=0).timestamp()


def _parse_date(label: str, value: str | None) -> datetime.datetime | None:
    """ISO 8601 in, `None` through unchanged — the conversations filter's date_from/date_to are
    optional query strings, not required to be present."""
    if value is None:
        return None
    try:
        return datetime.datetime.fromisoformat(value)
    except ValueError:
        raise Invalid(f"invalid {label} — expected ISO 8601")


def _encode_cursor(last_activity: datetime.datetime, session_id: str) -> str:
    """Opaque keyset-pagination cursor for admin_conversations: (last_activity, session_id) from
    the previous page's last row. Base64 so it's a single URL-safe query-param token; no codebase
    convention existed for this yet (checked — see SOF-34 research), so this one is it."""
    raw = json.dumps([last_activity.isoformat(), session_id])
    return base64.urlsafe_b64encode(raw.encode()).decode()


def _decode_cursor(cursor: str) -> tuple[datetime.datetime, str]:
    try:
        raw = base64.urlsafe_b64decode(cursor.encode()).decode()
        ts_str, session_id = json.loads(raw)
        return datetime.datetime.fromisoformat(ts_str), session_id
    except Exception:
        raise Invalid("invalid cursor")


class AdminService:
    def __init__(self, console, users, agent_store, tool_store, sow_store, conversation_repo):
        self.console = console
        self.users = users
        self.agent_store = agent_store   # SystemAgentStore — identity + prompt + model_id in one row
        self.tool_store = tool_store
        self.sow_store = sow_store
        self.conversation_repo = conversation_repo

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
        roster = tenexity_os.agent_roster(self.agent_store.all(), rollups)
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
        # The 4 orchestrators (STAGE-1/2/3 + CONCIERGE) have BOTH a system_agents row AND a richer
        # live card. Render each ONCE: the live card wins for those callsigns; the roster contributes
        # only OTHER (custom) agents → no dupes.
        live = tenexity_os.live_agent_cards()
        live_cs = {c["callsign"] for c in live}
        roster = tenexity_os.agent_roster(self.agent_store.all(), tenexity_os.agent_rollups())
        return {"agents": [r for r in roster if r["callsign"] not in live_cs] + live}

    def sync_agents(self) -> dict:
        # No-op: nothing is seeded from code anymore. The OS shows only the system_agents rows that
        # actually exist, so there is no canonical roster to reconcile. Kept so the existing
        # POST /api/admin/agents/sync route still returns cleanly.
        agents = self.agent_store.all()
        return {"synced": 0, "agents": agents}

    def agent(self, callsign: str, runtime: str = "claude") -> dict:
        cs = callsign.upper()
        row = self.agent_store.get(cs)
        live = tenexity_os.live_agent_detail(callsign, runtime)
        if live:
            # The stored system_agents row (if any) supplies the operator-edited prompt + version +
            # model; the live card supplies the read-only file/code-backed defaults. system_agents
            # has ONE row per stage callsign (no per-runtime override key anymore).
            if row and (row.get("prompt") or "").strip():
                live = {**live, "prompt": row["prompt"], "version": row["version"], "is_default": False,
                        "overridden": True, "updated_by": row["updated_by"], "updated_at": row["updated_at"]}
            else:
                live = {**live, "version": (row["version"] if row else 0), "is_default": True,
                        "overridden": False}
            if row and row.get("model_id"):
                live = {**live, "model": row["model_id"]}
            return {**live, "tools": [t for t in self.tool_store.all() if cs in (t.get("attached_to") or [])],
                    "activity": []}
        card = next((a for a in tenexity_os.agent_roster(self.agent_store.all(),
                                                         tenexity_os.agent_rollups())
                     if a["callsign"] == cs), None)
        if not card:
            raise NotFound("unknown agent")
        return {**card, "prompt": row["prompt"] if row else "",
                "prompt_applied": False,
                "tools": [t for t in self.tool_store.all() if cs in (t.get("attached_to") or [])],
                "activity": []}

    def create_agent(self, body) -> dict:
        cs = (body.callsign or "").strip().upper()
        if not cs or not (body.name or "").strip():
            raise Invalid("callsign + name required")
        if self.agent_store.get(cs):
            raise Conflict("callsign exists")
        # system_agents has no role/cost_tier/descr columns; body.model maps to model_id.
        return {"agent": self.agent_store.set(cs, name=body.name, model_id=body.model, by="")}

    def update_agent(self, callsign: str, body) -> dict:
        cs = callsign.upper()
        if not self.agent_store.get(cs):
            raise NotFound("unknown agent")
        # Only name + model_id are real system_agents columns; role/cost_tier/descr are ignored
        # (those registry columns no longer exist). model → model_id.
        return {"agent": self.agent_store.set(cs, name=body.name, model_id=body.model, by="")}

    def delete_agent(self, callsign: str) -> dict:
        cs = callsign.upper()
        if tenexity_os.is_editable_orchestrator(cs):
            raise Conflict("structural agent — required by the pipeline")
        if not self.agent_store.get(cs):
            raise NotFound("unknown agent")
        self.agent_store.delete(cs)
        return {"ok": True}

    def set_prompt(self, callsign: str, body, by: str) -> dict:
        # ONE row per callsign (the old per-runtime STAGE-1::claude override key is collapsed to the
        # bare stage callsign). The save updates the prompt (and/or model_id) and bumps version.
        cs = callsign.upper()
        applied = tenexity_os.is_editable_orchestrator(cs)
        row = self.agent_store.set(cs, prompt=body.prompt or "", by=by or "")
        return {"callsign": cs, "prompt": row["prompt"], "version": row["version"],
                "updated_by": row["updated_by"], "updated_at": row["updated_at"],
                "applied": applied, "is_default": False}

    def revert_prompt(self, callsign: str, runtime: str | None = None) -> dict:
        cs = callsign.upper()
        if not tenexity_os.is_editable_orchestrator(cs):
            raise NotFound("no editable override for this agent")
        # Revert = clear the stored override so the on-disk/code default drives the run again. The
        # whole system_agents row is the override, so dropping it is the revert.
        self.agent_store.delete(cs)
        return {"callsign": cs, "version": 0, "is_default": True}

    # ── tools / MCP registry (SOF-81) ────────────────────────────────────────────────
    def tools(self) -> dict:
        return {"tools": self.tool_store.all()}

    def create_tool(self, body, by: str) -> dict:
        name = (body.name or "").strip()
        if not name:
            raise Invalid("name required")
        if self.tool_store.get(name):
            raise Invalid(f"tool '{name}' already exists")
        return {"tool": self.tool_store.upsert(name, body.config, body.attached_to, by)}

    def update_tool(self, name: str, body, by: str) -> dict:
        existing = self.tool_store.get(name)
        if not existing:
            raise NotFound("unknown tool")
        fields = body.model_dump(exclude_unset=True)
        config = fields.get("config", existing["config"])
        return {"tool": self.tool_store.upsert(name, config, fields.get("attached_to"), by)}

    def set_tool_key(self, name: str, body, by: str) -> dict:
        if not self.tool_store.get(name):
            raise NotFound("unknown tool")
        value = (body.value or "").strip()
        if not value:
            raise Invalid("value required")
        return {"tool": self.tool_store.set_key(name, value, by)}

    def delete_tool_key(self, name: str) -> dict:
        return {"tool": self.tool_store.delete_key(name)}

    def delete_tool(self, name: str) -> dict:
        if not self.tool_store.get(name):
            raise NotFound("unknown tool")
        self.tool_store.delete(name)
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
            out.append({"id": u["id"], "email": u["email"], "type": "Tenexity" if staff else "New org",
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
            org_name = "Tenexity"
        else:
            if not (body.org_name or "").strip():
                raise Invalid("org_name required for a new org")
            oid = self.users.create_org(body.org_name, by=by)
            self.users.invite_member(email, oid, role=role or "admin", by=by)  # org default admin
            self.users.set_profile(email, name=body.name, designation=body.designation,
                                   sign_in_method=method)
            org_name = body.org_name
        if method == "password":
            self.users.set_password(email, body.password)
            self.users.set_status(email, "active")
        else:
            self.users.set_status(email, "invited")
        # SOF-195: mirror org_service's SOF-140 invite email — fire-and-forget, never fail the
        # provisioning (the user row is already created), UI reads invite_email_sent honestly.
        payload = self._access_rows()
        payload["invite_email_sent"] = self._send_invite_email(
            email, org_name=org_name, inviter=by, method=method, access_type=body.access_type)
        return payload

    def _send_invite_email(self, email: str, *, org_name: str, inviter: str, method: str,
                           access_type: str) -> bool:
        internal = access_type == "tenexity"
        where = "Tenexity" if internal else org_name
        verb = "granted access to" if method == "password" else "invited to"
        subject = f"You've been {verb} {where} on Software Factory"
        # method == "password": the admin set a real password directly (shared out-of-band —
        # NEVER put it in this email, which is a notification, not a secret carrier). Everything
        # else (invited): same "sign in with this email, no link needed" wording SOF-140 uses.
        if method == "password":
            action = (f"{inviter or 'An admin'} granted you access to {where} on Software Factory. "
                     f"Sign in with this email address ({email}) at:\n{CONSOLE_URL}\n")
        else:
            action = (f"{inviter or 'An admin'} invited you to {where} on Software Factory.\n\n"
                     f"Sign in with this email address ({email}) to get started — no invite link "
                     f"needed:\n{CONSOLE_URL}\n")
        sent = notify.send_to(email, subject, action)
        if not sent:
            logging.getLogger(__name__).warning(
                "invite email to %s not sent (Resend disabled or rejected — check RESEND_API_KEY / "
                "SF_NOTIFY_FROM verified sender); access still granted", email)
        return sent

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

    # ── conversation history (SOF-34, T1.5) — cross-tenant, staff-only ─────────────────
    def conversations(self, *, org_id=None, project_id=None, user_id=None, session_id=None,
                      role=None, date_from=None, date_to=None, cursor=None, limit=50) -> dict:
        """Sessions roll-up (§9 concierge-conversation-store.md): one row per session, aggregated
        via a single grouped query (ConversationRepository.rollup — no N+1). org/project/user
        names are resolved via the SAME batch context every other cross-tenant dashboard already
        uses (`_context()` + `list_users()`) — one query per lookup table, not per session row."""
        decoded_cursor = _decode_cursor(cursor) if cursor else None
        rows = self.conversation_repo.rollup(
            org_id=org_id, project_id=project_id, user_id=user_id, session_id=session_id,
            role=role, date_from=_parse_date("date_from", date_from),
            date_to=_parse_date("date_to", date_to), cursor=decoded_cursor, limit=limit)

        runs, orgs, _members, _o2o = self._context()
        org_names = {o["id"]: o["name"] for o in orgs}
        project_names = {r["project_id"]: r["name"] for r in runs}
        user_emails = {u["id"]: u["email"] for u in self.users.list_users()}

        sessions = [{
            "session_id": r["session_id"],
            "org_id": r["org_id"], "org_name": org_names.get(r["org_id"]),
            "project_id": r["project_id"], "project_name": project_names.get(r["project_id"]),
            "user_id": r["user_id"], "user_email": user_emails.get(r["user_id"]),
            "turn_count": r["turn_count"], "last_activity": r["last_activity"],
            "total_cost": float(r["total_cost"]),
        } for r in rows]
        next_cursor = (_encode_cursor(rows[-1]["last_activity"], rows[-1]["session_id"])
                      if len(rows) == limit else None)
        return {"sessions": sessions, "next_cursor": next_cursor}

    def conversation_transcript(self, session_id: str) -> dict:
        """Messages drill-down for one session — a single scoped query, oldest-first."""
        return {"session_id": session_id, "messages": self.conversation_repo.all_for_session(session_id)}
