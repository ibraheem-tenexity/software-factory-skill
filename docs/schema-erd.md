# Console Schema — reference

Flat single `public` schema. `src/software_factory/models.py` is the application schema source;
production Alembic revisions use frozen DDL, while `metadata.create_all` is reserved for test databases.
Model and migration parity therefore requires review when either changes. All DML goes through `dbshim`
(a minimal DB-API wrapper over psycopg3 against the configured Supabase endpoint). Every per-project
table is keyed by a `project_id` Text column; the
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
| content | Text | Converted/produced Markdown persisted inline |
| source_blob_id | Integer | FK → blobs.id; source upload for a user document |
| origin | Text | `agent` or `user` |

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

### runtime_agents
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
`source_blob_id`/`source_page`/`provenance` (SOF-26) are set only when this blob is itself an asset
extracted FROM another blob (e.g. an image pulled out of a document page) — null for an original upload.

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
| source_blob_id | Integer | FK → blobs.id; the document this asset was extracted from |
| source_page | Integer | 1-based source page/slide, when extracted |
| provenance | jsonb | not null default `'{}'`; extractor, bbox, etc. |

### blob_uses
One row per (blob, project) — a project drawing on an org-scoped knowledge-base doc. The org-KB
"used by N projects" count is `COUNT(DISTINCT project_id)` over these rows.

| Column | Type | Notes |
|---|---|---|
| id | Integer | PK, autoincrement |
| blob_id | Integer | not null; FK → blobs.id |
| project_id | Text | not null; FK → projectstate.project_id |
| created_at | DateTime(tz) | server_default `now()` |

### doc_summary
Project Memory (SOF-26): the per-document "2,000-ft view", keyed 1:1 on the document's `blobs` row.
`scope`/`scope_id` mirror `blobs` so project- and org-scoped memory share one app-layer filter shape
(isolation is app-layer + credential-scoped MCP, not RLS — see ARCHITECTURE §7). `assumptions` entries
carry their own source reference (document + section/page) — no bare confidence scores.

| Column | Type | Notes |
|---|---|---|
| blob_id | Integer | PK, FK → blobs.id (ON DELETE CASCADE) |
| scope | Text | not null; `'project'` or `'org'` |
| scope_id | Text | not null |
| summary_md | Text | map-reduce summary of the whole document |
| assumptions | jsonb | not null default `'{}'`; source-referenced document assumptions |
| outline | jsonb | not null default `'[]'`; section titles + one-line gist each |
| embedding | halfvec(3072) | pgvector; the document-level embedding (google/gemini-embedding-2, SOF-84) |
| token_count | Integer | |
| content_sha256 | Text | staleness check vs `blobs.sha256` |
| status | Text | not null default `'pending'` — `pending`\|`ready`\|`failed` |
| updated_at | DateTime(tz) | server_default `now()` |

### chunk
Project Memory (SOF-26): the leaf retrieval unit — one row per chunk of a document, hybrid-searchable
(dense `vector` + Postgres native `tsvector` as the sparse/keyword channel; no separate learned-sparse
model yet — see `project-memory-stack-2026.md`). `fts` is Postgres-generated from `content`, defined in
`models.py` via `Computed(...)` so `create_all` in tests builds the identical column the Alembic
migration does.

| Column | Type | Notes |
|---|---|---|
| id | Integer | PK, autoincrement |
| blob_id | Integer | not null; FK → blobs.id (ON DELETE CASCADE) |
| scope | Text | not null |
| scope_id | Text | not null |
| ordinal | Integer | not null; position within the document |
| section_path | Text | e.g. `"2 / 2.3 Auth"` — hierarchical nav |
| content | Text | not null |
| dense | halfvec(3072) | pgvector; OpenRouter dense embedding (google/gemini-embedding-2, SOF-84) |
| fts | tsvector | generated always as `to_tsvector('english', content)` stored |
| token_count | Integer | |

### conversation
Durable, provider-agnostic conversation store (SOF-26; replaces the in-memory `/converse` mock and
the volume-only `chat.jsonl` — see `concierge-conversation-store.md`). One row per message/turn; `id`
is the message_id returned to the FE. `json_blob` is the canonical content-block list — the source of
truth for provider replay; `input`/`tool_result` are denormalized display/query conveniences.

| Column | Type | Notes |
|---|---|---|
| id | uuid | PK, `gen_random_uuid()` — the message_id |
| session_id | uuid | not null; groups one conversation/thread |
| seq | Integer | not null; monotonic order within session (replay key) |
| user_id | uuid | FK → users.id; null for agent/tool/system turns |
| project_id | Text | null for org-level chat |
| org_id | Text | |
| role | Text | not null — `user`\|`agent`\|`tool`\|`system` |
| input | Text | plaintext, denormalized from `json_blob` |
| json_blob | jsonb | not null default `'[]'`; canonical content blocks (source of truth) |
| tool_name | Text | |
| tool_call_id | Text | correlates `tool_use` ↔ `tool_result` |
| tool_result | jsonb | convenience mirror of the result block |
| referenced_artifact | Integer | FK → blobs.id |
| model | Text | |
| provider | Text | `'openai'` \| `'anthropic'` \| `'openrouter'` \| ... |
| input_tokens | Integer | default `0` |
| output_tokens | Integer | default `0` |
| cost_usd | Float | default `0` |
| created_at | DateTime(tz) | not null, server_default `now()` |
| updated_at | DateTime(tz) | not null, server_default `now()` |

Unique constraint `(session_id, seq)`; indexes on `project_id`, `org_id`, `user_id`.

### system_agents, tools, and sow
`system_agents` stores the editable orchestrator identity, prompt, model, version, and editor per
callsign. `tools` stores the actual MCP/API config, stage attachment list, Vault key pointer/last-four,
and editor metadata. `sow` stores statement-of-work drafts and lifecycle metadata.

### checkpoint and org_secrets
`checkpoint` has one row per `(project_id, node)` with its JSON output and stamp time for host recovery.
`org_secrets` holds one Vault pointer per `(org_id, name)`, plus non-secret metadata and timestamps.

### Autopsy, recovery, and evaluation ledgers
`autopsy_processed_runs` records one autopsy result per project; `autopsy_signatures` deduplicates
cross-project failure signatures. `recovery_actions` holds the open/resolved recovery lifecycle per
project and cause. `eval_scores` holds one benchmark score payload per project.

## Files on the volume

Per-project files live at `SF_PROJECTS_DIR` (default `/data/projects`): `input/`, the active
`project.log`, and the disposable `workspace/` build directory. Conversation turns are not files;
they live in `conversation`. Storage-backed bytes use the env-gated `storage.py` adapter, with
`blobs.storage_key` as the metadata pointer and a local blob directory as its fallback.

## Migrations

Alembic, single `public` schema. Baseline `0001_project_baseline` is frozen inline DDL, as are
historical revisions where needed; `models.metadata.create_all` is used for test databases. Production
parity therefore requires review whenever schema models or migrations change. `python3 -m software_factory.migrate` runs `alembic upgrade head` at deploy
(wired into `entrypoint.sh` before uvicorn) and defensively from the boot lifespan. It is a no-op
without `DATABASE_URL`, idempotent, and safe to re-run.

`_wipe_if_stale` (in `migrate.py`) ran once for the big-bang project rename: when the DB carried a
pre-rename Alembic stamp it dropped the `public` schema so the baseline could rebuild from scratch. It
is a no-op on a fresh DB or one already on the current chain.

`0008_project_memory` adds `doc_summary`/`chunk` + the `vector` extension (pgvector) + `blobs`
provenance columns; `0009_conversation` adds `conversation`. Both require the target Postgres to
have pgvector available — `CREATE EXTENSION IF NOT EXISTS vector` fails loudly if it's absent
rather than silently degrading.
