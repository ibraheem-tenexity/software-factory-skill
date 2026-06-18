# Plan — FastAPI server + database-integration replacement

_Draft 2026-06-17. Companion to `docs/schema-erd.md` (authoritative for table shapes) and the ORM
analysis in chat. Owner: software-factory-skill (main) session._

## Context
The console HTTP layer is a hand-rolled stdlib `BaseHTTPRequestHandler` (`console/server.py`) and the
storage layer is hand-rolled SQL in store constructors + `dbshim`'s sqlite↔pg translation + per-run
`SET LOCAL search_path`. Two goals: (1) move the HTTP shell to **FastAPI** (typed routes, pydantic
validation, OpenAPI, testable, cleaner auth/ownership dependencies); (2) **replace the DB integration**
with **SQLAlchemy models + Alembic migrations** — killing the no-migrations `ALTER`-by-hand hazard and
the hand-rolled SQL translation, and making ownership/name-uniqueness real DB constraints. The
`Console` orchestrator + the `db` CLI contract + the stage SKILLs must keep working throughout.

## Non-goals (this plan)
- No full "flat relational, drop schema-per-run" rebuild in v1 (that's the eventual end-state; see Phase 4).
- No files/logs/chat → Supabase Storage in v1 (separate workstream; manifest tables sketched in docs/schema-erd.md).
- No DB cutover decision (operator-owned) — but the Alembic baseline must run cleanly on whichever DB.

## Sequencing vs. the pending deploy
The roles/Supabase work (`main` f3246fe) is merged but undeployed, and a DB cutover to
`software-factory-as-a-skill` is pending. **This plan ships AFTER that deploy+cutover settles** — doing a
server+DB rewrite on top of an undeployed, about-to-be-cut-over base multiplies risk. Phase 0 (the
provenance bug) is the only piece that should ship immediately/independently.

---

## Phase 0 — `pr` → `provenance` (live bug, standalone, ship now)
Independent of FastAPI/ORM. `tickets.pr` and `agents.pr` are `INTEGER`, but opencode `mark_done` writes a
commit-SHA string → **Postgres rejects it → opencode/Kimi runs on the live (pg) console can't close
tickets → can't reach done.** Fix: add `provenance text` (+ `provenance_type` `pr|commit`) to `tickets`
and `agents`; `mark_done`/`finish-agent` write `provenance`; keep `pr` readable for back-compat or
migrate it. Files: `tickets.py`, `agents.py`, `db.py` CLI, callers in `console.py`. Tests + a pg check.
(Coordinated with Codex — they've accepted it into `docs/schema-erd.md`; I offered to take the storage code.)

## Phase 1 — DB integration → SQLAlchemy + Alembic (hybrid)
**Approach (recommended): incremental hybrid, not a big-bang ORM rewrite.**
- Add deps: `sqlalchemy>=2`, `alembic`, `psycopg` (already present).
- **`models.py`** — SQLAlchemy 2.0 declarative models mirroring `docs/schema-erd.md`: `User`, `RunIndex` (new),
  and the per-run tables (`Phase/Artifact/Blocker/Gate/Verification/Ticket/Agent`). `runstate` stays a
  JSON blob initially (a `RunState`↔row mapping, not column-exploded yet).
- **Connection/session layer** replacing `dbshim`'s hand-rolled translation but KEEPING the model:
  - Global tables (`public.users`, `public.run_index`, registry) → one engine on `public` — clean, no
    per-run-schema complexity.
  - Per-run tables → a session whose connection sets `search_path` per transaction (reuse dbshim's proven
    `_tx`/advisory-lock primitive under a SQLAlchemy Core/ORM surface, or `schema_translate_map`). This is
    the load-bearing, risky part (transaction-pooler resets search_path per statement) — keep dbshim's
    routing semantics, swap only the SQL-building/translation.
  - sqlite (dev/tests) → per-run file engine; SQLAlchemy emits sqlite-correct DDL natively (retires the
    `?`→`%s` / `AUTOINCREMENT`→`IDENTITY` / `RETURNING` hand-translation).
- **Repositories preserved**: `RunDB`, `TicketStore`, `AgentRegistry`, `UserStore` keep their
  constructor signatures (`path` arg) and method APIs — reimplemented over SQLAlchemy. The
  `python3 -m software_factory.db <verb> <runs_dir> <run_id>` CLI and the `TicketStore('<run.db>')`
  SKILL snippets MUST stay byte-compatible.
- **`run_index`** (promoted into this pass per the schema review): a `public` projection — `run_id PK,
  name UNIQUE, owner (indexed), phase, stage, runtime, deploy_url, spent_usd, held, …, created_at,
  updated_at`. Write-through on every `RunState.save`. → `list_runs()` reads ONE table (kills the
  per-run-schema N+1), `name_taken` becomes a `UNIQUE` constraint (not a racy Python scan), ownership
  filtering becomes `WHERE owner = ?`.
- **Alembic**: a baseline migration capturing the current schema + Phase 0 provenance + `run_index`;
  run migrations at boot (or a deploy step). Forward-only, matching the existing migration philosophy.

## Phase 2 — FastAPI server (replaces `console/server.py`)
**Status: IMPLEMENTED on branch `fastapi-server` (off `consolidated-base`) — pending integrator merge.**
Done as a standalone server-layer port (independent of Phase 1): `console/app.py` (FastAPI/uvicorn)
replaces `console/server.py`; DI auth (`viewer`/`require_authed`/`authorize_run`), Pydantic bodies,
1:1 routes, SSE via `StreamingResponse`, poller+boot in the app lifespan, JSON access-log middleware.
`test_server_routes.py` ported to `TestClient` (8 passing); `Procfile`/`Dockerfile`/`entrypoint.sh`/
`scripts/dev-console.sh` switched to `uvicorn console.app:app`; `fastapi`+`uvicorn` added to deps.
Follow-up for the integrator: wire the viewer `role` through `ChatAgentRunner.handle_message(role=…)`
(k7apqsug's chat-ownership hardening) — left as-is here to keep the port behavior-preserving.

Swap the HTTP shell; `Console` + repositories unchanged behind dependencies.
- **App**: `console/app.py` — FastAPI + `uvicorn` (ASGI). Dockerfile `CMD` → `uvicorn console.app:app`.
- **Routers** mirroring today 1:1 (parity first): `GET /`, `/index.html` (static UI), `/api/health`
  (open), `/api/me`, `/api/users` (GET/POST admin), `/api/runs` (GET list / POST create), `/api/runs/{id}`
  + `/evidence /graph /events /artifact /log /deps`, run actions `POST /api/runs/{id}/{continue|deps|
  stage2|stage3|budget|retry|release}`, `/api/auth/google` (login), `/api/chat` (POST), `/api/chat/{id}/
  {history,stream,deps}`.
- **Pydantic models** for request bodies (run create, chat, user mgmt) + typed responses.
- **Dependencies** (this is where FastAPI is cleaner than today's inline gating):
  - `viewer()` → `(email, role, ok)` from the session cookie or `X-SF-Service-Token` (wraps `auth.py`).
  - `require_authed` → 401 if not ok.
  - `authorize_run(run_id, viewer)` → 403 unless admin/service or `run_owner(run_id)==email`. Applied to
    EVERY run-scoped route (preserves the §"ownership enforcement" rule — and fixes the chat-tool soft
    spot by scoping the concierge's run access to the viewer).
- **SSE** (`/api/chat/{id}/stream`): `StreamingResponse` (or `sse-starlette`) over the existing
  `_sse_clients` queue.
- **Background poller**: started in a FastAPI **lifespan** handler (asyncio task or the existing thread),
  same `_poll_transitions` logic (auto-advance, budget brake, narrate, Langfuse tick, boot janitor +
  backfill + owner-backfill).
- **Auth/static**: keep `auth.py` (Google tokeninfo + HMAC cookie); serve `index.html`/`login.html`;
  set the session cookie via the `Response`.

## Phase 3 — parity verification + cutover
- **Parity tests**: port `test_server_routes.py` to FastAPI's `TestClient`; assert every route's
  status/shape matches the stdlib server (auth gate, ownership 403s, SSE, create/list/actions).
- Full unit suite green (in a venv with `fastapi uvicorn sqlalchemy alembic pytest openai` — the local
  box can't run it today; a real test env is a prerequisite, not optional).
- Deploy behind the same `factory-console` service; smoke the live console (login, list, a run's
  graph/log, `/api/health`).

## Phase 4 — later (out of this plan, noted for the end-state)
Normalize `runstate` JSON → columns on `run_index` (or a `projects` table); chat → `public.chat_messages`;
files/logs → Supabase Storage + `run_blobs`; optionally retire schema-per-run for flat `run_id`-keyed
tables. Each is its own change once Phases 1–3 are stable.

## Risks & mitigations
- **Per-run-schema on the transaction pooler is the crux** — SQLAlchemy + dynamic per-run schema +
  per-statement `search_path` reset is the hardest part. Mitigation: keep dbshim's proven connection
  primitive; introduce SQLAlchemy for the SQL/model layer first on the GLOBAL tables, then per-run.
- **The `db` CLI + SKILL contracts are load-bearing** (stage agents write via them) — any signature/behavior
  drift breaks live runs. Mitigation: contract tests pinning the CLI + `TicketStore('<path>')` API.
- **Can't validate locally** (box lost py3.10; no fastapi/uvicorn/sqlalchemy/openai) — stand up a venv
  first; a server+DB rewrite shipped unverified to the live-critical service is an outage risk.
- **Coexistence with the gated deploy + DB cutover** — sequence AFTER them; don't stack three storage/HTTP
  changes on an undeployed base.
- **Adds runtime deps** (fastapi/uvicorn/sqlalchemy/alembic) to a deliberately-stdlib server — Dockerfile + dep policy change.

## Open decisions (for the operator)
1. **DB replacement scope**: hybrid (recommended — SQLAlchemy models + Alembic + `run_index`, keep
   dbshim per-run routing) vs full ORM rewrite of per-run storage now.
2. **Order**: ship Phase 0 now; do Phases 1–3 after the roles deploy + DB cutover (recommended), or in parallel.
3. Whether to fold the `software-factory-as-a-skill` cutover into the Alembic-baseline moment (one migration onto the new DB).

## Verification (end-to-end)
- Phase 0: pg insert of a commit-SHA provenance succeeds; opencode run closes a ticket on pg.
- Phase 1: hermetic sqlite suite green; `list_runs` reads `run_index` (one query); duplicate name → DB
  `UNIQUE` violation surfaced as 409; Alembic upgrade/downgrade clean.
- Phase 2/3: route-parity tests vs the stdlib server; live smoke (login, list, graph/log, health).
