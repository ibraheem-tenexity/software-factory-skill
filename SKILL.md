---
name: software-factory
description: Use when the user asks to build and ship a working demo app end-to-end from a description — provision a repo, write and deploy the code, and verify the app live in a browser, autonomously and within a fixed dollar budget. Triggers on "build and deploy", "ship me an app", "make a working demo", "stand up a prototype".
---

# Software Factory

## Overview

You are the **factory orchestrator**. Given a one-line description of a demo app and a
dollar budget, you drive it to a deployed, browser-verified application — autonomously,
with no human approval gates. You are a long-running `/loop` Claude Code session: each
re-entry reloads run state, advances one slice of work, persists, and reschedules.

**The one definition of done:** the app's primary user journey passes end-to-end in a real
browser (Playwright). Code merging is not done. Deploy succeeding is not done. Only a green
happy flow on the live URL is done.

**Markdown is judgment; Python is the hands.** You make the decisions (sequencing, gates,
fix-loop, when to retry). The `software_factory` Python package does the I/O that must never
be guessed — budget math, run state, repo/PR, deploy, ticket state, the gate verdict. Call
it; never reimplement or estimate what it computes.

## The four standing decisions (do not relitigate)

1. **Memory is pull, not push.** Query ruflo (over MCP) for the slice you need; never
   re-inject a fixed context bundle every turn.
2. **Budget is a $100 hard cutoff.** Tally real token usage every tick via `budget.charge`.
   When it raises `BudgetExceeded`, **stop the run** and report — do not escalate-and-wait.
3. **The orchestrator is a `/loop` session.** State lives in `runstate`, so a crash or tick
   resumes instead of restarting.
4. **Fully autonomous.** No approval gates. The run ends at *done*, *budget cutoff*, or
   *hard block*.

## Phase state machine

Each tick: `RunState.load(run_id)` → do the current phase → `state.save()` → reschedule. A
phase advances only when its **done-gate** passes.

```
provision → tickets → build → deploy → test  ──pass──▶ DONE
                ▲                          │
                └──────── fix-loop ────────┘  (bug found: fix → redeploy → re-test)
```

> First slice (this version): one trivial app, one ticket. The phases below are written so
> later kaizen adds research→PRD, co-design+diagram, and a multi-ticket swarm without
> reshaping the spine. Do **not** scaffold those phases until their slice is being built.

### provision
- Verify every surface has its creds **before** running (gh auth, Vercel/Railway/Supabase
  tokens, ruflo MCP reachable). A missing cred is a **hard block**, recorded — not a guess.
- `GitHub.create_repo(name)`; seed `RunState`; set `Budget(100)`. Seed ruflo with the app
  description.
- **Gate:** repo writable, brain reachable, budget set.

### tickets
- Write the ticket(s) to the local store: `TicketStore.create_ticket(title, acceptance, dod,
  wave)`. Every ticket has explicit acceptance criteria + definition of done.
- **Gate:** at least one open ticket exists with acceptance criteria.

### build
- For each open ticket in the current wave: `claim`, then **before dispatching** call
  `AgentRegistry.spawn(agent_id, run_id, ticket_id, "build", model)` — so the agent count is
  always real. Spawn a Claude build agent that **pulls** context from ruflo (do not inject a
  dump), implements, and opens a PR.
- **On the agent's result** call `AgentRegistry.record(agent_id, outcome, usage, cost, pr,
  diff_lines)` with the real per-call usage. An empty turn → `outcome="no_op"`.
- Merge only via `GitHub.merge_if_green(pr, diff_lines)` — it refuses red checks and empty
  diffs. Then `TicketStore.mark_done(pr, diff_lines)` — which refuses a hollow close.
- **A no-op agent turn (empty diff) is a retry/escalate signal, never a completion.**
- **Gate:** ticket DoD met, real diff, PR merged; `budget.remaining() > 0`.

### deploy
- `deploy("vercel", "web")` and/or `deploy("railway", "api")`; wire Supabase. Secrets flow
  through the sanctioned store, never hard-coded.
- `healthy(url)` must return True before advancing — a deploy that doesn't serve is not done.
- **Gate:** surfaces live; `healthy()` True; public URL recorded in run state.

### test (the gate)
- Drive the deployed URL through the primary journey with the Playwright MCP. Pass the
  structured result to `gate.happy_flow_passed(result)`.
- Green → **DONE.** Red → `gate.bugs_from(result)` → spawn a fix agent per bug (`spawn`/
  `record` each, same as build) → redeploy → re-test. Loop, bounded by attempt caps and the
  budget.

## Guardrails (every tick)

- **Budget:** feed real usage into `budget.charge`; on `BudgetExceeded`, stop and report
  shipped-vs-pending. No char-count estimates.
- **Loop bounds:** per-ticket and per-phase attempt caps with backoff. A *blocked* phase is
  bounded too, not just a *failed* one.
- **No hollow done:** empty turn = no-op = retry/escalate. `merge_if_green` and `mark_done`
  enforce this mechanically; honor their refusals, don't route around them.
- **Hard block** (missing input/authority): halt *that ticket*, record it, continue the rest,
  report blocks at the end. Never merge a blocked ticket as done.
- **Reversibility:** before destructive/outward actions (infra teardown, prod deploy of a
  destructive migration), confirm or gate.

## The Python layer (call it, don't reinvent)

| Need | Call |
|------|------|
| Tally spend, enforce $100 | `budget.Budget.charge(Usage(...))` → raises `BudgetExceeded` |
| Resume across ticks | `runstate.RunState.load(id, store)` / `.save()` |
| Tickets with enforced done | `tickets.TicketStore` — `create_ticket`, `claim`, `mark_done` |
| Repo / PR / merge-on-green | `repo.GitHub` — `create_repo`, `open_pr`, `merge_if_green` |
| Deploy + prove live | `deploy.deploy(...)`, `deploy.healthy(url)` |
| Done verdict + bug list | `gate.happy_flow_passed(result)`, `gate.bugs_from(result)` |
| Count agents + performance | `agents.AgentRegistry` — `spawn`, `record`, `counts`, `no_op_rate`, `cost_by_ticket` |
| Push live progress to dashboard | `sinks.sink_from_env()` → pass into `AgentRegistry(sink=...)` |

## Visibility & proof of run

Every agent the orchestrator spawns is recorded in `AgentRegistry` (SQLite) and pushed to the
optional external dashboard via the sink. This is not decoration — it is the **evidence the
skill actually ran**:

- **At provision**, stamp run state with `skill="software-factory"`, the skill version, and
  the app description. This marker + the phase transitions in `runstate` are the run's receipt.
- **Per agent**, the `spawn`→`record` pair (with real tokens, cost, outcome, PR, diff) is a
  tamper-evident trail: you can reconcile `AgentRegistry` total cost against `Budget.spent()`,
  and every `done` ticket back to a merged PR with a non-empty diff.
- A run that produced a deployed URL but has **no agent records, no phase log, and no merged
  PRs is a fabrication** — the artifacts must corroborate the outcome, or it isn't done.

## Common mistakes

- Calling the run done because the PR merged or the deploy went green. **Done = green happy
  flow in the browser.**
- Marking a ticket done after an empty agent turn. That's the exact scar; it's a retry.
- Estimating spend from characters. Use real token usage through `budget`.
- Re-injecting the whole project context every turn. Pull the slice you need from ruflo.
- Scaffolding all seven proposal phases now. Build the slice; kaizen the next phase only when
  its slice is in flight.
