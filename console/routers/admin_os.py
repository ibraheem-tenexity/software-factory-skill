"""Tenexity OS operator portal API (PRD §3) — CROSS-TENANT, staff-gated (require_staff)."""
import datetime

from fastapi import APIRouter, Depends, HTTPException

from software_factory import tenexity_os
from software_factory.agent_prompts import override_key
from software_factory.users import TENEXITY_ORG_ID

import console.state as state
from console.deps import require_staff
from console.schemas import (DemoIn, PromptIn, InviteIn, AccessPatchIn, AgentIn, AgentPatchIn,
                             ToolIn, ToolPatchIn, ClientIn, ClientPatchIn, SowIn, SowPatchIn)

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
    # The 4 REAL orchestrators (STAGE-1/2/3 + CONCIERGE) now have BOTH a registry row AND a richer
    # live card (kind/stage/runtimes/prompt_source + effective prompt). Render each ONCE: the live card
    # wins for those callsigns; the registry roster contributes only OTHER (custom) agents → no dupes.
    live = tenexity_os.live_agent_cards()
    live_cs = {c["callsign"] for c in live}
    roster = tenexity_os.agent_roster(state.agent_store.all(), tenexity_os.agent_rollups(),
                                      state.prompts.all())
    return {"agents": [r for r in roster if r["callsign"] not in live_cs] + live}


@router.post("/api/admin/agents/sync")
def admin_agents_sync(v: tuple = Depends(require_staff)):
    """Re-run canonical agent-registry reconciliation on demand (backs the OS dashboard Sync button).

    Upserts the 4 structural agents (STAGE-1/2/3 + CONCIERGE) with their authoritative definitions
    (name, role, current model from live config, cost_tier, descr). Purges legacy fake callsigns.
    Custom agents are never touched. Idempotent — calling twice is a no-op delta.

    Returns: {synced: N, agents: [{callsign, name, role, model, cost_tier, descr}, ...]}
    """
    agents = state.agent_store.sync_real_agents()
    return {"synced": len(agents), "agents": agents}


@router.get("/api/admin/agents/{callsign}")
def admin_agent(callsign: str, runtime: str = "claude", v: tuple = Depends(require_staff)):
    # Stage orchestrators serve the REAL SKILL.md and the concierge serves its live CONCIERGE_INSTRUCTIONS
    # (prompt_applied=true; ?runtime=opencode for a stage's opencode variant). Role agents serve their
    # editable PromptStore prompt (applied=false).
    live = tenexity_os.live_agent_detail(callsign, runtime)
    if live:
        # Overlay any operator override → the EFFECTIVE prompt that will drive the next run. Stages key
        # per-runtime ("STAGE-1::claude"); concierge is single. is_default/overridden/version let the FE
        # show edited-vs-default + a revert control.
        ov = state.prompts.get(override_key(callsign, live.get("runtime")))
        if ov:
            live = {**live, "prompt": ov["prompt"], "version": ov["version"], "is_default": False,
                    "overridden": True, "updated_by": ov["updated_by"], "updated_at": ov["updated_at"]}
        else:
            live = {**live, "version": 0, "is_default": True, "overridden": False}
        return {**live, "tools": [t for t in state.tool_store.all() if t["status"] == "connected"],
                "activity": []}
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
    # The 4 real orchestrators ARE the factory — refuse to delete them (boot would re-ensure anyway, so
    # a delete would be a confusing no-op-then-reappear). Custom agents remain freely deletable.
    if tenexity_os.is_editable_orchestrator(cs):
        raise HTTPException(status_code=409, detail="structural agent — required by the pipeline")
    if not state.agent_store.get(cs):
        raise HTTPException(status_code=404, detail="unknown agent")
    state.agent_store.delete(cs)
    return {"ok": True}


def _stage_runtime(cs: str, runtime: str | None) -> str | None:
    """Validate + normalize the runtime for a prompt write/revert: required (claude|opencode) for stage
    skills, ignored for the concierge."""
    if not cs.startswith("STAGE-"):
        return None
    if runtime not in ("claude", "opencode"):
        raise HTTPException(status_code=400, detail="runtime (claude|opencode) required for stage skills")
    return runtime


@router.patch("/api/admin/agents/{callsign}/prompt")
def admin_set_prompt(callsign: str, body: PromptIn, v: tuple = Depends(require_staff)):
    cs = callsign.upper()
    if tenexity_os.is_editable_orchestrator(cs):
        # The 4 MAIN cards: the edit is the override that DRIVES the next run (stages per-runtime via
        # ws/SKILL.md, concierge via the Agent's instructions). applied=true, NOT retroactive to in-flight.
        rt = _stage_runtime(cs, body.runtime)
        row = state.prompts.set(override_key(cs, rt), body.prompt or "", by=v[0] or "")
        return {"callsign": cs, "runtime": rt, "version": row["version"],
                "updated_by": row["updated_by"], "updated_at": row["updated_at"],
                "applied": True, "is_default": False}
    # Role/specialist agents: stored, NOT yet applied (subagent managed prompts = later part-2b).
    row = state.prompts.set(cs, body.prompt or "", by=v[0] or "")
    return {"callsign": row["callsign"], "prompt": row["prompt"], "version": row["version"],
            "updated_by": row["updated_by"], "updated_at": row["updated_at"],
            "applied": False}


@router.delete("/api/admin/agents/{callsign}/prompt")
def admin_revert_prompt(callsign: str, runtime: str | None = None, v: tuple = Depends(require_staff)):
    # Revert an editable orchestrator to its on-disk/code default (drop the override). Per-runtime for
    # stages. The next run uses the default again.
    cs = callsign.upper()
    if not tenexity_os.is_editable_orchestrator(cs):
        raise HTTPException(status_code=404, detail="no editable override for this agent")
    rt = _stage_runtime(cs, runtime)
    state.prompts.delete(override_key(cs, rt))
    return {"callsign": cs, "runtime": rt, "version": 0, "is_default": True}


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
    u = state.users.get_user(em)
    if not u:
        raise HTTPException(status_code=404, detail="unknown user")

    # "Make Tenexity admin" = {role:"admin", is_internal:true}; revoke staff = {is_internal:false}.
    # Compute the RESULTING staff-admin status so we can guard against stranding the platform.
    def _is_staff_admin(role, internal, status):
        return role == "admin" and internal in (1, True) and (status or "active") != "disabled"
    cur_role, cur_internal, cur_status = u["role"], u.get("is_internal"), (u.get("status") or "active")
    new_role = body.role if body.role in ("admin", "member") else cur_role
    new_internal = body.is_internal if body.is_internal is not None else cur_internal
    new_status = body.status if body.status in ("active", "invited", "disabled") else cur_status
    was, will = _is_staff_admin(cur_role, cur_internal, cur_status), _is_staff_admin(new_role, new_internal, new_status)

    if was and not will:
        # Guard (b): never let an admin de-staff/lock out their OWN active session.
        if em == (v[0] or "").lower():
            raise HTTPException(status_code=409, detail="cannot remove your own staff-admin access")
        # Guard (a): keep at least one Tenexity staff admin — never strand the platform.
        others = [x for x in state.users.list_users()
                  if (x["email"] or "").lower() != em
                  and _is_staff_admin(x["role"], x.get("is_internal"), x.get("status"))]
        if not others:
            raise HTTPException(status_code=409, detail="cannot remove the last Tenexity staff admin")

    if body.role in ("admin", "member"):
        state.users.upsert(em, body.role, by=v[0] or "")
    if body.is_internal is not None:
        state.users.set_profile(em, is_internal=body.is_internal)   # toggle Tenexity-staff
    if body.status == "disabled":
        state.users.disable(em)                            # status→disabled + token_version bump (revokes cookie)
    elif body.status in ("active", "invited"):
        state.users.set_status(em, body.status)
    return _access_rows()


@router.post("/api/admin/access/{email}/resend")
def admin_access_resend(email: str, v: tuple = Depends(require_staff)):
    """Return (or re-surface) the platform sign-in URL for an invited user.

    The factory's invite flow is allow-list-based: an invited email signs in via Google OAuth
    and the status flips to active automatically. There is no one-time token — the sign-in URL
    IS the invite link. Staff copy this URL from the drawer and share it with the invitee.

    Returns: {email, status: "invited", link: <sign-in URL>}
    403 for non-staff (require_staff gate).
    404 if the user is unknown.
    409 if the user is not in "invited" status (already active/disabled — nothing to resend).
    """
    import os as _os
    em = (email or "").strip().lower()
    u = state.users.get_user(em)
    if not u:
        raise HTTPException(status_code=404, detail="unknown user")
    if (u.get("status") or "active") != "invited":
        raise HTTPException(status_code=409,
                            detail=f"user is '{u.get('status', 'active')}' — only invited users can be resent")
    base = (_os.environ.get("SF_APP_URL") or "").rstrip("/")
    return {"email": em, "status": "invited", "link": f"{base}/" if base else "/"}


@router.delete("/api/admin/access/{email}")
def admin_access_revoke(email: str, v: tuple = Depends(require_staff)):
    # Revoke = disable + bump token_version (spec lifecycle): blocks new sign-ins AND invalidates the
    # user's current cookie on its next request. The bootstrap admin is guarded inside disable().
    state.users.disable((email or "").strip().lower())
    return _access_rows()


# ── SOW (Statement of Work) CRUD ──────────────────────────────────────────────────────────────────
@router.get("/api/admin/sow")
def admin_sow_list(v: tuple = Depends(require_staff)):
    return {"sows": state.sow_store.list_all()}


@router.post("/api/admin/sow")
def admin_sow_create(body: SowIn, v: tuple = Depends(require_staff)):
    try:
        row = state.sow_store.create(
            body.title,
            org=body.org, project=body.project, value=body.value,
            file=body.file, version=body.version, status=body.status, body=body.body,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return row


@router.patch("/api/admin/sow/{sow_id}")
def admin_sow_update(sow_id: int, body: SowPatchIn, v: tuple = Depends(require_staff)):
    if not state.sow_store.get(sow_id):
        raise HTTPException(status_code=404, detail="sow not found")
    try:
        row = state.sow_store.update(sow_id, body.model_dump(exclude_none=True))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return row
