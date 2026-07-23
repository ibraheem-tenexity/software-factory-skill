"""Project View (PRD §2.5) assemblers — pure functions over already-fetched run data.

Kept separate from `console` (the data access layer) so the Overview/Documents payloads can be
unit-tested without a DB: the app endpoint gathers raw pieces (status, tickets, deployments,
agents, artifacts, blobs, org) and these functions shape them into the screen's contract.
"""
from __future__ import annotations

import os

# Ticket statuses that count as delivered for the % complete bar.
_DONE_TICKET_STATES = {"done", "deployed", "approved"}

# SOF-199: artifact `kind`s that are INPUT material (read by a stage), not factory OUTPUT — never
# surfaced as a produced deliverable. 'context' = Stage-1's own reading material (SOF-70).
# 'product_brief' = the concierge's pre-handoff onboarding doc (SOF-137) — content-wise it's the
# precursor Stage 1 synthesizes the real PRD from, not the PRD itself; showing it as a peer of the
# real `kind=prd` artifact is exactly the "two pointers to the same spec" duplication SOF-182 found
# (the brief has no DB-inlined content and no source_blob_id, so it renders as a bare external link
# while the real PRD renders natively — same conceptual role, two different broken-feeling
# experiences). It stays reachable via the Overview tab's own dedicated brief link either way.
INPUT_ONLY_KINDS = {"context", "product_brief"}

_EXT_KIND = {"pdf": "pdf", "xlsx": "xlsx", "xls": "xlsx", "csv": "csv", "doc": "doc", "docx": "doc",
             "mp4": "video", "mov": "video", "png": "img", "jpg": "img", "jpeg": "img"}


def _kind_for(name: str) -> str:
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    return _EXT_KIND.get(ext, "doc")


def build_status(status: dict, tickets: list) -> dict:
    """Build-status card: % complete (delivered tickets), agents working, spend vs budget."""
    total = len(tickets)
    done = sum(1 for t in tickets if (t.get("status") or "") in _DONE_TICKET_STATES)
    agents = status.get("agents") or {}
    return {
        "pct": round(done / total * 100) if total else 0,
        "tickets_done": done,
        "tickets_total": total,
        "agents_working": int(agents.get("running") or 0),
        "spent_usd": round(status.get("spent_usd") or 0.0, 2),
        "budget_ceiling": status.get("budget_ceiling") or 0.0,
        "done": bool(status.get("done")),
        "deploy_url": status.get("deploy_url") or "",
    }


def services_at_work(org: dict | None, deployments: list, impl_model: str,
                     has_verification: bool, in_build: bool) -> list:
    """"Services at work" derived from REAL signals only — org integrations, deployments (hosting),
    the implementation LLM, and Playwright testing. Absent signals produce no row."""
    out = []
    for s in (org or {}).get("connected_systems", []) or []:
        out.append({"label": s, "kind": "Integration", "status": "connected",
                    "detail": "org system", "url": None})
    for d in deployments or []:
        out.append({"label": d.get("service_name") or "Railway", "kind": "Hosting",
                    "status": d.get("status") or "deploying", "detail": d.get("app") or "",
                    "url": d.get("url") or None})
    if impl_model:
        out.append({"label": impl_model, "kind": "LLM", "status": "active",
                    "detail": "implementation model", "url": None})
    if has_verification:
        out.append({"label": "Playwright", "kind": "Testing", "status": "passed",
                    "detail": "e2e verification", "url": None})
    elif in_build:
        out.append({"label": "Playwright", "kind": "Testing", "status": "running",
                    "detail": "e2e verification", "url": None})
    return out


def agents_projection(agents: list, tickets: list) -> list:
    """Agents on the project, each joined to its ticket's title (the task it's working)."""
    by_id = {t.get("id"): t.get("title", "") for t in (tickets or [])}
    return [{"role": a.get("role", ""), "model": a.get("model", ""), "status": a.get("status", ""),
             "task": by_id.get(a.get("ticket_id"), ""), "cost_usd": round(a.get("cost_usd") or 0.0, 4)}
            for a in (agents or [])]


def documents(blobs: list, artifacts: list, doc_summaries: dict | None = None,
              org_docs: list | None = None) -> dict:
    """Documents tab: user uploads (run blobs; display name = stored blob name, key-basename
    fallback — SOF-181) + factory
    artifacts + the org knowledge base. `doc_summaries` (SOF-36) is MemoryStore.list_doc_summaries's
    blob_id -> row map — optional so this stays callable/testable with no memory data at all (no
    doc_summary rows yet, e.g. ingestion still running or not yet started); a blob with no entry
    just gets summary=None/summary_status=None. `org_docs` (design change #32 / PRD §2.5b) is
    BlobStore.list_org_docs's rows for the project owner's org — surfaced here so a document toggled
    project→org still appears ON this page (in the "From your organization" group) with a path back
    to project scope, instead of vanishing; optional so callers that only need the counts (Overview)
    can omit it."""
    doc_summaries = doc_summaries or {}
    uploaded = []
    for b in blobs or []:
        key = b.get("storage_key") or ""
        # SOF-181: prefer the blob's stored (original) name; the storage key is uuid-prefixed
        # ("materials/<uuid>-<name>"), so its basename carries that prefix. Returning the prefixed
        # name here (a) showed the ugly "<uuid>-name" label and (b) broke the onboarding remove
        # control — attachFiles backfills blob_id by matching this name against the ORIGINAL
        # filename, so a prefixed name never matched → blob_id stayed null → the remove button
        # (gated on blob_id) never rendered on the fresh-upload path. Mirror the `org` branch below.
        name = b.get("name") or os.path.basename(key) or key
        ds = doc_summaries.get(b.get("id")) or {}
        uploaded.append({"id": b.get("id"), "name": name, "kind": _kind_for(name),
                         "size_bytes": b.get("size_bytes"), "content_type": b.get("content_type"),
                         "storage_key": key, "created_at": b.get("created_at"), "scope": "project",
                         "summary": ds.get("summary_md"), "summary_status": ds.get("status")})
    # SOF-60: origin='user' artifact rows are user-deposited document markdown (agent reading
    # material), not factory output — they'd double-list next to their own upload here.
    # SOF-70/SOF-199: kind='context' rows (Console._provision_and_launch's "input" artifacts, e.g.
    # input/interview.md, input/context.md) are Stage-1's OWN reading material — composed by the
    # console from the intake, not something the factory produced — so they default origin='agent'
    # (unlike SOF-60's user-deposited markdown) and slipped past the origin-only filter above.
    # kind='product_brief' is the same category (SOF-199) — see INPUT_ONLY_KINDS.
    produced = [{"id": a.get("id"), "title": a.get("title", ""), "path": a.get("path", ""),
                 "kind": a.get("kind", ""), "agent": a.get("agent", ""), "ts": a.get("ts")}
                for a in (artifacts or [])
                if a.get("origin") != "user" and a.get("kind") not in INPUT_ONLY_KINDS]
    # Org knowledge base surfaced on the project Documents tab (design #32 / PRD §2.5b). Each row
    # keeps scope="org" so the tile renders the toggle with "Org-wide" active — flipping it to
    # "Project" moves the doc back into this project (the reverse of the vanish-on-toggle bug).
    org = []
    for b in org_docs or []:
        name = b.get("name") or os.path.basename(b.get("storage_key") or "") or ""
        org.append({"id": b.get("id"), "name": name, "kind": _kind_for(name),
                    "size_bytes": b.get("size_bytes"), "content_type": b.get("content_type"),
                    "tag": b.get("tag"), "scope": "org", "used_count": b.get("used_count") or 0})
    return {"uploaded": uploaded, "produced": produced, "org": org}


def _files_scope(scope: str, scope_id: str, directory_rows: list | None,
                 blob_rows: list | None, doc_summaries: dict | None):
    """Shape one persisted scope (project or org) into (directory rows, file rows).

    Only top-level source blobs (`source_blob_id` IS NULL) are tree members — extracted-child
    assets stay provenance via source_blob_id, never a directory entry (mirrors the 0034 backfill
    and the NULL `directory_id` those children keep). Per directory we derive its live child-dir
    count (blobs.directory_id … via parent_id) and member-file count without an extra query, since
    the whole scope is already loaded.

    A top-level source blob with a NULL `directory_id` (record paths that do not yet file the
    blob — e.g. draft attachments, org-KB uploads) is attributed to its SCOPE ROOT: it renders at
    the root and is counted in the root's `member_file_count`. So the root's count never undercounts
    unfiled-but-in-scope material, and every readable file appears exactly once in the combined
    view."""
    doc_summaries = doc_summaries or {}
    members_by_dir: dict = {}
    files = []
    for b in blob_rows or []:
        if b.get("source_blob_id") is not None:
            continue
        did = b.get("directory_id")
        name = b.get("name") or os.path.basename(b.get("storage_key") or "") or ""
        ds = doc_summaries.get(b.get("id")) or {}
        files.append({"id": b.get("id"), "directory_id": did, "scope": scope, "scope_id": scope_id,
                      "name": name, "kind": _kind_for(name), "tag": b.get("tag"),
                      "size_bytes": b.get("size_bytes"), "content_type": b.get("content_type"),
                      "sha256": b.get("sha256"), "created_at": b.get("created_at"),
                      "summary": ds.get("summary_md"), "ingest_status": ds.get("status"),
                      "summary_status": ds.get("status")})
        members_by_dir[did] = members_by_dir.get(did, 0) + 1
    # In-scope files not filed under any folder (directory_id NULL) belong to the scope root — they
    # render there and are counted there, so an unfiled record path can't undercount the root.
    unfiled_members = members_by_dir.get(None, 0)
    child_counts: dict = {}
    for d in directory_rows or []:
        pid = d.get("parent_id")
        child_counts[pid] = child_counts.get(pid, 0) + 1
    dirs = []
    for d in directory_rows or []:
        did = d.get("id")
        member_count = members_by_dir.get(did, 0)
        if d.get("parent_id") is None:          # scope root absorbs the unfiled in-scope files
            member_count += unfiled_members
        dirs.append({"id": did, "parent_id": d.get("parent_id"), "scope": scope,
                     "scope_id": scope_id, "name": d.get("name"),
                     "summary_status": d.get("summary_status"), "summary_md": d.get("summary_md"),
                     "last_successful_summary_at": d.get("last_successful_summary_at"),
                     "created_at": d.get("created_at"), "updated_at": d.get("updated_at"),
                     "child_dir_count": child_counts.get(did, 0),
                     "member_file_count": member_count})
    return dirs, files


def files_tree(scopes: list) -> dict:
    """Files browser read model (SOF-253). `scopes` is an ordered list of persisted scope bundles
    `{scope, scope_id, directories, blobs, doc_summaries}` — the project's own project scope first,
    then the owner-organization scope (if any); a scope the project may not read is simply not in
    the list, so the payload can never leak another project/org.

    Returns:
      * `root`  — a SYNTHESIZED virtual combined root (mixed-scope, `is_virtual`, `id: null`); it is
                  NEVER a database row and never a mutation target.
      * `roots` — the persisted per-scope root identities (the NULL-parent directory of each scope).
      * `directories` — every directory row across the readable scopes, each with parent, scope,
                  child-dir/member-file counts, and truthful summary state + timestamps.
      * `files` — stable blob memberships: blob id, its directory id, scope, type, size, sha, ingest
                  + summary status, and the document summary.
      * `recent` — references (blob id + directory + scope) INTO `files`, not duplicated membership.

    NULL-`directory_id` rule (contract for consumers, e.g. SOF-255): a top-level file with a NULL
    `directory_id` LISTS AT ITS SCOPE ROOT and is COUNTED in that root's `member_file_count`. The
    file row keeps `directory_id: null` — the consumer places it under the file's `scope` root.
    Every readable file therefore appears exactly once in the combined view and root counts never
    undercount unfiled-but-in-scope material.

    File content: GET /api/projects/{pid}/files/{blob_id}/content serves any file in this read
    model — project- OR owner-org-scope — through the one project-relative Files route family
    (body/content-type identical to GET /api/org/docs/{id}/content, so the shared Artifact Viewer
    needs no new branch); out-of-scope is 403, unknown is 404.
    """
    all_dirs: list = []
    all_files: list = []
    for s in scopes or []:
        dirs, files = _files_scope(s["scope"], s["scope_id"], s.get("directories"),
                                   s.get("blobs"), s.get("doc_summaries"))
        all_dirs.extend(dirs)
        all_files.extend(files)
    roots = [d for d in all_dirs if d["parent_id"] is None]
    recent = sorted(all_files, key=lambda f: f.get("created_at") or 0.0, reverse=True)[:10]
    recent_refs = [{"id": f["id"], "directory_id": f["directory_id"], "scope": f["scope"],
                    "name": f["name"], "created_at": f["created_at"]} for f in recent]
    return {
        "root": {"id": None, "parent_id": None, "name": "Files", "scope": "combined",
                 "is_virtual": True, "child_dir_count": len(roots),
                 "member_file_count": len(all_files)},
        "roots": roots,
        "directories": all_dirs,
        "files": all_files,
        "recent": recent_refs,
    }


def brief_block(project: dict, status: dict, created) -> dict:
    """Project brief: name/goal/scope from the draft projection, owner/phase/stage from status."""
    return {
        "name": project.get("name") or status.get("name") or "",
        "description": status.get("description") or project.get("description") or "",
        "goal": project.get("goal") or "",
        "scope": list(project.get("scope") or []),
        "owner": status.get("owner") or "",
        "phase": status.get("phase") or "",
        "stage": status.get("stage") or 0,
        "created": created,
        "runtime": project.get("runtime") or "claude",
        "created_by": project.get("created_by") or status.get("owner") or "",
    }
