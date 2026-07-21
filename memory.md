# sof73-agent Update at Time: 02:07:2026:19:22:00.000
1. Opened PR #299 (branch sof-73-product-design-phases, worktree ~/software-factory-skill-bare/wt-sof-73) — added `product` (PRD-council synthesis + lock-in sign-off, closes Stage 1) and `design` (per-screen design-spec, closes Stage 2's design work before ticketing) as real, evidence-gated pipeline phases, per the canonical design source (docs/design/buildboard.jsx:5-19/nodemap.jsx, in-repo since 81ae064). STAGE_1/STAGE_2 (constants.py) + NODE_ORDER (checkpoint.py) updated; fixed two real latent bugs found while wiring it through console.py — derive_phases()'s closed-phase tuples were hardcoded literals never derived from STAGE_1/STAGE_2 (would've rendered product/design "skipped" forever), and graph()'s Stage-1-gate-diamond placement was hardcoded to "research" instead of stage 1's true last phase (StageRail.tsx had the same bug, fixed too).
2. PR https://github.com/ibraheem-tenexity/software-factory-skill/pull/299, Linear SOF-73 (In Review) + SOF-83 (filed separately, stale BudgetExceeded guardrail-text question, NOT bundled into #299 per operator instruction). fusion_research() (research.py, merged via #289/#290) wired into a narrowed Stage-1 `research` phase (3 bounded questions → market-scan.md/existing-solutions.md/requirements-fit.md, grounding the product council). PRODUCT/DESIGN are DB-backed system_agents rows materialized as native Claude Code subagent files (ws/.claude/agents/{product,design}.md) via new workspace_setup.write_agent_file(), mirroring the existing skill_override mechanism — dispatched via Task(subagent_type="product"/"design"). Opencode (no Task/subagent concept) customizes at the whole-stage STAGE-N granularity it already has; a narrower opencode-specific splice mechanism was designed then explicitly dropped mid-implementation as unjustified complexity for zero capability gain, per the operator's anti-bloat directive this round — noted in both the plan file and the PR.
3. Both gates mechanical, no human approval (gates.py stays deleted): product requires prd_is_complete() + new artifacts.prd_lock_in_verdict() reading SHIP_AS_IS/SHIP_WITH_EDITS from the PRD's existing lock-in tally line (never SEND_BACK/missing); design requires design-spec.md + new artifacts.design_spec_is_complete() cross-checking every PRD screen-catalog ID is referenced (artifacts.parse_screen_ids()). Full suite diffed directly against a pristine origin/main run — my branch's 58 failures are a strict subset of main's 67 (zero new failures; main's 9 extra are order-dependent flakiness unrelated to this change, e.g. test_status_model_reflects_opencode_alias). One real bug caught in my own diff before it shipped: design_spec_is_complete()'s empty-screen_ids case unconditionally appended to `reasons`, forcing ok=False despite the docstring's own "reported but not fatal" intent — caught by a new test before push.
4. Summary: PR #299 open, awaiting integrator (y96ilz0o, routed via allvn3xd) review. Stage-3's build→deploy→test order explicitly NOT changed (Playwright needs a live URL; the mockup's "test→deploy" wording is decorative, not literal) — documented in the plan and operator-approved before implementation. Back-compat for in-flight projects is free via the existing idempotent `if state.stageN_done: return True` short-circuit — no new code needed.

# prune-agent Update at Time: 02:07:2026:10:20:00.000
1. Opened PR #286 (branch prune-dead-code, worktree ~/software-factory-skill-bare/wt-prune-dead-code) — operator-directed prune: deleted ~3,300 lines of dead-at-collection tests (agents→runtime_agents rename left ~10 files ModuleNotFoundError'ing, incl. the 2,406-line test_console.py giving zero coverage on main; +3 more of the same root cause found during verification), Tier-1 dead code (budget.py's unused hard-cutoff class, gates.py, evidence.py, dead checkpoint.py halves, console.py's gated-hold flow), 9 zero-caller routes + the old chat SSE registry, the SF_CONVERSATION_DB flag (operator-confirmed, deconflicted with SOF-71's separate SF_MEMORY removal), FE dead exports + the statusOf/phaseTone #128-class duplication, and repo/Dockerfile/pyproject cruft.
2. PR https://github.com/ibraheem-tenexity/software-factory-skill/pull/286, Linear SOF-77, memory files docs/CONTEXT_EXPORT.md etc (deleted, not tracked in the diff), ~/.claude/worktrees/ (82 of 109 stale worktrees + 118 orphaned local branches removed on the MAIN checkout, disk-only, not part of the PR).
3. Full suite (pytest -q, ~1022 tests) verified against a disposable pgvector Postgres container and diffed against a pristine origin/main run of the SAME tests — zero new failures; the 44 failures present on both (40 pre-existing schema/brief-API drift from concurrent SOF-60/61/62 work + 4 order-dependent test_memory_mcp_server.py flakes, confirmed pass-in-isolation/fail-in-suite) are unrelated. `git branch --merged` under-detects squash-merges — used `gh pr list --state merged` instead for the worktree-removal safety check, after the naive check found 0 removable worktrees against 82 actually-safe ones.
4. Summary: PR #286 open, awaiting integrator (y96ilz0o) review; SOF-77 filed In Review; peer allvn3xd pinged (can drop the SF_CONVERSATION_DB Railway env var once merged). Legacy console (index.html) explicitly untouched per operator — being reworked separately. One live bug caught in my own diff before merge: a dangling `if not gated:` left after removing the `gated` param would have NameError'd every project creation.

# monitor-agent Update at Time: 28:06:2026:00:40:00.000
1. Re-synced with peers: #125 merged as PR #179 (commit 0d1a09d, equivalent to 4433dd9) and deployed; #126 pool cap merged as PR #180 and deployed. The launcher now drops root before launching Claude Code and the claude binary is pinned to 2.1.195.
2. src/software_factory/console.py, Dockerfile, entrypoint.sh, src/software_factory/dbshim.py.
3. project-67f3711d3b0a46a4 COMPLETED after the deploy: phase=done, deploy_url=https://sf-project-67f3711d3b0a46a4-production.up.railway.app (sign-in page + demo credentials render). Deps surfaced (DATABASE_URL, NEXTAUTH_SECRET, OPENROUTER_API_KEY=mock) — confirm OPENROUTER_API_KEY mock issue is separate #107.
4. Summary: no further action needed on #125/#126; run finished. I was stale due to Railway auth failing in this env and coeyi70e picked up the deploy.

# monitor-agent Update at Time: 27:06:2026:08:00:00.000
1. Investigated stall of project-67f3711d3b0a46a4 and resumed Stage 3 by wrapping the `claude` binary to drop to the `node` user. Root cause: Claude Code v2.1.195 refuses root + `--permission-mode bypassPermissions` (maps to `--dangerously-skip-permissions`), so every console launch as root died instantly.
2. /data/projects/project-67f3711d3b0a46a4/project.log, /usr/local/bin/claude wrapper, src/software_factory/console.py `_default_launch`.
3. Stage 2 had actually completed (stage2_done=true, architecture + tickets produced and pushed to https://github.com/ibraheem-tenexity/adaptive-learning-path-platform). Stage 3 launches now run as `node` and the process is alive (node PID 1400), log growing, spending resumed.
4. Summary: run is advancing again; stage=3, phase=provision, spent ~$17.13/$60; monitoring to the Playwright happy-flow gate. A durable launcher-privilege fix is needed before the next deploy.

# monitor-agent Update at Time: 27:06:2026:09:00:00.000
1. Confirmed #125 durable fix already exists on main (commit 4433dd9): entrypoint.sh drops to node user, _default_launch preexec_fn drops root, claude pinned to 2.1.195 in Dockerfile. No extra code changes needed.
2. src/software_factory/console.py, Dockerfile, entrypoint.sh.
3. The deployed prod image is older than 4433dd9, which is why the live run required a /usr/local/bin/claude wrapper. Deploying current main will make the wrapper unnecessary.
4. Summary: code fix is complete; deployment is blocked until Railway CLI is authenticated in this environment. Stage 3 monitoring continues.

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
4. Summary: branch worktree-os-stage-skills cleaned and force-pushed to a single code commit (3593d60); tsc + build green; awaiting qsvigmth deployed-tip ping and coordinator batch.

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

# Codex Update at Time: 24:06:2026:12:36:18.380
1. Implemented TTL-cached concierge prompt resolution from `agent_prompts.CONCIERGE` plus a read-only latency benchmark.
2. `src/software_factory/chat_agent.py`, `scripts/benchmark_prompt_fetch.py`, `tests/unit/test_chat_agent.py`, `docs/ARCHITECTURE.md`.
3. Prompt edits should drive new concierge sessions without adding a DB hit to each chat turn; DB failures keep the last good prompt or fallback constant.
4. Summary: created worktree `../software-factory-skill-prompt-fetch` on `feature/prompt-fetch-latency`; focused chat tests passed; full non-live suite passed.

# Backend agent Update at Time: 25:06:2026:00:00:00.000
1. Moved deploy-DB provisioning out of Console._launch_stage into a new `provision-db` db-CLI verb (the stage-3 agent calls it once); wired the exa remote web-search MCP into all stages/both runtimes.
2. `src/software_factory/{db.py (provision-db verb),console.py (deleted provision block + DEPLOY_DB_MAX_ATTEMPTS import + broadened Railway-MCP prompt),workspace_setup.py (_EXA remote server + _opencode_server branch),mcp_health.py (skip url-only spawn-probe),env.py (EXA_API_KEY passthrough)}`; `skills/stage-{1,2,3}-*/SKILL{,.opencode}.md`; tests in `tests/unit/test_{db,console,workspace_setup}.py`; `docs/ARCHITECTURE.md`.
3. Orphan backstop is now prompt(provision-once)+provision-idempotency+reaper, no code attempt cap; reaper/teardown unchanged (read state.deploy_db_service_id now written by the verb). exa key env-var'd (${EXA_API_KEY} / {env:EXA_API_KEY}), never literal; survives stage_env_baseline scrub. Supersedes ibraheem's exa stub; research.py / PHASE_AGENTS decentralization untouched (out of scope). Part-B deploy gate = EXA_API_KEY on factory-console.
4. Summary: full non-live suite green (844 passed, 2 skipped) except pre-existing flaky test_budget_kill_is_recoverable_raise_and_resume (passes in isolation; unrelated to this change). New provision-db verb + exa-all-stages unit tests pass.

# OpenCode agent (tqqqko1h) Update at Time: 26:06:2026:13:32:59.000
1. Built + merged #108 orchestrator-side state-machine fix as PR #152 / commit 29437c9, then learned 6pxbsagp is the canonical integrator with a parallel #108 build; stood down from integrator/deploy duties.
2. `src/software_factory/console.py`, `tests/unit/test_console.py`, worktree `../fix-108-stage3-resume-done`.
3. The process-health-driven change mirrors stages 1/2: `detect_stage3_done` requires `stage_finished()` before flipping done; `auto_resume_dead_stage`/`mark_stage_crashed` resume any dead stage-3 process unless the run is done; stage-3 auto-resume resets `in_progress` tickets. Tests: test_console.py 114 passed, full unit suite 877 passed / 1 skipped.
4. Summary: #108 orchestrator fix is in main at 29437c9. I am not the integrator; 6pxbsagp owns reconciliation keep/revert/layer. Holding stop_project on PathForge and any deploy until ibraheem greenlights. Awaiting backend ticket assignment (#114 or Concierge-hang).

# OpenCode agent (tqqqko1h) Update at Time: 26:06:2026:14:12:20.760
1. Received ibraheem greenlight (via xpyjn5m7) to act as deploy-lane executor; merged #103 by deleting tracing.py and Langfuse poller wiring as PR #156 / commit cd18624.
2. `src/software_factory/tracing.py`, `tests/unit/test_tracing.py`, `console/poller.py`, `src/software_factory/registries.py`, `src/software_factory/storage.py`, `docs/ARCHITECTURE.md`; worktree `../fix-103-delete-tracing`.
3. Main is now at cd18624 (#151 + #108/#111 + #103). Targeted tests green; full suite held by timeout but verified import clean. Next: park PathForge with stop_project, deploy main, then pick up #114 cross-project isolation.
4. Summary: #103 removed; deploy train unblocked pending PathForge safe-park. Logging refactor and memory changes stashed on main; will handle separately.

# OpenCode agent (tqqqko1h) Update at Time: 26:06:2026:14:22:24.948
1. Stopped PathForge and deployed main (#151 + #108/#111 + #103) to factory-console as deploy-lane executor.
2. `project-0362f961f0984e75` (DB projectstate.data): phase set to `stopped`; deployment via worktree `../sf-deploy-main` + `make deploy` linked to Railway project `softwarefactory` / service `factory-console`.
3. Live service `https://factory-console-software-factory-as-skill.up.railway.app` returns `/api/health {"ok":true,"pg":true,"disk_free_mb":41123}; startup logs show clean migration, no tracing import error.
4. Summary: deploy lane complete. Next: resume #114 cross-project isolation in worktree `../fix-114-cross-project-isolation` (tickets.py project scoping).

# OpenCode agent (tqqqko1h) Update at Time: 26:06:2026:14:24:09.818
1. Checked #114 after deploy and found it is an already-merged UI feature (discard-draft control on Dashboard + ProjectView/Overview), not the backend cross-project isolation work.
2. GitHub issue #114 `feat(dashboard): discard-draft control...` is CLOSED/MERGED; branch `fix/114-cross-project-isolation` exists but has no commits and its name does not match the issue.
3. Main has since advanced to 1cab932 (#158 logging refactor) after the deploy landed on cd18624.
4. Summary: deploy lane is done; stopping to ask the operator/coordinator for the real next backend ticket — likely the previously mentioned Concierge-hang or a correctly-numbered cross-project isolation issue.

# OpenCode agent (tqqqko1h) Update at Time: 26:06:2026:21:47:00.000
1. Investigated the real cross-project isolation ticket after discovering #114 is a merged discard-draft UI PR; found docs/CONTEXT_EXPORT.md task #13 naming it as a pending "project_id-scope TicketStore/canvas queries" issue, with evidence `scratchpad/edutech2.log` and `edutech3.log` (logs absent in this checkout).
2. `docs/CONTEXT_EXPORT.md`, `src/software_factory/{tickets.py,db.py}`, `console/routers/projects.py`, `console/deps.py`, GitHub issues/PRs via `gh` in `ibraheem-tenexity/software-factory-skill`.
3. GitHub search for "isolation" and "cross project" returns only PR #85 (intentional, gated cross-project artifact fetch) and unrelated cross-tenant operator-portal work; no open or closed issue matches the described TicketStore/canvas leak. Current TicketStore/ProjectStore SQL is project_id-scoped.
4. Summary: the cross-project isolation work appears unfiled or tracked outside GitHub. Propose creating a new issue/PR with a regression reproduction before changing code; waiting for operator confirmation and the missing log evidence.

# OpenCode agent (tqqqko1h) Update at Time: 26:06:2026:22:32:00.000
1. Picked up the GET /api/projects performance fix from coordinator xpyjn5m7: replaced per-project N+1 queries with batched set-based loads and added an opt-in application-side connection pool in dbshim.
2. `src/software_factory/console.py` (`list_projects`, `_load_states`, `_phase_statuses`, `_blockers_by_project`, `_agent_roles_by_project`, `_current_phase_from_state`), `src/software_factory/dbshim.py` (`_ConnectionPool`, `_pooled_conn`), `src/software_factory/projectstate.py` (`from_data`).
3. `list_projects` now does ~5 queries total (projectstate, phases, blockers, agents, registry) regardless of run count and no longer reparses project.log via `_cost`; it uses persisted `spent_usd`. The pool borrows connections per statement and is enabled automatically on Railway (default 10) or via `SF_DB_POOL_SIZE`, disabled in tests.
4. Summary: branch `perf/list-projects-pool` in worktree `../fix-perf-list-projects`; syntax-checked. Need to run the real test suite once a database is available, then open a PR through the integrator.

# OpenCode Update at Time: 27:06:2026:00:40:00.000
1. Implemented #114 guard: `project_id_from_path` now detects file-like leaves (e.g. `project.db`) and derives the project_id from the parent run directory, validating it against `PROJECT_ID_RE`.
2. `src/software_factory/db.py` (import + `project_id_from_path`), `tests/unit/test_db.py` (new tests).
3. Prevents `project.db` from becoming a project_id and leaking across runs; preserves existing test fixtures that use generic directory ids like `run`.
4. Summary: `test_db.py`/`test_tickets.py`/`test_agents.py` pass. Prod data-hygiene sweep blocked: Supabase `software-factory-state` project is INACTIVE, so I cannot query `project_id='project.db'` counts yet. Waiting for go/no-go on restoring it.


# OpenCode agent Update at Time: 26:06:2026:16:10:00.000
1. Resolved the #155 live-log-flush merge conflict, merged it, and deployed the batch (#161 db pool + #154 phase-lag + #155 log flush) to factory-console.
2. `console/poller.py` (kept log-flush block, dropped removed tracing `_tracer.tick`); main repo `29d6254`; worktree `../fix-perf-list-projects`.
3. Deploy succeeded (Railway build `67b98090-5325-4eaf-8dfb-5f02e11b377a`); rebased `perf/list-projects-pool` onto updated main, stripped redundant dbshim pool code since #161 owns pooling, and rewrote PR #162 as a list-only change.
4. Summary: full unit suite 872 passed / 2 pre-existing failures (`opencode_config()` `steps` kwarg drift); PR #162 titled/body updated and force-pushed to `3af53d2`; ready for integrator merge.

# OpenCode agent Update at Time: 26:06:2026:18:30:00.000
1. Merged/deployed #165 (#114 project_id guard) and queried live factory-state DB via factory-console Railway env: 33 orphaned tickets under project_id='project.db', all other project tables clean.
2. `src/software_factory/db.py`, `tests/unit/test_db.py`; live DB is the Supabase pooler behind factory-console (not the inactive MCP project).
3. Root cause identified: filenames like project.db were used as project_id. Purge is the safe cleanup (real ID lost), but per xpyjn5m7 this is HELD for ibraheem's explicit ok because it deletes prod ticket rows.
4. Summary: guard shipped; data-hygiene on hold awaiting operator consent.

# OpenCode agent Update at Time: 26:06:2026:18:45:00.000
1. Replaced the home-grown #166 Langfuse hook with the official script (#172), added runtime Dockerfile deps (#171), set TRACE_TO_LANGFUSE="true", and deployed.
2. `resources/langfuse_hook.py`, `src/software_factory/workspace_setup.py`, `src/software_factory/env.py`, `Dockerfile`.
3. The runner image manually installed packages and had drifted from pyproject.toml, so langfuse/openinference were missing; #170's SDK-v4 rewrite became obsolete once coeyi70e vendored the official 2000-line hook.
4. Summary: headless `claude -p "Say hello"` in a prod-container workspace fired the Stop hook and a trace ("Claude Code - Turn 1") landed in Langfuse; #122 verification complete.

# OpenCode agent Update at Time: 26:06:2026:18:55:00.000
1. Verified Supabase Vault is live in prod (#123): vault.create_secret / vault.decrypted_secrets round-trips a throwaway secret on the factory-console state DB.
2. `src/software_factory/vault.py`, `src/software_factory/console.py` (logged warning instead of silent pass), PR #174.
3. Caveat: vault.delete_secret(uuid) does not exist in our Vault extension, so vault_delete_many is broken; cleaned the test row manually with DELETE FROM vault.secrets. Console's silent except/pass around vault_store is now a logger.warning with exc_info.
4. Summary: Vault encryption/return works; deletion path needs a separate fix. #174 deployed.

# OpenCode agent Update at Time: 26:06:2026:19:05:00.000
1. Fixed vault_delete_many (#124): replaced per-row vault.delete_secret() (which doesn't exist in our pgsodium) with a single DELETE FROM vault.secrets WHERE id = ANY(%s), added/updated tests, and deployed.
2. `src/software_factory/vault.py`, `tests/unit/test_vault.py`, PR #176.
3. Verified live: stored a throwaway secret, vault_delete_many removed it, and a subsequent retrieve returned {}. BYOK secrets can now be purged on archive/teardown.
4. Summary: #124 complete; backend queue is now clear unless #114 purge gets ibraheem's ok or new work is assigned.

# OpenCode agent Update at Time: 27:06:2026:06:12:00.000
1. ibraheem APPROVED #114 data purge; executed DELETE FROM tickets WHERE project_id='project.db' against the live state DB via railway run.
2. Live state DB via factory-console Railway env.
3. Count was 33 orphans (LMS/workforce app run mislabeled with file basename project.db). The #165 guard prevents new 'project.db' rows from landing.
4. Summary: 33 rows deleted; post-purge count is 0. #114 data-hygiene complete.

# Claude (brief-refactor agent) Update at Time: 01:07:2026:00:00:00.000
1. Removed the dead 7-section brief system (brief.py already deleted): Stage-1 input is now the Concierge-finalized product-brief markdown, read via Console.product_brief() from the newest kind='product_brief' artifact (content column from PR #277, path fallback).
2. src/software_factory/{console,projectstate,input_pipeline}.py, console/routers/projects.py, console/web/src/{api.ts,components/onboarding/InterviewView.tsx}, migrations/versions/{0002_tenexity_os.py,0012_agent_tables_consolidation.py} (renamed from 0011, re-parented onto PR #277's 0011_assumptions_and_document_artifacts).
3. ProjectState.brief/interview_coverage replaced by plain `goal`; promote gate is now open reflection_questions ONLY (user decides readiness); GET /brief returns {brief_markdown, learned_facts, reflection_questions}; PUT /brief is a thin goals/scope editor via set_draft_project; migration 0002 froze its DDL inline (no models import).
4. Summary: brief dict/coverage/enough are gone end-to-end; old stored JSON keys are silently ignored by the _PERSISTED filter; py compileall + FE tsc both clean. Not committed.

# Claude (SOF-68 console-design agent) Update at Time: 02:07:2026:00:00:00.000
1. Closed the SOF-68 design-fidelity gap list on the factory console: ArtifactChip/KIND_BADGE ported to shared design.tsx and used by the Concierge tray (grouped per producing node) + DocViewer header; Tree view rebuilt on the design's GraphView spine; Map view (cytoscape) restyled per nodemap.jsx (dotted grid, hot-path edges, teal gate diamonds, clickable purple artifact nodes, 6-entry legend); Concierge rail got the ConciergeHeader band, shared Message bubbles, synthesized status bubbles from real state, QuickReplies + Steer-the-build card; peer-tab strip added to the console header (Overview/Documents navigate back to ProjectView via new onSwitchTab prop); WaitForDeps got the design chrome + green "build unblocked" beat; NEW badge now driven by pipeline.ts NEW_PHASES (empty until SOF-73); Kanban "needs key" tag wired to real title text + ConfidencePill behind a presence check; the inline view toggle replaced by the shared Segmented (now icon-capable).
2. console/web/src/components/factory/{FactoryConsole,Concierge,Artifacts,NodeMap,StageRail,WaitForDeps,BuildBoard}.tsx, factory/pipeline.ts, onboarding/design.tsx, App.tsx, api.ts (Ticket.confidence optional). Branch sof-68-console-design.
3. All data stays real (graph/tickets/events/status props; synthesized concierge bubbles derive from them); no backend changes; tokens from T except design-specified constants kept verbatim (KIND_BADGE repo/fig pairs, nodemap orchestrator ink + artifact purple).
4. Summary: tsc -b and vite build clean; FE-only; PR to main opened from sof-68-console-design.

# Codex Update at Time: 14:07:2026:23:48:49.927
1. Implemented SOF-180 graph artifact previews: selecting a graph artifact now opens a compact rendered preview with an explicit route to the existing full artifact viewer.
2. console/web/src/components/factory/{NodeMap,FactoryConsole,Artifacts}.tsx on branch agent/sof-180-artifact-preview.
3. This preserves the established full-viewer behavior while allowing operators to inspect an artifact without leaving the map.
4. Summary: artifact-node taps resolve the same artifact reference as before; local artifacts load their content in the preview; external artifacts retain an open-source control.

# Codex Update at Time: 15:07:2026:01:20:40.540
1. Started SOF-179 and SOF-181: added independent Kanban column scrolling plus intake drag-and-drop and material removal with downstream cleanup.
2. console/web/src/components/{factory/BuildBoard,onboarding/{OnboardingScreen,design},project/DocumentsTab}.tsx; console/routers/projects.py; src/software_factory/{storage,blobs,db,memory/store,repositories/{blobs,canvas}}.py.
3. Removal must erase durable bytes, blob metadata, document chunks/summaries, and the agent-readable markdown artifact; drag/drop reuses the existing attach pipeline.
4. Summary: both Linear tickets set In Progress; Python compile and Vite production build pass; staging browser verification is pending deployment after the benchmark hold.

# Codex Update at Time: 16:07:2026:00:00:00.000
1. Synced the canonical architecture narrative and schema/service diagrams with current staging code.
2. docs/ARCHITECTURE.md, docs/schema-erd.{dot,md,svg}, docs/service-architecture.svg.
3. Corrected stale runtime, stage-gate, persistence, auth, schema, and deployment claims from a source-backed audit.
4. Summary: DOT render and model-table coverage pass; documentation diff is clean.

# Claude Update at Time: 20:07:2026:14:30:40.000
1. SOF-194: credential check no longer treats a transient GitHub/Railway 5xx as a permanently-dead credential (which SOF-148 makes non-resumable → hard-wedged a valid-token run).
2. src/software_factory/creds.py (retry + transient/terminal classify, capture stderr); skills/stage-1-research/SKILL.md + SKILL.opencode.md (record check.blocks category, not hardcoded 'credential').
3. check_gh/check_railway retry a non-definitive failure (3 attempts, 1s/2s backoff); a surviving 5xx/network signal → resumable 'transient' blocker (auto-resume relaunches), only a real auth reject (401/403/Bad credentials) → non-resumable 'credential' (SOF-148 preserved).
4. Summary: creds.py compiles; verified via injected-runner driver (10 cases incl. simulated 5xx + auth-reject + the exact incident) — all pass; poller credential_stopped is category-keyed so 'transient' correctly auto-resumes.

# Codex Update at Time: 20:07:2026:20:03:35.000
1. Recorded the approved backend structure direction: bounded-context modular monolith.
2. CLAUDE.md and docs/{ARCHITECTURE,STRUCTURE}.md on agent/structure-direction-20260720.
3. The policy applies to parallel work: feature ownership over generic layers, no pass-through files, preserve behavior, and keep migrations/vendor tooling isolated.
4. Summary: source-backed audit covered 153 non-test Python files; refactor plan follows this decision record.
