# Memory & context architecture + comms  (Proposal §4 + §5)

## §4 — Memory & context (the core fix: pull, not push)

- **Storage of record:** the GitHub repo (code) + **ruflo memory** (AgentDB) for product/decision
  knowledge + coordination state.
- **Access = pull over MCP.** Each agent gets a tiny **memory-first instruction** ("query ruflo for
  what you need before acting") + the ruflo MCP tools (`memory_usage` retrieve/search,
  `retrieveWithReasoning`) — *not* a fixed context dump. Retrieval is hybrid (vector + BM25 + RRF +
  rerank), scoped by **namespace**: `project/<id>`, `run/<id>`, `tickets/<id>`, `coordination`.
  → `memory.project_ns / run_ns / ticket_ns / COORDINATION`; local fallback `memory.MemoryStore`.
- **Reasoning/precedent loop (ReasoningBank):** each agent's trajectory + outcome is written back
  (trajectory → verdict → distill → prune) so later agents query "how was this handled" by
  similarity, with confidence/success counts. → `memory.record_precedent`, `memory.recall_precedent`.
- **Consolidation:** distil + prune **between phases**, so memory stays sharp and small instead of an
  ever-larger blob re-sent every turn. → `memory.consolidate`.

In production these bind to ruflo over MCP (`npx -y ruflo@latest mcp start`); `memory.py` is the
namespace + precedent convention + a local fallback so the behaviour is deterministic/testable.

## §5 — Agent communication model (two complementary channels)

- **Direct peer messaging (`claude-peers` / session-bridge MCP)** — synchronous, push,
  conversational. The **live bus**: the **co-design pair** negotiating architecture/features
  ("two agents communicating exactly"), orchestrator↔worker "I'm blocked / here's feedback" pings,
  fix-loop dispatch. Best for the **persistent** agents (orchestrator + co-design pair).
- **Shared memory (ruflo AgentDB: `coordination` + project namespaces)** — async, durable,
  queryable. The **system-of-record + handoff + precedent**: artifacts, decisions, ticket state,
  "what's done," dependency status. Survives crashes; **ephemeral per-ticket build agents
  write-and-exit here** (`swarm/<agent>/{status,progress,complete}`, `swarm/shared/<component>`).

**Rule of thumb:** *live / "I need you now" / decide-together* → `claude-peers`; *durable / async /
"what happened"* → shared memory. The **orchestrator** is the hub and the only actor that declares a
phase complete.

# main-owner (software-factory-skill) Update at Time: 18:06:2026:04:30:00.000
1. Implemented the Nick-feedback plan on branch feature/console-v2 (off consolidated-base): interview→council PRD, React console + graph/kanban toggle, docx2md ingestion, multi-deliverable.
2. src/software_factory/{brief.py,console.py,chat_agent.py,runstate.py,tickets.py,db.py,docx_extract.py,input_pipeline.py}, console/app.py, console/web/** (Vite+React+TS SPA), skills/stage-1/2/3 SKILL(.opencode).md; plan at ~/.claude/plans/this-is-the-feedback-purring-donut.md
3. Operator goal "implement this plan without my input"; built phases 1,2,D,A,B,H-step1. SF_CONSOLE=react serves the SPA (legacy index.html still default → nothing breaks). Drafts mint canonical run-<8hex> up front (poller-invisible).
4. Summary: full unit suite 412 passed/1 skipped; live E2E smoke green (draft/brief/tickets/deployments/React all serve). REMAINING (operator-gated): F = live babysit (needs real API/Railway/GitHub keys + spend — not run autonomously); H steps 3-5 (Build IR, screenshot-diff verify) deferred per plan. 6 commits c3c6e0e..d2f2303.

# Tenexity OS agent Update at Time: 22:06:2026:15:24:17.285
1. Opened PR #20 (Factories/Settings placeholder views), PR #21 (tools status toggle + colored prompt-panel badges), and PR #23 (§3.6 Provide access/invite polish for auth-rbac schema).
2. console/web/src/admin/AdminPortal.tsx, src/admin/views.tsx, src/admin/modals.tsx; design source at ~/Downloads/Software Factory/admin.jsx + shared.jsx.
3. Operator/integrator: work does not touch auth schema; following sequencing after auth-rbac PR.
4. §3.6 uses existing /api/admin/* endpoints that now write users/roles; list shows friendly Operator/Org admin labels and supports revoke.

# main integrator (software-factory-skill) Update at Time: 22:06:2026:22:37:00.000
1. Shipped + DEPLOYED the auth data-model + hardening refactor to prod (main 36e1d76, PR #22): DB-backed allowlist/RBAC, google-auth token verify, uid+token_version HMAC session cookie.
2. src/software_factory/{models,users,auth}.py, console/app.py, migrations/versions/0003_auth_rbac.py, Dockerfile (google-auth in pip list), conftest.py, tests/unit/*, docs/ARCHITECTURE.md + schema-erd.{dot,svg}.
3. Operator directive "big & breaking, don't care about the live app": killed SF_AUTH_EMAILS/SF_ADMIN_EMAILS env allowlists → public.users (status invited|active|disabled) is the SOLE access source of truth; tenexity→is_internal; role resolved per-request from role_id→roles (instant demote/revoke); /admin gate = role==admin AND is_internal.
4. Summary: 526 unit tests green; 0002→0003 prod-upgrade rehearsed incl. acceptance gate; deploy needed SF_BOOTSTRAP_ADMIN_EMAIL=ibraheem@tenexity.ai (lockout-critical — 0003 wipes users, bootstrap reseeds) + fresh SF_SESSION_SECRET; headless smoke + ibraheem's live Google /admin sign-in both verified. 0003 is the LAST drop+rebuild (additive-only after, per crew policy).

# main integrator (software-factory-skill) Update at Time: 22:06:2026:22:38:00.000
1. Integrated + DEPLOYED OS-portal PRs #19/#20/#21 in one coordinator-serialized window (main f01175f).
2. .gitignore + opencode.json untracked (#19); console/web/src/admin/{AdminPortal,views,modals}.tsx (#20 Factories/Settings placeholders, #21 Tools status toggle + colored badges).
3. FE/config-only, no schema/auth impact; rebased each onto current main, merged #19→#20→#21 (clean auto-merge, no conflicts); placeholders are honest "out of scope" cards — NO fake data (per the no-dummy-data rule).
4. Summary: SPA built clean (tsc -b + vite); railway up green (migrate 0003 no-op re-run); new admin bundle served; Tools PATCH verified against live data. PR #23 (§3.6 provide-access/invite polish) remains OPEN/unintegrated — a future window.

# backend (software-factory-skill) Update at Time: 22:06:2026:22:45:00.000
1. Modularized the 1551-line console/app.py monolith into a package (behavior-preserving pure move, zero logic/route changes) on branch worktree-app-modularize off main 36e1d76.
2. NEW: console/{state.py,deps.py,schemas.py,poller.py} + console/routers/{open_routes,auth,org,admin_os,projects,chat}.py + routers/__init__.py; app.py reduced to FastAPI()+middleware+lifespan+static-mounts+router-includes; docs/ARCHITECTURE.md updated; 5 test monkeypatch targets repointed to state.* + 2 fixtures unchanged.
3. Singletons moved to state.py behind reset() (called by app.py on every import) so importlib.reload(console.app) still re-instantiates stores per test — critical: re-seeds the bootstrap admin AFTER conftest's per-test TRUNCATE (else login 403). Consumers late-bind state.X so they see post-reset instances; no shadow rebinds (one canonical home per symbol).
4. Summary: full unit suite 526 passed/1 skipped (the only reds were a missing google-auth dep in the local venv, now installed — not a code issue). Every route path/method/auth-dep/response shape byte-identical. Atomic PR; merge held by coordinator behind the OS-PR train. No data wiring changed; flagged agent_registry/mcp_tools as seeded-real-table (not fake) and activity[]/avg_friction as honest empties.

KNOWN FOLLOW-UP (backend, non-blocking): POST /api/auth/password (in the queued user-mgmt work) has NO brute-force throttle — add a minimal per-email/IP attempt limit or backoff before/after it ships. Generic 401 (never leak bad-pw vs no-pw vs disabled) is intentional.

# main integrator (software-factory-skill) Update at Time: 23:06:2026:00:08:00.000
1. SHIPPED the user-mgmt + OS-users train to prod in two serialized windows (ibraheem direct GO + standing operator-greenlight delegation): #25→#26→#24 (main 7aeedf4) then #27 OS users-management (main 51d241e).
2. console/* (modularized package: state/deps/schemas/poller/routers), migrations/versions/0004_user_mgmt.py, src/software_factory/{auth,users,models}.py (scrypt hash_password/verify_password + authenticate_password + set_password + last_active + Tenexity-org seed), console/web/src/admin/users.tsx + LoginScreen.tsx + api.ts.
3. Pre-flighted all 4 gates locally before GO (0003→0004 rehearsed additive/idempotent; password reuses sign_session+status gate; pure-move preserved viewer/_staff_session; 534 green). Each window: rebase→build SPA→railway up→verify checklist.
4. Verify GREEN both windows: 0004 applied, auth gates no-regression after pure-move, Tenexity-org seed (ibraheem row org="Tenexity"/admin/active + 0004 cols), password error-path generic-401, users screen renders REAL /api/admin/access rows. Closed merged-but-open PRs #19/20/21/24/26.

# main integrator (software-factory-skill) Update at Time: 23:06:2026:00:09:00.000  [SECURITY — ACTION NEEDED]
1. RATE-LIMIT HARD GATE IS LIVE-SCOPE NOW, not a future window: #26 already shipped password PROVISIONING (admin_os.py admin_invite → users.set_password when method=="password") AND the unthrottled POST /api/auth/password login — both live @7aeedf4/51d241e. #27 adds the AddUser password UI.
2. console/routers/admin_os.py:215 (set_password call), console/routers/auth.py (/api/auth/password, no throttle), src/software_factory/users.py authenticate_password.
3. Not exploitable THIS instant (provisioning is require_staff; ZERO passwords provisioned — ibraheem=google/hash NULL), but one staff click from a brute-forceable account on an unthrottled endpoint. I escalated to ibraheem.
4. REQUIRED before anyone uses method=password in prod: qsvigmth's per-email/IP throttle (or hard-disable method==password in admin_invit until then). Interim control: provision NO passwords. Escalated to ibraheem for his call (throttle-first vs code-guard vs operational-hold).
