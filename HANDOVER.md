# Handover — software-factory-skill

_Last updated: 2026-06-19._

## LATEST (2026-06-19) — feature build on branch `worktree-flat-project` (NOT merged, NOT deployed)

An autonomous build off the plan `this-is-the-feedback-purring-donut.md`. **8 commits on
`worktree-flat-project`** (tip `c9c01e1`), **full suite 451 passed / 3 skipped, `console/web` build
green.** Nothing deployed, nothing pushed, no Supabase resources created — per the operator's standing
constraints. Built by the integrator + three subagents (onboarding, QA-gate done inline, neck-beard).

**Shipped (all on the CURRENT schema-per-run model):**
- **Org/User model** (`users.py`) — `public.organizations` + user profile cols (`org_id`,
  `designation`, `role_description`, `tenexity`); headcount/revenue are **band-label text**. `fd71538`
- **6-state tickets + QA loop** (`tickets.py`, `db.py` CLI) — `open→in_progress→done→deployed→
  qa_testing→approved`; `qa_reject` bounces to `open` with a markdown bug report in the new
  `description`; `IllegalTransition` guards. `fbfc19a`
- **Storage adapter + blobs** (`storage.py`, `blobs.py`) — Supabase Storage REST / local fallback,
  env-gated; manifest table. `fc21c80`
- **Stage-3 QA gate** — `detect_stage3_done` now also requires `all_approved()`; both stage-3 SKILLs
  document the per-ticket QA loop. `a45cbb8`
- **Option C onboarding** (`console/web/src/components/onboarding/`) — both paths (first-time capture /
  returning org-on-file) selected by `GET /api/org`; `GET/POST/PATCH /api/org` endpoints; handoff reuses
  the existing run/brief/Stage-1 flow. `c4bfbcc`
- **Kanban 6 columns** + docs. `6ad061b`, `34c039e`

**Verify:** `python3 -m venv .venv && .venv/bin/pip install -e '.[dev,postgres]'`, then
`. .venv/bin/activate && PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q` (≈3.7 min) and
`cd console/web && npm install && npm run build`. (The "local test env is broken" gotcha below is
OUTDATED for this worktree — a fresh `.venv` runs the **whole** suite incl. the openai/httpx tests.)

**DEFERRED to an operator-reviewed follow-up (integrator decision — see ARCHITECTURE §11):** the
flat-schema rewrite + global `run→project` rename + Alembic-flat + the one-time live data migration.
Reason: highest blast radius (rewrites `dbshim`'s pooler primitive, every store, the `db` CLI/SKILL
contract, `console.py`'s graph projection); benefit is ops-only; the live migration is operator-gated
regardless. Because it's deferred, the per-run fan-out / `schema_ddl` / `sf_run_schema_version` are
**still live** — do not delete them until that rewrite is done.

**Operator next steps for this build:** (1) review the branch; (2) to enable real blob storage, the
one-time `SUPABASE_AT` setup — create the `factory-run-blobs` bucket + read the project `service_role`
key (adapter falls back to local until then); (3) follow-ups noted in the onboarding commit: bundle the
real Hanken Grotesk/JetBrains Mono woff2 (system fallbacks for now), and wire doc/video upload through
the storage adapter (model-only today); (4) decide whether to schedule the deferred flat rewrite.

---

## TL;DR — the one thing to know
`main` is at **`f3246fe`** with the full combined work merged, but the **live console is still
`ee6aad4` — NOT deployed**. Merging didn't deploy (deploys are an explicit `railway up`). The next
action is a gated deploy that also needs a DB cutover decision. Nothing is mid-build, so it's safe.

## What's on `main` now (merged, not live)
- **Multi-user roles & ownership**: admin/member roles (`users.py`, `public.users`); every run has an
  `owner`; admins see all projects, members see only their own — enforced on **every** run-scoped
  route; admin **Team panel** + `/api/users` + `/api/me`.
- **Project identity**: the user-chosen **name** is unique (enforced at creation); console displays
  the name, never the run-id.
- **Runs-list loading skeleton** (ops-reported UX fix).
- **Kimi K2.7-code** default + **dev/prod env isolation** (`env.py`: `db_backend()`,
  `stage_env_baseline()` secret-scrub, Railway project allowlist) — from the opencode-kimi peer.
- **Supabase removed from agents** + **factory-provided deploy database** (`deploy_db.py`): stage-3
  agents have NO Supabase MCP/token; the factory provisions a per-run Railway Postgres and hands the
  agent `context/deploy-db.json`; DB tokens are a new `deploy-db` disposition.

## Session arc (how we got here)
pg migration (run state → Postgres) → **registry-guard incident** (a wrong db-CLI arg order created
junk pg schemas; fixed with run-id guards + boot janitor) → **roles/ownership** build → **Supabase
credential incident** (see below) → PR #3 (roles+Kimi+env) + PR #4 (Supabase removal) merged.

## Branches & PRs
- `main` = `f3246fe` (PR #3 + #4 merged).
- `feature/spec-to-demo-harness` — the gk9 spec-to-demo harness **plan only** (`docs/plans/spec-to-demo-harness.md`), not started.
- Stale, safe to delete: `roles-ownership`, `opencode-kimi`, `feature/no-supabase-deploy-db`, `pg-migration-wip`.

## The pending deploy (gated on the operator)
To go live, `railway up` the `factory-console` service after:
1. Set **`SF_AUTH_SECRET`** (so this is the last forced logout; without it every deploy logs everyone out).
2. Clear the ghost run **`run-48133f03`** (empty/$0, state-only delete — safe).
3. **DB cutover decision** — flip `DATABASE_URL` from `software-factory-state` (`uxlrlwxnhtphvddbgbge`,
   personal org, the CURRENT live DB) to **`software-factory-as-a-skill`** (`dbqgnwhshrskfnyqcewd`,
   Tenexity org, the intended DB). Needs **migrate-vs-fresh** + the new connection string
   (operator-owned — this session's Supabase access can't reach the Tenexity org). **Do not delete
   `software-factory-state` until after the cutover is verified** — it's the live DB right now.

## Supabase credential incident (resolved structurally; audit open)
The deployed `SUPABASE_ACCESS_TOKEN` was an **account-wide PAT** (`sbp_4ed6…`) that could create/DELETE
any project incl. the **Tenexity production org** — and autonomous stage-3 agents held it, provisioning
into prod. Resolution: token **REVOKED** (operator); agents made **Supabase-free** (PR #4, the hard
fix). **Standing rules (also in `CLAUDE.md`):** use `software-factory-as-a-skill` for the console DB;
**never create new Supabase projects.** Still open (operator, via Supabase dashboard): the **delete-side
audit** — whether any agent deleted a prod project mid-run (the revoked token can't read the audit log).

## Open decisions for the operator
1. Deploy now keeping the old DB, **or** deploy + cut over to `software-factory-as-a-skill` (then delete the old).
2. **FastAPI** server conversion — recommend *after* this deploy (settled `server.py` + a real test env).
3. **ORM** — recommend the **hybrid** (SQLAlchemy models + Alembic migrations, keep `dbshim` routing)
   over a full SQLModel rewrite; the per-run-schema-on-a-transaction-pooler model is the hard part.
4. **Supabase Storage for files** — durable home for uploads/images/logs/chat (today only on `/data`);
   must live under the dedicated factory account, never prod.

## Gotchas / facts the next agent needs
- Secrets live in `env_text.txt` (repo root, gitignored) + Railway service vars / Doppler.
- The `gh` active account drifts to **`ibraheem-111`**; pushing to the repo needs **`ibraheem-tenexity`**
  (`gh auth switch --user ibraheem-tenexity`).
- **Local test env is broken** (box lost python3.10; no pytest/openai). Use a fresh venv:
  `python3 -m venv /tmp/sfvenv && /tmp/sfvenv/bin/pip install pytest`, run with
  `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`, and skip the `openai`-dep tests (`test_chat_agent*`, `test_server_routes`).
- Storage seam: `dbshim.connect(path)` — sqlite (dev) or Postgres schema-per-run (prod) via per-statement
  `SET LOCAL search_path` (the 6543 transaction pooler resets it). Run STATE in pg; files/logs/chat on `/data`.
- **No migrations**: tables are `CREATE TABLE IF NOT EXISTS` in store constructors — adding a *column*
  needs an explicit `ALTER` (e.g. the harness's `tickets.app`); JSON fields on `runstate` are free.
- Railway: `factory-console` (orchestrator + `/data` volume) + `sf-<run_id>` (each built app).

## Pointers
`ARCHITECTURE.md` (full architecture), `SPEC.md` (the behavioral contract),
`docs/plans/spec-to-demo-harness.md` (the next workstream), `COORDINATION.md` (inter-agent).
