# Software Factory — Architecture (current state)

**As of:** `main` (roles/ownership + Kimi K2.7 + dev/prod env isolation + agents-have-no-Supabase /
factory-provided deploy DB, merged at `f3246fe`). Live console still runs `ee6aad4` (pre-roles) —
deploy pending.
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
│   │  software_factory.console.Console   the orchestrator (start_run, stage launches,      │  │
│   │     gates, deploy, status/graph projection)                                           │  │
│   │        │ subprocess.Popen (per stage)                                                 │  │
│   │        ▼                                                                              │  │
│   │   stage agent process  ── claude -p  (Opus/Sonnet, native Task subagents)             │  │
│   │                        └─ opencode run (Kimi K2.7-code, monolithic)  [SF_RUNTIME]     │  │
│   │        │ writes run.log (stdout)         │ bash: python3 -m software_factory.db …     │  │
│   │        │ MCP: playwright (+ railway for stage 3) — NO supabase access                 │  │
│   │        ▼                                  ▼                                           │  │
│   │   /data volume                       dbshim ─► Postgres (run STATE)                   │  │
│   │     runs/<id>/ input/ run.log chat.jsonl workspace/                                   │  │
│   └────────────────────────────────────────────────────────────────────────────────────┘  │
│                                            │ stage 3 deploys the built app                  │
│   ┌─ built demo apps (one Railway service per run) ─ sf-<run_id>  (+ its own Postgres) ──┐  │
│   └────────────────────────────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────────────────────────────┘
        │                              │                                  │
        ▼                              ▼                                  ▼
  Supabase Postgres            Langfuse Cloud                    Resend (email)
  software-factory-state       LLM traces                       operator notifications
  (factory run STATE)          (per-run, per-turn)
        ▲
        └── (PLANNED) Supabase Storage bucket — durable blob storage for uploaded files,
            run.log, chat.jsonl (today these live only on the /data volume; see §6)
```

Other infra: GitHub (the factory pushes each built app to a repo), the Railway + Playwright MCP
servers (stage-3 agents deploy + browser-verify through these — they have **no Supabase access**; a
run's database is factory-provisioned and handed to the build via `context/deploy-db.json`),
OpenAI/OpenRouter (the chat concierge model).

---

## 2. The pipeline (the product)

A run is born from an **onboarding interview** (a durable *draft*), then moves through three stages,
each a separate agent subprocess launched by the console, gated mechanically (no human review):

```
Stage 0 INTERVIEW  concierge interviews the user → a structured 7-section BRIEF + transcript,
                   persisted on a DRAFT run (canonical run-<8hex>, poller-invisible). On "proceed"
                   the draft is PROMOTED → Stage 1. (Brief editable via the form or the chat.)
Stage 1 RESEARCH   brief + interview + attachments → COUNCIL (3 drafting seats → synthesizer) →
                   PRD.md            gate: PRD complete (≥3 real product URLs, acceptance criteria,
                                           ticket seeds). The PRD targets the harness Input Contract.
Stage 2 DESIGN     PRD → architecture.md + architecture.svg  gate: artifacts exist AND ≥1 buildable
                          + tickets (TicketStore, each tagged   ticket; then the deps gate
                          with its target app)
Stage 3 BUILD      tickets → built app(s) → deploy → verify  gate: done tickets trace to agents AND a
                   (1..N deliverables: sf-<run_id>-<app>)        recorded PASSING Playwright happy-flow
                                                                  per deliverable
```

- **Autonomy (poller, every 3s):** flips a stage to done only when its gate passes *and* its process
  has exited; auto-launches the next stage; auto-satisfies dependencies when no human secret is
  needed. The **only** human pause is a required credential whose disposition is "provide".
- **Budget brake:** per-run ceiling (`SF_COST_CEILING`, per-run override). The poller watches each
  live run's spend; at the ceiling it terminates the stage process (SIGTERM→SIGKILL), records a
  `budget` blocker, preserves state. Operator raises the cap to resume.
- **Definition of done:** a recorded passing Playwright happy-flow against the live URL — deploying
  or merging is NOT done.

---

## 3. Components (`src/software_factory/`)

| Module | Responsibility |
|---|---|
| `console.py` | The orchestrator: `Console` class — `start_run`, `create_draft`/`update_draft_brief`/`promote_draft` (the interview→run lifecycle), `_provision_and_launch`, stage gates (`detect_stage{1,2,3}_done`), budget, `list_runs`/`status`/`graph`/`tickets`/`deployments` projection, ownership. `RunRequest` dataclass. |
| `console/app.py` | FastAPI/uvicorn (ASGI) HTTP shell: auth gate (DI dependencies `viewer`/`require_authed`/`authorize_run`) + REST/JSON (Pydantic bodies) + `/api/chat` (mints a draft for new conversations) + `/api/runs/{id}/{tickets,brief,deployments}` + Project View §2.5 aggregates `/api/runs/{id}/{overview,documents}` + SSE (`StreamingResponse`) + the background poller (started in the app lifespan) + `/api/health`, `/api/me`, `/api/users`. Serves the **React SPA** (`console/web/dist`) when `SF_CONSOLE=react`, else the legacy `index.html`. Also serves the **Tenexity OS operator portal** (separate `admin.html` SPA entry) at `/admin` + `/admin.html` (React mode only). |
| `console/web/` | The **React console** (Vite + React + TypeScript SPA): toolbar with the **graph↔kanban view toggle**, Cytoscape graph, kanban (status columns + wave swimlanes + per-app badge/filter), chat + SSE, the structured **brief form**, projects screen. Built at image-build time; served by `console/app.py`. Opt-in via `SF_CONSOLE=react`. A second entry — `console/web/admin.html` → `src/admin/main.tsx` → `AdminPortal.tsx` (PRD §3 Tenexity OS operator portal: shell + Factory Pulse + Overview/Clients/Projects/Agents/Tools/Provide-access, mock data per §5) — builds alongside it (vite `rollupOptions.input` main+admin) and is served at `/admin`. |
| `brief.py` | The structured onboarding **brief** vocabulary: the 7 sections, interview topics + rubrics, `coverage`/`enough` (the "ready to proceed" heuristic), `brief_to_prompt_block` (injected into Stage 1). |
| `runstate.py` | `RunState` dataclass (run metadata, incl. `brief` + `interview_coverage`, `phase="draft"` for pre-run interviews) + the `Store` protocol; persisted as JSON in the `runstate` table. |
| `db.py` | `RunDB` — the per-run datastore (runstate + canvas tables incl. `deployments`) + the `python3 -m software_factory.db` CLI (incl. `record-deployment`) the stage agents call to record state. |
| `tickets.py`, `agents.py` | `TicketStore` (work units, per-wave, each tagged with its target `app` for multi-deliverable builds) and `AgentRegistry` (per-agent telemetry/cost). |
| `dbshim.py` | The storage seam: `connect(path)` → sqlite (default) or Postgres (schema-per-run). All three stores go through it. |
| `env.py` | dev/prod tiering (`SF_ENVIRONMENT`): `db_backend()` (dev→sqlite, postgres only in prod/test), `stage_env_baseline()` (scrubs console secrets from stage child processes), Railway project allowlist. |
| `auth.py` + `users.py` | Google-OAuth login + HMAC session cookie + service token; `UserStore` directory (roles: admin/member) backing membership + per-run ownership. |
| `chat_agent.py` | The "Factory Concierge" — an OpenAI-Agents-SDK agent that turns a chat conversation into a `start_run` (and answers status/deps questions). |
| `input_pipeline.py`, `pdf_extract.py`, `docx_extract.py` | Ingest: attachments → Markdown, compose the Stage-1 input (`context.txt` + `brief.md` + `interview.md`). `docx_extract.extract_with_images` (mammoth + markdownify) keeps **wireframe images inside Word tables** → `input/images/`. |
| `workspace_setup.py`, `workspace.py` | Per-stage ephemeral workspace: SKILL contract, `.mcp.json`, prior-stage artifacts, vendored design skills. |
| `deploy.py` | Railway deploy + health-check helpers (stage 3). |
| `deploy_db.py` | Factory-provisions a per-run Railway Postgres and writes `context/deploy-db.json` for the build (agents have no Supabase access). |
| `gate.py` | Happy-flow verdict from the Playwright result. |
| `streamlog.py` | Parses `run.log` (claude stream-json / opencode JSON) → authoritative cost + agent graph. |
| `tracing.py` | Langfuse exporter (run.log → traces); env-gated no-op. |
| `notify.py` | Resend email on the four operator events; env-gated no-op. |
| `swarm_adapter.py`, `swarm_stage3.py` | `SF_SWARM=1` parallel-ticket stage-3 driver (opencode swarm). |
| `skills/stage-{1,2,3}-*` | The stage contracts (SKILL.md + .opencode.md variants) the agents follow; `skills/tenexity-design/` is the vendored brand canon. |

---

## 4. Runtimes

A run is pinned at start to one runtime:
- **claude** (default): `claude -p`, Opus 4.8 for Stage 1/2 orchestration, Sonnet 4.6 for Stage 3,
  native **Task subagents** per ticket. Bills the Anthropic key.
- **opencode** (`SF_RUNTIME=opencode`): `opencode run`, **Kimi K2.7-code** via OpenRouter,
  monolithic (one session does all the work; "logical agents" recorded for accounting). Optional
  `SF_SWARM=1` runs stage-3 tickets in parallel via the opencode swarm.

Both write the same `run.log` shape and call the same `db` CLI, so everything downstream is
runtime-agnostic.

---

## 5. Data model & where state lives

**Run STATE → Postgres** (Supabase **`software-factory-as-a-skill`**, Tenexity org — cut over from the
old personal-org `software-factory-state`; see [`schema-erd.md`](schema-erd.md), when `SF_DB=postgres`):
- `public.sf_runs` — the run registry (discovery).
- `public.users` — the user directory (roles) + onboarding profile columns **`org_id`,
  `designation`, `role_description`, `tenexity`** (Tenexity-staff flag).
- `public.organizations` (top-level tenant: `name`, `industry`, `sub_focus`, `headcount`/`revenue`
  stored as **band-label text** e.g. `"51–200"` / `"$10M–$50M"`, `location`, `website`,
  `connected_systems`, plus **`plan`/`monthly_budget_cap`** for Org Admin Usage & billing) — the
  org-on-file model behind the Option C onboarding.
- `public.blobs` — manifest for durable file storage (scope `run`|`org`, scope_id, kind, **`name`**
  (display filename), **`tag`** (category), storage_key, content_type, size, sha256); see §6. The
  org knowledge base (PRD §2.3) is the `scope='org'` rows.
- `public.blob_uses` (`blob_id`, `run_id`) — one row per project that imported an org knowledge-base
  doc; the doc's "used by N projects" count is `COUNT(DISTINCT run_id)`.
- one **schema per run** `sf_run_<id>` containing: `runstate` (the `RunState` JSON, incl.
  description, name, **owner**, models, budget, **`brief`** + `interview_coverage`, and `phase`
  which is `"draft"` for a pre-run interview), `phases`, `artifacts` (metadata: title + path +
  kind, not the bytes), `blockers`, `gates`, `verifications`, **`deployments`** (one row per
  deliverable: `app`, `service_name`, `url`, `status`, `verified`), `tickets` (each with an `app`
  tag, a **6-state `status`** `open → in_progress → done → deployed → qa_testing → approved`, and a
  markdown **`description`** that carries QA bug reports on a `qa_reject` bounce), `agents`.
- `dbshim` translates the stores' SQLite SQL to Postgres (schema-per-run via `SET LOCAL
  search_path`, `?`→`%s`, DDL deltas, `RETURNING id`). Unset `SF_DB` = plain SQLite (local/dev/tests).
- **Migrations (Alembic):** `software_factory.migrate` (run at deploy via `entrypoint.sh` + defensively
  in the boot lifespan, Postgres-only) applies **Alembic** revisions to the global `public` tables
  (`migrations/`, baseline `0001`) and runs a **per-run fan-out** that versions every `sf_run_<id>`
  schema in `public.sf_run_schema_version` (new schemas are stamped at head by `dbshim` on creation).
  This replaces the old scattered `CREATE TABLE IF NOT EXISTS` self-creation as the source of truth.
- **Drafts:** the onboarding interview persists on a `phase="draft"` run with no recorded artifact,
  so `is_pipeline_run` is False and the poller ignores it until `promote_draft` launches Stage 1.
- **Multi-deliverable:** a run ships **1..N deliverables**; per-app deploy/verify state lives in the
  `deployments` table (no scalar run-level `deploy_url`). **Target relational shape (FastAPI/DB
  rebuild):** a `public.run_index` projection, `public.deployments`, and `provenance` replacing the
  `pr INTEGER` hazard on `tickets`/`agents`. Source-of-truth ERD: [`schema-erd.svg`](schema-erd.svg)
  (detail in [`schema-erd.md`](schema-erd.md)).

**Files → the `/data` volume** (NOT in the database today):
- `runs/<id>/input/` — `context.txt` (composed Stage-1 input) + converted attachments + raw uploads
  (incl. **wireframe images**).
- `runs/<id>/run.log` — full agent transcript (cost is parsed from here).
- `runs/<id>/chat.jsonl` — the concierge chat history.
- `runs/<id>/workspace/` — ephemeral checkout the stage agent builds in (deleted on teardown).

So: **short structured metadata is in Postgres; everything a user uploads + all logs/chat are files
on the volume.** Deleting the volume keeps the run list/status/cost (Postgres) but loses uploaded
inputs, logs, and chat — and the factory cannot run without a volume to write to.

---

## 6. Supabase Storage as durable file storage (adapter BUILT; bucket + write-through pending)

Today the volume is a single point of data loss for files. Direction: **a Supabase Storage bucket
(`factory-run-blobs`) becomes the durable home for blobs** — uploaded attachments/images, `run.log`,
`chat.jsonl`, and artifact bytes — keyed by `run_id`, with a `public.blobs` manifest table holding
the pointers. The volume becomes a cache/scratch space, not the source of truth.

**Built:** `software_factory.storage` (`put`/`get`/`url`/`listing`/`sha256`) + `software_factory.blobs.BlobStore`
manifest. The adapter is **env-gated, mirroring `notify`/`tracing`:** with
`SUPABASE_URL` + `SUPABASE_SERVICE_KEY` + `SF_STORAGE_BUCKET` it uploads via the Supabase Storage
REST API using the **project-scoped service_role key** (a console-side secret — agents never get an
account-wide token); without them it falls back to a local `SF_BLOB_DIR`, so dev + the hermetic test
suite need no creds. Two scopes share one bucket: run-scoped `<run_id>/<kind>/<file>` and org-scoped
`org/<org_id>/<kind>/<file>`. The immediate consumer is **durable QA screenshots** (a bug report
bounced to a ticket's `description` links `![](<url>)` images).

**Pending (operator-gated):** creating the `factory-run-blobs` bucket + reading the project service
key (a one-time `SUPABASE_AT` setup step), and the full write-through of inputs/logs/artifacts.

---

## 7. Auth, roles & multi-tenancy (current, combined tip)

- **Login:** Google OAuth → server validates the ID token → issues an HMAC-signed session cookie.
  Allowlist = `SF_AUTH_EMAILS` ∪ the `public.users` directory. Machine callers use the
  `X-SF-Service-Token` header. `/api/health` is open; everything else gated.
- **Roles:** `admin` | `member`. `SF_ADMIN_EMAILS` are bootstrap admins (can't be locked out) and
  seed the directory. Admins manage the team in-console (`/api/users`, the Team panel).
- **Ownership:** every run has an `owner` (creating user's email). **Admins see all projects;
  members see only their own** — enforced on *every* run-scoped route, not just the list.
- **Project identity:** the user-chosen **name** is unique (enforced at creation) and is what the
  console displays — never the run id.

---

## 8. Observability & infra

- **Langfuse** — LLM traces (trace=run, generation=turn, event=tool), exported from `run.log`.
- **Structured logs** — one JSON line per request to stdout (Railway logs).
- **`/api/health`** — pg reachability + disk free + active runs; console health dot + one-shot
  unhealthy email.
- **Railway services:** `factory-console` (the orchestrator + volume), `sf-<run_id>` (each built
  demo app + its factory-provisioned Railway Postgres), `autobuilder`/`factory-api` (legacy).
  **Supabase:** `software-factory-as-a-skill` (Tenexity org — factory state; cut over from the old
  personal-org `software-factory-state`). **Secrets** are Railway service env vars (Anthropic,
  OpenRouter, OpenAI, Resend, Langfuse, Google client id, service token, `DATABASE_URL`).

---

## 9. Key request flows

- **Create a run:** `POST /api/runs` (or chat→concierge) → `start_run` writes `input/`, stamps
  `owner`, persists `RunState`, launches Stage 1.
- **Advance:** poller detects stage done → launches next stage → auto-satisfies deps or pauses for a
  secret → stage 3 builds, deploys to `sf-<run_id>`, drives Playwright, records verification.
- **Watch:** the console polls `status`/`graph`/`events`/`log` (a pure projection of the datastore)
  and streams chat over SSE; cost pill + canvas update live.

---

## 10. Determinism / boundaries (design invariants)

- The canvas/graph/status are a **pure projection of the datastore** — no separate event log.
- A stage is done only on gate-pass **and** process-exit (a crash can't wedge a run; the poller
  bounded-auto-resumes).
- Run *state* is in the DB; *files/logs* are on the volume (→ Supabase Storage, §6).
- The model is used only where judgment is needed (research, design, code, verification); lint,
  parsing, scaffolding, migrations, deploy stay deterministic — the principle the spec-to-demo
  harness (separate plan) extends.

---

## 11. SHIPPED (this change) — orgs + 6-state kanban + QA loop + storage + Option C onboarding

Built on the **current schema-per-run model** (the flat rewrite below was deliberately deferred), all
behind the green test suite:
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
  `GET/POST/PATCH /api/org` endpoints. Handoff reuses the existing run/brief/Stage-1 flow.
- **Kanban** — 6 lifecycle columns.

### Still DEFERRED (operator-reviewed follow-up) — flat project schema + run→project rename
The highest-blast-radius part of the original plan is intentionally **not** in this change (rewrites the
proven `dbshim` pooler primitive, every store, the `db` CLI/SKILL contract, and `console.py`'s graph
projection; benefit is ops-only; the payoff live migration is operator-gated):
- **Rename `run` → `project`** everywhere (`run_index → projects`, `run_id → project_id`,
  `RunState → ProjectState`/`RunDB → ProjectDB`, the `db` CLI arg, the SKILLs, the volume `runs/ → projects/`).
- **Drop schema-per-run** → one `public` schema keyed by `project_id`; retire the per-run fan-out +
  `schema_ddl` + `sf_run_schema_version`; Alembic manages one schema.
- The one-time **data migration** (`sf_run_*` → flat tables; `claimed → in_progress`).
- Full schema in [`schema-erd.md`](schema-erd.md) (the "PROPOSED" section).
- **Layer 1 unchanged either way:** each built app still gets its own **Railway Postgres** (`deploy_db.py`).
