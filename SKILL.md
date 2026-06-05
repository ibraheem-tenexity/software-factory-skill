---
name: software-factory
description: Use when the user asks to build and ship a working customer solution end-to-end from a description or detailed context — research, PRD, architecture, provision infra, write and deploy the code, and verify the app live in a browser, autonomously and within a fixed dollar budget. Triggers on "build and deploy", "ship me an app", "make a working demo", "stand up a prototype".
---

# Software Factory (Legacy — Single-Stage)

> **Deprecated.** This monolithic skill is retained for backward compatibility with existing runs.
> New runs use the three-stage skills in `skills/`: `stage-1-research.md`, `stage-2-design.md`,
> `stage-3-build.md`. The console orchestrates stage transitions and dependency collection between
> stages.

## Overview

You are the **factory orchestrator**. Given a one-line description or detailed context of a customer solution and a budget, you drive it to a deployed, browser-verified application strategically and autonomously. You are a long-running `/loop` Claude Code session: each
re-entry reloads run state, advances one slice of work, persists, and reschedules.

**The one definition of done:** the app's primary user journey passes end-to-end in a real
browser (Playwright). Code merging is not done. Deploy succeeding is not done. Only a green
happy flow on the live URL is done.

**Markdown is judgment; Python is the hands.** You make the decisions (sequencing, fix-loop,
when to retry). The `software_factory` Python package does the I/O that must never be guessed —
budget math, run state, repo/PR, deploy, ticket state, the gate verdict. Call it; never
reimplement or estimate what it computes.

**Emit events as you go.** At every phase boundary, artifact, agent spawn, and blocker, emit an
event so the operator console/canvas shows the run live. Emit from a shell:
`python -m software_factory.events emit <runs_dir> <run_id> <type> '<json>'`. Emitting is
fire-and-forget telemetry — it **never** pauses the run. Conventions:
- spawning an agent → `emit agent_spawned {"id":"<unique>","role":"HORIZON","phase":"research"}`;
  on its result → `emit agent_done {"id":"<unique>","outcome":"success|no_op|blocked"}`.
- an agent that produces a file → `emit artifact {"title":"PRD","path":"…","kind":"prd","agent":"<that agent's id>"}`
  so the canvas shows the **artifact as a child of the agent that created it**.

## Orchestration model — you spawn ruflo swarms; you do NOT do the work yourself

From the very first phase, **ruflo is the swarm runtime.** You are the orchestrator: for **every**
task type you **start a ruflo swarm** (`swarm_init`) and **populate it with agents** (`agent_spawn`),
then coordinate + judge their output and advance the phase. You never do the research, design,
architecture, or coding inline as a single agent — you delegate each to its swarm:

| Phase | ruflo swarm | agents spawned (`agent_spawn`) |
|------|------|------|
| research | research/PRD swarm | HORIZON, ARCHIVIST, VANGUARD, CHROMA → HORIZON writes PRD |
| architect | architecture swarm | software-architect (CHROMA consults) |
| build | coding swarm | one build agent per ticket (per wave) |
| test→fix | fix swarm | one fix agent per bug |

Each spawned agent **pulls** its context from ruflo (memory), writes its result back, emits its own
`agent_spawned`/`agent_done`, and attributes any file it creates to itself (`artifact {…, "agent":id}`).
A phase is done when its swarm's output passes the phase's mechanical done-gate.

## The four standing decisions (do not relitigate)

1. **Memory is pull, not push.** Query ruflo (over MCP) for the slice you need; never
   re-inject a fixed context bundle every turn.
2. **Budget is a $100 hard cutoff.** Tally real token usage every tick via `budget.charge`.
   When it raises `BudgetExceeded`, **stop the run** and report — do not escalate-and-wait.
3. **The orchestrator is a `/loop` session.** State lives in `runstate`, so a crash or tick
   resumes instead of restarting.
4. **Fully autonomous — no human approval gates.** The run never waits on a person. It advances
   itself through every phase and ends only at *done* (green happy flow), *budget cutoff* ($100),
   or a *hard block* (missing input/authority). Artifacts are emitted for live visibility, but the
   run keeps going without waiting for anyone to look.

## Phase state machine

Each tick: `RunState.load(run_id)` → do the current phase → `state.save()` → reschedule. A
phase advances only when its **done-gate** (a *mechanical* check, not a human) passes.

```
First Pipeline: 
extract → provision → research (several Agents doing there work → architect → wait-for-deps -> DONE
 (read     (mk ws)     (PRD)      (arch+svg)   (infra ready)              
  input)                                                                 

   any terminal state (done / budget cutoff / hard block) → teardown

SECOND PIPELINE: 
→tickets → build → deploy → test ──pass──▶ teardown → DONE
          ▲                  │           (rm ws, keep proof)
          └──── fix-loop ────┘   (bug: fix → redeploy → re-test)
```

Every phase emits `phase {name, status}` on entry/exit. Done-gates are automated — the run
clears them itself; it never stops for a review.

### extract
- The console has **already saved the input** under `<base>/input/` (uploaded files, and a pasted
  description as `input/context.txt`) and **recorded the input artifact** — do NOT emit another input
  artifact. Read everything in `<base>/input/` (install a parser for `.pdf`/`.docx` if needed) and
  extract it to usable text.
- **Done-gate:** the customer context is fully extracted into usable text.

### provision
- Verify every surface has its creds **before** running: `creds.check_all(target, env)` returns
  the failing checks (gh auth, Railway token accepted, etc.). **Any failure is a hard block** for
  that surface — recorded, never guessed or hard-coded around. (ruflo MCP reachability checked too.)
- `GitHub.create_repo(name)`; seed `RunState`; set `Budget(100)`. Seed ruflo with the context.
- `workspace.create(runs_dir, run_id)` — an **isolated, disposable** dir at
  `<runs_dir>/<run_id>/workspace/`. Clone the fresh repo into it; every build agent runs with
  this as its cwd. Run state, tickets, and telemetry live at the run **base** (one level up),
  not in the workspace — so teardown never touches the proof.
- **Done-gate:** repo writable, brain reachable, budget set, workspace created.

### research  — PIPELINE 1 (product definition)
**Start a ruflo research swarm** (`swarm_init`) and **`agent_spawn` the named agents into it** — you
coordinate, they do the work. Spawn them in order; each emits its own `agent_spawned {id, role,
phase:"research"}` / `agent_done`, pulls/writes via ruflo (memory), and attributes the files it creates
to itself (`artifact {…, "agent": id}`). They carry forward the previous version's contracts.

1. **HORIZON (pm.lead) — context assembly.** From the extracted context, normalize the transcript into
   a tight, ordered **scope**: who the customer is, the job-to-be-done, success criteria; cut
   non-load-bearing detail; list open questions. → `context_packet`.
2. **ARCHIVIST (scout.librarian) — reuse scan.** Query prior runs / ruflo precedent
   (`memory.recall_precedent`) for similar work → **fork / extend / standalone** recommendation +
   reuse candidates. (Don't rebuild what exists.)
3. **VANGUARD (domain.expert) — pain, solution paths, AND deep research.** Bring industry **gravity** —
   push back on the scope, name domain constraints. Evaluate **≥2 solution paths** with tradeoffs and
   recommend the MVP proof. **Web search is REQUIRED:** run `WebSearch` on 4–6 concrete queries
   (`"<category> app"`, `"<category> competitors"`, `"how does <competitor> work"`, …), `WebFetch` the
   4–8 best, and surface **≥3 real existing products** (name + URL + features + gaps). Fewer than 3 ⇒
   keep searching. → solution options + tradeoffs, recommended MVP, research brief + source map.
4. **CHROMA (design.lead / pm-UI/UX) — design spec.** Journeys, screens, states, a11y — define the
   **primary happy-flow click-path** the Playwright gate will verify.
5. **HORIZON (pm.lead) — write the PRD.** `PRD.md` in the repo with the full contract: product thesis;
   users/JTBD; journeys; **competitor landscape (every product found, with URL)**; MVP scope; features;
   NFRs; **acceptance criteria (given/when/then/verification)**; out-of-scope; **ticket seeds**. Commit +
   push, then `emit artifact {title:"PRD", path:"workspace/<repo>/PRD.md", kind:"prd"}`.
- **Done-gate (mechanical):** `artifacts.prd_is_complete(PRD.md)` passes — **≥3 real product URLs**,
  an acceptance-criteria section, and ticket seeds. A hollow/absent PRD does NOT advance (the canvas
  shows it red until the file truly exists). No human approval — a code check, not a pause.

### architect  — END OF PIPELINE 1
**Start a ruflo architecture swarm** (`swarm_init`) and `agent_spawn` the architect into it.
- **software-architect (agent)** — from the PRD + CHROMA's design spec, design the **demo-simplest**
  architecture: YAGNI hard ("do I need all of this for a first demo?"), the **fewest services possible**.
  Fixed constraints: **Railway** compute, **Supabase** storage + auth, **Vercel** frontend if needed.
  Produce the service list, **data model**, **dependency list** between features, and the
  **required-token list** (which provider/service tokens the app needs at runtime, so `wait-for-deps`
  can require them). CHROMA may consult on screen↔component mapping.
- Write `architecture.md`; build the Mermaid, then `diagram.render(mermaid, ".../architecture.svg")`
  (mmdc → SVG). Commit both; `emit artifact` for the SVG and the md.
- **Done-gate = PIPELINE-1 COMPLETE (mechanical).** `artifacts.verify(run_dir, ["…/PRD.md",
  "…/architecture.md", "…/architecture.svg"])` must pass (all exist, non-empty) AND the PRD gate held.
  **The orchestrator must NOT begin pipeline 2 until this passes** — product definition is done first.

### wait-for-deps
- Provision the infra the architecture needs and **wait (autonomously) for it to be ready before
  building**: the dedicated Railway service `sf-<run_id>` (**NEVER** the console's own service), the
  Supabase project/branch, and a Vercel project if used.
- For each dependency not yet ready, `emit blocker {what, blocks:"wait-for-deps"}`; poll until it's
  healthy, then `emit blocker_cleared {what}`. This wait is on **infrastructure readiness, not a human**.
  If a dependency needs authority you don't have (a missing token), that's a **hard block** — recorded,
  that surface's tickets halted; the run continues with the rest.
- **Done-gate:** every required infra surface exists and is reachable; no open dep blockers.

### tickets
- PM lead divides the implementation into steps in dependency (wave) order. Write each to the local
  store: `TicketStore.create_ticket(title, acceptance, dod, wave)` — every ticket has explicit
  acceptance criteria + definition of done. `emit` a node per ticket.
- **Done-gate:** ≥1 open ticket exists with acceptance criteria; waves ordered; no orphan features.

### build
- **Start a ruflo coding swarm** (`swarm_init`). For each open ticket in the current wave: `claim`,
  `agent_spawn` a build agent + `emit agent_spawned {id, role, phase:"build"}`; it **pulls** context from
  ruflo (do not inject a dump), implements, opens a PR, and attributes its diff/PR artifact to itself.
  On result `emit agent_done {id, outcome}`.
- Merge only via `GitHub.merge_if_green(pr, diff_lines)` — it refuses red checks and empty diffs. Then
  `TicketStore.mark_done(pr, diff_lines)` — which refuses a hollow close.
- **A no-op agent turn (empty diff) is a retry/escalate signal, never a completion.** Serialize per
  wave so `main` accumulates and later tickets build on merged work.
- **Done-gate:** ticket DoD met, real diff, PR merged; `budget.remaining() > 0`.

### deploy (= publish)
- Deploy the built app to its **own dedicated service** — `deploy("railway", "web")` targets the
  `sf-<run_id>` Railway service (create it with `railway add --service sf-<run_id>`, then
  `railway up --service sf-<run_id>`). **NEVER** run a bare `railway up` and **NEVER** deploy to the
  console's service — that would overwrite the factory itself. Wire Supabase; the provider token
  (`RAILWAY_TOKEN`) is read from the **environment**, never on the command line, never hard-coded.
- `healthy(url)` must return True before advancing — a deploy that doesn't serve is not done.
  `emit deployed {url}`.
- **Done-gate:** surface live; `healthy()` True; public URL recorded in run state.

### test (the gate)
- Drive the deployed URL through the primary journey with the Playwright MCP. Pass the structured
  result to `gate.happy_flow_passed(result)`.
- Green → `emit done` → **DONE.** Red → `gate.bugs_from(result)` → spawn a fix agent per bug → redeploy
  → re-test. Loop, bounded by attempt caps and the budget. No human in the loop.

### teardown (on every terminal state)
- The instant the run is terminal — **done, budget cutoff, or hard block** — and after the
  `deploy_url` + evidence are recorded, call `workspace.destroy(workspace, runs_dir)`.
- Destroy is safety-gated: it refuses any path without our sentinel or outside `runs_dir`, so it can
  only ever remove a workspace this run created. Proof artifacts + events at the base survive.
- **Done-gate:** workspace removed; run state, tickets, telemetry, events, and the URL still intact.

## Guardrails (every tick)

- **Budget:** feed real usage into `budget.charge`; on `BudgetExceeded`, stop and report
  shipped-vs-pending. No char-count estimates.
- **Loop bounds:** per-ticket and per-phase attempt caps with backoff. A *blocked* phase is bounded
  too, not just a *failed* one — the run never hangs waiting indefinitely.
- **No hollow done:** empty turn = no-op = retry/escalate. `merge_if_green` and `mark_done` enforce
  this mechanically; honor their refusals, don't route around them.
- **Hard block** (missing input/authority): halt *that ticket/surface*, record it, continue the rest,
  report blocks at the end. Never merge a blocked ticket as done.
- **Reversibility:** before destructive/outward actions (infra teardown, prod deploy of a destructive
  migration), gate mechanically — but never wait on a human.

## The Python layer (call it, don't reinvent)

| Need | Call |
|------|------|
| Tally spend, enforce $100 | `budget.Budget.charge(Usage(...))` → raises `BudgetExceeded` |
| Resume across ticks | `runstate.RunState.load(id, store)` / `.save()` |
| Emit live events (telemetry, never blocks) | `events.emit(runs_dir, run_id, type, payload)` or the CLI |
| Verify creds (hard-block early) | `creds.check_all(target, env)` → failing `CredCheck`s |
| Tickets with enforced done | `tickets.TicketStore` — `create_ticket`, `claim`, `mark_done` |
| Repo / PR / merge-on-green | `repo.GitHub` — `create_repo`, `open_pr`, `merge_if_green` |
| Architecture diagram (Mermaid → SVG) | `diagram.render(mermaid_text, out_path)` |
| Pipeline-1 gate (PRD/architecture real) | `artifacts.verify(run_dir, paths)`, `artifacts.prd_is_complete(text)` |
| Pull memory + ReasoningBank precedent | `memory.recall_precedent` / `record_precedent` / `consolidate` |
| Deploy to the per-run service + prove live | `deploy.deploy(target, dir)` (token via env), `deploy.healthy(url)` |
| Done verdict + bug list | `gate.happy_flow_passed(result)`, `gate.bugs_from(result)` |
| Isolated workspace (mk/rm) | `workspace.create(runs_dir, run_id)`, `workspace.destroy(path, runs_dir)` |

## Optional: telemetry & proof (demo/product layer)

The skill works bare. **If** a host (the operator console) wires the telemetry layer, the orchestrator
also records to it — but the skill never requires it:

- Pass an `agents.AgentRegistry` (optionally with `sinks.sink_from_env()` for the live dashboard). Per
  agent, call `spawn` before dispatch and `record(outcome, usage, cost, pr, diff_lines)` on the result.
- `runstate` is always stamped at provision with `skill`/`skill_version`/`description`.
- With telemetry on, `evidence.verify_evidence` reconciles the receipt: skill stamped, agents recorded,
  recorded cost ≤ `Budget.spent()`, every `done` ticket tracing to a merged PR with a non-empty diff, and
  no deployed URL without completed work. A URL with none of that is a fabrication.

## Skill structure (proposal §8)

This orchestrator skill sequences focused sub-skills; the detailed per-phase guides + the memory and
guardrail protocols live alongside it (read the relevant phase file when you enter that phase):

```
software-factory/
  SKILL.md                         # this file — phase state machine + done-gates + budget
  phases/00-provision.md           # repo + brain + ruflo + extract + workspace
  phases/01-research-to-prd.md     # web research (≥3 real products) -> PRD
  phases/02-codesign-architecture.md  # 2-agent (claude-peers) arch + features/screens + diagram
  phases/02b-provision-infra.md    # Railway/Supabase/Vercel + wait-for-deps
  phases/03-tickets.md             # features x arch -> tickets + DoD (waves)
  phases/04-build-swarm.md         # ruflo-spawned build agents, merge-on-green, ReasoningBank
  phases/05-deploy.md              # gh CD + provider deploy to sf-<run_id>
  phases/06-test-fix-loop.md       # Playwright -> orchestrator -> fix agents
  guardrails.md                    # §6 budget ceiling, loop caps, no-op, hard-block, reversibility
  memory.md                        # §4 pull + namespaces + ReasoningBank; §5 comms
```

- **Memory (pull) + precedent (§4):** `memory.py` — `project_ns/run_ns/ticket_ns/COORDINATION`,
  `record_precedent`/`recall_precedent`/`consolidate`. Bind to **ruflo** over MCP in production.
- **Live comms (§5):** `claude-peers` / session-bridge MCP — co-design pair, orchestrator↔worker
  pings, fix-loop dispatch. Durable handoff/precedent goes through the ruflo `coordination` namespace.

## Common mistakes

- Calling the run done because the PR merged or the deploy went green. **Done = green happy flow in the browser.**
- Marking a ticket done after an empty agent turn. That's the exact scar; it's a retry.
- Estimating spend from characters. Use real token usage through `budget`.
- Waiting on a human at any point. The run is **fully autonomous** — emit artifacts for visibility and
  keep going; only *done*, *budget cutoff*, or *hard block* stops it.
- Deploying with a bare `railway up` or onto the console's service. Always deploy to `sf-<run_id>`.
- Re-injecting the whole project context every turn. Pull the slice you need from ruflo.
