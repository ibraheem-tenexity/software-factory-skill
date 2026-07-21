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
    """Documents tab: user uploads (run blobs; display name = storage-key basename) + factory
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
        name = os.path.basename(key) or key
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
