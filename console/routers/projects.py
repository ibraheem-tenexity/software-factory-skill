"""Projects (runs) + drafts: list/create, run-scoped GETs, Project View §2.5 aggregates,
run-scoped actions, and the Option C draft write-through + handoff."""
import base64
import mimetypes
import os

from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.responses import PlainTextResponse

from software_factory import storage, project_view
from software_factory.console import ProjectRequest, project_paths
from software_factory.db import artifact_by_id
from software_factory.deps import extract_env_creds

import console.state as state
from console.deps import require_authed, authorize_project, _can_see
from console.schemas import (ProjectCreateIn, DraftCreateIn, ProjectPatchIn, MaterialScopeIn, OrgDocIn,
                             ContinueIn, DepsIn, Stage3In, BudgetIn, RetryIn, RetryNodeIn, RewindIn,
                             DraftPatchIn, AttachIn, PromoteIn, CredsIn)

router = APIRouter()


# ── Runs: list + create ───────────────────────────────────────────────────────────────────────
@router.get("/api/projects")
def projects_list(include_archived: bool = False, v: tuple = Depends(require_authed)):
    owner = None if v[1] == "admin" else v[0]
    return {"projects": state.console.list_projects(owner=owner, include_archived=include_archived)}


@router.post("/api/projects")
def projects_create(body: ProjectCreateIn, v: tuple = Depends(require_authed)):
    creds = {}
    if body.railway_token:
        creds["RAILWAY_TOKEN"] = body.railway_token
    if body.railway_project_id:
        creds["RAILWAY_PROJECT_ID"] = body.railway_project_id
    req = ProjectRequest(
        description=body.description,
        context=body.context,
        budget=float(body.budget),
        target=body.target,
        credentials=creds,
        context_files=body.files,
        runtime=body.runtime,
        planning_model=body.planning_model,
        impl_model=body.impl_model,
        model=body.model,
        name=body.project_name,
        gated=bool(body.gated),
        owner=v[0] or "",
    )
    try:
        return {"project_id": state.console.start_project(req)}
    except ValueError as e:           # duplicate project name
        raise HTTPException(status_code=409, detail=str(e))


# ── Drafts (Option C onboarding) ──────────────────────────────────────────────────────────────
@router.post("/api/drafts")
def create_draft(body: DraftCreateIn, v: tuple = Depends(require_authed)):
    """Mint a durable draft run at the START of onboarding (the form is the sole eager creator on
    mount). Returns its canonical run-<8hex> id; the form passes it into every subsequent
    PATCH/attach/promote and into /api/chat so the rail and the form share ONE draft."""
    if not (body.project_name or "").strip():
        raise HTTPException(status_code=400, detail="project_name is required")
    project_id = state.console.create_draft(owner=v[0] or "", name=body.project_name,
                                  runtime=body.runtime, planning_model=body.planning_model,
                                  impl_model=body.impl_model, model=body.model,
                                  budget=body.budget)
    return {"project_id": project_id}


# ── Run-scoped GETs ─────────────────────────────────────────────────────────────────────────
@router.get("/api/projects/{pid}")
def project_status(pid: str, v: tuple = Depends(authorize_project)):
    return state.console.status(pid)


@router.get("/api/projects/{pid}/evidence")
def project_evidence(pid: str, v: tuple = Depends(authorize_project)):
    return state.console.evidence(pid)


@router.get("/api/projects/{pid}/graph")
def project_graph(pid: str, v: tuple = Depends(authorize_project)):
    return state.console.graph(pid)


@router.get("/api/projects/{pid}/tickets")
def project_tickets(pid: str, v: tuple = Depends(authorize_project)):
    """Build-ticket projection for the kanban view (empty before Stage 2)."""
    return state.console.tickets(pid)


@router.get("/api/projects/{pid}/deployments")
def project_deployments(pid: str, v: tuple = Depends(authorize_project)):
    """Per-deliverable deployments (a run may ship multiple apps)."""
    return state.console.deployments(pid)


@router.get("/api/projects/{pid}/brief")
def project_brief(pid: str, v: tuple = Depends(authorize_project)):
    """The structured onboarding brief (shared by the chat interview and the brief form)."""
    from software_factory.brief import coverage as _cov
    brief = state.console.draft_brief(pid)
    return {"brief": brief, "coverage": _cov(brief)}


@router.put("/api/projects/{pid}/brief")
def update_project_brief(pid: str, body: dict, v: tuple = Depends(authorize_project)):
    """Edit the brief from the form. Body: {section: text, ...} (only known sections persist)."""
    from software_factory.brief import BRIEF_SECTIONS
    sections = {k: v2 for k, v2 in (body or {}).items() if k in BRIEF_SECTIONS}
    cov = state.console.update_draft_brief(pid, sections)
    return {"brief": state.console.draft_brief(pid), "coverage": cov}


@router.get("/api/projects/{pid}/events")
def project_events(pid: str, v: tuple = Depends(authorize_project)):
    return {"events": state.console.events(pid)}


@router.get("/api/artifacts/{artifact_id}")
def artifact_detail(artifact_id: int, v: tuple = Depends(require_authed)):
    """Fetch an artifact by its stable integer id (cross-project lookup for the standalone viewer).

    Returns: {id, project_id, title, kind, path, content, updated, agent}
    content is the file text (up to 200 KB); null when the path is a URL or the file is absent.
    No confidence field — not in the artifacts table; viewer must omit that pill.
    """
    row = artifact_by_id(artifact_id)
    if not row:
        raise HTTPException(status_code=404, detail="artifact not found")
    if not _can_see(v, row["project_id"]):
        raise HTTPException(status_code=403, detail="forbidden")
    content = None
    path = row.get("path") or ""
    if path and not path.startswith(("http://", "https://")):
        # Resolve via the owning project's content reader (path-escape-safe).
        result = state.console.artifact(row["project_id"], path)
        content = result.get("content")
    return {
        "id": row["id"],
        "project_id": row["project_id"],
        "title": row.get("title"),
        "kind": row.get("kind"),
        "path": path,
        "content": content,
        "updated": row.get("ts"),
        "agent": row.get("agent"),
    }


@router.get("/api/projects/{pid}/artifact")
def project_artifact(pid: str, path: str = "", raw: str = "", v: tuple = Depends(authorize_project)):
    result = state.console.artifact(pid, path)
    if raw and "content" in result:
        # Raw mode: serve the file itself (right Content-Type) so e.g. the architecture SVG
        # opens full-size in its own browser tab.
        ctype = {"svg": "image/svg+xml", "html": "text/html", "json": "application/json",
                 "md": "text/markdown"}.get(path.rsplit(".", 1)[-1].lower(), "text/plain")
        return Response(content=result["content"].encode(), media_type=f"{ctype}; charset=utf-8")
    return result


@router.get("/api/projects/{pid}/log")
def project_log(pid: str, full: str = "", v: tuple = Depends(authorize_project)):
    if full == "json":
        return {"log": state.console.read_log(pid, max_bytes=None)}
    if full:
        body = state.console.read_log(pid, max_bytes=None)
        return PlainTextResponse(body, media_type="text/plain; charset=utf-8",
                                 headers={"Content-Disposition": f'attachment; filename="{pid}.log"'})
    return state.console.read_log_envelope(pid)


@router.get("/api/projects/{pid}/deps")
def project_deps(pid: str, v: tuple = Depends(authorize_project)):
    return state.console.stage2_artifacts(pid)


# ── Project View (PRD §2.5): Overview + Documents aggregates ─────────────────────────────────────
@router.get("/api/projects/{pid}/overview")
def project_overview(pid: str, v: tuple = Depends(authorize_project)):
    status = state.console.status(pid)
    tickets = state.console.tickets(pid)["tickets"]
    deployments = state.console.deployments(pid)["deployments"]
    owner = status.get("owner") or ""
    org = state.users.org_for_user(owner) if owner else None
    has_verification = bool(status.get("done")) or any(d.get("verified") for d in deployments)
    in_build = (status.get("stage") or 0) >= 2 and not status.get("done")
    docs = project_view.documents(state.blobs.list_for("project", pid), state.console.artifacts(pid))
    return {
        "brief": project_view.brief_block(state.console.draft_project(pid), status,
                                          state.console.project_created(pid)),
        "build": project_view.build_status(status, tickets),
        "services": project_view.services_at_work(org, deployments, status.get("impl_model") or "",
                                                  has_verification, in_build),
        "agents": project_view.agents_projection(state.console.agents(pid), tickets),
        "org": ({"name": org["name"], "industry": org.get("industry"),
                 "connected_systems": org.get("connected_systems", [])} if org else None),
        "materials_count": len(docs["uploaded"]),
        "produced_count": len(docs["produced"]),
    }


@router.get("/api/projects/{pid}/documents")
def project_documents(pid: str, v: tuple = Depends(authorize_project)):
    return project_view.documents(state.blobs.list_for("project", pid), state.console.artifacts(pid))


@router.post("/api/projects/{pid}/materials")
def project_material_upload(pid: str, body: OrgDocIn, v: tuple = Depends(authorize_project)):
    """Upload a project-scoped material at ANY phase (attach is draft-only). Shows up in
    GET /api/projects/{pid}/documents.uploaded."""
    if not (body.name or "").strip():
        raise HTTPException(status_code=400, detail="name required")
    try:
        raw = base64.b64decode(body.data_b64 or "", validate=True)
    except Exception:
        raise HTTPException(status_code=400, detail="data_b64 must be valid base64")
    key = f"materials/{body.name}"
    storage.put(pid, key, raw)
    state.blobs.record("project", pid, f"{pid}/{key}", name=body.name, tag=body.tag,
                 kind=state._doc_kind(body.name), content_type=body.content_type,
                 size_bytes=len(raw), sha256=storage.sha256(raw))
    return project_view.documents(state.blobs.list_for("project", pid), state.console.artifacts(pid))


@router.patch("/api/projects/{pid}")
def project_update(pid: str, body: ProjectPatchIn, v: tuple = Depends(authorize_project)):
    """Rename / re-scope / re-describe a promoted project (drafts use PATCH /api/projects/{pid}/draft).
    Sending `scope` recomposes the description (goal + scope line) server-side."""
    return state.console.rename_project(pid, name=body.name, description=body.description, scope=body.scope)


@router.delete("/api/projects/{pid}")
def project_delete(pid: str, v: tuple = Depends(authorize_project)):
    """Soft-delete (archive) a project — hidden from the default listing; discards a draft."""
    return {"project_id": pid, "archived": state.console.set_archived(pid, True)}


@router.post("/api/projects/{pid}/restore")
def project_restore(pid: str, v: tuple = Depends(authorize_project)):
    """Restore an archived project — un-archives it so it lists again."""
    return {"project_id": pid, "archived": state.console.set_archived(pid, False)}


@router.delete("/api/projects/{pid}/permanent")
def project_delete_permanent(pid: str, v: tuple = Depends(authorize_project)):
    """Permanently delete a project — removes the run dir + state rows. Cannot be undone."""
    return state.console.delete_project(pid)


@router.patch("/api/projects/{pid}/materials/{material_id}")
def project_material_scope(pid: str, material_id: int, body: MaterialScopeIn,
                           v: tuple = Depends(authorize_project)):
    """Move an uploaded material between project-scope and org-wide (PRD §2.4). →org puts it in the
    org knowledge base (appears in /api/org/docs); →project moves it back to this project."""
    b = state.blobs.get_blob(material_id)
    if not b:
        raise HTTPException(status_code=404, detail="material not found")
    if body.scope == "org":
        org = state.users.org_for_user(state.console.project_owner(pid))
        if not org:
            raise HTTPException(status_code=409, detail="project owner has no org on file")
        state.blobs.set_scope(material_id, "org", org["id"])
    elif body.scope == "project":
        state.blobs.set_scope(material_id, "project", pid)
    else:
        raise HTTPException(status_code=400, detail="scope must be 'project' or 'org'")
    return project_view.documents(state.blobs.list_for("project", pid), state.console.artifacts(pid))


# ── Run-scoped actions ──────────────────────────────────────────────────────────────────────
@router.post("/api/projects/{pid}/continue")
def project_continue(pid: str, body: ContinueIn, v: tuple = Depends(authorize_project)):
    return state.console.continue_project(pid, body.gate)


@router.post("/api/projects/{pid}/deps")
def project_submit_deps(pid: str, body: DepsIn, v: tuple = Depends(authorize_project)):
    result = state.console.submit_deps(pid, body.deps)
    # Launch Stage 3 immediately once deps are satisfied — mirror the chat submit path (chat.py).
    # The background poller would also pick this up, but launching here starts the build without
    # waiting for the next poll tick. extract_env_creds rides provided dep VALUES into the stage env.
    if result.get("satisfied"):
        state.console.start_stage3(pid, extra_creds=extract_env_creds(body.deps))
    return result


@router.post("/api/projects/{pid}/stage2")
def project_stage2(pid: str, v: tuple = Depends(authorize_project)):
    result = state.console.start_stage2(pid)
    if result:
        return {"project_id": result, "stage": 2}
    raise HTTPException(status_code=409, detail="stage1 not done or MCP unhealthy")


@router.post("/api/projects/{pid}/stage3")
def project_stage3(pid: str, body: Stage3In, v: tuple = Depends(authorize_project)):
    result = state.console.start_stage3(pid, extra_creds=extract_env_creds(body.creds or {}))
    if result:
        return {"project_id": result, "stage": 3}
    raise HTTPException(status_code=409, detail="stage2 not done or deps not satisfied")


@router.post("/api/projects/{pid}/budget")
def project_budget(pid: str, body: BudgetIn, v: tuple = Depends(authorize_project)):
    try:
        ceiling = float(body.ceiling)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="ceiling (number) required")
    return state.console.raise_budget(pid, ceiling)


@router.post("/api/projects/{pid}/stop")
def project_stop(pid: str, v: tuple = Depends(authorize_project)):
    """Operator 'stop all progress': kill the live stage process + mark the run stopped (terminal —
    the poller won't re-advance or re-provision). Idempotent. Pairs with the dashboard Stop button."""
    return state.console.stop_project(pid)


@router.post("/api/projects/{pid}/relaunch")
def project_relaunch(pid: str, v: tuple = Depends(authorize_project)):
    """Mint a fresh run from the spec of a stopped or done project.

    Creates a NEW project_id seeded from the source's description, brief, scope, runtime,
    models, budget ceiling, creds_vault_ids, and input materials. Source run is untouched.
    Returns the new project_id. 409 if the source is not stopped or done."""
    email, _role, _ok = v
    try:
        new_id = state.console.relaunch_project(pid, owner=email)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return {"project_id": new_id, "relaunched_from": pid}


@router.post("/api/projects/{pid}/retry")
def project_retry(pid: str, body: RetryIn, v: tuple = Depends(authorize_project)):
    result = state.console.retry_stage(pid, int(body.stage), extra_creds=body.creds)
    if result:
        return {"project_id": result, "retried_stage": int(body.stage)}
    raise HTTPException(status_code=409, detail="cannot retry: invalid stage or prior stage not done")


@router.post("/api/projects/{pid}/pause")
def project_pause(pid: str, v: tuple = Depends(authorize_project)):
    """Kill the live stage process and hold the run at phase='paused'. The Recovery bar
    resumes via /resume. Idempotent — pausing an already-paused run is a no-op."""
    return state.console.pause_project(pid)


@router.post("/api/projects/{pid}/resume")
def project_resume(pid: str, v: tuple = Depends(authorize_project)):
    """Resume a paused or crashed run from the last recorded node. Clears the pause/crash
    markers and relaunches the appropriate stage."""
    result = state.console.resume_project(pid)
    if result:
        return {"project_id": result, "resumed": True}
    raise HTTPException(status_code=409, detail="cannot resume: project is not paused or crashed")


@router.post("/api/projects/{pid}/retry-node")
def project_retry_node(pid: str, body: RetryNodeIn, v: tuple = Depends(authorize_project)):
    """Invalidate the checkpoint at `node` and all downstream nodes, then resume from there.
    Upstream completed nodes are preserved — the stage skips them."""
    result = state.console.retry_node(pid, body.node)
    if result:
        return {"project_id": result, "retried_from": body.node}
    raise HTTPException(status_code=409, detail=f"cannot retry node '{body.node}'")


@router.post("/api/projects/{pid}/rewind")
def project_rewind(pid: str, body: RewindIn, v: tuple = Depends(authorize_project)):
    """Invalidate checkpoints at `node` and downstream, kill the running process, and set
    phase='paused'. Does NOT auto-resume — call /resume when ready."""
    return state.console.rewind_to_node(pid, body.node)


@router.post("/api/projects/{pid}/release")
def project_release(pid: str, v: tuple = Depends(authorize_project)):
    if state.console.release_project(pid):
        return {"project_id": pid, "released": True}
    raise HTTPException(status_code=409, detail="not held")


# ── Draft write-through + handoff (Option C onboarding; drafts only) ──────────────────────────
@router.get("/api/projects/{pid}/draft")
def get_draft(pid: str, v: tuple = Depends(authorize_project)):
    """Read the draft's intake fields to REHYDRATE the onboarding form when resuming an existing draft
    (the read counterpart to PATCH /draft). Returns {name, goal, scope, description, brief, coverage}.
    Draft-only: a promoted project has no editable draft intake."""
    if not state.console.is_draft(pid):
        raise HTTPException(status_code=409, detail="not a draft (already promoted)")
    return state.console.draft_project(pid)


@router.patch("/api/projects/{pid}/draft")
def patch_draft(pid: str, body: DraftPatchIn, v: tuple = Depends(authorize_project)):
    """Structured project write-through: {name?, goal?, scope?, runtime?}. Server composes the canonical
    description (goal + scope-of-work line). runtime updates the draft's build engine (claude|opencode)
    after the eager create. Call debounced/on-blur, NOT per keystroke."""
    if not state.console.is_draft(pid):
        raise HTTPException(status_code=409, detail="not a draft (already promoted)")
    result = state.console.set_draft_project(pid, name=body.name, goal=body.goal, scope=body.scope,
                                             runtime=body.runtime, model=body.model)
    if body.budget is not None:
        state.console.raise_budget(pid, body.budget)
        result["budget_ceiling"] = body.budget
    return result


@router.post("/api/projects/{pid}/attach")
def attach_draft(pid: str, body: AttachIn, v: tuple = Depends(authorize_project)):
    """Attach project materials (walkthrough video / documents) to the draft's input/.
    PDF/DOCX originals are kept alongside their .md extractions, pushed to object storage,
    and recorded as blobs so they appear in GET /api/projects/{pid}/documents.uploaded."""
    if not state.console.is_draft(pid):
        raise HTTPException(status_code=409, detail="not a draft (already promoted)")
    written = state.console.attach_to_draft(pid, body.files or [])
    # push PDF/DOCX originals to blob storage and record in the manifest
    input_dir = project_paths(state.PROJECTS_DIR, pid)["input_dir"]
    for name in written:
        nl = name.lower()
        if nl.endswith(".pdf") or nl.endswith(".docx"):
            file_path = os.path.join(input_dir, name)
            if not os.path.exists(file_path):
                continue
            raw = open(file_path, "rb").read()
            key = f"materials/{name}"
            storage.put(pid, key, raw)
            state.blobs.record("project", pid, f"{pid}/{key}", name=name,
                               kind=state._doc_kind(name),
                               content_type=mimetypes.guess_type(name)[0] or "application/octet-stream",
                               size_bytes=len(raw), sha256=storage.sha256(raw))
    return {"attached": written}


@router.post("/api/projects/{pid}/creds")
def store_draft_creds(pid: str, body: CredsIn, v: tuple = Depends(authorize_project)):
    """Store BYOK credentials in Vault against a draft. Returns cred names, never values."""
    if not state.console.is_draft(pid):
        raise HTTPException(status_code=409, detail="not a draft (already promoted)")
    return state.console.store_draft_creds(pid, body.credentials)


@router.post("/api/projects/{pid}/promote")
def promote_draft(pid: str, body: PromoteIn, v: tuple = Depends(authorize_project)):
    """Hand off to the factory: promote the draft into a real run and launch Stage 1. The composed
    state.description + accumulated brief are the payload (description override optional)."""
    if not state.console.is_draft(pid):
        raise HTTPException(status_code=409, detail="not a draft (already promoted)")
    try:
        project_id = state.console.promote_draft(pid, description=body.description, target=body.target)
    except ValueError as e:                # duplicate project name
        raise HTTPException(status_code=409, detail=str(e))
    return {"project_id": project_id, "status": "started"}
