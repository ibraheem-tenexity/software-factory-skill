# CLAUDE.md — Software Factory

## The Philosophy: Minimum Machinery

This product's bet is that **agent intelligence is the product**. Every piece of machinery that
substitutes for an agent's judgment weakens the product and adds code nobody asked for.

1. **Agent judgment over machinery.** If a behavior can live in a system prompt, it lives in the
   system prompt. "The agent should stop when it has enough", "the agent decides what to ask",
   "the agent knows when the brief is ready" are PROMPT conditions — never state machines, never
   DB-materialized flags, never gates keyed to agent-generated state. Do not build `resolve_*`
   flows, readiness trackers, or approval queues around an agent decision. The recurring failure
   mode: an instruction like "the interview must not end early" pattern-matches to
   validation-and-state; resist it. When you feel the pull to materialize a judgment, write a
   prompt line instead.
2. **Code is plumbing.** Tools, storage, transport, rendering. A tool does one real thing against
   a real backend and returns the truth (including error text — a broken tool degrades the
   answer, never kills the conversation). Decisions route through agents; code moves data.
3. **Gates check facts, not judgment.** A hard block is allowed only for a mechanical
   prerequisite, expressed as one honest check — e.g. hand-off requires that a product brief
   artifact EXISTS (`SELECT … WHERE kind='product_brief'`), nothing more. Machinery IS correct
   where money and process lifecycle live: budget ceilings, retry caps, heartbeats, dead-stage
   detection. Judgment for product decisions; hard invariants for money and lifecycle.
4. **Honest errors, everywhere, to everyone.** When something refuses, the refusal states the
   actual reason — to the user in the UI and to the agent in the tool result (agents act on
   errors too; a tool and the button it mirrors must call the SAME function and surface the SAME
   error). Never a plausible-sounding guess ("name might be taken"), never a dead affordance,
   never a mock that looks real.
5. **Minimum code that solves the problem.** No speculative abstractions, flexibility, or
   error-handling for impossible cases. If 200 lines could be 50, write 50. Would a senior
   engineer call it overcomplicated? Simplify.
6. **Surgical changes.** Touch only what the task needs. Match existing style. Don't refactor
   the unbroken; don't clean up other people's dead code (mention it); do remove orphans YOUR
   change created. Every changed line traces to the request.
7. **Don't assume — surface.** State assumptions; if multiple interpretations exist, present
   them; if something is confusing, say what and ask. When code has changed between sessions,
   operator edits are authoritative — surface anything questionable in them, then defer.

## Product requirements

`design/PRD.md` is authoritative. Before enforcing it, consolidate conflicting requirements
across all PRDs and docs into it; surface unresolved conflicts instead of choosing silently.

## Code Organization Direction

The target backend shape is a **bounded-context modular monolith**. The detailed package map,
ownership rules, and transition guidance live in `docs/STRUCTURE.md`; read it before making a
structural change.

- Organize production code by the business capability it owns (`projects`, `execution`,
  `conversation`, `identity`, `memory`, etc.), not by generic technical buckets such as a broad
  `services/` or `repositories/` layer.
- Keep related functions together when they change for the same workflow. Do not create a module
  for a single function or class merely to make files smaller.
- Split a module only when its callers, dependencies, or policy diverge. A new repository,
  service, helper, or interface must own real SQL, policy, mapping, lifecycle, or an external
  boundary; pass-through layers are clutter and should be folded into their owner.
- Keep API routers and CLI commands thin transport adapters. Workers own background lifecycle
  policy; integrations own provider-specific transport; feature packages own application policy.
- Preserve HTTP, CLI, database, queue, artifact, and agent behavior while refactoring. Internal
  imports may change. Use short-lived compatibility shims only while real callers migrate, then
  remove the shim in the same refactor program.
- Keep Alembic revisions as immutable operational history. Keep vendored resources and bundled
  skills isolated from application packages. Do not merge them into the modular-monolith layout.
- Prefer explicit query/projection modules for cross-context reads over adding unrelated methods
  to a generic service. Update `docs/ARCHITECTURE.md` and `docs/STRUCTURE.md` when a structural
  move lands.


# Log full traceback for every caught exception — NEVER swallow silently or with basic message
Every `except` block MUST log the full traceback — `logger.exception(...)` or
`logger.error("...: %s", traceback.format_exc())` — *including* fire-and-forget paths that 
return a fallback (`None`/`False`/a default): log the traceback FIRST, then fall back. A bare 
`except: pass`, `except: return False`, or `except: return None` that logs nothing or a custom message is forbidden — it destroys the only evidence of what actually failed and 
makes remote debugging impossible. 
Honest errors reach the LOGS, not just the user and the agent.
Full traceback should be logged for errors

## Verification (NO unit/integration tests — operator directive, 2026-07-08)

Do not write, run, or wait on unit/integration tests; they must not block or delay anything.
Verify by exercising the real thing: compile/build, then drive the actual flow — browser for UI
(the `software-qa` subagent in `.claude/agents/` runs destructive browser QA against a live app),
real API calls for backend — and confirm observed behavior before claiming anything works.
Do not theorize about a failure you can reproduce and read logs for. Never claim "done" without
having watched it work; report outcomes faithfully, including what you did not verify.

**UI review:** Every UI change MUST be reviewed with Playwright through the available MCP/plugin.
In Codex, use the in-app browser's Playwright interface when it is available.

**Testing the app (for agents):** the console has no agent password — machine callers authenticate
with a **service token**. Send the header `X-SF-Service-Token: <SF_SERVICE_TOKEN>` and the backend
treats you as admin (`auth.service_token_ok`, `console/deps.py`). `SF_SERVICE_TOKEN` is a Railway
env var (staging service `factory-console`, env `software-factory-console-staging`; prod env
`software-factory-as-skill`); read it via the Railway MCP or `railway run` (the `railway variables`
CLI is flaky headless) and NEVER print, paste, or commit the value — it is admin-equivalent.
- **Staging, authed browser:** Playwright `page.route('**/api/**', …)` injecting that header →
  `/api/me` returns 200 → the SPA login gate passes → all authed screens load (no OAuth, no cookie).
  For a specific user/org instead, mint an HMAC `sf_session` cookie via `auth.sign_session` using
  `SF_SESSION_SECRET` and set it as a Playwright cookie.
- **Local, no gate:** run the console with `SF_GOOGLE_CLIENT_ID` / `SF_SESSION_SECRET` /
  `SF_SERVICE_TOKEN` UNSET → `auth.enabled()` is false → every request is admin. Scratch DB: a local
  Postgres with `CREATE EXTENSION vector` + `models.metadata.create_all` (NOT alembic — the fresh-DB
  migration chain is broken); point the app via `DATABASE_URL`. Mirrors `conftest.py`.
- **A project in a specific state:** never insert a row directly (SOF-23); `Console.create_draft()`
  then drive it via the real API/code (e.g. `record_artifact(kind="product_brief")` for a Concierge
  brief version, `briefs.save()` for a direct edit).

**No time estimates** (operator directive, 2026-07-08): AI development-time estimates are
systematically wrong — days of "estimate" are minutes of agent work. Never defer or descope for
time reasons; report by what is DONE, not by ETA.

Every task states its goal and acceptance criteria up front (define them if not given) and the
delivery reports pass/fail against each — that's what the integrator judges.

## How we work

- **Worktrees:** every session/agent works in a git worktree under `~/software-factory-skill-bare`
  — never the main working dir.
- **PR loop:** integrator leaves concrete review comments on every PR (even when merging); the
  author polls its PR until merged/closed and addresses feedback. Merge at branch HEAD.
- **PR state:** open a ready-for-review PR once its scoped implementation and author verification
  are complete. Use draft only while work is incomplete, required verification is missing, or
  early feedback is requested; review, checks, dependencies, and merge order are blockers, not
  reasons to keep completed work in draft.
- **Linear is the source of truth** for task status: project "Software Factory" (team SOF,
  https://linear.app/tenexity/project/software-factory-f19bffa5f61f). Every ticket assigned to
  Ibraheem, classified `existing` vs `new`. Reflect starts/landings/new findings promptly.
- **memory.md** is the cross-agent notebook: short entries (what/where/why, ≤4 lines) whenever
  something significant lands.
- **docs/ARCHITECTURE.md** is canonical; structural changes update it (and the diagrams in
  `docs/`) as part of the change, not later.
- **Blast radius:** when the operator explicitly instructs something, do it — this project is
  early; big changes are acceptable. Don't self-reject on risk grounds.

## Domain rules (cost real money when violated)

- **Seeding test projects (SOF-23):** never insert a project row directly — the poller
  auto-resumes anything that looks mid-pipeline and has launched real, costly stage agents
  against seeded rows. Always `Console.create_draft()` (drafts are ignored); promote only to
  actually run. Test runs start with `budget_ceiling=10`.
- **Deploy flow (STAGING FIRST — operator directive 2026-07-09):** all changes land on the
  `staging` branch and are tested on the staging deployment BEFORE promotion to `main`. PRs
  target `staging`; after live verification there, fast-forward/merge `staging` → `main`. `main`
  is the stable environment Nick & Graham test on — never push work directly to it (docs-only
  changes exempt at operator discretion). Both branches auto-deploy to their Railway environments.
- **Supabase gotcha (staging setup, 2026-07-09):** a new Supabase project's DIRECT db host
  (`db.<ref>.supabase.co`) is IPv6-only — Railway can't reach it ("Network is unreachable" crash
  loop at migration). Use the POOLER host in SESSION mode (port 5432, `aws-1-us-west-2.pooler.supabase.com`
  for our region; transaction mode 6543 breaks psycopg prepared statements). Never paste DB
  passwords on the peer bus.
- **Deploy:** prod is **https://softwarefactory-console.up.railway.app** (the old
  `factory-console-…up.railway.app` host was Safe-Browsing-flagged and dropped, SOF-15 — never
  resurrect it; never render provider-replica sign-in buttons, mock SSO/credential affordances,
  or unverifiable trust badges on the login page). Auto-deploys on push to `main`;
  `scripts/deploy.sh` is the manual fallback. NOTE: a console deploy currently kills in-flight
  stage agents silently (SOF-116) — avoid pushing while a run you care about is mid-stage.
- **Design system:** the claude_design project is the canonical look for every screen —
  https://claude.ai/design/p/b4af3934-9633-4d26-bade-e53b92d7cc49?file=Software+Factory+Onboarding.html
  (import via the claude_design MCP, auth via /design-login).
- **Python imports** at the top of the file unless deferral is deliberate.
