# Project View backend API (PRD §2.5)

Contract for the Project View frontend (`orgproject.jsx → ProjectDashboard`). Branch
`worktree-project-view-backend` off main `dcd50d2` (post-concierge). Status: **building (TDD).**

The §2.5 screen has two tabs — **Overview** and **Documents** — both scoped to one project (run).
Almost all underlying data already exists (status/tickets/deployments/agents/artifacts/blobs/org);
this branch adds **two aggregate endpoints** so the frontend makes one call per tab instead of
five, and so derived fields (% complete, services-at-work, agent→task join) are computed
server-side. Both routes reuse the existing `authorize_run` ownership gate (admin/owner only).

> Naming: built against current `run` naming; rebases onto 40zxvvrk's `run→project` sweep later
> (mechanical `run_id`→`project_id`, `/api/runs`→`/api/projects`). Route *shapes* below are stable.

---

## 1. Overview tab

`GET /api/runs/{rid}/overview` → `200`

```jsonc
{
  "brief": {
    "name": "Quote-to-Epicor automation",
    "description": "...",
    "goal": "...",                  // from the structured brief
    "scope": ["Quoting / RFQ", "Pricing & approvals"],
    "owner": "ibraheem@acme.com",
    "phase": "Build · stage 3",
    "stage": 3,
    "created": 1718000000.0          // epoch seconds, or null
  },
  "build": {
    "pct": 45,                       // round(tickets_done / tickets_total * 100); 0 if no tickets
    "tickets_done": 5,
    "tickets_total": 11,
    "agents_working": 3,             // agents currently running
    "spent_usd": 4.20,
    "budget_ceiling": 30.0,
    "done": false,
    "deploy_url": ""                 // live URL once shipped + verified
  },
  "services": [                       // "services at work" — derived from REAL signals (see below)
    {"label": "Epicor", "kind": "Integration", "status": "connected", "detail": "org system", "url": null},
    {"label": "Railway", "kind": "Hosting", "status": "live", "detail": "web", "url": "https://..."},
    {"label": "claude-opus-4-8", "kind": "LLM", "status": "active", "detail": "implementation model", "url": null},
    {"label": "Playwright", "kind": "Testing", "status": "passed", "detail": "e2e verification", "url": null}
  ],
  "agents": [                         // agents on this project (role → its ticket title)
    {"role": "opus", "model": "claude-opus-4-8", "status": "running", "task": "Discount approval workflow", "cost_usd": 1.10}
  ],
  "org": {"name": "Acme Industrial Supply", "industry": "Industrial Distribution",
          "connected_systems": ["epicor"]},   // inherited org context; null if no org on file
  "materials_count": 3,              // uploaded-by-user docs (full list in /documents)
  "produced_count": 8               // factory-produced artifacts
}
```

**`services` derivation** (honest — only what we actually know about the run):
- **Integration** — one per `org.connected_systems` entry (`status: "connected"`).
- **Hosting** — one per deployment (`label` = service host, `status` = live/deploying, `url`, `detail` = app).
- **LLM** — the run's `impl_model` (`status: "active"`).
- **Testing** — `Playwright` when the run has a passing verification (`status: "passed"`), else `running` while in build.
No fabricated services; if a signal is absent the row is omitted.

## 2. Documents tab

`GET /api/runs/{rid}/documents` → `200`

```jsonc
{
  "uploaded": [   // "Uploaded by you" — run-scoped blobs (name derived from the storage key basename)
    {"name": "sample-rfq-email.pdf", "kind": "pdf", "size_bytes": 94208,
     "content_type": "application/pdf", "storage_key": "run-abc/inputs/sample-rfq-email.pdf",
     "created_at": 1718000000.0}
  ],
  "produced": [   // "Produced by the factory" — artifacts table
    {"title": "Architecture", "path": "workspace/ARCHITECTURE.md", "kind": "plan",
     "agent": "architect", "ts": 1718000500.0}
  ]
}
```

`kind` ∈ `pdf | xlsx | csv | doc | video | img` for uploaded (derived from filename ext → your
`FILE_KIND` tiles); artifact `kind` is the factory's own label (`repo`/`deploy`/`plan`/`context`/…).

---

### What's new vs reused
- **New** (this branch): `GET /api/runs/{rid}/overview`, `GET /api/runs/{rid}/documents`;
  `console.agents(rid)` + `console.artifacts(rid)` read accessors; pure assembler module
  `software_factory.project_view`.
- **Reused unchanged**: `console.status/tickets/deployments/draft_brief/run_owner`, `BlobStore.list_for`,
  `users.org_for_user`, the `authorize_run` gate.
- **No schema change.** (Run-blob display name comes from the storage key — no new column; the
  org-admin branch separately owns `blobs.name/tag`.)
