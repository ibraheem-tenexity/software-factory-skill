"""Tenexity OS operator portal API (PRD §3) — CROSS-TENANT, staff-gated (require_staff).

Thin HTTP layer: each handler runs the require_staff gate, extracts the caller email, and delegates
to `state.admin_service`. Cross-tenant aggregation, the invite orchestration, and the staff-admin
lockout guards live there (raising domain errors mapped to HTTP by console/app.py)."""
from fastapi import APIRouter, Depends

import console.state as state
from console.deps import require_staff
from console.schemas import (DemoIn, PromptIn, InviteIn, AccessPatchIn, AgentIn, AgentPatchIn,
                             ToolIn, ToolPatchIn, OrgIn, OrgPatchIn, SowIn, SowPatchIn)

router = APIRouter()


# ── dashboards (cross-tenant) ──────────────────────────────────────────────────────────────────
@router.get("/api/admin/overview")
def admin_overview(v: tuple = Depends(require_staff)):
    return state.admin_service.overview()


@router.get("/api/admin/clients")
def admin_clients(v: tuple = Depends(require_staff)):
    return state.admin_service.clients()


@router.get("/api/admin/projects")
def admin_projects(mode: str = "all", v: tuple = Depends(require_staff)):
    return state.admin_service.projects(mode)


@router.patch("/api/admin/projects/{pid}")
def admin_set_demo(pid: str, body: DemoIn, v: tuple = Depends(require_staff)):
    return state.admin_service.set_demo(pid, body.is_demo)


# ── agents ───────────────────────────────────────────────────────────────────────────────────
@router.get("/api/admin/agents")
def admin_agents(v: tuple = Depends(require_staff)):
    return state.admin_service.agents()


@router.post("/api/admin/agents/sync")
def admin_agents_sync(v: tuple = Depends(require_staff)):
    return state.admin_service.sync_agents()


@router.get("/api/admin/agents/{callsign}")
def admin_agent(callsign: str, runtime: str = "claude", v: tuple = Depends(require_staff)):
    return state.admin_service.agent(callsign, runtime)


@router.post("/api/admin/agents")
def admin_agent_create(body: AgentIn, v: tuple = Depends(require_staff)):
    return state.admin_service.create_agent(body)


@router.patch("/api/admin/agents/{callsign}")
def admin_agent_update(callsign: str, body: AgentPatchIn, v: tuple = Depends(require_staff)):
    return state.admin_service.update_agent(callsign, body)


@router.delete("/api/admin/agents/{callsign}")
def admin_agent_delete(callsign: str, v: tuple = Depends(require_staff)):
    return state.admin_service.delete_agent(callsign)


@router.patch("/api/admin/agents/{callsign}/prompt")
def admin_set_prompt(callsign: str, body: PromptIn, v: tuple = Depends(require_staff)):
    return state.admin_service.set_prompt(callsign, body, by=v[0] or "")


@router.delete("/api/admin/agents/{callsign}/prompt")
def admin_revert_prompt(callsign: str, runtime: str | None = None, v: tuple = Depends(require_staff)):
    return state.admin_service.revert_prompt(callsign, runtime)


# ── tools / MCP registry ───────────────────────────────────────────────────────────────────────
@router.get("/api/admin/tools")
def admin_tools(v: tuple = Depends(require_staff)):
    return state.admin_service.tools()


@router.post("/api/admin/tools")
def admin_tool_create(body: ToolIn, v: tuple = Depends(require_staff)):
    return state.admin_service.create_tool(body)


@router.patch("/api/admin/tools/{tool_id}")
def admin_tool_update(tool_id: int, body: ToolPatchIn, v: tuple = Depends(require_staff)):
    return state.admin_service.update_tool(tool_id, body)


@router.delete("/api/admin/tools/{tool_id}")
def admin_tool_delete(tool_id: int, v: tuple = Depends(require_staff)):
    return state.admin_service.delete_tool(tool_id)


# ── clients / tenants (admin-scoped org CRUD) ────────────────────────────────────────────────────
@router.post("/api/admin/clients")
def admin_client_create(body: OrgIn, v: tuple = Depends(require_staff)):
    return state.admin_service.create_client(body, by=v[0] or "")


@router.patch("/api/admin/clients/{org_id}")
def admin_client_update(org_id: str, body: OrgPatchIn, v: tuple = Depends(require_staff)):
    return state.admin_service.update_client(org_id, body)


@router.delete("/api/admin/clients/{org_id}")
def admin_client_delete(org_id: str, v: tuple = Depends(require_staff)):
    return state.admin_service.delete_client(org_id)


# ── invites / allow-list ─────────────────────────────────────────────────────────────────────────
@router.get("/api/admin/access")
def admin_access(v: tuple = Depends(require_staff)):
    return state.admin_service.access()


@router.post("/api/admin/access")
def admin_invite(body: InviteIn, v: tuple = Depends(require_staff)):
    return state.admin_service.invite(body, by=v[0] or "")


@router.patch("/api/admin/access/{email}")
def admin_access_update(email: str, body: AccessPatchIn, v: tuple = Depends(require_staff)):
    return state.admin_service.access_update(email, body, caller=v[0] or "")


@router.post("/api/admin/access/{email}/resend")
def admin_access_resend(email: str, v: tuple = Depends(require_staff)):
    return state.admin_service.access_resend(email)


@router.delete("/api/admin/access/{email}")
def admin_access_revoke(email: str, v: tuple = Depends(require_staff)):
    return state.admin_service.access_revoke(email)


# ── SOW (Statement of Work) CRUD ──────────────────────────────────────────────────────────────────
@router.get("/api/admin/sow")
def admin_sow_list(v: tuple = Depends(require_staff)):
    return state.admin_service.sow_list()


@router.get("/api/admin/sow/{sow_id}")
def admin_sow_get(sow_id: int, v: tuple = Depends(require_staff)):
    return state.admin_service.sow_get(sow_id)


@router.post("/api/admin/sow")
def admin_sow_create(body: SowIn, v: tuple = Depends(require_staff)):
    return state.admin_service.sow_create(body)


@router.patch("/api/admin/sow/{sow_id}")
def admin_sow_update(sow_id: int, body: SowPatchIn, v: tuple = Depends(require_staff)):
    return state.admin_service.sow_update(sow_id, body)


# ── conversation history (SOF-34, T1.5) — cross-tenant, staff-only ──────────────────────────────
@router.get("/api/admin/conversations")
def admin_conversations(org_id: str | None = None, project_id: str | None = None,
                        user_id: str | None = None, session_id: str | None = None,
                        role: str | None = None, date_from: str | None = None,
                        date_to: str | None = None, cursor: str | None = None,
                        limit: int = 50, v: tuple = Depends(require_staff)):
    return state.admin_service.conversations(
        org_id=org_id, project_id=project_id, user_id=user_id, session_id=session_id, role=role,
        date_from=date_from, date_to=date_to, cursor=cursor, limit=limit)


@router.get("/api/admin/conversations/{session_id}")
def admin_conversation_transcript(session_id: str, v: tuple = Depends(require_staff)):
    return state.admin_service.conversation_transcript(session_id)
