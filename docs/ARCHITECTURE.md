# Software Factory — Architecture (current state)

**As of:** `staging` @ `2d4c77b8` (2026-07-16). The codebase uses one flat Postgres `public`
schema keyed by `project_id`; the former schema-per-run and `run → project` transition are complete.
**One-line:** an autonomous pipeline that turns a product description (+ attachments) into a
deployed, browser-verified demo app — research → design → build → deploy — with a web console to
drive and watch it.

**Sources and diagrams:** [`src/software_factory/models.py`](../src/software_factory/models.py) is the
schema source of truth. [`schema-erd.dot`](schema-erd.dot), [`schema-erd.svg`](schema-erd.svg), and
[`schema-erd.md`](schema-erd.md) are synchronized schema references. [`service-architecture.svg`](service-architecture.svg)
is the manually maintained service/storage topology.

---

## 1. Top-level topology

```
                                   ┌──────────────────── operators ────────────────────┐
                                   │ browser (Google or password)   local CLI / scripts │
                                   │        │ cookie                  │ X-SF-Service-Token│
                                   └────────┼──────────────────────────┼─────────────────┘
                                            ▼                          ▼
┌─ Railway project: softwarefactory ─────────────────────────────────────────────────────────┐
│                                                                                              │
│   ┌──────────────── factory-console (the ONE long-lived service) ────────────────────────┐  │
│   │  console/app.py   FastAPI/uvicorn (ASGI) + a 3s background poller                     │  │
│   │     • auth gate (Google/password → HMAC cookie · service token · roles)               │  │
│   │     • REST/JSON API + /api/chat + /mcp/memory; ingest progress has an SSE stream      │  │
│   │     • poller: auto-advance stages, enforce budget, narrate, export traces             │  │
│   │  software_factory.console.Console   the orchestrator (promote_draft, stage launches,      │  │
│   │     gates, deploy, status/graph projection)                                           │  │
│   │        │ subprocess.Popen (per stage)                                                 │  │
│   │        ▼                                                                              │  │
│   │   stage agent process  ── claude -p  (Opus/Sonnet, native Task subagents)             │  │
│   │                        └─ opencode run (Kimi K2.7-code, monolithic)  [SF_RUNTIME]     │  │
│   │        │ writes project.log (stdout)         │ bash: python3 -m software_factory.db …     │  │
│   │        │ MCP: playwright (+ railway for stage 3) — NO supabase access                 │  │
│   │        ▼                                  ▼                                           │  │
│   │   /data volume                       dbshim ─► Postgres (state, artifacts, chat)      │  │
│   │     projects/<id>/ input/ project.log workspace/                                      │  │
│   └────────────────────────────────────────────────────────────────────────────────────┘  │
│                                            │ stage 3 deploys the built app                  │
│   ┌─ built demo apps (one Railway service per project) ─ sf-<project_id> (+ its own Postgres)┐  │
│   └────────────────────────────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────────────────────────────┘
        │                              │                                  │
        ▼                              ▼                                  ▼
  Supabase Postgres            Langfuse Cloud                    Resend (email)
  software-factory-as-a-skill  LLM traces                       operator notifications
  factory state + metadata     (per-project, per-turn)
        ▲
        └── Storage adapter — uploaded bytes and selected artifacts/log snapshots when configured;
            `/data` remains the active log and ephemeral-workspace surface (see §6)
```

Other infra: GitHub (the factory pushes each built app to a repo); the tool registry attaches
Playwright, Exa, and project-memory MCPs to stages, while Railway MCP is Stage 3 only. Stage agents
have **no Supabase access**; Stage 3 provisions its app database through the `provision-db` db-CLI
verb, which writes `context/deploy-db.json`. The concierge uses OpenAI/OpenRouter-compatible chat models.

---

## 2. The pipeline (the product)

A project is born from an **onboarding interview** (a durable *draft*), then moves through three stages,
each a separate agent subprocess launched by the console, gated mechanically (no human review):

```
Stage 0 INTERVIEW  concierge interviews the user → a structured 7-section BRIEF + transcript,
                   persisted on a DRAFT project (canonical project-<8hex>, poller-invisible). On "proceed"
                   the draft is PROMOTED → Stage 1. (Brief editable via the form or the chat.)
Stage 1 RESEARCH   brief + interview + attachments → Research agent (fusion_research: market-scan.md,
                   → PRODUCT           existing-solutions.md, requirements-fit.md) → COUNCIL (3 drafting
                                       seats grounded in those + a PRODUCT Task-subagent synthesizer) →
                                       PRD.md   gate: complete PRD with URLs/ticket seeds, personas,
                                                user stories + acceptance criteria, non-goals, roadmap,
                                                scope modules, and a lock-in verdict to ship.
Stage 2 DESIGN     PRD → architecture.md + architecture.svg → design-spec.md (a DESIGN Task-subagent,
                   → TICKETS          every PRD screen ID referenced) → tickets (TicketStore, each
                                       tagged with its target app)  gate: six required artifacts, design,
                                       mockup, and flow-map screen coverage, valid decision log, and deep
                                       buildable tickets; then the dependency gate.
Stage 3 BUILD      tickets → built app(s) → deploy → verify  gate: recorded agents, all tickets QA-approved,
                   (1..N deliverables: sf-<project_id>-<app>)        build decision log, a passing live
                                                                  Playwright flow, and sign-in proof when demo credentials exist.
```

`PRODUCT` and `DESIGN` are DB-backed `system_agents` rows (like `CONCIERGE`/`STAGE-N`), operator-editable
in Tenexity OS and materialized at workspace-prep time into a native Claude Code subagent file
(`ws/.claude/agents/{product,design}.md`) the orchestrator dispatches via `Task(subagent_type=...)`.
Opencode (no subagent concept) customizes these steps at the existing whole-stage `STAGE-N` prompt
granularity instead.

- **Autonomy (poller, every 3s):** flips a stage to done only when its gate passes *and* its process
  has exited; auto-launches the next stage; auto-satisfies dependencies when no human secret is
  needed. The **only** human pause is a required credential whose disposition is "provide".
- **Budget brake:** per-project ceiling (`SF_COST_CEILING`, per-project override). The poller watches each
  live project's spend; at the ceiling it terminates the stage process (SIGTERM→SIGKILL), records a
  `budget` blocker, preserves state. Operator raises the cap to resume.
- **Definition of done:** a passing live Playwright happy-flow is necessary, not sufficient. Stage 3
  also requires recorded ticket agents, every ticket `approved`, a complete build decision log, and,
  when demo credentials exist, a sign-in step in the passing flow.

---

## 3. Components (`src/software_factory/`)

| Module | Responsibility |
|---|---|
| `console.py` | The orchestrator: `Console` class — `create_draft`/`promote_draft` (the interview→run lifecycle, the only path into a run), `product_brief` (reads the concierge-finalized `kind='product_brief'` artifact), `_provision_and_launch`, stage gates (`detect_stage{1,2,3}_done`), budget, `list_projects`/`status`/`graph`/`tickets`/`deployments` projection, ownership. `ProjectRequest` dataclass. |
| `console/app.py` | FastAPI/uvicorn HTTP shell: local-env bootstrap, singleton reset, lifespan, access logging, static mounts, routers (`open_routes`, `auth`, `org`, `admin_os`, `projects`, `chat`, `research`), and the `/mcp/memory` ASGI mount. |
| `console/web/` | The mandatory Vite + React + TypeScript console. The Dockerfile builds `console/web/dist`; `console/state.py` serves it unconditionally, with no `SF_CONSOLE` switch or legacy-console fallback. It includes the graph, five-column Kanban projection, chat, structured brief form, project view, and the staff-gated `admin.html` operator portal. Admin aggregates, clients, projects, agents, conversations, SOW, tools, and access use real stores/services; unavailable metrics are returned honestly. |
| `services/` | Framework-free application logic between routers and data access: `OrgService`, `Secrets`, `DbConversation`, and `AdminService` are wired in `console/state.py::reset()`. `services/errors.py` maps domain errors to HTTP responses; repositories hold parameterized SQLAlchemy Core CRUD. `UserStore` is the lifecycle/cache façade over `repositories/users.py::UserRepository`. |
| `projectstate.py` | `ProjectState` dataclass (project metadata, incl. the plain `goal`, `phase="draft"` for pre-run interviews; the structured brief is the Concierge-authored `product_brief` artifact, not state) + the `Store` protocol; persisted in the `projectstate` table — most fields as JSON in `data`, with `name` + `summary` promoted to their own authoritative columns (the store pops them out of the blob on write, merges them back on read). |
| `db.py` | `ProjectStore` — the per-project datastore (projectstate + canvas tables incl. `deployments`) + the `python3 -m software_factory.db` CLI (incl. `record-deployment`) the stage agents call to record state. |
| `tickets.py`, `runtime_agents.py` | `TicketStore` (work units, per-wave, each tagged with its target `app` for multi-deliverable builds) and `AgentRegistry` (per-agent telemetry/cost in `runtime_agents`). |
| `tools.py` | `ToolStore` (SOF-81) — the real, live tool/MCP registry (`tools` table: `name` PK, `config` JSONB, `attached_to` JSONB, `key_vault_id`/`key_last4`). Migration-seeded (0013), no code seeding. `config` is the literal shape `workspace_setup.mcp_config()` composes into a stage's `.mcp.json` (or `{"kind":"api",...}` for a non-MCP tool like `github`/`fusion`); `attached_to` names the `system_agents` callsigns / pipeline nodes that use it. A key is vault-only (`vault.py`, same pattern as `org_secrets`) — `all()`/`get()` never surface `key_vault_id`, only `has_key`+`key_last4`. |
| `dbshim.py` | The storage seam: `connect(path)` returns a minimal DB-API wrapper over **psycopg3** against the configured Postgres/pooler endpoint (`prepare_threshold=None`); `?`→`%s` + `RETURNING` translation. All per-project stores go through it; `registry_projects()` lists `public.projectstate`. |
| `env.py` | dev/prod tiering (`SF_ENVIRONMENT`): `stage_env_baseline()` (scrubs console secrets from stage child processes), Railway project allowlist. |
| `auth.py` + `users.py` | Google-OAuth login (`google-auth` token verify) + HMAC `uid`/`token_version` session cookie + service token; `UserStore` = the allowlist+RBAC directory (`roles`/`role_permissions`, status invited/active/disabled, per-request role resolution) backing membership + per-project ownership. |
| `chat_agent.py` | The LangChain `ChatOpenAI`-compatible Factory Concierge. It interviews the user over the onboarding draft, calls `hand_off_to_factory` (`promote_draft`) once the brief is finalized, and answers status/dependency questions. Its effective prompt is `CONCIERGE_INSTRUCTIONS` plus an env-safe, 60-second cached `system_agents.CONCIERGE` override. |
| `input_pipeline.py`, `pdf_extract.py`, `docx_extract.py` | Ingest: attachments → Markdown, compose the Stage-1 input (`context.md` + `brief.md` + `interview.md`). `docx_extract.extract_with_images` (mammoth + markdownify) keeps **wireframe images inside Word tables** → `input/images/`. |
| `workspace_setup.py`, `workspace.py` | Per-stage ephemeral workspace: SKILL contract, `.mcp.json`, prior-stage artifacts, vendored design skills. `.mcp.json` (SOF-81) is COMPOSED FROM the `tools` table (`mcp_config(stage)` → `tools.ToolStore`, filtered by `attached_to` containing `STAGE-{n}`, MCP-shaped rows only) — the OS Tools tab is the source of truth for what a stage build gets, by construction. Falls back to a hardcoded dict only if the table read itself fails (boot resilience). `tool_env_overrides(stage)` returns vault-backed env var overrides for any attached tool with a key set, merged into the stage's env by `console.py::_launch_stage`. |
| `deploy.py` | Shared command and health-check primitives used by deployment/database helpers; Stage 3 drives app deployment through its Railway MCP/skill contract. |
| `deploy_db.py` | Provisions a per-project Railway Postgres and writes `context/deploy-db.json` for the build. `railway add --database postgres --json` captures the generated service id, then reads its `DATABASE_URL`. The durable service id/pending marker make retries reuse rather than orphan a database; host logic caps provisioning at two attempts. The Stage-3 `provision-db` db-CLI verb persists the service/volume ids and records the artifact. |
| `gate.py` | Happy-flow verdict from the Playwright result. |
| `streamlog.py` | Parses the distinct Claude stream-json and OpenCode event shapes into the common downstream cost and agent-graph projection. |
| `notify.py` | Resend email on the four operator events; env-gated no-op. |
| `swarm_adapter.py`, `swarm_stage3.py` | `SF_SWARM=1` parallel-ticket stage-3 driver (opencode swarm). |
| `skills/stage-{1,2,3}-*` | The stage contracts (Claude and OpenCode variants); `skills/tenexity-design/` is the vendored brand canon. The Tenexity OS surfaces the three stage skills and the Concierge as live orchestrator cards. A prompt edit is stored in one `system_agents` row per bare callsign, so a stage override applies to both runtime variants on the next launch; the Concierge override is cached for 60 seconds. Specialist cards remain stored but not applied to runtime prompts. |

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
`project_id` column. SQLAlchemy `models.py` is the current table definition; production upgrades use
the frozen Alembic DDL chain, while test databases use `metadata.create_all`. Changes require an explicit
parity review because those two schema construction paths can drift.

*Per-project tables (keyed by `project_id`):*
- `projectstate` (PK `project_id`) — the `ProjectState`: most fields as JSON in `data` (description,
  **owner**, models, budget, **`goal`**, `phase` — `"draft"` for a pre-run
  interview), with **`name`** + **`summary`** promoted to their own authoritative columns (queryable;
  the store keeps them out of the JSON blob — `summary` is the customer-facing blurb shown on the
  dashboard card, populated externally). This table doubles as the **project registry** — discovery
  (`dbshim.registry_projects()`) lists it.
- `phases`, `artifacts` (title + path + kind, **plus the `content` column** — the produced/uploaded
  text is persisted inline at record time (SOF-138) so it survives workspace teardown; the read path
  serves `content` and only falls back to the workspace file for pre-content rows), `blockers`, `gates`
  (composite PK `(project_id, name)`), `verifications`, **`deployments`** (one row per deliverable:
  `app`, `service_name`, `url`, `status`, `verified`).
- `tickets` — each with an `app` tag, a **6-state `status`** `open → in_progress → done → deployed →
  qa_testing → approved`, a markdown **`description`** carrying QA bug reports on a `qa_reject` bounce,
  and `provenance`/`provenance_type`/`diff_lines`.
- `runtime_agents` (composite PK `(agent_id, project_id)`) — per-agent telemetry/cost.
- `checkpoint` — one durable checkpoint per `(project_id, node)` for host-managed recovery.

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
  display filename, **`tag`** category, storage_key, content_type, size, sha256, and **provenance**
  — `source_blob_id`/`source_page`/`provenance` jsonb, set when a blob is itself an asset extracted
  FROM another blob, e.g. an image pulled out of a document page); see §6. The org knowledge base
  (PRD §2.3) is the `scope='org'` rows.
- `blob_uses` (`blob_id`, `project_id`) — one row per project that imported an org knowledge-base doc;
  the doc's "used by N projects" count is `COUNT(DISTINCT project_id)`.
- **Project Memory (SOF-26):** `doc_summary` (PK `blob_id`→`blobs.id` cascade) — the per-document
  "2,000-ft view": `summary_md`, source-referenced `assumptions` jsonb, `outline` jsonb, a pgvector
  `embedding halfvec(3072)`, and a
  `status` (`pending|ready|failed`) advanced by the ingestion pipeline. `chunk` (PK `id`) — the leaf
  retrieval unit: `ordinal`/`section_path`, `content`, a dense `halfvec(3072)` embedding, and a
  Postgres-generated `fts tsvector` (the sparse/keyword channel — no separate learned-sparse model
  yet, see `project-memory-stack-2026.md`). Both are `scope`/`scope_id`-filtered like `blobs`, so
  project- and org-scoped memory share one app-layer filter shape. Requires `CREATE EXTENSION
  vector` (pgvector) on the target Postgres. Embeddings are produced by `google/gemini-embedding-2`
  via OpenRouter (`memory/embed.py`); its native 3072-dim output is why both columns are `halfvec`
  rather than plain `vector` — pgvector's HNSW/IVFFlat indexes cap out at 2000 dimensions for
  `vector`, but `halfvec` (half-precision) raises that to 4000 (SOF-84).
- **Conversation store (SOF-26):** `conversation` — one row per message/turn (PK `id` = the
  message_id returned to the FE), `session_id`+`seq` (unique together) for deterministic replay
  order, `role`, a canonical `json_blob` content-block list (the source of truth for provider
  replay — `input`/`tool_result` are denormalized display/query conveniences), and per-turn
  `model`/`provider`/token/`cost_usd` attribution. Replaces the in-memory `/converse` mock and the
  volume-only `chat.jsonl` — see `concierge-conversation-store.md`.
- `system_agents` — one editable prompt/model row per orchestrator callsign; `tools` — the stage-attached
  MCP/API registry; `sow` — statement-of-work records; `org_secrets` — org-secret metadata with Vault
  pointers; `autopsy_processed_runs` / `autopsy_signatures`, `recovery_actions`, and `eval_scores` —
  durable benchmark, recovery, and evaluation ledgers.

*Access + migrations:*
- `dbshim` is the storage seam: `connect(path)` returns a **minimal DB-API wrapper over psycopg3**
  against the configured flat-`public` Postgres/pooler endpoint (`prepare_threshold=None`);
  it translates `?`→`%s` and appends `RETURNING id`. Every per-project store goes through it.
- **Migrations (Alembic):** `software_factory.migrate` (run at deploy via `entrypoint.sh` + defensively
  in the boot lifespan; no-op when `DATABASE_URL` is unset) applies **Alembic** revisions to the one
  `public` schema (`migrations/`; baseline `0001_project_baseline` is frozen inline DDL).
  There is no per-project fan-out and no `sf_run_schema_version` — Alembic owns every table directly.
- **Drafts:** the onboarding interview persists on a `phase="draft"` project. It may already have uploaded
  material artifacts, but `is_pipeline_project` excludes it solely by phase until `promote_draft` launches Stage 1.
- **Multi-deliverable:** a project ships **1..N deliverables**; per-app deploy/verify state lives in the
  `deployments` table (no scalar project-level `deploy_url`). Source-of-truth ERD:
  [`schema-erd.svg`](schema-erd.svg) (detail in [`schema-erd.md`](schema-erd.md)).

**Persistent and file surfaces:**
- **Postgres:** project state/canvas/tickets/agent telemetry, conversation turns, artifact Markdown in
  `artifacts.content`, and blob metadata.
- **Object storage through `software_factory.storage`:** uploaded project/org material, user-uploaded
  document bytes, concierge-written brief content, and periodic `project.log` snapshots when storage is configured.
  `blobs.storage_key` is the durable pointer; the local blob directory is the configured fallback.
- **`/data/projects/<id>/`:** the active append-only `project.log`, generated input context, and the
  ephemeral stage workspace. The workspace is deleted after teardown; the active log is retained locally
  and snapshotted to storage when available.

---

## 6. Supabase Storage and blob persistence

`software_factory.storage` (`put`/`get`/`url`/`listing`/`sha256`) and `BlobStore` are the file-byte
adapter and manifest. The adapter is **env-gated, mirroring `notify`:** with
`SUPABASE_URL` + `SUPABASE_SERVICE_KEY` + `SF_STORAGE_BUCKET` it uploads via the Supabase Storage
REST API using the **project-scoped service_role key** (a console-side secret — agents never get an
account-wide token); without them it falls back to a local `SF_BLOB_DIR`, so dev + the hermetic test
suite need no creds. Two scopes share one bucket: project-scoped `<project_id>/<kind>/<file>` and org-scoped
`org/<org_id>/<kind>/<file>`. Project/org upload routes write through this adapter and `blobs`; the poller
and `Console` snapshot active `project.log` content, and user-document Markdown is persisted as artifacts.
The remaining operational requirement is deployment-specific bucket/credential configuration, not a
future write-through implementation.

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
  `X-Forwarded-For` entry. The code relies on Railway's edge to strip client-supplied XFF and prepend
  the client address; this was observed on 2026-06-23 but is an **operational assumption**, not a
  code-guaranteed fact. Re-verify it whenever the edge or ingress changes. Multi-replica
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
- **Project identity:** the user-chosen **name** is a display field; it is not currently database-unique.
  The canonical identity remains the generated project id.

---

## 8. Observability & infra

- **Langfuse** — LLM traces (trace=project, generation=turn, event=tool), exported from `project.log`.
- **Structured logs** — one JSON line per request to stdout (Railway logs).
- **`/api/health`** — pg reachability + disk free + active projects; console health dot + one-shot
  unhealthy email.
- **Deployment inventory:** the code expects a console service with a volume and creates `sf-<project_id>`
  app services with their own provisioned Postgres. Exact Railway/Supabase service names, environments,
  and secret values are operational state and must be verified in those providers. Console secrets are
  Railway service environment variables (Anthropic, OpenRouter, OpenAI, Resend, Langfuse, Google client id,
  service token, `DATABASE_URL`).

**How Python deps reach the deploy image (SOF-48).** `pyproject.toml`'s `dependencies` list is the
single source of truth for everything `software_factory`/`console` actually imports — the
Dockerfile installs directly from it (`pip3 install "/app[postgres]"`, the `postgres` extra pulling
`psycopg[binary]` since the image has no system `libpq-dev`), copying only `pyproject.toml` + `src/`
for that layer so unrelated `console/`/`docs/` changes don't invalidate it. There is no second,
hand-maintained dependency list to drift out of sync — that drift (pgvector landed in `pyproject.toml`
but not a separate Dockerfile `pip3` line) crash-looped prod once (#237). A small number of stage-
workspace CLI/npm tools (Claude Code, OpenCode, opencode-swarm, Playwright browsers, `gh`) are
**not** Python dependencies and stay pinned directly in the Dockerfile as before.
`scripts/verify_deps.py` runs at build time right after the Python install: it imports every
`software_factory`/`console` submodule plus a short explicit list of known *lazily* (function-
local) imported third-party packages that a plain module walk can't see (`markitdown`, `pypandoc`,
`mammoth`, `markdownify` — used inside `pdf_extract.py`/`docx_extract.py`). Any import failure fails
the **build**, not a live deploy. Add a new lazy import to that list whenever one is introduced,
alongside its `pyproject.toml` declaration.

---

## 9. Key request flows

- **Create a project (Option C, the only path):** `POST /api/drafts` mints the canonical id
  (`create_draft`, phase="draft"; attached material may already create artifacts, but the poller ignores
  drafts) → the
  concierge interview finalizes a product brief → `POST /api/projects/{id}/promote` (or the
  concierge's `hand_off_to_factory` tool, same call) → `promote_draft` → `_provision_and_launch`
  writes `input/`, stamps `owner`, persists `ProjectState`, launches Stage 1.
- **Advance:** poller detects stage done → launches next stage → auto-satisfies deps or pauses for a
  secret → stage 3 builds, deploys to `sf-<project_id>`, drives Playwright, records verification.
- **Watch:** the React console polls project/status/graph/ticket/document endpoints. Chat is normal API
  streaming plus durable conversation persistence; the remaining SSE surface is project-document ingest progress.

---

## 10. Determinism / boundaries (design invariants)

- The canvas/graph/status are a **pure projection of the datastore** — no separate event log.
- A stage is done only on gate-pass **and** process-exit (a crash can't wedge a project; the poller
  bounded-auto-resumes).
- State, conversations, artifact text, and blob metadata are in Postgres; uploaded bytes and log snapshots
  use the storage adapter when configured; `/data` holds active logs and the disposable workspace (§6).
- The model is used only where judgment is needed (research, design, code, verification); lint,
  parsing, scaffolding, migrations, deploy stay deterministic — the principle the spec-to-demo
  harness (separate plan) extends.

---

## 11. Changelog — orgs + 6-state kanban + QA loop + storage + Option C onboarding

The current product surface includes:
- **Organizations + user profiles** — `public.organizations` (top-level tenant) and the
  `org_id`/`designation`/`role_description`/`is_internal` columns on `public.users`; headcount/revenue are
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
- **Kanban** — six backend lifecycle states projected into five UI columns: Backlog (`open`), Claimed
  (`in_progress` without an agent), Building (`in_progress` with an agent), Testing
  (`done`/`deployed`/`qa_testing`), and Done (`approved`).

### Subsequently shipped — flat schema + `run → project` rename (now live)
The following schema/lifecycle changes are now in the codebase (see the header + §5):
- **Flat schema** — dropped schema-per-run; one `public` schema keyed by `project_id`, defined by
  `models.py` and owned by a single Alembic chain. The per-project fan-out, `schema_ddl`, and
  `sf_run_schema_version` are gone; `dbshim` is now a thin Postgres-pooler wrapper, no `search_path`
  juggling.
- **`run → project` rename** — identifiers, DB tables/columns (`runstate → projectstate`,
  `run_id → project_id`), API (`/api/runs → /api/projects`), `RunDB → ProjectStore`,
  `RunState → ProjectState`, the `db` CLI arg, the SKILLs, ids (`run-<hex> → project-<hex>`), and the
  volume layout (`SF_RUNS_DIR → SF_PROJECTS_DIR`, `runs/ → projects/`). Baseline
  `0001_project_baseline` is frozen inline DDL; later revisions are also explicit Alembic migrations.
- **Layer 1 unchanged:** each built app still gets its own **Railway Postgres** (`deploy_db.py`).
