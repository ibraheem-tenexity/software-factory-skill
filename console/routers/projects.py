"""Projects (runs) + drafts: list/create, run-scoped GETs, Project View §2.5 aggregates,
run-scoped actions, and the Option C draft write-through + handoff."""
import asyncio
import base64

from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.responses import StreamingResponse

from software_factory import project_view
from software_factory.projects.materials import ProjectMaterials
from software_factory.db import artifact_by_id
from software_factory.deps import extract_env_creds

import console.state as state
from console.deps import require_authed, authorize_project, _can_see, project_visibility

from console.schemas import (DraftCreateIn, ProjectPatchIn, MaterialScopeIn, MaintenanceToggleIn,
                             OrgDocIn, DepsIn, ProvideDepIn, BudgetIn, RetryNodeIn,
                             RewindIn, DraftPatchIn, AttachIn, PromoteIn, CredsIn, RepoAccessIn,
                             DirectoryCreateIn, FileUploadIn, FileMoveIn, BriefVersionIn)

router = APIRouter()


def _materials() -> ProjectMaterials:
    return ProjectMaterials(
        state.PROJECTS_DIR,
        blobs=state.blobs,
        console=state.console,
        records=state.console.records,
        users=state.users,
        document_kind=state._doc_kind,
        push_ingest_progress=state._push_ingest_sse,
    )


# ── Scope genres (SOF-108): the intake chips, DB-backed ──────────────────────────────────────
@router.get("/api/recipes")
def list_recipes(v: tuple = Depends(require_authed)):
    return {"recipes": state.recipes.published()}


# ── Runs: list + create ───────────────────────────────────────────────────────────────────────
@router.get("/api/projects")
def projects_list(include_archived: bool = False, v: tuple = Depends(require_authed)):
    # SOF-221: scope to the session's tenancy boundary (was v[1]=="admin" → every org's runs, a
    # cross-tenant leak for non-internal customer org-admins). project_visibility() returns None for
    # the operator god-view, else the set of run-owner emails this session may see.
    scope = project_visibility(v)
    if scope is None:
        runs = state.console.list_projects(owner=None, include_archived=include_archived)
    elif len(scope) == 1:                       # member / org-less admin → own only (efficient path)
        runs = state.console.list_projects(owner=next(iter(scope)), include_archived=include_archived)
    else:                                       # org-admin → their org's runs (any member as owner)
        runs = [r for r in state.console.list_projects(owner=None, include_archived=include_archived)
                if (r.get("owner") or "").lower() in scope]
    return {"projects": runs}


# ── Drafts (Option C onboarding) ──────────────────────────────────────────────────────────────
@router.post("/api/drafts")
def create_draft(body: DraftCreateIn, v: tuple = Depends(require_authed)):
    """Mint a durable draft run at the START of onboarding (the form is the sole eager creator on
    mount). Returns its canonical run-<8hex> id; the form passes it into every subsequent
    PATCH/attach/promote and into /api/chat so the rail and the form share ONE draft."""
    if not (body.project_name or "").strip():
        raise HTTPException(status_code=400, detail="project_name is required")
    project_id = state.console.intake.create_draft(
        owner=v[0] or "", name=body.project_name, runtime=body.runtime,
        planning_model=body.planning_model, impl_model=body.impl_model, model=body.model,
        budget=body.budget, github_username=body.github_username,
    )
    return {"project_id": project_id}


# ── Run-scoped GETs ─────────────────────────────────────────────────────────────────────────
@router.get("/api/projects/{pid}")
def project_status(pid: str, v: tuple = Depends(authorize_project)):
    return state.console.status(pid)


@router.get("/api/projects/{pid}/recovery-actions")
def project_recovery_actions(pid: str, v: tuple = Depends(authorize_project)):
    """SOF-165 PR2: this run's tier-2 recovery-action history (open + resolved, newest first).
    Read-only; authed like the rest of the project reads."""
    return {"recovery_actions": state.console.recovery_actions(pid)}


@router.get("/api/projects/{pid}/graph")
def project_graph(pid: str, v: tuple = Depends(authorize_project)):
    return state.console.graph(pid)


@router.get("/api/projects/{pid}/tickets")
def project_tickets(pid: str, v: tuple = Depends(authorize_project)):
    """Build-ticket projection for the kanban view (empty before Stage 2)."""
    return state.console.records.tickets(pid)


@router.get("/api/projects/{pid}/deployments")
def project_deployments(pid: str, v: tuple = Depends(authorize_project)):
    """Per-deliverable deploy state (a run ships 1..N apps; no scalar run-level deploy_url). SOF-216:
    the route delegating to Console.deployments was dropped in the app.py→routers split, leaving the
    method orphaned; this restores it (thin transport, same authorize_project guard as the siblings)."""
    return state.console.records.deployments(pid)


@router.get("/api/projects/{pid}/brief")
def project_brief(pid: str, v: tuple = Depends(authorize_project)):
    """The concierge-finalized product brief — markdown (null until the concierge records the
    kind='product_brief' artifact) plus its durable-storage URL (SOF-137) — and reference-backed
    assumptions from ready doc_summary rows."""
    from software_factory.memory.store import MemoryStore
    brief_rows = [a for a in state.console.records.artifacts(pid)
                  if (a.get("kind") or "") == "product_brief"]
    return {
        "brief_markdown": state.console.intake.product_brief(pid),
        "brief_url": brief_rows[-1].get("path") if brief_rows else None,
        "assumptions": MemoryStore().assumptions("project", pid),
    }


@router.put("/api/projects/{pid}/brief")
def update_project_brief(pid: str, body: dict, v: tuple = Depends(authorize_project)):
    """Thin goal/scope editor (post-promote 'Edit brief' in the Overview tab). Body:
    {goals?: str, scope?: list}. Writes through set_draft_project, which recomposes the
    canonical description; the product brief itself is the Concierge-authored artifact and is
    not editable here. Returns {name, goal, scope, description}."""
    body = body or {}
    return state.console.intake.set_draft_project(
        pid, goal=body.get("goals"), scope=body.get("scope"),
    )


# ── Product Brief: versioned document read/write + history (SOF-244) ─────────────────────────
# Distinct from PUT /brief above (the thin goal/scope projection). These edit the CANONICAL
# kind='product_brief' artifact as a versioned document, converging direct edits with Concierge
# finalization on one newest-wins, immutable-history stream. Invalid/NotFound/Conflict raised by
# state.console.briefs are mapped to 400/404/409 by app.py's ServiceError handler.
@router.get("/api/projects/{pid}/product-brief")
def product_brief_latest(pid: str, v: tuple = Depends(authorize_project)):
    """Newest canonical Product Brief (metadata + markdown), or {"latest": null} if none yet."""
    return {"latest": state.console.briefs.latest(pid)}


@router.get("/api/projects/{pid}/product-brief/versions")
def product_brief_versions(pid: str, v: tuple = Depends(authorize_project)):
    """Every version newest-first — stable artifact ids, timestamps, provenance; no bodies."""
    return {"versions": state.console.briefs.versions(pid)}


@router.get("/api/projects/{pid}/product-brief/versions/{artifact_id}")
def product_brief_version(pid: str, artifact_id: int, v: tuple = Depends(authorize_project)):
    """One historical version by artifact id, authorized to this project (read-only).
    404 if unknown, not a product_brief, or owned by another project."""
    return state.console.briefs.version(pid, artifact_id)


@router.post("/api/projects/{pid}/product-brief/versions")
def product_brief_save(pid: str, body: BriefVersionIn, v: tuple = Depends(authorize_project)):
    """Create a new immutable version from complete markdown (direct document edit). Optimistic:
    a stale base_version_id returns 409 with the current latest; empty markdown returns 400.
    Never mutates a prior version; provenance is origin='user'."""
    return state.console.briefs.save(pid, body.markdown, body.base_version_id, agent=v[0] or "user")


@router.get("/api/projects/{pid}/events")
def project_events(pid: str, v: tuple = Depends(authorize_project)):
    return {"events": state.console.records.events(pid)}


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
    # SOF-139: missing content is an honest 404 (with the reason), never a 200 carrying an error
    # body — a 200 made dead download links look like successful downloads of a JSON error blob.
    if "content" not in result:
        raise HTTPException(status_code=404,
                            detail=f"artifact content not available for {path!r} — the file is no "
                                   "longer stored (it may have been lost when its workspace was torn down)")
    if raw and "content" in result:
        # Raw mode: serve the file itself (right Content-Type) so e.g. the architecture SVG
        # opens full-size in its own browser tab.
        ctype = {"svg": "image/svg+xml", "html": "text/html", "json": "application/json",
                 "md": "text/markdown"}.get(path.rsplit(".", 1)[-1].lower(), "text/plain")
        return Response(content=result["content"].encode(), media_type=f"{ctype}; charset=utf-8")
    return result


@router.get("/api/projects/{pid}/deps")
def project_deps(pid: str, v: tuple = Depends(authorize_project)):
    return state.console.stage2_artifacts(pid)


# ── Project View (PRD §2.5): Overview + Documents aggregates ─────────────────────────────────────
@router.get("/api/projects/{pid}/overview")
def project_overview(pid: str, v: tuple = Depends(authorize_project)):
    status = state.console.status(pid)
    tickets = state.console.records.tickets(pid)["tickets"]
    deployments = state.console.records.deployments(pid)["deployments"]
    owner = status.get("owner") or ""
    org = state.users.org_for_user(owner) if owner else None
    has_verification = bool(status.get("done")) or any(d.get("verified") for d in deployments)
    in_build = (status.get("stage") or 0) >= 2 and not status.get("done")
    docs = project_view.documents(state.blobs.list_for("project", pid), state.console.records.artifacts(pid))
    return {
        "brief": project_view.brief_block(state.console.intake.draft_project(pid), status,
                                          state.console.records.project_created(pid)),
        "build": project_view.build_status(status, tickets),
        "services": project_view.services_at_work(org, deployments, status.get("impl_model") or "",
                                                  has_verification, in_build),
        "agents": project_view.agents_projection(state.console.records.agents(pid), tickets),
        "org": ({"name": org["name"], "industry": org.get("industry"),
                 "connected_systems": org.get("connected_systems", [])} if org else None),
        "materials_count": len(docs["uploaded"]),
        "produced_count": len(docs["produced"]),
    }


@router.get("/api/projects/{pid}/repo-access")
def project_repo_access(pid: str, v: tuple = Depends(authorize_project)):
    return state.console.intake.repo_access(pid)


@router.post("/api/projects/{pid}/repo-access")
def request_project_repo_access(pid: str, body: RepoAccessIn, v: tuple = Depends(authorize_project)):
    username = (body.github_username or "").strip().lstrip("@")
    if not username:
        raise HTTPException(status_code=400, detail="github_username is required")
    owner = state.console.records.project_owner(pid)
    if v[0] and v[0].lower() != owner:
        raise HTTPException(status_code=403, detail="only the project owner can request repository access")
    return state.console.intake.request_repo_access(pid, username)


def _project_documents(pid: str) -> dict:
    return _materials().documents(pid)


@router.get("/api/projects/{pid}/documents")
def project_documents(pid: str, v: tuple = Depends(authorize_project)):
    return _project_documents(pid)


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
    m = _materials()
    m.upload(pid, body.name, raw, body.tag, body.content_type)
    return m.documents(pid)


@router.delete("/api/projects/{pid}/materials/{material_id}")
def project_material_delete(pid: str, material_id: int, v: tuple = Depends(authorize_project)):
    """Delete an uploaded material plus storage, memory chunks/summary, and source artifact."""
    m = _materials()
    if m.delete(pid, material_id) is None:
        raise HTTPException(status_code=404, detail="material not found")
    return m.documents(pid)


@router.post("/api/projects/{pid}/documents/{blob_id}/summarize")
def project_document_summarize(pid: str, blob_id: int, v: tuple = Depends(authorize_project)):
    """Auto-summarize / Regenerate (SOF-36/T3.3): synchronously re-runs the T3.2 ingestion
    pipeline for one document, bypassing the unchanged-content skip so a click always produces a
    fresh summary. The user is waiting on this, unlike the upload path's fire-and-forget
    maybe_ingest_async — small enough (one document) to just block on."""
    result = _materials().summarize(pid, blob_id)
    if result is None:
        raise HTTPException(status_code=404, detail="document not found")
    if result.get("status") == "failed":
        raise HTTPException(status_code=502, detail=result.get("error") or "summarization failed")
    return _materials().documents(pid)


@router.get("/api/projects/{pid}/ingest/stream")
async def project_ingest_stream(pid: str, v: tuple = Depends(authorize_project)):
    """SOF-32: SSE for real-time ingestion progress — a channel SEPARATE from the chat stream
    (see console/state.py's _push_ingest_sse docstring). Same drain/keepalive pattern as
    chat_stream (console/routers/chat.py)."""
    q: list[str] = []
    with state._ingest_sse_lock:
        state._ingest_sse_clients.setdefault(pid, []).append(q)

    async def gen():
        try:
            while True:
                if q:
                    yield q.pop(0)
                else:
                    yield ": keepalive\n\n"
                    await asyncio.sleep(2)
        finally:
            with state._ingest_sse_lock:
                clients = state._ingest_sse_clients.get(pid, [])
                if q in clients:
                    clients.remove(q)

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "Connection": "keep-alive"})


@router.patch("/api/projects/{pid}")
def project_update(pid: str, body: ProjectPatchIn, v: tuple = Depends(authorize_project)):
    """Rename / re-scope / re-describe / re-summarize a promoted project (drafts use PATCH
    /api/projects/{pid}/draft). Sending `scope` recomposes the description (goal + scope line)
    server-side; `summary` sets the customer-facing blurb."""
    return state.console.rename_project(pid, name=body.name, description=body.description,
                                        scope=body.scope, summary=body.summary)


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


@router.post("/api/projects/{pid}/maintenance")
def project_maintenance_toggle(pid: str, body: MaintenanceToggleIn,
                               v: tuple = Depends(authorize_project)):
    """SOF-94: set the maintenance-agent placeholder preference. No-op stub — persists the flag but
    nothing acts on it yet (the maintenance agent isn't built). Surfaced on completed projects."""
    return {"project_id": pid, "maintenance_enabled": state.console.set_maintenance(pid, body.enabled)}


@router.patch("/api/projects/{pid}/materials/{material_id}")
def project_material_scope(pid: str, material_id: int, body: MaterialScopeIn,
                           v: tuple = Depends(authorize_project)):
    """Move an uploaded material between project-scope and org-wide (PRD §2.4). →org puts it in the
    org knowledge base (appears in /api/org/docs); →project moves it back to this project. The moved
    blob is re-homed under the destination scope's tree (SOF-253). Refusals raise a ServiceError
    mapped centrally in console/app.py."""
    m = _materials()
    m.set_scope(pid, material_id, body.scope)
    return m.documents(pid)


# ── Files browser (SOF-253): directory-aware source tree ──────────────────────────────────────
@router.get("/api/projects/{pid}/files")
def project_files(pid: str, v: tuple = Depends(authorize_project)):
    """The Files browser read model: virtual combined root, persisted project + org roots, the
    directory tree with child/member counts + summary state, stable file memberships, and recent
    references. Exposes only this project's scope + its owner org — never another tenant."""
    return _materials().files(pid)


@router.post("/api/projects/{pid}/directories")
def project_directory_create(pid: str, body: DirectoryCreateIn, v: tuple = Depends(authorize_project)):
    """Create a folder under a real scoped parent (a scope root or a folder within it). The virtual
    Files root is rejected; duplicate sibling names return a precise 409. Returns the Files tree."""
    return _materials().create_directory(pid, body.parent_id, body.name)


@router.post("/api/projects/{pid}/files")
def project_file_upload(pid: str, body: FileUploadIn, v: tuple = Depends(authorize_project)):
    """Upload a source file into a real project directory (defaults to the project root). Storage +
    blob metadata + directory membership are written together (no successful orphan). Returns the
    Files tree."""
    if not (body.name or "").strip():
        raise HTTPException(status_code=400, detail="name required")
    try:
        raw = base64.b64decode(body.data_b64 or "", validate=True)
    except Exception:
        raise HTTPException(status_code=400, detail="data_b64 must be valid base64")
    m = _materials()
    m.upload(pid, body.name, raw, body.tag, body.content_type, directory_id=body.directory_id)
    return m.files(pid)


@router.patch("/api/projects/{pid}/files/{blob_id}")
def project_file_move(pid: str, blob_id: int, body: FileMoveIn, v: tuple = Depends(authorize_project)):
    """Move a source file. Omit `scope` to move WITHIN its scope (re-home under `directory_id`);
    set `scope` to "project"/"org" for a cross-scope move (existing scope-change policy + re-home
    under `directory_id`, or the destination scope root if omitted). Returns the Files tree."""
    m = _materials()
    if body.scope:
        m.set_scope(pid, blob_id, body.scope, directory_id=body.directory_id)
        return m.files(pid)
    return m.move_file(pid, blob_id, body.directory_id)


@router.get("/api/projects/{pid}/files/{blob_id}/content")
def project_file_content(pid: str, blob_id: int, v: tuple = Depends(authorize_project)):
    """Raw text for the shared Artifact Viewer — serves BOTH project- and owner-org-scope blobs
    through the project's Files surface (the browser never calls the org content route). Authorized
    by the same read-model rule as the other Files routes (own project OR owner org); out-of-scope
    is 403, unknown is 404. Body/content-type mirror GET /api/org/docs/{id}/content exactly."""
    return _materials().file_content(pid, blob_id)


@router.delete("/api/projects/{pid}/files/{blob_id}")
def project_file_delete(pid: str, blob_id: int, v: tuple = Depends(authorize_project)):
    """Delete a source file (storage + derived memory + source artifacts), same cleanup as the
    materials delete. Returns the Files tree."""
    m = _materials()
    if m.delete(pid, blob_id) is None:
        raise HTTPException(status_code=404, detail="file not found")
    return m.files(pid)


# ── Run-scoped actions ──────────────────────────────────────────────────────────────────────
@router.post("/api/projects/{pid}/deps")
def project_submit_deps(pid: str, body: DepsIn, v: tuple = Depends(authorize_project)):
    result = state.console.submit_deps(pid, body.deps)
    # Launch Stage 3 immediately once deps are satisfied — mirror the chat submit path (chat.py).
    # The background poller would also pick this up, but launching here starts the build without
    # waiting for the next poll tick. extract_env_creds rides provided dep VALUES into the stage env.
    if result.get("satisfied"):
        state.console.start_stage3(pid, extra_creds=extract_env_creds(body.deps))
    return result


@router.post("/api/projects/{pid}/deps/provide")
def project_provide_deployed_dep(pid: str, body: ProvideDepIn, v: tuple = Depends(authorize_project)):
    """#107 post-deploy flow: a user revisiting a live project replaces one mocked provider dep
    (e.g. OPENROUTER_API_KEY) with their own real value. Pushes it onto the deployed app's Railway
    service (triggers a redeploy) — see `Console.provide_deployed_dep`. Always 200; the body's
    `ok` field carries success/failure so the UI can show a specific error, never a silent no-op."""
    return state.console.provide_deployed_dep(pid, body.name, body.value)


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

    Creates a NEW project_id seeded from the source's description, goal, scope, runtime,
    models, budget ceiling, creds_vault_ids, and input materials. Source run is untouched.
    Returns the new project_id. 409 if the source is not stopped or done."""
    email, _role, _ok = v
    try:
        new_id = state.console.relaunch_project(pid, owner=email)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return {"project_id": new_id, "relaunched_from": pid}


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
    # SOF-150: resume_project restores paused_at_node/crashed_at_node on a failed attempt, so a
    # STILL-paused/crashed phase here means the row genuinely was resumable and the retry itself
    # is what failed — surface the real reason (e.g. the budget blocker), not a stale generic
    # message that reads as "this was never resumable" when it actually was.
    if state.console.current_phase(pid) in ("paused", "crashed"):
        reason = state.console.resume_failure_reason(pid)
        raise HTTPException(status_code=409, detail=f"resume failed: {reason}" if reason else
                            "resume failed: no recorded reason — check project.log")
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


# ── Draft write-through + handoff (Option C onboarding; drafts only) ──────────────────────────
@router.get("/api/projects/{pid}/draft")
def get_draft(pid: str, v: tuple = Depends(authorize_project)):
    """Read the draft's intake fields to REHYDRATE the onboarding form when resuming an existing draft
    (the read counterpart to PATCH /draft). Returns {name, goal, scope, description}.
    Draft-only: a promoted project has no editable draft intake."""
    if not state.console.intake.is_draft(pid):
        raise HTTPException(status_code=409, detail="not a draft (already promoted)")
    return state.console.intake.draft_project(pid)


@router.patch("/api/projects/{pid}/draft")
def patch_draft(pid: str, body: DraftPatchIn, v: tuple = Depends(authorize_project)):
    """Structured project write-through: {name?, goal?, scope?, runtime?, recipe_id?}. Server composes
    the canonical description (goal + scope-of-work line). runtime updates the draft's build engine
    (claude|opencode|codex) after the eager create. recipe_id (CBT-9) must name a published recipe — a bad
    id is refused with the real reason instead of silently pinning a draft/archived one; "" clears the
    selection. Call debounced/on-blur, NOT per keystroke."""
    if not state.console.intake.is_draft(pid):
        raise HTTPException(status_code=409, detail="not a draft (already promoted)")
    if body.recipe_id:
        recipe = state.recipes.get(body.recipe_id)
        if not recipe or recipe.get("status") != "published":
            raise HTTPException(status_code=400,
                                detail=f"recipe_id {body.recipe_id!r} does not name a published recipe")
    result = state.console.intake.set_draft_project(
        pid, name=body.name, goal=body.goal, scope=body.scope, runtime=body.runtime,
        model=body.model, recipe_id=body.recipe_id, github_username=body.github_username,
    )
    if body.budget is not None:
        state.console.raise_budget(pid, body.budget)
        result["budget_ceiling"] = body.budget
    return result


@router.post("/api/projects/{pid}/attach")
def attach_draft(pid: str, body: AttachIn, v: tuple = Depends(authorize_project)):
    """Attach project materials (walkthrough video / documents) to the draft's input/.
    PDF/DOCX originals are kept alongside their .md extractions, pushed to object storage,
    and recorded as blobs so they appear in GET /api/projects/{pid}/documents.uploaded."""
    if not state.console.intake.is_draft(pid):
        raise HTTPException(status_code=409, detail="not a draft (already promoted)")
    written = state.console.intake.attach_to_draft(pid, body.files or [])
    _materials().record_draft_attachments(pid, body.files or [])
    return {"attached": written}


@router.post("/api/projects/{pid}/creds")
def store_draft_creds(pid: str, body: CredsIn, v: tuple = Depends(authorize_project)):
    """Store BYOK credentials in Vault against a draft. Returns cred names, never values."""
    if not state.console.intake.is_draft(pid):
        raise HTTPException(status_code=409, detail="not a draft (already promoted)")
    return state.console.intake.store_draft_creds(pid, body.credentials)


@router.post("/api/projects/{pid}/promote")
def promote_draft(pid: str, body: PromoteIn, v: tuple = Depends(authorize_project)):
    """Hand off to the factory: promote the draft into a real run and launch Stage 1. The composed
    state.description + concierge-finalized product brief are the payload (description override
    optional).

    SOF-137 (Minimum Machinery): the only gate — a product brief exists — lives in
    console.promote_draft() itself, not here, so it raises the SAME services.errors.Conflict (409,
    identical wire shape) for every caller: this route AND the concierge's hand_off_to_factory tool
    (concierge_tools.py). Neither the button nor the agent sees a different reason."""
    if not state.console.intake.is_draft(pid):
        raise HTTPException(status_code=409, detail="not a draft (already promoted)")
    try:
        project_id = state.console.promote_draft(pid, description=body.description, target=body.target)
    except ValueError as e:                # duplicate project name (a separate, pre-existing
        raise HTTPException(status_code=409, detail=str(e))  # check inside _provision_and_launch)
    return {"project_id": project_id, "status": "started"}
