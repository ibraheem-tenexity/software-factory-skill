# Console Schema — reference

Flat single `public` schema. `src/software_factory/models.py` is the single source of truth: Alembic
owns it in prod (baseline `0001_project_baseline` = `models.metadata.create_all`) and
`metadata.create_all` builds it in the test suite — both from the same `metadata`, so they cannot
drift. All DML goes through `dbshim` (a minimal DB-API wrapper over psycopg3 against the
Supabase 6543 transaction pooler). Every per-project table is keyed by a `project_id` Text column; the
global directory tables are single row-sets. See `schema-erd.svg` (regenerated from `schema-erd.dot`).

## Per-project tables (keyed by project_id)

### projectstate
The project registry and the canonical project state. One row per project; `data` is the JSON-encoded
`ProjectState`. `dbshim.registry_projects()` lists projects by scanning this table.

| Column | Type | Notes |
|---|---|---|
| project_id | Text | PK |
| data | Text | not null; JSON-encoded `ProjectState` (excludes `name`/`summary`, which live in their own columns) |
| name | Text | authoritative project name (promoted out of `data`; backfilled by migration 0007) |
| summary | Text | customer-facing project summary shown on the dashboard card; populated externally |

### phases
Pipeline phases recorded for a project.

| Column | Type | Notes |
|---|---|---|
| id | Integer | PK, autoincrement |
| project_id | Text | not null |
| name | Text | not null |
| status | Text | not null, server_default `'active'` |
| stage | Integer | |
| ts | Float | not null |

### artifacts
Files/outputs produced during a project, attributed to the producing agent.

| Column | Type | Notes |
|---|---|---|
| id | Integer | PK, autoincrement |
| project_id | Text | not null |
| title | Text | |
| path | Text | |
| kind | Text | |
| agent | Text | |
| ts | Float | not null |

### blockers
Open/cleared blockers raised during a project.

| Column | Type | Notes |
|---|---|---|
| id | Integer | PK, autoincrement |
| project_id | Text | not null |
| what | Text | |
| blocks | Text | |
| cleared | Integer | not null, server_default `'0'` |
| ts | Float | not null |

### gates
Named quality/approval gates and their status. Composite PK `(project_id, name)` — a gate name is
unique only within a project.

| Column | Type | Notes |
|---|---|---|
| project_id | Text | PK (composite) |
| name | Text | PK (composite) |
| status | Text | not null |
| ts | Float | not null |

### verifications
Verification runs against a deployed URL, pass/fail with result detail.

| Column | Type | Notes |
|---|---|---|
| id | Integer | PK, autoincrement |
| project_id | Text | not null |
| url | Text | |
| passed | Integer | not null |
| result | Text | |
| ts | Float | not null |

### deployments
Deployed apps/services for a project and their state.

| Column | Type | Notes |
|---|---|---|
| id | Integer | PK, autoincrement |
| project_id | Text | not null |
| app | Text | |
| service_name | Text | |
| url | Text | |
| status | Text | not null, server_default `'deploying'` |
| verified | Integer | not null, server_default `'0'` |
| ts | Float | not null |

### tickets
The build backlog. `status` follows the 6-state kanban
`open → in_progress → done → deployed → qa_testing → approved`, with `qa_reject` bouncing a ticket
from `qa_testing` back to `open`. On a QA reject the `description` column carries the appended markdown
QA bug report (what failed + repro + screenshot links), and the agent is cleared so a fresh build
agent re-claims it.

| Column | Type | Notes |
|---|---|---|
| id | Integer | PK, autoincrement |
| project_id | Text | not null |
| title | Text | not null |
| acceptance | Text | not null |
| dod | Text | not null |
| wave | Integer | not null |
| status | Text | not null, server_default `'open'` |
| agent | Text | |
| provenance | Text | merged PR number/URL or commit sha |
| provenance_type | Text | `'pr'` or `'commit'` |
| diff_lines | Integer | not null, server_default `'0'` |
| app | Text | |
| description | Text | not null, server_default `''`; carries QA bug reports |

### agents
Per-agent execution record with token/cost accounting. Composite PK `(agent_id, project_id)` — an
agent id is unique only within a project.

| Column | Type | Notes |
|---|---|---|
| agent_id | Text | PK (composite) |
| project_id | Text | PK (composite) |
| ticket_id | Integer | |
| role | Text | not null |
| model | Text | not null |
| phase | Text | |
| status | Text | not null, server_default `'running'` |
| outcome | Text | |
| cost_usd | Float | not null, server_default `'0'` |
| input_tokens | Integer | not null, server_default `'0'` |
| cached_tokens | Integer | not null, server_default `'0'` |
| output_tokens | Integer | not null, server_default `'0'` |
| reasoning_tokens | Integer | not null, server_default `'0'` |
| provenance | Text | |
| provenance_type | Text | |
| diff_lines | Integer | not null, server_default `'0'` |
| started_at | Float | not null |
| ended_at | Float | |

## Global directory tables

These are single row-sets, not per-project.

### organizations
The org directory. `headcount` and `revenue` are band-label text (e.g. `"51–200"`, `"$10M–$50M"`),
not numbers. `sub_focus` and `connected_systems` are JSON-encoded lists.

| Column | Type | Notes |
|---|---|---|
| id | Text | PK |
| name | Text | not null |
| industry | Text | |
| sub_focus | Text | JSON-encoded list |
| headcount | Text | band label, e.g. `"51–200"` |
| revenue | Text | band label, e.g. `"$10M–$50M"` |
| location | Text | |
| website | Text | |
| connected_systems | Text | JSON-encoded list |
| plan | Text | billing plan label, e.g. `"Team"` |
| monthly_budget_cap | Float | USD/month cap shown in Usage & billing |
| created_at | DateTime(tz) | server_default `now()` |
| created_by | Text | |

### roles
RBAC role definitions (seeded `admin` / `member`). A user links to exactly one role via `role_id`.

| Column | Type | Notes |
|---|---|---|
| id | uuid | PK, `gen_random_uuid()` |
| name | Text | not null, unique — `'admin'` \| `'member'` |
| description | Text | |
| created_at | DateTime(tz) | server_default `now()` |

### role_permissions
Per-role permission grants (composite PK). Cascade-deleted with the role.

| Column | Type | Notes |
|---|---|---|
| role_id | uuid | PK (composite), FK → roles.id (ON DELETE CASCADE) |
| permission | Text | PK (composite) — e.g. `'projects.delete'` |

### users
The user directory **and** the single-source-of-truth allowlist (no env allowlist). Identity is the
uuid `id`; `email` is the invite/match key; access is governed by `status` (invited→active→disabled)
and `role_id`→`roles`, resolved per-request. `password_hash` (scrypt) backs email+password sign-in.

| Column | Type | Notes |
|---|---|---|
| id | uuid | PK, `gen_random_uuid()` |
| google_sub | Text | unique; null until first Google sign-in (match key thereafter) |
| email | Text | not null, unique — invite/allowlist key |
| role_id | uuid | not null, FK → roles.id |
| is_internal | Boolean | not null, default `false` — Tenexity-staff flag (gates `/admin`) |
| status | Text | not null, default `'invited'` — `invited` \| `active` \| `disabled` (CHECK) |
| token_version | Integer | not null, default `0` — bump to revoke live sessions |
| metadata | jsonb | not null, default `'{}'` — non-auth extensibility |
| invited_by | uuid | FK → users.id |
| onboarded_at | DateTime(tz) | set on first sign-in |
| created_at | DateTime(tz) | not null, server_default `now()` |
| updated_at | DateTime(tz) | not null, server_default `now()` |
| org_id | Text | FK → organizations.id |
| designation | Text | |
| role_description | Text | |
| name | Text | display name |
| sign_in_method | Text | not null, default `'google'` — `google` \| `microsoft` \| `password` \| `sso` |
| last_active | DateTime(tz) | touched per authed request (throttled) |
| password_hash | Text | scrypt hash; null = no password set (never selected into the general user row) |

### blobs
Metadata for stored files (the bytes live in object storage, addressed by `storage_key`). `scope` is
`'project'` or `'org'`; `scope_id` is the owning project/org id. `name`/`tag` are display labels.

| Column | Type | Notes |
|---|---|---|
| id | Integer | PK, autoincrement |
| scope | Text | not null; `'project'` or `'org'` |
| scope_id | Text | not null; owning project/org id |
| kind | Text | |
| name | Text | display filename, e.g. `"standard-pricing.xlsx"` |
| tag | Text | category label, e.g. `"Price book"` |
| storage_key | Text | not null; object-storage address |
| content_type | Text | |
| size_bytes | Integer | |
| sha256 | Text | |
| created_at | DateTime(tz) | server_default `now()` |

### blob_uses
One row per (blob, project) — a project drawing on an org-scoped knowledge-base doc. The org-KB
"used by N projects" count is `COUNT(DISTINCT project_id)` over these rows.

| Column | Type | Notes |
|---|---|---|
| id | Integer | PK, autoincrement |
| blob_id | Integer | not null; FK → blobs.id |
| project_id | Text | not null; FK → projectstate.project_id |
| created_at | DateTime(tz) | server_default `now()` |

## Files on the volume

Not in the DB. Per-project files live on the volume at `SF_PROJECTS_DIR` (default `/data/projects`):
`projects/<id>/{input, project.log, chat.jsonl, workspace}`. The `workspace` is the ephemeral build
dir (created → built in → published → destroyed); the rest are durable proof.

The direction for durable blob bytes is the Supabase Storage adapter (env-gated; without it,
`storage.py` falls back to a local directory). It stores the bytes; the `blobs` table holds the
metadata manifest addressing them by `storage_key`.

## Migrations

Alembic, single `public` schema. Baseline `0001_project_baseline` rebuilds every table directly from
`models.metadata.create_all` (the flat project_id-keyed tables plus the global directory tables);
irreversible by design. `python3 -m software_factory.migrate` runs `alembic upgrade head` at deploy
(wired into `entrypoint.sh` before uvicorn) and defensively from the boot lifespan. It is a no-op
without `DATABASE_URL`, idempotent, and safe to re-run.

`_wipe_if_stale` (in `migrate.py`) ran once for the big-bang project rename: when the DB carried a
pre-rename Alembic stamp it dropped the `public` schema so the baseline could rebuild from scratch. It
is a no-op on a fresh DB or one already on the current chain.
