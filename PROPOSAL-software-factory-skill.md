# Proposal: Autonomous Software Factory (skill-driven, clean-room)

**Status:** draft for review · **Date:** 2026-06-01 · **Author:** operator + graph-viz
**Goal:** a single **skill** that takes a description of a demo app and drives it
all the way to a deployed, Playwright-verified application — research → PRD →
architecture → infra → tickets → build swarm → deploy → test → fix-loop — with a
**central orchestrator** following this skill and spawning agents throughout.

> Built clean-room (not on the current Symphony/Postgres stack), but carrying the
> scar tissue from the last run (see `REVIEW-INDEX-2026-05-30.md`): **pull, don't
> push, context** (`agent-memory.md`), **cap spend hard**, **never mark hollow
> work done**, **the happy-flow test is the real gate.**

---

## 1. Design principles (earned, non-negotiable)

1. **Pull, not push.** Agents *query* a project brain over MCP for the slice they
   need; we never re-inject a fixed multi-KB context bundle every turn. (Last run:
   ~94% of tokens were cached re-injection — the dominant cost.)
2. **Hard cost ceiling + accurate accounting.** A run-level budget kill-switch,
   real per-call token usage (not char estimates), and loop bounds. (Last run:
   ~$700, no cap, runaway loops billed invisibly.)
3. **No hollow "done."** A ticket is done only on real, verified change — empty
   agent turns are no-ops to retry/escalate, never "merged as complete." (Last
   run: a QA-gate ticket merged having done nothing.)
4. **The happy-flow Playwright run is the integration gate.** Code merging ≠ a
   working app. Done = the primary user journey passes in a browser.
5. **Demo-scope simplicity.** Architecture is deliberately basic; YAGNI hard.
6. **Resumable orchestration.** The orchestrator is a `/loop` Claude Code session;
   run state lives in ruflo memory, so a crash or loop-tick re-loads and resumes.
   Build agents are durable jobs, not fire-and-forget promises.
7. **Coherent assembly.** Work accumulates into a single deployable repo, built
   bottom-up; later work builds on merged earlier work.

---

## 2. Actors & components

| Actor | Role | Tech |
|-------|------|------|
| **Factory Orchestrator** | The long-running **Claude Code session kept alive via `/loop`** that *is* this skill: drives phases, spawns agents, owns run state + budget, consumes test feedback, runs the fix-loop; reloads state from ruflo memory on each loop re-entry. | Claude Code + `/loop` |
| **ruflo (swarm + memory)** | Spawns/coordinates worker agents **and** is the project memory: research, PRD, architecture, decisions, features/screens, ticket precedent + working/coordination state + precedent loop. Exposed as **MCP** (pull). | **ruflo** — AgentDB (vector) + ReasoningBank |
| **Research agent** | Deep web research on the product + competitors → feeds PRD. | Codex session + `deep-research` |
| **Co-design agents (×2)** | Two agents that *converse* to co-produce the architecture + features/screens from the PRD. | Claude (ruflo-spawned) |
| **Build agents** | Spawned per ticket; implement + open PRs; communicate via brain + channel. | Claude (ruflo-spawned) |
| **Test agent** | Drives the deployed app end-to-end, reports findings. | Playwright MCP |
| **Infra** | Backend deploy, auth+DB, frontend hosting. | **Railway** + **Supabase** + **Vercel** (MCP/CLI) |
| **VCS/CD** | Repo + deployment wiring. | GitHub (`gh` CLI, PAT/OAuth) |

**Memory = ruflo (decided, Q1).** One tool for both swarm orchestration **and**
memory keeps it simple: ruflo's **AgentDB** (vector + BM25 + RRF + rerank) holds
durable project knowledge (PRD, architecture, decisions, feature specs) and
working/coordination state, with a **ReasoningBank** precedent loop; agents
**pull** it over MCP. (GBrain was the alternative — see `agent-memory.md` — but a
single tool for swarm + memory wins here.)

---

## 3. The workflow (phases, each with a done-gate)

```
[0 Provision] -> [1 Research→PRD] -> [2 Co-design: arch+features (+infra)]
   -> [3 Tickets] -> [4 Build swarm] -> [5 Deploy] -> [6 Test→Fix loop] -> DONE
        ^------------------------------ fix-loop -----------------------------|
```

### Phase 0 — Provision / bootstrap
- **In:** user's app context (uploaded to the console) + a GitHub repo (created
  fresh, or a URL + creds: PAT+username+email, or OAuth).
- **Do:** create/connect the repo via `gh`; instantiate the **Factory
  Orchestrator** session (Claude Code + `/loop`); stand up **ruflo** (swarm
  runtime + memory), wired as MCP; seed ruflo memory with the uploaded context;
  start the **Codex** research session.
- **Gate:** repo reachable + writable; brain + swarm MCP reachable; budget set.

### Phase 1 — Deep research → PRD
- **Do:** research agent runs `deep-research` on the proposed app **and similar
  products on the web**; writes findings into the brain; synthesizes a **PRD**
  (problem, users, value, MVP scope, feature candidates, risks/unknowns).
- **Out:** `PRD` page in the brain (pullable).
- **Gate:** PRD covers problem + users + MVP scope + a feature list, and is
  coherent (a judge/self-check pass).

### Phase 2 — Co-design: architecture + features/screens (+ infra)
- **Do:** the orchestrator spawns **two agents that converse** to co-produce, from
  the PRD: (a) a **simple** architecture under fixed constraints — **Railway**
  (backend), **Supabase** (auth + DB), **Vercel** (frontend) — and (b) the
  **feature + screen list**. Dependencies are disclosed. The architecture is
  **exported as a diagram** (Mermaid → image). Then **infra is provisioned** in
  Railway/Supabase/Vercel via MCP/CLI.
- **Out:** `architecture` page + diagram, `features`/`screens` list, live infra
  handles (project IDs, URLs), `dependencies` list — all in the brain.
- **Gate:** diagram renders; infra projects exist and are reachable; feature list
  maps to PRD scope.

### Phase 3 — Tickets
- **Do:** derive **tickets/tasks** from features × architecture, in dependency
  (wave) order, each with explicit **acceptance criteria** + **definition of
  done**. *(Open question Q2: ticket store — GitHub Issues vs ruflo task queue vs
  Linear.)*
- **Gate:** every ticket has acceptance criteria; waves ordered; no orphan
  features.

### Phase 4 — Build swarm
- **Do:** **ruflo spawns Claude build agents** per ticket; they **pull** context
  from the brain (not injected), **communicate** via the swarm channel + shared
  brain namespace, implement, and open PRs. Repo is wired for deploy via `gh`.
- **Assembly:** serialize per wave; merge-on-green so `main` accumulates and later
  tickets build on merged work. **No-op turns retry/escalate, never auto-complete.**
- **Gate:** ticket DoD met + a real diff + PR merged; budget within ceiling.

### Phase 5 — Deploy
- **Do:** deploy backend→Railway, frontend→Vercel, DB/auth wired to Supabase, via
  the deploy wiring (`gh` CD + provider MCP). Secrets flow through one sanctioned
  store, never hard-coded.
- **Gate:** all three surfaces deploy green; health checks pass; public URL up.

### Phase 6 — Test → fix loop
- **Do:** the **Playwright agent** drives the deployed app through the primary
  user journey; reports pass/fail + bugs to the **orchestrator**. The orchestrator
  spawns fix agents for each bug; redeploy; re-test. Loop.
- **DONE:** the **happy flow passes end-to-end** in the browser (within the budget
  ceiling).

---

## 4. Memory & context architecture (the core fix)

- **Storage of record:** the GitHub repo (code) + **ruflo memory** (AgentDB) for
  product/decision knowledge + coordination state.
- **Access = pull over MCP.** Each agent gets a tiny **memory-first instruction**
  ("query ruflo for what you need before acting") + the ruflo MCP tools
  (`memory_usage` retrieve/search, `retrieveWithReasoning`) — *not* a fixed
  context dump. Retrieval is hybrid (vector + BM25 + RRF + rerank), scoped by
  **namespace** (`project/<id>`, `run/<id>`, `tickets/<id>`, `coordination`).
- **Reasoning/precedent loop:** each agent's trajectory + outcome is written back
  (ReasoningBank: trajectory→verdict→distill→prune) so later agents query "how was
  this handled" by similarity, with confidence/success counts.
- **Consolidation:** ReasoningBank distills + prunes between phases, so memory
  stays sharp and small instead of an ever-larger blob re-sent every turn.

---

## 5. Agent communication model

Two complementary channels, chosen by agent lifecycle + need. **ruflo's native
coordination is a shared-memory blackboard, not direct messaging** — agents write
`swarm/<agent>/{status,progress,complete}` + `swarm/shared/<component>` to the
`coordination` namespace and **poll dependencies ("retrieve, wait if missing")**;
pre/post hooks auto-sync; a swarm-memory-manager keeps an index + conflict-
resolving manifest; topology (hierarchical/mesh/…) is only the coordination
*shape*. That's durable but laggy for real-time negotiation. So we **add direct
messaging** for the live channel:

- **Direct peer messaging (`claude-peers` MCP)** — synchronous, push,
  conversational. The **live bus**: the **co-design pair** negotiating
  architecture/features ("two agents communicating exactly"), orchestrator↔worker
  "I'm blocked / here's feedback" pings, fix-loop dispatch. Best for the
  **persistent** agents (orchestrator + co-design pair).
- **Shared memory (ruflo AgentDB: `coordination` + project namespaces)** —
  async, durable, queryable. The **system-of-record + handoff + precedent**:
  artifacts, decisions, ticket state, "what's done," dependency status. Survives
  crashes; **ephemeral per-ticket build agents write-and-exit here** (the
  blackboard fits their lifecycle better than registering as a peer).

**Rule of thumb:** *live / "I need you now" / decide-together* → claude-peers;
*durable / async / "what happened"* → shared memory.

- The **orchestrator** is the hub: it spawns agents, holds run state, routes
  Playwright feedback to fix agents (via claude-peers), and is the only actor
  that declares a phase complete.

---

## 6. Cost & safety guardrails (mandatory)

- **Run-level budget ceiling = $100, HARD CUTOFF** (decided, Q7): the orchestrator
  tallies real spend each `/loop` tick and **stops the run** the moment spend hits
  $100 — cutoff, not escalate-and-wait — then reports completed vs pending.
- **Accurate accounting:** read real model token usage (input/cached/output/
  reasoning) per call — never char-count estimates.
- **Loop bounds:** per-ticket/per-phase attempt caps with backoff; a
  blocked-but-not-failed phase is also bounded (last run's gap).
- **No-op = no-op:** an empty agent turn is a retry/escalate signal, not success.
- **Fully autonomous (decided, Q8):** no human approval gates between phases — the
  run goes to *done* (happy flow), *budget cutoff* ($100), or a *hard block*. A
  hard block (missing inputs/authority) **halts that ticket** (recorded, never
  merged-as-done); the run continues with the rest and reports blocks at the end.
- **Reversibility check:** before destructive/outward actions (infra teardown,
  prod deploy), confirm or gate.

---

## 7. Infrastructure & secrets

- **Railway** (backend services + any worker/DB add-ons), **Supabase** (auth +
  Postgres), **Vercel** (frontend) — provisioned via their MCP servers / CLIs in
  Phase 2, deployed in Phase 5.
- **Secrets** flow through one sanctioned store and are injected into the right
  surface; never committed; never hard-coded. (Last run: env not auto-loaded bit
  us — bootstrap must verify each surface has what it needs before running.)
- The repo's CD is wired with `gh` so merges to `main` redeploy.

---

## 8. Skill structure (how this is packaged)

A top-level orchestrator skill that sequences focused sub-skills:

```
software-factory/                  # the central orchestrator skill (this workflow)
  SKILL.md                         # phase state machine + done-gates + budget
  phases/
    00-provision.md                # repo + brain + ruflo + codex bootstrap
    01-research-to-prd.md          # deep-research -> PRD
    02-codesign-architecture.md    # 2-agent arch + features/screens + diagram
    02b-provision-infra.md         # Railway/Supabase/Vercel
    03-tickets.md                  # features x arch -> tickets + DoD
    04-build-swarm.md              # ruflo-spawned build agents, merge-on-green
    05-deploy.md                   # gh CD + provider deploy
    06-test-fix-loop.md            # Playwright -> orchestrator -> fix agents
  guardrails.md                    # budget ceiling, loop caps, no-op, escalation
  memory.md                        # brain-first pull protocol + namespaces
```

Authoring uses `superpowers:writing-skills`; the orchestrator leans on existing
skills (`deep-research`, `use-railway`, Playwright MCP, `session-bridge`).

---

## 9. Definition of done

The run is **done** when the deployed app's **primary happy-flow journey passes
end-to-end in Playwright** and all three surfaces are live. It **stops** at done,
at the **$100 budget cutoff**, or when only hard-blocked tickets remain. Anything
short of a passing happy flow is "in progress / stopped," not done.

---

## 10. Open questions to confirm (please answer / correct)

- **Q1 — Memory:** RESOLVED — **ruflo only** (AgentDB + ReasoningBank over MCP);
  one tool for swarm + memory. GBrain dropped (kept as alt in `agent-memory.md`).
- **Q2 — Ticket store:** GitHub Issues, ruflo's task queue, or Linear?
- **Q3 — Agent channel:** RESOLVED (§5) — **both**: `claude-peers` for live
  direct messaging (orchestrator + co-design pair + fix-loop), shared memory for
  durable handoff/precedent (ephemeral build agents). Confirm this split.
- **Q4 — Build agent runtime:** Claude (ruflo-spawned) for build *and* Codex for
  research, as written? Or unify?
- **Q5 — Orchestrator runtime:** RESOLVED — a **Claude Code session kept alive
  with `/loop`**; run state persists in ruflo memory so each loop re-entry resumes.
  *(Sub-q still open: where does that session physically run — local box or hosted
  runner — so the `/loop` survives a laptop sleeping?)*
- **Q6 — Repo shape:** one repo (backend + frontend together) given the
  Railway/Vercel split, or two?
- **Q7 — Budget:** RESOLVED — **$100 per run, hard cutoff** (stop on hit).
- **Q8 — Autonomy:** RESOLVED — **fully autonomous**, no approval gates.

---

## 11. Suggested first slice (to de-risk before building the whole skill)

Prove the spine on one trivial app: **Phase 0 → 1 → 2 (diagram + infra) → 3 →
one ticket built+deployed → Playwright happy-flow**, with the budget cap and
pull-based brain live from the start. If that holds end-to-end with zero manual
steps and accurate spend, scale the swarm and the fix-loop.
