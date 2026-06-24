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

# main integrator (software-factory-skill) Update at Time: 23:06:2026:00:36:00.000  [HOLD RESOLVED]
1. SHIPPED + verified the password brute-force/DoS throttle (#29) + drift-banner removal (#28) to prod (main b6de2ef); no-provisioning HOLD now LIFTED (email/password sign-in safe).
2. console/throttle.py (LoginThrottle: per-email free=5 + per-IP free=20, exp backoff, checked BEFORE scrypt), console/routers/auth.py (_client_ip + 429/Retry-After + auth_password debug log), console/web/src/admin/views.tsx (#28).
3. EMPIRICAL IP-RESOLUTION FINDING: on Railway X-Envoy-External-Address is NULL (not set, contrary to assumption) + XFF rightmost-hops=1 resolved to a ROTATING internal hop (84.17.44.x) → per-IP key never locked. Real client is LEFTMOST + edge-set (forged leftmost XFF is STRIPPED). FIX applied: prod env SF_TRUSTED_PROXY_HOPS=2 (parts[-2]=leftmost real IP) — load-bearing band-aid.
4. Verified post-tune: per-IP lock trips at attempt 21 (free_ip=20), ip==real 70.163.214.199, forged leftmost stripped; per-email lock + correct-pw-while-locked 429+Retry-After. FRAGILE: hops=2 assumes exactly [real,1 internal hop] — qsvigmth owns the robust leftmost-canonicalization (parts[0], hop-independent) in the next backend window; drop SF_TRUSTED_PROXY_HOPS then. Throttle is single-replica in-memory (move to shared store if console scales out).

# main integrator (software-factory-skill) Update at Time: 23:06:2026:00:51:00.000
1. SHIPPED Factory Pulse real stats + the ROBUST leftmost-IP canonicalization (#31) + Pulse FE strip (#30) to prod (main 8750cf7); DELETED the SF_TRUSTED_PROXY_HOPS env band-aid (env now clean).
2. console/routers/auth.py (_client_ip → XFF parts[0], drops SF_TRUSTED_PROXY_HOPS read; Envoy kept as defensive dead-weight), console/throttle.py (free_ip 20→10), src/software_factory/tenexity_os.py (pulse.projects_active), console/web/src/admin/{AdminPortal,api}.* (#30).
3. parts[0]=leftmost is hop-count-INDEPENDENT and non-forgeable on Railway (edge strips inbound XFF + prepends real client — empirically confirmed). Supersedes the fragile hops=2 band-aid; re-verify only if Railway's edge/ingress changes.
4. Verified GREEN: DISCRIMINATING test — with the env var DELETED, ip still == real 70.163.214.199 via parts[0] (old code would've resolved to rotating internal → proves new code live + hop-independent). Throttle 429 at 11th fail (free_ip=10), forged-leftmost stripped. Pulse = {tenants:1,projects:0,projects_active:0,agents_active:0,agents_total:0,today_burn:0.0,avg_friction:null} — REAL shape, honest zeros (no fake data). DRIFT banner stays gone.

# main integrator (software-factory-skill) Update at Time: 23:06:2026:01:15:00.000  [EFFORT COMPLETE]
1. SHIPPED the FINAL repo-cleanup window (#33 cleanup + #32 guard-drop) to prod (main fa676bb) and DELETED the dead Railway vars SF_AUTH_EMAILS + SF_ADMIN_EMAILS (zero code reads; allowlist now resolves purely from public.users — confirmed live).
2. #33: COMMENT-only fixes (models.py bcrypt→scrypt — NO column change/no migration; auth.py/open_routes.py), untrack build junk (.claude-flow/.playwright-mcp/vamac.pdf)+.gitignore, schema-erd.{dot,md,svg} rewrite, docs/plans; #32: console/web/src/admin/AdminPortal.tsx 1-line FE fallback (TASKS_RUNNING ?? 0).
3. Non-destructive cleanup on standing delegation; full suite 547 passed/0 fail; light verify GREEN (boot/health 200/admin gate 303/admin-API 200 no-regression/new bundle/ibraheem admin+active); schema-erd.svg valid 34KB. Closed gh-open-but-deployed PRs #27/#28/#30 + superseded #23.
4. AUTH HARDENING EFFORT COMPLETE — 8 serialized windows, all green: auth-rbac(36e1d76)→OS #19/20/21(f01175f)→user-mgmt+modularize #25/26/24(7aeedf4)→OS users #27(51d241e)→throttle+drift #29/28(b6de2ef)→Factory Pulse+leftmost-IP #31/30(8750cf7)→cleanup #33/32(fa676bb). Prod: DB allowlist/RBAC, google-auth, uid+tv cookie+per-request revocation, scrypt password login + working brute-force throttle, real-data pulse, clean env. Standing operator-greenlight delegation to coordinator l2a7ngax active (I escalate only destructive ops to ibraheem).

# Tenexity OS agent Update at Time: 22:06:2026:16:48:00.000
1. Implemented real-data AccountMenu for the OS portal and opened PR #36.
2. console/web/src/admin/AccountMenu.tsx, console/web/src/admin/AdminPortal.tsx, console/web/src/admin/primitives.tsx, console/web/src/api.ts.
3. Wires to assumed contract from qsvigmth: GET /api/me adds optional name/is_staff; POST /api/auth/logout ends session. No mock data: name fallback to email, OPERATOR badge from is_staff, Account settings disabled/flagged.
4. Summary: tsc + build green on console/web; PR body documents required backend contract and disabled Account-settings follow-up. Coordinator to batch/deploy with qsvigmth's backend changes.

# Tenexity OS agent Update at Time: 22:06:2026:17:02:00.000
1. Aligned AccountMenu PR #36 to qsvigmth's locked backend contract and l2a7ngax's simpler scope (per-app instance).
2. console/web/src/admin/AccountMenu.tsx, console/web/src/api.ts.
3. Renamed FE field is_staff → is_internal for OPERATOR badge; removed Account-settings item entirely (no screen exists); sign-out flow unchanged.
4. Summary: pushed fixup commit 4b38e43; tsc + build green; waiting for qsvigmth deployed-tip ping before merge/deploy.

# main integrator (software-factory-skill) Update at Time: 23:06:2026:18:20:00.000
1. SHIPPED the account-menu trio (#34 backend logout + /api/me name/is_internal, #35 customer AccountMenu, #36 OS AccountMenu) + onboarding optionC (#37) to prod in ONE window (main 7aef37f).
2. console/routers/auth.py (POST /api/auth/logout clears sf_session max-age=0; /api/me→{email,role,name,is_internal,auth}); console/web/src/components/{AccountMenu,Dashboard,OrgAdminScreen,project/ProjectView,factory/FactoryConsole,onboarding/OnboardingScreen}.tsx + admin/{AccountMenu,AdminPortal,primitives}.tsx + api.ts.
3. MERGE: #35+#36 both touched api.ts → resolved 2 conflicts (kept is_internal Me + never-throw logout). #36's 1st commit had a Me.is_staff/backend.is_internal MISMATCH but its own 2nd commit (4b38e43) already fixed it to is_internal — no manual fix needed. tsc -b clean validated the resolution.
4. Verify GREEN: logout 200 + cookie cleared (max-age=0, same flags); /api/me new shape; both bundles served; /admin gate + admin API no-regression; ibraheem admin/active; /api/org PATCH wired. DEPLOY GOTCHA: `railway up --ci` hit a transient Railway-API streaming timeout (reqwest error) and exited before "Deploy complete" — but the deploy COMPLETED server-side; first verify was premature (rolling lag). LESSON: on a railway-up CLI timeout, re-probe the served bundle before concluding failure (don't re-deploy blindly). Human spot-checks (account-menu render, sign-out redirect, onboarding inline-edit PATCH persistence) are ibraheem's behind the session gate.

# Tenexity OS agent Update at Time: 23:06:2026:20:15:00.000
1. Implemented OS §3.4 Agents dashboard wiring to real stage SKILL.md sources and opened PR #39.
2. console/web/src/admin/{modals,views}.tsx, console/web/src/api.ts.
3. Locked contract with qsvigmth: stage cards have kind="stage_skill" and callsigns STAGE-1/2/3; detail endpoint returns prompt=full SKILL.md markdown, prompt_source="skill_file", editable=false. FE renders read-only with "live skill" badge and skill_path.
4. Summary: tsc + build green; branch worktree-os-stage-skills; ready for coordinator batch with qsvigmth's backend PR.

# Tenexity OS agent Update at Time: 23:06:2026:20:25:00.000
1. Generalized PR #39 to also surface the CONCIERGE live code-backed prompt card (4th live card).
2. console/web/src/admin/{modals,views}.tsx, console/web/src/api.ts.
3. Read-only rendering now keys off `editable===false` and any `kind` present; badges skill_file→"live skill", code→"live code"; AgentCard hides Edit/Delete for live cards. Concierge source_ref displayed.
4. Summary: pushed additional commit 13169b2; tsc + build green; PR body updated to locked contract incl. concierge.

# Tenexity OS agent Update at Time: 23:06:2026:20:30:00.000
1. Final badge labeling tweak per qsvigmth: prompt_source==="code" now badges as "live concierge" instead of generic "live code".
2. console/web/src/admin/modals.tsx.
3. Matches backend contract exactly; no functional change.
4. Summary: PR #39 final; tsc + build green; waiting for qsvigmth deployed-tip ping and coordinator batch.

# Tenexity OS agent Update at Time: 23:06:2026:20:35:00.000  [RE-SCOPE / HOLD]
1. Operator re-scoped the 4 live prompt cards to be EDITABLE from the OS web UI. Pending qsvigmth's PATCH/store contract before FE changes.
2. console/web/src/admin/modals.tsx (planned changes), console/web/src/api.ts (planned PATCH contract).
3. Need to reverse read-only rendering, add Save (PATCH /api/admin/agents/{callsign}/prompt), default-vs-override indicator, version display, revert-to-default. Coordinate with qsvigmth on runtime keying for stage skills.
4. Summary: asked qsvigmth for PATCH body shape, default signal, revert endpoint, versioning, per-runtime overrides. Holding PR #39 FE changes until contract is locked.

# Tenexity OS agent Update at Time: 23:06:2026:20:40:00.000  [HOLD — qsvigmth proposed contract]
1. qsvigmth proposed PATCH/store contract: PATCH body {prompt, runtime?}, GET returns is_default/overridden/version, DELETE reverts to default, stage overrides per-runtime, concierge single.
2. console/web/src/admin/modals.tsx (pending), console/web/src/api.ts (pending endpoint additions).
3. Contract not yet coordinator-validated; FE changes remain on hold.
4. Summary: pre-plan only; awaiting l2a7ngax sign-off before implementing edits.

# Tenexity OS agent Update at Time: 23:06:2026:21:00:00.000
1. Implemented editable prompt manager for the 4 live cards per locked coordinator contract and force-pushed clean PR #39.
2. console/web/src/admin/modals.tsx, console/web/src/api.ts.
3. 4 main cards (kind present) are editable with runtime toggle for stage skills, default/override badge, version, revert-to-default DELETE, and "new runs only" notice. 12 role cards remain read-only.
4. Summary: branch worktree-os-stage-skills cleaned and force-pushed to a single code commit (3593d60); tsc + build green; PR body updated; awaiting qsvigmth deployed-tip ping and coordinator batch.

# main integrator (software-factory-skill) Update at Time: 23:06:2026:19:40:00.000  [FACTORY RUNS]
1. SHIPPED the stage-runner LLM-key injection fix (main bd2f9e2) — THE fix that makes the factory run — then the (A) agent-cards window (main c3bf33f: #38 deps-pill + #39/#40 read-only prompt cards + concierge→gpt-5.4 + #41 load_dotenv).
2. src/software_factory/console.py (_launch_stage: BYOK-or-platform runner-key inject), console/routers/projects.py (deps-route launches Stage 3), tests/unit/test_console.py (+3 tests).
3. ROOT CAUSE: stage_env_baseline scrubbed ANTHROPIC/OPENROUTER from the claude -p runner (the scrub protects the BUILT APP, but the runner needs the key) → Stage 1 died at auth → 0%. Fix injects the runtime key into the runner env only (guardrail: stage_env_baseline still scrubs by default → never reaches the customer app); BYOK wins over platform.
4. PROVEN LIVE (project-b0227fcf): stage1_done+stage2_done+14 real tickets, claude -p authed ($0.55→$10). gpt-5.4 probed VALID (gpt-5.4-2026-03-05). (A) verify: 4 live cards render real SKILL.md/CONCIERGE prompts (prompt_applied=true). KNOWN edge: mid-run console restart leaves finished Stage-2 child reading "alive" via _stage_process_alive → Stage2→3 won't auto-advance (deployed-app bonus blocked; optional qsvigmth follow-up). See [[factory-runs-keyinjection]].

# Tenexity OS agent Update at Time: 23:06:2026:21:25:00.000
1. Implemented staff-only "Make Tenexity admin" control in the OS master users table and opened PR #49.
2. console/web/src/admin/users.tsx, console/web/src/api.ts.
3. PATCH /api/admin/access/{email} now sends role + is_internal together; UI adds a Tenexity internal toggle in the user drawer + a row-menu quick action. Backend queued after provision-capture fix.
4. Summary: tsc + build green; branch worktree-users-staff-toggle; hold merge until qsvigmth deploys the backend endpoint.

# Tenexity OS agent Update at Time: 23:06:2026:21:35:00.000
1. Applied operator feedback to PR #49: dropped "Operator" label, gated "Make Tenexity admin" row action on session staff (me.role==='admin' && me.is_internal===true), added self-demote guard and 409 error surfacing.
2. console/web/src/admin/users.tsx.
3. Per operator: staff = /api/me role admin + is_internal; UI hides action for non-staff; role is "Admin" with a separate Tenexity/staff badge; drawer toggle handles both grant and revoke; backend enforces last-staff/self-demote 409.
4. Summary: pushed fix commit; tsc + build green; still holding merge for qsvigmth backend deploy.

# Tenexity OS agent Update at Time: 23:06:2026:17:45:00.000
1. Added `created_by` + `created_at` to the OS master projects list and opened PR.
2. `src/software_factory/tenexity_os.py` (project_rows), `console/web/src/api.ts` (AdminProjectRow), `console/web/src/admin/views.tsx` (AdminProjectsView columns).
3. Replaced the placeholder F/Auto columns with Created by/Created; backend fields already live from #53.
4. Summary: tsc + build green; admin agent tests pass (4 real orchestrators, no fake callsigns). OS portal still has Placeholder Factories/Settings and gated sign-in methods/Symphony.

# Tenexity OS agent Update at Time: 23:06:2026:18:30:00.000
1. Wired OS portal no-op controls in PR: removed + New project and Configure repo; added real client-side filter pills (clients/factories/statuses/modes).
2. `console/web/src/admin/views.tsx` — new `FilterSelect` component; `AdminProjectsView` derives options from loaded projects; `AdminAgents` no longer shows Configure repo.
3. Sync registry button left untouched — no backend sync endpoint exists; stopped and escalated to l2a7ngax/qsvigmth per instruction.
4. Summary: tsc + build green. Honest "coming soon" cards (Factories/Settings/Symphony, Microsoft/SSO) unchanged.
# Tenexity OS agent Update at Time: 23:06:2026:18:55:00.000
1. Wired Sync registry button to the upcoming POST /api/admin/agents/sync endpoint (PR #71 follow-up).
2. `console/web/src/api.ts` (adminSyncAgents), `console/web/src/admin/views.tsx` (AdminTools loading/toast/error), `console/web/src/admin/AdminPortal.tsx` (agent table refetch callback).
3. PR opened as #69 follow-up; held for qsvigmth endpoint deploy before merge.
4. Summary: tsc + build green; no silent no-op; surfaces synced count or error.
