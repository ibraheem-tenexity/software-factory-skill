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
provision → tickets → build → deploy → test  ──pass──▶ teardown → DONE
   (mk ws)      ▲                        │              (rm ws, keep proof)
               └────────── fix-loop ─────┘   (bug: fix → redeploy → re-test)

   any terminal state (done / budget cutoff / hard block) → teardown
```

> First slice (this version): one trivial app, one ticket. The phases below are written so
> later kaizen adds research→PRD, co-design+diagram, and a multi-ticket swarm without
> reshaping the spine. Do **not** scaffold those phases until their slice is being built.

### provision
- Verify every surface has its creds **before** running: `creds.check_all(target, env)` returns
  the failing checks (gh auth, Railway token accepted, etc.). **Any failure is a hard block** for
  that surface — recorded, never guessed or hard-coded around. (ruflo MCP reachability checked too.)
- `GitHub.create_repo(name)`; seed `RunState`; set `Budget(100)`. Seed ruflo with the app
  description.
- `workspace.create(runs_dir, run_id)` — an **isolated, disposable** dir at
  `<runs_dir>/<run_id>/workspace/`. Clone the fresh repo into it; every build agent runs with
  this as its cwd. Run state, tickets, and telemetry live at the run **base** (one level up),
  not in the workspace — so teardown never touches the proof.
- **Gate:** repo writable, brain reachable, budget set, workspace created.

### tickets
- Write the ticket(s) to the local store: `TicketStore.create_ticket(title, acceptance, dod,
  wave)`. Every ticket has explicit acceptance criteria + definition of done.
- **Gate:** at least one open ticket exists with acceptance criteria.

### build
- For each open ticket in the current wave: `claim`, then spawn a Claude build agent that
  **pulls** context from ruflo (do not inject a dump), implements, and opens a PR.
- Merge only via `GitHub.merge_if_green(pr, diff_lines)` — it refuses red checks and empty
  diffs. Then `TicketStore.mark_done(pr, diff_lines)` — which refuses a hollow close.
- **A no-op agent turn (empty diff) is a retry/escalate signal, never a completion.**
- **Gate:** ticket DoD met, real diff, PR merged; `budget.remaining() > 0`.
- *(If telemetry is wired — see Optional below — record each agent's spawn + result.)*

### deploy (= publish)
- `deploy("railway", "web")` (runs `railway up` then returns the public domain) and/or
  `deploy("vercel", "web")`; wire Supabase. The provider token (e.g. `RAILWAY_TOKEN`) is read
  from the **environment** by the CLI — injected by the host, never on the command line, never
  hard-coded.
- `healthy(url)` must return True before advancing — a deploy that doesn't serve is not done.
- **Publishing moves the work to durable surfaces** (the merged GitHub repo + the live URL); the
  workspace is no longer the source of record after this point.
- **Gate:** surfaces live; `healthy()` True; public URL recorded in run state.

### test (the gate)
- Drive the deployed URL through the primary journey with the Playwright MCP. Pass the
  structured result to `gate.happy_flow_passed(result)`.
- Green → **DONE.** Red → `gate.bugs_from(result)` → spawn a fix agent per bug → redeploy →
  re-test. Loop, bounded by attempt caps and the budget.

### teardown (on every terminal state)
- The instant the run is terminal — **done, budget cutoff, or hard block** — and after the
  `deploy_url` + evidence are recorded, call `workspace.destroy(workspace, runs_dir)`.
- Destroy is safety-gated: it refuses any path without our sentinel or outside `runs_dir`, so it
  can only ever remove a workspace this run created. Proof artifacts at the base survive.
- **Gate:** workspace removed; run state, tickets, telemetry, and the URL still intact.

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
| Verify creds (hard-block early) | `creds.check_all(target, env)` → failing `CredCheck`s |
| Deploy + prove live | `deploy.deploy(target, dir)` (token via env), `deploy.healthy(url)` |
| Done verdict + bug list | `gate.happy_flow_passed(result)`, `gate.bugs_from(result)` |
| Isolated workspace (mk/rm) | `workspace.create(runs_dir, run_id)`, `workspace.destroy(path, runs_dir)` |

These modules are the whole skill. It runs with nothing else.

## Optional: telemetry & proof (demo/product layer)

The skill works bare. **If** a host (the operator console) wants live visibility and a
tamper-evident receipt, it wires in the telemetry layer — the orchestrator then records to it,
but the skill never requires it:

- Pass an `agents.AgentRegistry` (optionally with `sinks.sink_from_env()` for the live
  dashboard). Per agent, call `spawn` before dispatch and `record(outcome, usage, cost, pr,
  diff_lines)` on the result — a no-op turn records `outcome="no_op"`.
- `runstate` is always stamped at **provision** with `skill`/`skill_version`/`description` — that
  marker is plain run metadata (no harness dependency) and stays part of the core run.
- With telemetry on, `evidence.verify_evidence` reconciles the receipt: skill stamped, agents
  recorded, recorded cost ≤ `Budget.spent()`, every `done` ticket tracing to a merged PR with a
  non-empty diff, and no deployed URL without completed work. A URL with none of that is a
  fabrication.

## Common mistakes

- Calling the run done because the PR merged or the deploy went green. **Done = green happy
  flow in the browser.**
- Marking a ticket done after an empty agent turn. That's the exact scar; it's a retry.
- Estimating spend from characters. Use real token usage through `budget`.
- Re-injecting the whole project context every turn. Pull the slice you need from ruflo.
- Scaffolding all seven proposal phases now. Build the slice; kaizen the next phase only when
  its slice is in flight.
