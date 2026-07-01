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

Transform tasks into verifiable goals:
- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

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
* Git worktree should be used by sessions and agents so that their work doesn't conflict with other sessions and/or agents.

* Worktrees Must Be Checked out in ~/software-factory-skill-bare Not in Home Dir

~/software-factory-skill-bare is a bare clone of the software factory skill repository and worktree should be checked out there and not in the home dir.


## PR Review Loop
PRs are a two-way conversation, not a fire-and-forget hand-off:
- **The integrator MUST leave review comments on every PR** — concrete, actionable suggested improvements (not a silent merge or a bare reject). Even when merging, note what could be better; when bouncing, say exactly what to change.
- **The build agent that opened the PR MUST poll its own PR in a loop** until the PR is merged/closed, checking for the integrator's comments and suggested improvements, and address each one (push fixes, reply, re-request review). Do not consider the task done while the PR is open with unaddressed feedback. Use `gh pr view <n> --comments` / `gh pr checks` to poll.

## Edits by the operator
Edits by the operator are authoritative. If in between sessions you realise that code has changed, check with the operator to make sure if the code was manually edited by the operator, if it was, then you MUST surface errors or assumptions inherent in those edits and make sure that they were explicitly and correctly made, or if the code is correct then defer to the operator. 

## Task Tracking — Source of Truth
The **Linear** project "Software Factory" (https://linear.app/tenexity/project/software-factory-f19bffa5f61f, team **Software Factory / SOF**, project id `2c6a2f7c-72db-4258-a98a-44b6757f2655`) is the **single source of truth for task status**. Keep it up to date: when work starts, advances, lands, or a new issue is found, reflect it in Linear (status + assignee). Every ticket is **assigned to Ibraheem**, and each carries an `existing` vs `new` classification. The internal task board and `docs/KNOWN_ISSUES.md` are working mirrors — Linear is authoritative.

## Design System: 
Use the claude_design MCP (https://api.anthropic.com/v1/design/mcp, auth via /design-login) to import this project:
https://claude.ai/design/p/b4af3934-9633-4d26-bade-e53b92d7cc49?file=Software+Factory+Onboarding.html

That is the design system contain prototypes of all screens and tokens and 