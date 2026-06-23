# Tenexity OS admin API (PRD §3)

Real-data backend for the operator portal (`AdminPortal.tsx`, owner: mhk7nz7i). Branch
`worktree-tenexity-os-api` off main `daf5878`. **All routes are `/api/admin/*` and CROSS-TENANT.**

## Auth gate (baked into every route)
`require_staff` — admits ONLY Tenexity platform staff, because these expose cross-tenant data:
- a valid `X-SF-Service-Token` (headless), **or**
- a human session that is BOTH role `admin` AND has `is_internal` set (Tenexity platform staff).

A customer **org-admin** (role=`admin`) does **NOT** qualify — `require_admin` is per-org; this is
platform-staff only. Cookie auth works for the browser (operator just needs to be staff); no extra
header needed. Non-staff → `403`. The `/admin` SPA route is already React-gated; this gates the data.

## Survey: real-derivable vs new storage
| Section | Real now (no new storage) | New storage / decision |
|---|---|---|
| 3.1 Overview | tenants (`list_orgs`), projects (`list_runs`), agents_active + today_burn + per-role rollups (cross-run SQL on `public.agents`) | friction/autonomy are **not tracked** → returned `null` (honest) |
| 3.2 Clients | orgs × runs (projects/spend/last) + tickets cross-run | — |
| 3.3 Projects | `list_runs(owner=None)` (all tenants) | **REAL/DEMO** → `is_demo` on RunState JSON (no migration), default real |
| 3.4 Agents | cost/success/active/runs per role from `public.agents` | **editable prompt** → new `agent_prompts` table; roster identity → code constant (the 12 callsigns) |
| 3.5 Tools | — | curated **code registry** of real factory tools (DB-backed connect/auth-config = follow-up) |
| 3.6 Access | allow-list = `users` table | **invited vs active** → `users.status` column + flip on first login |

## Endpoints

### 3.1 `GET /api/admin/overview`
```jsonc
{ "pulse": { "tenants": 4, "projects": 24, "agents_active": 27, "agents_total": 55,
             "today_burn": 0.0, "avg_friction": null /* not tracked */ },
  "active_projects": [ { "run_id","name","client","phase","spent_usd","updated" } ],  // top 6 by recency
  "agents": [ { "callsign","sign","role","success","on" } ] }                          // snapshot
```

### 3.2 `GET /api/admin/clients`
```jsonc
{ "clients": [ { "org_id","name","initials","projects","tickets","spend","last_activity" } ] }
```
`projects` = active runs owned by org members; `tickets` = open/in_progress across them; `spend` = Σ run spend; `last_activity` = max run `updated` (epoch|null).

### 3.3 `GET /api/admin/projects?mode=all|real|demo`
```jsonc
{ "projects": [ { "run_id","name","client","factory" /* runtime */,"phase","stage",
                  "tasks_done","tasks_total","spent_usd","updated","is_demo","owner" } ] }
```
`PATCH /api/admin/projects/{rid}` `{is_demo: bool}` → `{run_id, is_demo}`. `mode` filters by `is_demo`.

### 3.4 `GET /api/admin/agents`
```jsonc
{ "agents": [ { "callsign","sign","role","desc","model","cost_tier","success","runs","on","prompt_version" } ] }
```
`GET /api/admin/agents/{callsign}` → adds `{ "prompt","tools":[…],"activity":[…] }`.
`PATCH /api/admin/agents/{callsign}/prompt` `{prompt}` → `{callsign,prompt,version,updated_by,updated_at}`.
Roster identity (callsign/sign/desc/model) is a curated constant (the 12 PRD callsigns); cost/success/runs/on
are rolled up live from `public.agents` by role; `prompt` persists in `agent_prompts`.
> NOTE: stored prompts are served + editable here, but **wiring them back into the live pipeline is a
> separate follow-up** (the pipeline still builds prompts in code). Flagged, not in this PR.

### 3.5 `GET /api/admin/tools`
```jsonc
{ "tools": [ { "name","type","provider","scope","status","used","auth" } ] }
```
A curated registry of the factory's REAL tools (Playwright MCP, Railway MCP, GitHub, the factory-provided
DB, OpenAI/OpenRouter). `used` derived where possible. DB-backed connect/disconnect + auth-config = follow-up.

### 3.6 `GET /api/admin/access`  ·  `POST /api/admin/access`
```jsonc
// GET → { "users": [ { "email","type" /* "New org"|"Tenexity" */,"org","role","status" /* active|invited */ } ] }
// POST { "email", "access_type": "org"|"tenexity", "org_name"? } → { users:[…] }
//   org      → creates the org, user becomes its org-admin, status=invited
//   tenexity → sets the tenexity staff flag, status=invited
```
Login (`auth.login`) flips an invited user → `active` on first successful sign-in. Allow-list = presence in
`users`; sign-in already admits only allow-listed emails.

## Schema (Alembic `0005_tenexity_os`, idempotent; subsumed by the run→project rename)
- `agent_prompts(callsign PK, prompt, version, updated_by, updated_at)`
- `users.status` TEXT default `active`
- (`is_demo` lives in the RunState JSON blob — no column.)

## Rebase note
Off `daf5878`; rebases onto the run→project rename (mechanical `run_id`→`project_id`; `/api/admin/*`
shapes stable, `projects[].run_id` field renames). Migration `0005` is temporary (the rename fresh-baselines).
