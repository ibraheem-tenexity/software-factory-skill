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

## Verification (NO unit/integration tests — operator directive, 2026-07-08)

Do not write, run, or wait on unit/integration tests; they must not block or delay anything.
Verify by exercising the real thing: compile/build, then drive the actual flow — browser for UI
(the `software-qa` subagent in `.claude/agents/` runs destructive browser QA against a live app),
real API calls for backend — and confirm observed behavior before claiming anything works.
Do not theorize about a failure you can reproduce and read logs for. Never claim "done" without
having watched it work; report outcomes faithfully, including what you did not verify.

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
