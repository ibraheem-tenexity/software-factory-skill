# Software Factory — Architecture (current state)

**As of:** `main` @ `d9fa7b3` — the **flat Postgres schema** (one `public` schema, every per-project
table keyed by `project_id`; schema-per-run dropped) plus the **big-bang `run → project` rename**
(identifiers, DB, API, UI, volume layout) — deployed to `factory-console`.
**One-line:** an autonomous pipeline that turns a product description (+ attachments) into a
deployed, browser-verified demo app — research → design → build → deploy — with a web console to
drive and watch it.

**Diagrams (keep aligned with this doc):** [`schema-erd.svg`](schema-erd.svg) is the source-of-truth
ERD for the console datastore (table-by-table detail in [`schema-erd.md`](schema-erd.md));
[`service-architecture.svg`](service-architecture.svg) is the service/storage topology.

---

## 1. Top-level topology

```
                                   ┌──────────────────── operators ────────────────────┐
                                   │  browser (Google sign-in)      local CLI / scripts │
                                   │        │ cookie                  │ X-SF-Service-Token│
                                   └────────┼──────────────────────────┼─────────────────┘
                                            ▼                          ▼
┌─ Railway project: softwarefactory ─────────────────────────────────────────────────────────┐
│                                                                                              │
│   ┌──────────────── factory-console (the ONE long-lived service) ────────────────────────┐  │
│   │  console/app.py   FastAPI/uvicorn (ASGI) + SSE + a 3s background poller               │  │
│   │     • auth gate (Google OAuth → HMAC cookie · service token · roles)                  │  │
│   │     • REST/JSON API + /api/chat (concierge) + SSE stream                              │  │
│   │     • poller: auto-advance stages, enforce budget, narrate, export traces             │  │
│   │  software_factory.console.Console   the orchestrator (start_project, stage launches,      │  │
│   │     gates, deploy, status/graph projection)                                           │  │
│   │        │ subprocess.Popen (per stage)                                                 │  │
│   │        ▼                                                                              │  │
│   │   stage agent process  ── claude -p  (Opus/Sonnet, native Task subagents)             │  │
│   │                        └─ opencode run (Kimi K2.7-code, monolithic)  [SF_RUNTIME]     │  │
│   │        │ writes project.log (stdout)         │ bash: python3 -m software_factory.db …     │  │
│   │        │ MCP: playwright (+ railway for stage 3) — NO supabase access                 │  │
│   │        ▼                                  ▼                                           │  │
│   │   /data volume                       dbshim ─► Postgres (project STATE)               │  │
│   │     projects/<id>/ input/ project.log chat.jsonl workspace/                           │  │
│   └────────────────────────────────────────────────────────────────────────────────────┘  │
│                                            │ stage 3 deploys the built app                  │
│   ┌─ built demo apps (one Railway service per project) ─ sf-<project_id> (+ its own Postgres)┐  │
│   └────────────────────────────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────────────────────────────┘
        │                              │                                  │
        ▼                              ▼                                  ▼
  Supabase Postgres            Langfuse Cloud                    Resend (email)
  software-factory-state       LLM traces                       operator notifications
  (factory project STATE)      (per-project, per-turn)
        ▲
        └── (PLANNED) Supabase Storage bucket — durable blob storage for uploaded files,
            project.log, chat.jsonl (today these live only on the /data volume; see §6)
```

Other infra: GitHub (the factory pushes each built app to a repo), the Railway + Playwright + exa
(remote web-search, all stages) MCP servers (stage-3 agents deploy + browser-verify through Railway +
Playwright — they have **no Supabase access**; the stage-3 agent provisions the project's database
itself via the `provision-db` db-CLI verb, which writes `context/deploy-db.json`),
OpenAI/OpenRouter (the chat concierge model).

---

## 2. The pipeline (the product)

A project is born from an **onboarding interview** (a durable *draft*), then moves through three stages,
each a separate agent subprocess launched by the console, gated mechanically (no human review):

```
Stage 0 INTERVIEW  concierge interviews the user → a structured 7-section BRIEF + transcript,
                   persisted on a DRAFT project (canonical project-<8hex>, poller-invisible). On "proceed"
                   the draft is PROMOTED → Stage 1. (Brief editable via the form or the chat.)
Stage 1 RESEARCH   brief + interview + attachments → COUNCIL (3 drafting seats → synthesizer) →
                   PRD.md            gate: PRD complete (≥3 real product URLs, acceptance criteria,
                                           ticket seeds). The PRD targets the harness Input Contract.
Stage 2 DESIGN     PRD → architecture.md + architecture.svg  gate: artifacts exist AND ≥1 buildable
                          + tickets (TicketStore, each tagged   ticket; then the deps gate
                          with its target app)
Stage 3 BUILD      tickets → built app(s) → deploy → verify  gate: done tickets trace to agents AND a
                   (1..N deliverables: sf-<project_id>-<app>)        recorded PASSING Playwright happy-flow
                                                                  per deliverable
```

- **Autonomy (poller, every 3s):** flips a stage to done only when its gate passes *and* its process
  has exited; auto-launches the next stage; auto-satisfies dependencies when no human secret is
  needed. The **only** human pause is a required credential whose disposition is "provide".
- **Budget brake:** per-project ceiling (`SF_COST_CEILING`, per-project override). The poller watches each
  live project's spend; at the ceiling it terminates the stage process (SIGTERM→SIGKILL), records a
  `budget` blocker, preserves state. Operator raises the cap to resume.
- **Definition of done:** a recorded passing Playwright happy-flow against the live URL — deploying
  or merging is NOT done.

---

## 3. Components (`src/software_factory/`)

| Module | Responsibility |
|---|---|
| `console.py` | The orchestrator: `Console` class — `start_project`, `create_draft`/`update_draft_brief`/`promote_draft` (the interview→run lifecycle), `_provision_and_launch`, stage gates (`detect_stage{1,2,3}_done`), budget, `list_projects`/`status`/`graph`/`tickets`/`deployments` projection, ownership. `ProjectRequest` dataclass. |
| `console/app.py` | FastAPI/uvicorn (ASGI) HTTP shell. **Modularized**: `app.py` is now only `FastAPI()` + access-log middleware + lifespan + static mounts + router includes. Pieces: `console/state.py` (shared singletons console/users/blobs/prompts/tool_store/agent_store/`_chat_runner`/`login_throttle` behind `reset()` + SSE registry/`_push_sse` + SPA/serving helpers), `console/throttle.py` (in-process password-login brute-force/DoS throttle), `console/deps.py` (auth DI: `viewer`/`require_authed`/`authorize_project`/`require_admin`/`require_staff`/`_staff_session`), `console/schemas.py` (Pydantic bodies), `console/poller.py` (3s background poller + `_health` + lifespan), `console/routers/{open_routes,auth,org,admin_os,projects,chat}.py`. Routes unchanged: `/api/chat` (mints a draft) + `/api/projects/{id}/{tickets,brief,deployments}` + Project View §2.5 `/api/projects/{id}/{overview,documents}` + SSE + `/api/health`, `/api/me`, `/api/users` + Org §2.3 + Tenexity OS §3. Serves the **React SPA** (`console/web/dist`) when `SF_CONSOLE=react`, else the legacy `index.html`. Also serves the **Tenexity OS operator portal** (`admin.html` SPA entry) at `/admin` + `/admin.html` (React mode only, staff-gated). |
| `console/web/` | The **React console** (Vite + React + TypeScript SPA): toolbar with the **graph↔kanban view toggle**, Cytoscape graph, kanban (status columns + wave swimlanes + per-app badge/filter), chat + SSE, the structured **brief form**, projects screen. Built at image-build time; served by `console/app.py`. Opt-in via `SF_CONSOLE=react`. A second entry — `console/web/admin.html` → `src/admin/main.tsx` → `AdminPortal.tsx` (PRD §3 Tenexity OS operator portal: shell + Factory Pulse + Overview/Clients/Projects/Agents/Tools/Provide-access, mock data per §5) — builds alongside it (vite `rollupOptions.input` main+admin) and is served at `/admin`. |
| `services/` | **Service layer** (in progress): application/business logic between the HTTP routers and the data-access stores — validation, orchestration, cross-store aggregation, caching policy. Framework-free; signals failure with domain errors in `services/errors.py` (`Invalid`/`NotFound`/`Forbidden`), which `console/app.py` maps to HTTP 400/404/403. `services/org_service.py` (`OrgService`) owns the Org Admin §2.3 logic the `org` router used to inline; `services/files.py` holds the shared `doc_kind` classifier. Service singletons are built in `console/state.py::reset()` (e.g. `state.org_service`) and routers call them. Remaining routers/stores migrate incrementally. |
| `brief.py` | The structured onboarding **brief** vocabulary: the 7 sections, interview topics + rubrics, `coverage`/`enough` (the "ready to proceed" heuristic), `brief_to_prompt_block` (injected into Stage 1). |
| `projectstate.py` | `ProjectState` dataclass (project metadata, incl. `brief` + `interview_coverage`, `phase="draft"` for pre-run interviews) + the `Store` protocol; persisted in the `projectstate` table — most fields as JSON in `data`, with `name` + `summary` promoted to their own authoritative columns (the store pops them out of the blob on write, merges them back on read). |
| `db.py` | `ProjectStore` — the per-project datastore (projectstate + canvas tables incl. `deployments`) + the `python3 -m software_factory.db` CLI (incl. `record-deployment`) the stage agents call to record state. |
| `tickets.py`, `agents.py` | `TicketStore` (work units, per-wave, each tagged with its target `app` for multi-deliverable builds) and `AgentRegistry` (per-agent telemetry/cost). |
| `dbshim.py` | The storage seam: `connect(path)` returns a minimal DB-API wrapper over **psycopg3** against the flat `public` schema (Supabase 6543 transaction pooler, `prepare_threshold=None`); `?`→`%s` + `RETURNING` translation. All per-project stores go through it; `registry_projects()` lists `public.projectstate`. |
| `env.py` | dev/prod tiering (`SF_ENVIRONMENT`): `stage_env_baseline()` (scrubs console secrets from stage child processes), Railway project allowlist. |
| `auth.py` + `users.py` | Google-OAuth login (`google-auth` token verify) + HMAC `uid`/`token_version` session cookie + service token; `UserStore` = the allowlist+RBAC directory (`roles`/`role_permissions`, status invited/active/disabled, per-request role resolution) backing membership + per-project ownership. |
| `chat_agent.py` | The "Factory Concierge" — an OpenAI-Agents-SDK agent that turns a chat conversation into a `start_project` (and answers status/deps questions). Its effective prompt is `CONCIERGE_INSTRUCTIONS` plus an env-safe, 60s TTL cached `agent_prompts.CONCIERGE` override so prompt edits apply to new concierge sessions without per-turn DB latency. |
| `input_pipeline.py`, `pdf_extract.py`, `docx_extract.py` | Ingest: attachments → Markdown, compose the Stage-1 input (`context.txt` + `brief.md` + `interview.md`). `docx_extract.extract_with_images` (mammoth + markdownify) keeps **wireframe images inside Word tables** → `input/images/`. |
| `workspace_setup.py`, `workspace.py` | Per-stage ephemeral workspace: SKILL contract, `.mcp.json`, prior-stage artifacts, vendored design skills. |
| `deploy.py` | Railway deploy + health-check helpers (stage 3). |
| `deploy_db.py` | Provisions a per-project Railway Postgres and writes `context/deploy-db.json` for the build (agents have no Supabase access). Uses `railway add --database postgres --json` (the bare form is interactive and hangs headless) → **captures the real auto-named serviceId** → reads `DATABASE_URL` via `railway variables --service <serviceId> --json`. Idempotent: the serviceId is persisted before the variables read, so a retry **reuses** that service (never re-adds → no orphan). serviceId is the durable handle for teardown. Invoked by the **stage-3 agent** via the `provision-db` db-CLI verb (`db.py`), which persists the serviceId/volumeId to ProjectState + records the artifact; the agent runs it once and `add-blocker`+STOPs on failure (no code-level attempt cap — prompt + provision-idempotency + reaper are the orphan backstop). |
| `gate.py` | Happy-flow verdict from the Playwright result. |
| `streamlog.py` | Parses `project.log` (claude stream-json / opencode JSON) → authoritative cost + agent graph. |
| `notify.py` | Resend email on the four operator events; env-gated no-op. |
| `swarm_adapter.py`, `swarm_stage3.py` | `SF_SWARM=1` parallel-ticket stage-3 driver (opencode swarm). |
| `skills/stage-{1,2,3}-*` | The stage contracts (SKILL.md + .opencode.md variants) the agents follow; `skills/tenexity-design/` is the vendored brand canon. The 3 SKILL.md files are also surfaced **read-only** in the Tenexity OS §3.4 Agents API as `kind:"stage_skill"` orchestrator cards (`GET /api/admin/agents/{STAGE-1,STAGE-2,STAGE-3}` returns the real on-disk prompt, `prompt_applied:true`, `?runtime=claude\|opencode`); a 4th `kind:"concierge"` card (`CONCIERGE`) surfaces the live `CONCIERGE_INSTRUCTIONS` constant (`prompt_source:"code"`, model = `chat_agent.select_chat_model` default **gpt-5.4**). All 4 are **editable from the dashboard AND the edits DRIVE runs** (Part 2): `PATCH /api/admin/agents/{callsign}/prompt {prompt, runtime?}` stores an override in `agent_prompts` under a composite key (`STAGE-1::claude`/`::opencode` per-runtime, `CONCIERGE`); `DELETE` reverts to the default. The override is read at run launch — stage skills via `prepare_workspace(skill_override=…)` writing `ws/SKILL.md`, the concierge via a 60s TTL cached PromptStore lookup passed into `Agent(instructions=...)` — so an edit applies to the NEXT run/session after cache refresh (not in-flight). GET returns the effective prompt + `is_default`/`overridden`/`version`. The 12 role/specialist cards stay `applied:false` (subagent managed prompts = later part-2b). |

---

## 4. Runtimes

A project is pinned at start to one runtime:
- **claude** (default): `claude -p`, Opus 4.8 for Stage 1/2 orchestration, Sonnet 4.6 for Stage 3,
  native **Task subagents** per ticket. Bills the Anthropic key.
- **opencode** (`SF_RUNTIME=opencode`): `opencode run`, **Kimi K2.7-code** via OpenRouter,
  monolithic (one session does all the work; "logical agents" recorded for accounting). Optional
  `SF_SWARM=1` runs stage-3 tickets in parallel via the opencode swarm.

Both write the same `project.log` shape and call the same `db` CLI, so everything downstream is
runtime-agnostic.

---

## 5. Data model & where state lives

**Project STATE → Postgres** — **one flat `public` schema** (Supabase **`software-factory-as-a-skill`**,
Tenexity org — cut over from the old personal-org `software-factory-state`; full detail in
[`schema-erd.md`](schema-erd.md)). Schema-per-run is gone; every per-project table carries a
`project_id` column. SQLAlchemy `models.py` is the single table definition; Alembic owns the schema in
prod and `metadata.create_all` builds it in tests, so the two cannot drift.

*Per-project tables (keyed by `project_id`):*
- `projectstate` (PK `project_id`) — the `ProjectState`: most fields as JSON in `data` (description,
  **owner**, models, budget, **`brief`** + `interview_coverage`, `phase` — `"draft"` for a pre-run
  interview), with **`name`** + **`summary`** promoted to their own authoritative columns (queryable;
  the store keeps them out of the JSON blob — `summary` is the customer-facing blurb shown on the
  dashboard card, populated externally). This table doubles as the **project registry** — discovery
  (`dbshim.registry_projects()`) lists it.
- `phases`, `artifacts` (metadata: title + path + kind, not the bytes), `blockers`, `gates`
  (composite PK `(project_id, name)`), `verifications`, **`deployments`** (one row per deliverable:
  `app`, `service_name`, `url`, `status`, `verified`).
- `tickets` — each with an `app` tag, a **6-state `status`** `open → in_progress → done → deployed →
  qa_testing → approved`, a markdown **`description`** carrying QA bug reports on a `qa_reject` bounce,
  and `provenance`/`provenance_type`/`diff_lines`.
- `agents` (composite PK `(agent_id, project_id)`) — per-agent telemetry/cost.

*Global directory tables (one row-set, not per-project):*
- `roles` / `role_permissions` — RBAC: one row per named role (`admin`/`member`, uuid PK, seeded);
  `role_permissions` maps a role to many permission strings (e.g. `projects.delete`).
- `users` — canonical identity **and** the allowlist (single source of truth for who can access).
  uuid PK; **`google_sub`** (Google's stable id, set on first sign-in — the match key thereafter),
  unique **`email`** (invite/allowlist key), **`role_id`**→`roles`, **`is_internal`** (Tenexity-staff
  flag, was `tenexity`), **`status`** ∈ `invited|active|disabled`, **`token_version`** (per-user session
  revoke), **`metadata`** jsonb (non-auth extensibility only), `invited_by`, `onboarded_at`,
  `created_at`/`updated_at` (trigger). Onboarding profile columns **`org_id`, `designation`,
  `role_description`** are kept (Org Admin/onboarding join on them).
- `organizations` (top-level tenant: `name`, `industry`, `sub_focus`, `headcount`/`revenue` as
  **band-label text** e.g. `"51–200"` / `"$10M–$50M"`, `location`, `website`, `connected_systems`,
  plus **`plan`/`monthly_budget_cap`** for Org Admin Usage & billing) — the org-on-file model behind
  Option C onboarding.
- `blobs` — manifest for durable file storage (scope **`project`**|`org`, scope_id, kind, **`name`**
  display filename, **`tag`** category, storage_key, content_type, size, sha256); see §6. The org
  knowledge base (PRD §2.3) is the `scope='org'` rows.
- `blob_uses` (`blob_id`, `project_id`) — one row per project that imported an org knowledge-base doc;
  the doc's "used by N projects" count is `COUNT(DISTINCT project_id)`.

*Access + migrations:*
- `dbshim` is the storage seam: `connect(path)` returns a **minimal DB-API wrapper over psycopg3**
  against the flat `public` schema (Supabase 6543 transaction pooler, `prepare_threshold=None`);
  it translates `?`→`%s` and appends `RETURNING id`. Every per-project store goes through it.
- **Migrations (Alembic):** `software_factory.migrate` (run at deploy via `entrypoint.sh` + defensively
  in the boot lifespan; no-op when `DATABASE_URL` is unset) applies **Alembic** revisions to the one
  `public` schema (`migrations/`, baseline **`0001_project_baseline`** = `models.metadata.create_all`).
  There is no per-project fan-out and no `sf_run_schema_version` — Alembic owns every table directly.
- **Drafts:** the onboarding interview persists on a `phase="draft"` project with no recorded artifact,
  so `is_pipeline_run` is False and the poller ignores it until `promote_draft` launches Stage 1.
- **Multi-deliverable:** a project ships **1..N deliverables**; per-app deploy/verify state lives in the
  `deployments` table (no scalar project-level `deploy_url`). Source-of-truth ERD:
  [`schema-erd.svg`](schema-erd.svg) (detail in [`schema-erd.md`](schema-erd.md)).

**Files → the `/data` volume** (NOT in the database today; dir set by `SF_PROJECTS_DIR=/data/projects`):
- `projects/<id>/input/` — `context.txt` (composed Stage-1 input) + converted attachments + raw uploads
  (incl. **wireframe images**).
- `projects/<id>/project.log` — full agent transcript (cost is parsed from here).
- `projects/<id>/chat.jsonl` — the concierge chat history.
- `projects/<id>/workspace/` — ephemeral checkout the stage agent builds in (deleted on teardown).

So: **short structured metadata is in Postgres; everything a user uploads + all logs/chat are files
on the volume.** Deleting the volume keeps the project list/status/cost (Postgres) but loses uploaded
inputs, logs, and chat — and the factory cannot run without a volume to write to.

---

## 6. Supabase Storage as durable file storage (adapter BUILT; bucket + write-through pending)

Today the volume is a single point of data loss for files. Direction: **a Supabase Storage bucket
(`factory-run-blobs`) becomes the durable home for blobs** — uploaded attachments/images, `project.log`,
`chat.jsonl`, and artifact bytes — keyed by `project_id`, with a `public.blobs` manifest table holding
the pointers. The volume becomes a cache/scratch space, not the source of truth.

**Built:** `software_factory.storage` (`put`/`get`/`url`/`listing`/`sha256`) + `software_factory.blobs.BlobStore`
manifest. The adapter is **env-gated, mirroring `notify`:** with
`SUPABASE_URL` + `SUPABASE_SERVICE_KEY` + `SF_STORAGE_BUCKET` it uploads via the Supabase Storage
REST API using the **project-scoped service_role key** (a console-side secret — agents never get an
account-wide token); without them it falls back to a local `SF_BLOB_DIR`, so dev + the hermetic test
suite need no creds. Two scopes share one bucket: project-scoped `<project_id>/<kind>/<file>` and org-scoped
`org/<org_id>/<kind>/<file>`. The immediate consumer is **durable QA screenshots** (a bug report
bounced to a ticket's `description` links `![](<url>)` images).

**Pending (operator-gated):** creating the `factory-run-blobs` bucket + reading the project service
key (a one-time `SUPABASE_AT` setup step), and the full write-through of inputs/logs/artifacts.

---

## 7. Auth, roles & multi-tenancy (current, combined tip)

- **Login:** Google OAuth → server verifies the ID token via **`google-auth`** (`verify_oauth2_token`:
  signature against Google's JWKS w/ key rotation, `exp`, `aud`, `iss`) + `email_verified`. It then
  resolves the token to an allowed user (`users.authenticate`: match `google_sub`, else `email`;
  invited/active OK, disabled rejected; first sign-in sets `google_sub`+`status=active`+`onboarded_at`)
  and mints an **HMAC-signed cookie carrying only `uid`+`token_version`+`exp`** (`HttpOnly; Secure;
  SameSite=Lax; Path=/; Max-Age`). The **role is NOT in the cookie**.
- **Email+password login** (`POST /api/auth/password`, alongside Google): `users.authenticate_password`
  applies the **same** allowlist + `active`-lifecycle gate, constant-time-verifies a stdlib-**scrypt**
  hash (`password_hash`, never selected into the general user row), and mints the **same** `uid`+`tv`
  cookie. Generic `401` for every failure (never leaks which). A **brute-force/DoS throttle**
  (`console/throttle.py`, in-process per-replica, behind `state.login_throttle`) gates it: per-email
  (free 5, the tight per-account net) **and** per-IP (free 10) failed-attempt counters with exponential
  backoff (2s→…, capped 15 min) → `429` + `Retry-After`, **checked before the scrypt verify** so a
  throttled attempt pays no hash cost (closes online brute-force *and* the scrypt-per-attempt DoS). A
  good login clears the counters; idle keys reset after 15 min. The per-IP key uses the **LEFTMOST**
  `X-Forwarded-For` entry: Railway's edge **strips** any client-supplied XFF and **prepends** the real
  client, so leftmost is the real, non-forgeable client and is independent of internal-hop count (the
  rightmost entries are rotating Railway-internal addresses — verified empirically on prod 2026-06-23,
  `X-Envoy-External-Address` absent; kept only as a defensive first-check). ⚠️ Non-forgeability relies
  on Railway's edge stripping inbound XFF — re-verify if the edge/ingress changes. Multi-replica
  scale-out would move the counters to a shared store (flagged, not built).
- **Allowlist = the `public.users` table only** (no env allowlist — `SF_AUTH_EMAILS`/`SF_ADMIN_EMAILS`
  are gone). `status ∈ invited|active|disabled` is the whole "who can access" question. Machine callers
  use the constant-time-checked `X-SF-Service-Token` header. `/api/health` is open; everything else gated.
- **Per-request authorization:** `viewer` verifies the cookie (sig+expiry, no DB), loads the user by
  `uid`, and **rejects a disabled user or a stale `token_version`** — so a demotion/revoke takes effect
  on the *next* request. Role is resolved per-request from `role_id`→`roles.name`. **Revoke** = set
  `status=disabled` + bump `token_version` (invalidates the live cookie); secret rotation
  (`SF_SESSION_SECRET`) is the global-logout lever.
- **Roles:** `admin` | `member`. Cold-start is seeded from **`SF_BOOTSTRAP_ADMIN_EMAIL`** (the only
  email allowed in env, seeded once as an `is_internal` admin, never removable); thereafter all access
  is managed in-console (`/api/users`/`/api/admin/access`, the Team & access screen) — no redeploy.
- **Tenexity OS `/admin` gate (`_staff_session`):** a human session reaches the operator portal only if
  `role==admin` **AND** `is_internal==true`.
- **Ownership:** every project has an `owner` (creating user's email). **Admins see all projects;
  members see only their own** — enforced on *every* project-scoped route, not just the list.
- **Project identity:** the user-chosen **name** is unique (enforced at creation) and is what the
  console displays — never the project id.

---

## 8. Observability & infra

- **Langfuse** — LLM traces (trace=project, generation=turn, event=tool), exported from `project.log`.
- **Structured logs** — one JSON line per request to stdout (Railway logs).
- **`/api/health`** — pg reachability + disk free + active projects; console health dot + one-shot
  unhealthy email.
- **Railway services:** `factory-console` (the orchestrator + volume), `sf-<project_id>` (each built
  demo app + its factory-provisioned Railway Postgres), `autobuilder`/`factory-api` (legacy).
  **Supabase:** `software-factory-as-a-skill` (Tenexity org — factory state; cut over from the old
  personal-org `software-factory-state`). **Secrets** are Railway service env vars (Anthropic,
  OpenRouter, OpenAI, Resend, Langfuse, Google client id, service token, `DATABASE_URL`).

---

## 9. Key request flows

- **Create a project:** `POST /api/projects` (or chat→concierge) → `start_project` writes `input/`, stamps
  `owner`, persists `ProjectState`, launches Stage 1.
- **Advance:** poller detects stage done → launches next stage → auto-satisfies deps or pauses for a
  secret → stage 3 builds, deploys to `sf-<project_id>`, drives Playwright, records verification.
- **Watch:** the console polls `status`/`graph`/`events`/`log` (a pure projection of the datastore)
  and streams chat over SSE; cost pill + canvas update live.

---

## 10. Determinism / boundaries (design invariants)

- The canvas/graph/status are a **pure projection of the datastore** — no separate event log.
- A stage is done only on gate-pass **and** process-exit (a crash can't wedge a project; the poller
  bounded-auto-resumes).
- Project *state* is in the DB; *files/logs* are on the volume (→ Supabase Storage, §6).
- The model is used only where judgment is needed (research, design, code, verification); lint,
  parsing, scaffolding, migrations, deploy stay deterministic — the principle the spec-to-demo
  harness (separate plan) extends.

---

## 11. Changelog — orgs + 6-state kanban + QA loop + storage + Option C onboarding

The product surface below, all behind the green test suite:
- **Organizations + user profiles** — `public.organizations` (top-level tenant) and the
  `org_id`/`designation`/`role_description`/`tenexity` columns on `public.users`; headcount/revenue are
  **band-label text**. Org context is available to feed the Stage-1 PRD.
- **Tickets → 6 states** (`open → in_progress → done → deployed → qa_testing → approved`, with
  `qa_reject` bouncing to `open`) + a markdown **`description`** carrying bug reports; transition verbs
  on `TicketStore` and the `db` CLI. The Stage-3 **QA loop** is documented in both stage-3 SKILLs and the
  host **done-gate now requires `all_approved()`** (every ticket QA-approved) on top of the
  traceable-agents + passing-Playwright gates.
- **Supabase Storage adapter + `blobs` manifest** — see §6 (env-gated; local fallback).
- **Option C onboarding** — the React front door (`console/web/src/components/onboarding/`), two paths
  selected by `GET /api/org` (first-time company capture vs returning org-on-file), with
  `GET/POST/PATCH /api/org` endpoints. Handoff reuses the existing project/brief/Stage-1 flow.
- **Kanban** — 6 lifecycle columns.

### Subsequently shipped — flat schema + `run → project` rename (now live)
The two highest-blast-radius items that were once deferred are now **in `main` and deployed** (see the
header + §5):
- **Flat schema** — dropped schema-per-run; one `public` schema keyed by `project_id`, defined by
  `models.py` and owned by a single Alembic chain. The per-project fan-out, `schema_ddl`, and
  `sf_run_schema_version` are gone; `dbshim` is now a thin Postgres-pooler wrapper, no `search_path`
  juggling.
- **`run → project` rename** — identifiers, DB tables/columns (`runstate → projectstate`,
  `run_id → project_id`), API (`/api/runs → /api/projects`), `RunDB → ProjectStore`,
  `RunState → ProjectState`, the `db` CLI arg, the SKILLs, ids (`run-<hex> → project-<hex>`), and the
  volume layout (`SF_RUNS_DIR → SF_PROJECTS_DIR`, `runs/ → projects/`). Baseline `0001_project_baseline`
  rebuilds the schema from scratch (no data migration — the operator chose a clean wipe).
- **Layer 1 unchanged:** each built app still gets its own **Railway Postgres** (`deploy_db.py`).
