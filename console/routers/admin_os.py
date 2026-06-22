"""Tenexity OS operator portal API (PRD §3) — CROSS-TENANT, staff-gated (require_staff)."""
import datetime

from fastapi import APIRouter, Depends, HTTPException

from software_factory import tenexity_os
from software_factory.users import TENEXITY_ORG_ID

import console.state as state
from console.deps import require_staff
from console.schemas import (DemoIn, PromptIn, InviteIn, AccessPatchIn, AgentIn, AgentPatchIn,
                             ToolIn, ToolPatchIn, ClientIn, ClientPatchIn)

router = APIRouter()


def _midnight_epoch() -> float:
    now = datetime.datetime.now()
    return now.replace(hour=0, minute=0, second=0, microsecond=0).timestamp()


def _admin_context():
    """Shared cross-tenant reads: all projects, all orgs, members-by-org, owner→org-name map."""
    runs = state.console.list_projects(owner=None)
    orgs = state.users.list_orgs()
    members_by_org = {o["id"]: state.users.list_org_members(o["id"]) for o in orgs}
    o2o = tenexity_os.owner_to_org(orgs, members_by_org)
    return runs, orgs, members_by_org, o2o


@router.get("/api/admin/overview")
def admin_overview(v: tuple = Depends(require_staff)):
    runs, orgs, _members, o2o = _admin_context()
    rollups = tenexity_os.agent_rollups()
    roster = tenexity_os.agent_roster(state.agent_store.all(), rollups, state.prompts.all())
    return tenexity_os.overview(orgs, runs, rollups, tenexity_os.agents_active_count(),
                                tenexity_os.today_burn(_midnight_epoch()), roster, o2o)


@router.get("/api/admin/clients")
def admin_clients(v: tuple = Depends(require_staff)):
    runs, orgs, members_by_org, _o2o = _admin_context()
    return {"clients": tenexity_os.client_rows(orgs, runs, members_by_org,
                                               tenexity_os.open_tickets_by_project())}


@router.get("/api/admin/projects")
def admin_projects(mode: str = "all", v: tuple = Depends(require_staff)):
    runs, _orgs, _members, o2o = _admin_context()
    return {"projects": tenexity_os.project_rows(runs, o2o, tenexity_os.ticket_counts_by_project(),
                                                 mode=mode)}


@router.patch("/api/admin/projects/{pid}")
def admin_set_demo(pid: str, body: DemoIn, v: tuple = Depends(require_staff)):
    return {"project_id": pid, "is_demo": state.console.set_demo(pid, body.is_demo)}


# Agents (identity from agent_registry table; cost/success merged live; prompt editable) ----------
@router.get("/api/admin/agents")
def admin_agents(v: tuple = Depends(require_staff)):
    return {"agents": tenexity_os.agent_roster(state.agent_store.all(), tenexity_os.agent_rollups(),
                                               state.prompts.all())}


@router.get("/api/admin/agents/{callsign}")
def admin_agent(callsign: str, v: tuple = Depends(require_staff)):
    cs = callsign.upper()
    card = next((a for a in tenexity_os.agent_roster(state.agent_store.all(), tenexity_os.agent_rollups(),
                                                     state.prompts.all()) if a["callsign"] == cs), None)
    if not card:
        raise HTTPException(status_code=404, detail="unknown agent")
    p = state.prompts.get(cs)
    return {**card, "prompt": p["prompt"] if p else "",
            "prompt_applied": False,   # saved here but NOT yet wired into the live pipeline
            "tools": [t for t in state.tool_store.all() if t["status"] == "connected"],
            "activity": []}


@router.post("/api/admin/agents")
def admin_agent_create(body: AgentIn, v: tuple = Depends(require_staff)):
    cs = (body.callsign or "").strip().upper()
    if not cs or not (body.name or "").strip():
        raise HTTPException(status_code=400, detail="callsign + name required")
    if state.agent_store.get(cs):
        raise HTTPException(status_code=409, detail="callsign exists")
    return {"agent": state.agent_store.create(cs, body.name, role=body.role, model=body.model,
                                        cost_tier=body.cost_tier, descr=body.descr)}


@router.patch("/api/admin/agents/{callsign}")
def admin_agent_update(callsign: str, body: AgentPatchIn, v: tuple = Depends(require_staff)):
    cs = callsign.upper()
    if not state.agent_store.get(cs):
        raise HTTPException(status_code=404, detail="unknown agent")
    fields = {k: val for k, val in body.model_dump().items() if val is not None}
    return {"agent": state.agent_store.update(cs, fields)}


@router.delete("/api/admin/agents/{callsign}")
def admin_agent_delete(callsign: str, v: tuple = Depends(require_staff)):
    cs = callsign.upper()
    if not state.agent_store.get(cs):
        raise HTTPException(status_code=404, detail="unknown agent")
    state.agent_store.delete(cs)
    return {"ok": True}


@router.patch("/api/admin/agents/{callsign}/prompt")
def admin_set_prompt(callsign: str, body: PromptIn, v: tuple = Depends(require_staff)):
    row = state.prompts.set(callsign.upper(), body.prompt or "", by=v[0] or "")
    return {"callsign": row["callsign"], "prompt": row["prompt"], "version": row["version"],
            "updated_by": row["updated_by"], "updated_at": row["updated_at"],
            "applied": False}   # honest: stored, not yet applied to live agents


# Tools / MCP registry (real datastore) -----------------------------------------------------------
@router.get("/api/admin/tools")
def admin_tools(v: tuple = Depends(require_staff)):
    return {"tools": [{**t, "used": None} for t in state.tool_store.all()]}


@router.post("/api/admin/tools")
def admin_tool_create(body: ToolIn, v: tuple = Depends(require_staff)):
    if not (body.name or "").strip():
        raise HTTPException(status_code=400, detail="name required")
    return {"tool": state.tool_store.create(body.name, type=body.type, provider=body.provider,
                                      scope=body.scope, auth=body.auth, status=body.status)}


@router.patch("/api/admin/tools/{tool_id}")
def admin_tool_update(tool_id: int, body: ToolPatchIn, v: tuple = Depends(require_staff)):
    fields = {k: val for k, val in body.model_dump().items() if val is not None}
    tool = state.tool_store.update(tool_id, fields)
    if not tool:
        raise HTTPException(status_code=404, detail="unknown tool")
    return {"tool": tool}


@router.delete("/api/admin/tools/{tool_id}")
def admin_tool_delete(tool_id: int, v: tuple = Depends(require_staff)):
    state.tool_store.delete(tool_id)
    return {"ok": True}


# Clients / tenants (admin-scoped org CRUD) -------------------------------------------------------
@router.post("/api/admin/clients")
def admin_client_create(body: ClientIn, v: tuple = Depends(require_staff)):
    if not (body.name or "").strip():
        raise HTTPException(status_code=400, detail="name required")
    oid = state.users.create_org(body.name, industry=body.industry, website=body.website, by=v[0] or "")
    return {"client": state.users.get_org(oid)}


@router.patch("/api/admin/clients/{org_id}")
def admin_client_update(org_id: str, body: ClientPatchIn, v: tuple = Depends(require_staff)):
    if not state.users.get_org(org_id):
        raise HTTPException(status_code=404, detail="unknown org")
    fields = {k: val for k, val in body.model_dump().items() if val is not None}
    state.users.update_org(org_id, **fields)
    return {"client": state.users.get_org(org_id)}


@router.delete("/api/admin/clients/{org_id}")
def admin_client_delete(org_id: str, v: tuple = Depends(require_staff)):
    if not state.users.get_org(org_id):
        raise HTTPException(status_code=404, detail="unknown org")
    state.users.delete_org(org_id)
    return {"ok": True}


# Invites / allow-list ----------------------------------------------------------------------------
def _access_rows():
    out = []
    for u in state.users.list_users():
        staff = u.get("is_internal") in (1, True)
        org = state.users.get_org(u["org_id"]) if u.get("org_id") else None
        out.append({"email": u["email"], "type": "Tenexity" if staff else "New org",
                    "org": "Tenexity" if staff else (org["name"] if org else None),
                    "role": u["role"], "status": u.get("status") or "active",
                    "name": u.get("name"), "designation": u.get("designation"),
                    "sign_in_method": u.get("sign_in_method"), "last_active": u.get("last_active"),
                    "invited_by": u.get("invited_by")})
    return {"users": out}


@router.get("/api/admin/access")
def admin_access(v: tuple = Depends(require_staff)):
    return _access_rows()


@router.post("/api/admin/access")
def admin_invite(body: InviteIn, v: tuple = Depends(require_staff)):
    email = (body.email or "").strip().lower()
    if not email:
        raise HTTPException(status_code=400, detail="email required")
    method = body.method or "google"
    if method == "password" and not (body.password or ""):
        raise HTTPException(status_code=400, detail="password required when method is 'password'")
    role = body.role if body.role in ("admin", "member") else None
    by = v[0] or ""
    if body.access_type == "tenexity":
        state.users.upsert(email, role or "member", by=by)   # staff default member unless role given
        state.users.set_profile(email, is_internal=True, org_id=TENEXITY_ORG_ID,
                                name=body.name, designation=body.designation, sign_in_method=method)
    else:
        if not (body.org_name or "").strip():
            raise HTTPException(status_code=400, detail="org_name required for a new org")
        oid = state.users.create_org(body.org_name, by=by)
        state.users.invite_member(email, oid, role=role or "admin", by=by)  # org default admin
        state.users.set_profile(email, name=body.name, designation=body.designation,
                                sign_in_method=method)
    # method=password → provision an active credentialed user; otherwise the user is invited (pending
    # first sign-in via their method). set_password also flips sign_in_method to 'password'.
    if method == "password":
        state.users.set_password(email, body.password)
        state.users.set_status(email, "active")
    else:
        state.users.set_status(email, "invited")
    return _access_rows()


@router.patch("/api/admin/access/{email}")
def admin_access_update(email: str, body: AccessPatchIn, v: tuple = Depends(require_staff)):
    em = (email or "").strip().lower()
    if not state.users.get_user(em):
        raise HTTPException(status_code=404, detail="unknown user")
    if body.role in ("admin", "member"):
        state.users.upsert(em, body.role, by=v[0] or "")
    if body.status == "disabled":
        state.users.disable(em)                            # status→disabled + token_version bump (revokes cookie)
    elif body.status in ("active", "invited"):
        state.users.set_status(em, body.status)
    return _access_rows()


@router.delete("/api/admin/access/{email}")
def admin_access_revoke(email: str, v: tuple = Depends(require_staff)):
    # Revoke = disable + bump token_version (spec lifecycle): blocks new sign-ins AND invalidates the
    # user's current cookie on its next request. The bootstrap admin is guarded inside disable().
    state.users.disable((email or "").strip().lower())
    return _access_rows()
