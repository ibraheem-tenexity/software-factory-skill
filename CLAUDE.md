# CLAUDE.md

Behavioral guidelines to reduce common LLM coding mistakes. Merge with project-specific instructions as needed.

## 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them - don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

## 2. Verify Data Structures

Before shipping:
- Verify that the object an API returns is actually the shape you expect.
- Do not avoid exceptions by attaching try/catches or fail-safes — use the correct return object.

## 3. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

## 4. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it - don't delete it.

When your changes create orphans:
- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: Every changed line should trace directly to the user's request.

## 5. Goal-Driven Execution

**Define success criteria. Loop until verified.**

> **OPERATOR DIRECTIVE (2026-07-08): NO TIME ESTIMATES.** Do not give or plan around
> development-time estimates — AI time estimates are systematically wrong. What sounds like days
> is usually minutes of agent work. Never defer, phase, or descope work because it "would take
> too long"; just do it now. Report progress by what is DONE, not by ETA.

> **OPERATOR DIRECTIVE (2026-07-08): NO UNIT/INTEGRATION TESTS.** Do not write, run, or wait on
> unit/integration tests — they are not required for PRs or merges right now and must not block
> or delay any work. This overrides every test-related instruction in this file and in ticket
> acceptance criteria. Verification = LIVE verification instead: compile/build, run the real
> app/flow (browser for UI, real API calls for backend), confirm observed behavior. The
> browser-verify-before-Done rule stands. (Revisit when the operator lifts this.)

Transform tasks into verifiable goals (verify by exercising the real flow, not by test suites):
- "Add validation" → "Drive the real endpoint/UI with invalid inputs and observe the rejection"
- "Fix the bug" → "Reproduce it live, apply the fix, confirm it no longer reproduces"
- "Refactor X" → "Exercise the affected flow end-to-end before and after"

For multi-step tasks, state a brief plan:
```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
```

Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.

### Acceptance Criteria

Every task has a GOAL and explicit SATISFACTION / ACCEPTANCE CRITERIA — the concrete, verifiable conditions that define "done" (tests pass, endpoint returns X, screen renders/behaves like Y, no regression in Z). When you deliver (open the PR / hand off), RETURN both in your report:
- **Goal** — what the task achieves, in one line.
- **Acceptance criteria** — the checkable conditions that prove the goal is met, each marked pass/fail.

This lets the integrator JUDGE the delivery against its own criteria before merging — not merely that it builds. If the operator handed you criteria, restate them and report pass/fail against each. If a task arrives without criteria, define them, state them back, and build to them. A PR/hand-off that doesn't state its goal + acceptance criteria gets bounced back.

## 6. Architecture Doc

`docs/ARCHITECTURE.md` is the canonical description of how the system is built. **Update it on every major structural change** — new/removed service, datastore or schema change, a new pipeline stage or runtime, an auth/ownership change, or anything that moves where state lives. Keep it aligned with the diagrams in `docs/` (`docs/schema-erd.svg` is the source-of-truth ERD, with `docs/schema-erd.md` the schema detail; `docs/service-architecture.svg` is the service/storage topology). If your change makes the doc or a diagram wrong, fixing them is part of the change, not a follow-up.

## 7. Blast Radius

If the operator has explicitly instructed you to do something, do not autonomously reject it or defer it based on the blast radius. This project is in its early stages and high blast radius changes are acceptable.

---

**These guidelines are working if:** fewer unnecessary changes in diffs, fewer rewrites due to overcomplication, and clarifying questions come before implementation rather than after mistakes.

---

## Operational Notes

### Memory Log Format

`memory.md` entries follow this format:

```
# $AGENT_NAME Update at Time: $DD:MM:YYYY:HH:MM:SS.SSS
1. Decision taken or work performed in a single line
2. Related file or artifact location
3. Reasoning
4. Summary in 3 lines
```

The file is a long-term store for information sharing between agents — a central reference, not a detailed log. Each entry should let an agent know enough to find more detail. Write an entry whenever a significant change has been made.

### Verify Before Concluding

Do not theorize. If you think you know why something is breaking, look at the code or logs to confirm before proposing a fix.

## Worktrees
- **All sessions and agents MUST work in a git worktree** so their work doesn't conflict with other sessions and/or agents.
- **Worktrees MUST be checked out in `~/software-factory-skill-bare`** (a bare clone of this repository) — never in the home dir.


## Seeding test/verify projects (SOF-23)
Never insert a project row directly (writing state/artifacts straight into the project store) to
exercise a feature. The live poller auto-resumes any project row that looks mid-pipeline — it has
launched a real Stage-1 `claude -p` agent against a bare seeded row before, creating a real GitHub
repo and burning real cost, because a seeded row with an artifact can look identical to a stage
that "died without finishing."
- **Always seed via `Console.create_draft()`** — it sets `phase='draft'` and records no artifact,
  and the poller explicitly ignores drafts (`is_pipeline_project` returns False for any draft).
  Promote it via `promote_draft()` only when you actually want the pipeline to run.
- If your fixture needs a non-draft row with a pre-recorded artifact (drafts can't have artifacts),
  `auto_resume_dead_stage` also refuses any row whose current stage was never actually launched
  (no `state.launch_attempted` and no `project.log` on disk) — but `create_draft()` remains the
  required, primary method; this is defense-in-depth, not a green light to skip it.

## PR Review Loop
PRs are a two-way conversation, not a fire-and-forget hand-off:
- **The integrator MUST leave review comments on every PR** — concrete, actionable suggested improvements (not a silent merge or a bare reject). Even when merging, note what could be better; when bouncing, say exactly what to change.
- **The build agent that opened the PR MUST poll its own PR in a loop** until the PR is merged/closed, checking for the integrator's comments and suggested improvements, and address each one (push fixes, reply, re-request review). Do not consider the task done while the PR is open with unaddressed feedback. Use `gh pr view <n> --comments` / `gh pr checks` to poll.

## Subagents

### `software-qa` — browser QA agent (`.claude/agents/software-qa.md`)
Destructive-mode QA agent that tests a **running** web app through a real browser (Playwright MCP): drives the actual UI, creates/edits/deletes test records, probes edge cases, invalid inputs, refresh/back/duplicate-tab flows, and reports reproducible bugs with console/network evidence. It does not change application code. Hard stop: it never completes real payments or financially binding actions.

**When to use it:**
- Before claiming any UI feature or fix is done — hand it the app URL + the flow and its acceptance criteria, and treat its pass/fail report as the E2E verification (complements the "Verify feature end-to-end" rule; per-PR green tests are not enough).
- After a deploy, to smoke-test the live console against the flows a change touched.
- When a bug report is vague — have it reproduce the issue and return concrete repro steps before anyone writes a fix.
- For regression sweeps over flows adjacent to a merged change (archive/delete, onboarding, drafts, etc.).

**When NOT to use it:** static code review, writing/fixing code, or anything where no app is running — it tests behavior in a browser, nothing else. Give it the URL, credentials/auth route, the flow under test, and whether the environment's data is disposable.

## Edits by the operator
Edits by the operator are authoritative. If in between sessions you realise that code has changed, check with the operator to make sure if the code was manually edited by the operator, if it was, then you MUST surface errors or assumptions inherent in those edits and make sure that they were explicitly and correctly made, or if the code is correct then defer to the operator. 

## Task Tracking — Source of Truth
The **Linear** project "Software Factory" (https://linear.app/tenexity/project/software-factory-f19bffa5f61f, team **Software Factory / SOF**, project id `2c6a2f7c-72db-4258-a98a-44b6757f2655`) is the **single source of truth for task status**. Keep it up to date: when work starts, advances, lands, or a new issue is found, reflect it in Linear (status + assignee). Every ticket is **assigned to Ibraheem**, and each carries an `existing` vs `new` classification. The internal task board and `docs/KNOWN_ISSUES.md` are working mirrors — Linear is authoritative.

## Design System
Use the claude_design MCP (https://api.anthropic.com/v1/design/mcp, auth via /design-login) to import this project:
https://claude.ai/design/p/b4af3934-9633-4d26-bade-e53b92d7cc49?file=Software+Factory+Onboarding.html

That is the design system: it contains the prototypes of all screens and the design tokens. It is the canonical reference for what any screen should look like.

## Deploy (SOF-16)
**Prod URL: https://softwarefactory-console.up.railway.app** (since 2026-07-09 — the old
`factory-console-software-factory-as-skill.up.railway.app` host was dropped after a Google Safe
Browsing flag, SOF-15; never resurrect it, and never render provider-replica buttons or mock
credential affordances on the login page — that's what got the old host flagged).
`factory-console` auto-deploys on push to `main` via Railway's native GitHub source connect
(armed once by an operator running `scripts/enable-auto-deploy.sh`) — this is the norm, not a
manual step. `scripts/deploy.sh` (preflight → bake `SF_GIT_SHA` → `railway up`) is the **fallback**
for a hand-driven deploy (hotfix, re-deploy without a new commit, or if auto-deploy is disconnected). 

## Python Imports
Python imports should be at the top of a file unless you want to stop something from inadvertently executing.