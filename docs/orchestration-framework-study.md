# Orchestration framework study (SOF-104 / C1)

Nick's Priority #2 (2026-06-26 meeting): a deep-research pass over three competing
orchestration frameworks — Sakana (Fugu), Paperclip, Hermes — extracting principles worth
adopting, delivered as concrete proposals against **this repo**, not a reading report.

**Identification caveat (per pozly3ga, operator confirmation pending):** the three names were
given informally in a meeting; I identified the most plausible match for each via web research
and marked every finding below with what was actually verified vs. inferred. If Nick meant a
different product under one of these names, the *patterns* below (atomic checkout, liveness
contracts, bounded revision loops, silent-run watchdogs, declarative data-flow) still hold as
real, evidence-grounded engineering ideas — the proposals don't depend on getting the exact
product match right, only on the mechanism being real and comparable to our own code.

- **Sakana Fugu** — identified as [Sakana AI's Fugu](https://sakana.ai/fugu-release/) /
  Fugu-Ultra, a multi-agent-orchestration-as-a-single-model system (arXiv 2606.21228).
- **Paperclip** — identified as [paperclipai/paperclip](https://github.com/paperclipai/paperclip),
  an open-source "company of AI agents" control plane.
- **Hermes** — identified as the OpenCode-AI 17-specialized-agent variant
  ([1ilkhamov/opencode-hermes-multiagent](https://github.com/1ilkhamov/opencode-hermes-multiagent)),
  not the NousResearch Hermes LLM series or the separate "hermes-agent.ai" product (a same-named
  but distinct product that may be the source of a "parallel execution" claim I could not verify
  against the repo I settled on — flagged, not asserted, below).

---

## 1. Sakana Fugu — architecture & orchestration model

**What it is:** a single language model *trained* (via RL, arXiv 2606.21228) to itself decide
whether to answer a query directly or design a multi-step "agentic workflow" that delegates
subtasks to a pool of frontier worker models, then synthesizes their outputs — all behind one
OpenAI-compatible API call. It is explicitly positioned against hand-wired graphs (LangGraph,
CrewAI, AutoGen) where a human defines nodes/edges/state up front.

**Concrete mechanisms verified from the paper:**

- **Delegation decision**: a lightweight prediction head reads the model's hidden state at early
  token positions and scores which worker model(s) to route to — a cheap classification, not a
  full autoregressive decision. Fugu-Ultra additionally *learns* (via RL, not a hand-written
  rule) to design a workflow of "up to 5 steps" per query.
- **"Verification"**: **not a runtime pre-synthesis gate** (correcting my own initial hypothesis
  before research) — it's a *training-time* reward signal: each Conductor response is scored 1
  if its final output matches the known solution, 0 otherwise. At inference time there is no
  separate verify-then-synthesize step; the model just executes the workflow it designed.
- **Synthesis**: each workflow step is a tuple of `(natural-language subtask, assigned worker id,
  access list)` — the *access list* explicitly indexes which prior steps' outputs that worker
  receives as context. This is fully **declarative, per-query, and dynamically generated** — it
  enables best-of-N, sequential chains, and arbitrary parallelizable tree topologies purely by
  varying the access-list wiring, with no fixed schema.

**What this tells us, honestly:** Fugu's headline claim ("hides orchestration behind one API
call") doesn't map cleanly onto a multi-stage build pipeline like ours — we're not trying to
collapse research→design→build→deploy into one model call. The one concretely portable idea is
the **access list**: explicit, per-step declaration of which upstream outputs a downstream
consumer reads, instead of ambient/implicit data-passing.

---

## 2. Paperclip — architecture & orchestration model

**What it is:** an MIT-licensed, Node.js+React "operational control plane" for teams of AI
agents — org charts, budgets, governance, audit logs. Verified via `doc/execution-semantics.md`
in the actual repo (not marketing copy) — this is the single richest, most directly comparable
source of the three.

**Concrete mechanisms verified from the repo's execution-semantics doc:**

- **Checkout vs. execution identity are separate fields.** `checkoutRunId` answers "who currently
  owns execution rights for this issue"; `executionRunId` answers "which run is actually live
  right now." A run owns `checkoutRunId` only while non-terminal; on finalization the lock
  columns must be **compare-and-cleared** (only cleared if they still point at the finishing
  run — never blindly overwritten), and finalization must never clear a lock already reacquired
  by a successor run. Stale locks (pointing at terminal/missing runs) are **self-healing** — a
  later checkout attempt can adopt them. A `409` on checkout means a *real* live owner or an
  active gate — agents must treat it as a stop signal, never a retry-the-same-checkout signal.
- **Non-terminal liveness contract.** For every agent-owned, non-terminal unit of work, *something*
  must always be responsible for the next move: an active run, a queued wake, a one-shot monitor,
  a human owner, a first-class blocker chain, or an open, named recovery action. The doc is
  explicit that an unmanaged local process (a PID, a `nohup`, a detached watcher) is **not** a
  valid liveness path — "the process may be killed when the adapter invocation or heartbeat exits
  and cannot be assumed observable or recoverable by another worker."
- **Three-tier recovery, not two.** (1) **Auto-Recover** — a bounded, ownership-preserving retry
  (requeue one dispatch/continuation wake) when the control plane merely lost execution
  continuity. (2) **Explicit Recovery Action** — a first-class, *named* object opened when
  auto-retry is exhausted or the situation is ambiguous: it must name the source issue, the
  recovery kind + idempotency fingerprint, the recovery owner, the cause + evidence, and the
  wake/monitor/timeout/escalation policy that moves it forward — plus its eventual resolution
  outcome (restored / delegated / false positive / blocked / escalated / cancelled). (3) **Human
  Escalation** — only when the next safe action needs board/budget/policy judgment.
- **Silent active-run watchdog.** A `running` process can still be unhealthy. Output silence is
  classified `ok` / `suspicious` / `critical` / `snoozed` / `not_applicable` — critical silence
  raises a high-priority recovery action **without cancelling the active process**; `snooze`
  records an explicit future quiet-until window; `continue` re-arms a 30-minute re-check rather
  than either killing the process or declaring it healthy forever.
- **Startup/periodic reconciliation is a fixed 5-step sequence**: reap orphaned running runs →
  resume persisted queued runs → reconcile stranded assigned work → scan silent active runs →
  reconcile productivity reviews. Every step is separately named and separately owned.

**What this tells us:** this is the most structurally mature of the three, and — because it's an
operational control plane for exactly the same *shape* of problem we have (long-running,
crash-prone, budget-bounded agent work) — nearly every mechanism above has a direct, nameable
counterpart (or gap) in our own poller/console/tickets code. See §5.

---

## 3. Hermes (OpenCode 17-agent variant) — architecture & orchestration model

**What it is:** a prompt-defined orchestrator (`agent/core/hermes.md`) that classifies an
incoming request, selects a fixed pipeline of specialized subagents by keyword/category rule
(not learned), and enforces **mandatory** quality gates rather than leaving them to agent
judgment.

**Concrete mechanisms verified from the actual orchestrator prompt file:**

- **Rule-based dispatch, not judgment-based.** Trigger rules are literal keyword/category tables
  (e.g. "`@security` is MANDATORY when any of: auth, login, password, token, session, cookie,
  jwt, oauth, api key, secret, encrypt... appears, OR the affected files match a security-ish
  path"). Standard pipelines are named sequences (`New Feature`: finder → analyst → architect →
  planner → coder → reviewer → tester → documenter).
- **Mandatory quality-gate chain with a bounded revision loop.** "After @coder/@editor/@fixer:
  → @reviewer (ALWAYS) → @tester (ALWAYS). Cannot complete task without them." On
  `NEEDS_REVISION`: bounce back to the implementer, re-review, **max 3 iterations**, then
  escalate to the user. `@security` returning FAIL **stops the pipeline immediately** — no bounce
  loop at all for security findings.
- **Context passing is one cumulative object**, explicitly documented: "Full context flows
  between all agents" — every subagent receives `original_request`, its `category`, and the
  **full accumulated results of every previous agent** in a single structured object (research /
  planning / implementation / quality / documentation / infrastructure sub-keys). This is a real,
  working example of the "shared context" end of C2's spectrum — not a configurable choice
  between shared and isolated (this repo only implements the shared-context design; I could not
  verify an isolated-context option anywhere in the actual source, only in an unrelated marketing
  snippet for a *different*, similarly-named product — flagging rather than asserting it).
- **Per-subagent timeout, bounded, with an explicit degrade path.** ">5 min no response → retry
  once with the same prompt → if still failing: log it, tell the user, **continue the pipeline
  without this agent**, mark the task 'incomplete — manual review needed.'" This is a clean,
  bounded skip-and-continue pattern at the *individual subagent* level, not the whole-pipeline
  level.
- **Explicit validation checklist before "done."** A literal checkbox list ("was @finder called
  first? if code changed, did @reviewer/@tester return PASS? if security-related, did @security
  run AFTER @reviewer and PASS?") — "if ANY checkbox is NO → call the missing agent. Do not
  complete." This is a rule-enforced completeness gate, not an agent self-assessment.

**What this tells us:** Hermes is the closest of the three to *pure prompt-level orchestration*
(a system prompt with rules, not a state machine) — which resonates with this repo's own
Minimum Machinery philosophy (§1: "if a behavior can live in a system prompt, it lives in the
system prompt"). The genuinely new idea for us is the **bounded per-subagent timeout with a
skip-and-continue degrade**, which nothing in our stage-2/3 pipeline currently does at that
granularity (see §5, gap F).

---

## 4. Feeds SOF-105 (C2 — sub-agent communication topology)

C2 asks: shared context / mutual awareness between sub-agents, vs. communicating only back to
the orchestrator. The two frameworks that actually implement a topology land on opposite,
internally-consistent designs:

- **Hermes = always-shared, cumulative context object.** Every subagent sees everything every
  prior subagent produced. Simple to reason about, but the context object grows unboundedly
  across a long pipeline (their own schema shows 6 top-level sub-objects each with multiple
  nested agent results) — there is no visible mechanism limiting what a downstream agent
  actually *needs* to see vs. what it's handed.
- **Fugu = declarative, per-step, orchestrator-mediated access lists.** No subagent sees
  "everything" — each step explicitly names which prior steps' outputs it may read. This is
  strictly more information-hygienic (no accidental leakage of irrelevant context, easier to
  reason about token cost) but requires the orchestrator (or, in Fugu's case, the trained
  routing head) to correctly declare the right access list for every step.

**Our own current position** (from the grounding survey, §5 below) is closer to Fugu's model
*by accident of implementation* rather than by deliberate design: Stage 1→2→3 pass data through
committed files/artifacts in a shared workspace directory, which is technically "shared" (any
stage *could* read any prior artifact) but is consumed selectively in practice (each stage's
SKILL.md tells it which specific files to read) — i.e. an **implicit, convention-based access
list**, not an enforced one. Recommendation for the ADR: don't adopt Hermes's fully-cumulative
model (it doesn't obviously buy us anything our file-based approach doesn't already have, and it
would grow an ever-larger context blob across a 3-stage pipeline that already fights token
budgets); instead **make the existing implicit access-list explicit** — each stage's SKILL.md
already effectively declares "read these artifacts," so the ADR's job is to decide whether that
declaration should become a real, checked manifest (Proposal 5 below) rather than convention
enforced only by prompt text.

---

## 5. Grounding: what we actually have today

(Full file:line citations in the working notes; summarized here for the proposals below.)

| Pattern | External framework | Our code | Gap |
|---|---|---|---|
| Atomic checkout / CAS lock | Paperclip `checkoutRunId`/`executionRunId` | `console.py`'s `self._procs: dict` (in-process only, `console.py:263`) + `_stage_process_alive`/`_launch_stage` TOCTOU-aware but **not persisted**, no CAS, no self-heal across a console restart | **Gap** |
| Ticket claim is atomic | Paperclip checkout semantics | `TicketStore.claim` (`tickets.py:173-179`) does a separate SELECT then an UPDATE with **no status predicate in the WHERE clause** (`repositories/tickets.py:36-38`) — safe only because dispatch is currently single-actor-per-ticket by convention | **Gap** |
| Non-terminal liveness contract | Paperclip §8 | An *ensemble* of independent one-shot/bounded checks in `poller.py`'s tick loop (health, reaper, auto-advance, budget, auto-resume, narrate), each wrapped in its own bare `except: pass` — no single invariant that guarantees every non-terminal project has *some* owner for its next move | **Partial gap** |
| 3-tier recovery (auto → named recovery action → human) | Paperclip §13 | We have tier 1 (`auto_resume_dead_stage`, bounded by `SF_AUTO_RESUME_MAX`) and tier 3 (`mark_stage_crashed` → Recovery-bar UI + email, or SOF-93's Linear filing for benchmark runs) — **no tier 2**: recovery is a `phase` string, not a named/owned/policy-bearing object | **Gap** |
| Silent-but-not-crashed classification | Paperclip watchdog (ok/suspicious/critical/snoozed) | `console.stage_finished` (`console.py:296-324`) collapses "quiet" straight into a **binary** finished/not-finished via mtime staleness (120s/300s thresholds) — patched twice already for real incidents (run-45b8c4d5, run-5b7aef7a) that a graded classification could have surfaced earlier. `run_autopsy.py` DOES have a stall/timeout split (`TIMEOUT_HOURS=6.0`, `STALL_HOURS=1.0`) but only for benchmark-owned runs via an external cron script, not production | **Gap in production poller** |
| Per-subagent bounded timeout → skip | Hermes error handling | **Nothing found** at the individual-Task-subagent level in Stage 2/3 — only whole-stage-process kill (`_kill_stage_process`, 5s SIGTERM grace) or whole-swarm-wave settle-grace (120s) | **Gap** |
| Mandatory quality-gate chain, bounded revision loop | Hermes §4/§6 | SOF-119's REVIEW agent (`tickets.py:248-278`, `review_reject`) — **this one we already have**, and it's genuinely bounded (`SF_REVIEW_BOUNCE_MAX`, default 2) with an escalation path (stays `deployed`, forces `add-blocker`) | **No gap — validates the pattern** |
| Declarative per-step access list | Fugu | Stage1→2→3 pass data via committed workspace files, read per SKILL.md *convention*, not an enforced/declared manifest | **Soft gap (hygiene, not correctness)** |

---

## 6. Proposals

Each proposal: what to adopt + why, the evidence that motivates it, a diff sketch against the
real file, size (S/M/L), and its expected effect on the benchmark harness's own scores (SOF-92's
`classify_run` terminal states: `DEPLOYED` / `BUDGET_STOPPED` / `CRASHED` / `BLOCKED` / `TIMEOUT`
/ `UNKNOWN`).

### Proposal 1 — Persist the stage-launch claim as a durable, self-healing lock [M]

**Adopt from:** Paperclip's `checkoutRunId`/`executionRunId` separation + compare-and-clear
finalization + self-healing stale locks.

**Why:** `console.py`'s double-orchestrator guard is an **in-process dict** (`self._procs`). Its
own docstring at `console.py:989-997` already documents the residual TOCTOU window it can't
close, and — more importantly — a console **restart** wipes `self._procs` entirely, so a
genuinely-still-running orphaned process from before the restart is silently treated as "not
alive." I hit the exact same *class* of bug personally on SOF-92 this week: a killed local
harness process left its already-launched server-side run going unnoticed, burning ~$25
unattended, because nothing outside my own process's memory recorded "this run is claimed." This
generalizes past my one harness — it's a property of `_procs` itself.

**Diff sketch** (`src/software_factory/projectstate.py` + `console.py`):
```python
# projectstate.py — new persisted fields (mirrors deploy_db_service_id's own pattern)
launch_run_token: str = ""      # opaque uuid4, set atomically at launch
launch_run_pid: int = 0         # OS pid, for staleness self-heal after a restart

# console.py — _launch_stage, replacing the in-process-only check
def _launch_stage(self, project_id, stage, prompt, env):
    state = self._load_state(project_id)
    if state.launch_run_token and self._launch_token_alive(state):
        return None  # real conflict — a live claim exists, do not retry blindly
    token = uuid.uuid4().hex
    state.launch_run_token, state.launch_run_pid = token, os.getpid()  # placeholder; real pid set post-Popen
    state.save()
    proc = self._popen(...)
    state.launch_run_pid = proc.pid
    state.save()
    ...

def _launch_token_alive(self, state) -> bool:
    # self-heal: pid not running (or belongs to a different, unrelated process — PID reuse) -> stale
    return state.launch_run_pid and _pid_belongs_to_us(state.launch_run_pid)
```
The key behavior change: `_stage_process_alive` currently answers from `self._procs` (memory);
after this change it answers from `ProjectState` (disk/DB), so a fresh console process can
correctly self-heal a stale lock from a dead PID instead of defaulting to "not alive" (today) or
"alive forever" (the naive fix).

**Expected effect on benchmark scores:** directly reduces `UNKNOWN`/orphaned-spend incidents —
the failure mode this closes is exactly "a run keeps burning budget/creating resources that
nothing is tracking," which either shows up as a phantom `BUDGET_STOPPED` far later than
expected, or (worse) doesn't show up in `classify_run` at all because nothing ever re-observes
the orphaned process. Should reduce variance in cost-per-run and eliminate double-launch-driven
budget burn entirely (the SOF-92 lesson, generalized).

---

### Proposal 2 — Compare-and-swap the ticket claim, don't read-check-then-write [S]

**Adopt from:** Paperclip's atomic-checkout requirement ("task checkout and budget enforcement
are atomic, so no double-work").

**Why:** `TicketStore.claim` (`tickets.py:173-179`) calls `_require` (a SELECT) and then
`_repo.update` (`repositories/tickets.py:36-38`) — and that `update()`'s WHERE clause has **no
status predicate at all**. Two concurrent `claim()` calls on the same ticket would both pass the
SELECT-time check and both blindly overwrite `status`/`agent` — last writer wins, silently, no
error. Today this is safe only because dispatch is single-actor-per-ticket by *convention*
(stage-3's claude-native orchestrator claims sequentially; the swarm driver assigns one ticket
per spawned agent) — not because the data layer enforces it. That convention is exactly the kind
of implicit invariant that broke once already this project (SOF-92's own concurrency bug was the
identical shape: "nothing enforced it, so it eventually didn't hold").

**Diff sketch** (`src/software_factory/repositories/tickets.py`):
```python
def claim_atomic(self, ticket_id: int, agent: str, allowed: tuple) -> bool:
    """CAS: only succeeds if status is still one of `allowed` at write time. Returns False
    (not an exception) on a lost race — the caller treats False as 'already claimed', a
    Paperclip-style 409, not a retry-the-same-claim signal."""
    stmt = (update(tickets)
            .where(tickets.c.id == ticket_id, self._scoped(), tickets.c.status.in_(allowed))
            .values(status="in_progress", agent=agent))
    return self._x.execute(stmt).rowcount == 1
```
`TicketStore.claim` calls `claim_atomic` instead of `_require`+`update`; on `False`, raises the
existing `IllegalTransition` (same external contract, now actually race-safe instead of
race-shaped-safe-by-convention).

**Expected effect on benchmark scores:** low direct effect on the benchmark harness itself
(single-actor today), but closes a real latent bug ahead of any future multi-orchestrator or
higher-parallelism swarm mode — cheap insurance sized to match its current low urgency.

---

### Proposal 3 — Bounded per-subagent timeout → retry-once → skip-and-continue [M]

**Adopt from:** Hermes's per-subagent timeout handling (">5 min no response → retry once →
skip, mark incomplete, keep the pipeline moving").

**Why:** confirmed via the codebase survey (gap F) that **nothing** in Stage 2/3 bounds an
individual spawned Task subagent's runtime — only the whole stage process (`_kill_stage_process`,
a 5s SIGTERM grace) or the whole swarm wave (120s settle-grace) are bounded. A single stuck
ticket-agent inside a wave is currently invisible until the *entire stage* is judged dead by
`auto_resume_dead_stage`/`crashed_at_node` — an expensive, coarse-grained failure mode. I proved
the value of exactly this pattern this week, one level up: SOF-92's harness now self-terminates
a hang via an internal alarm rather than relying on an external kill, specifically because an
external kill runs no cleanup code (`scripts/benchmark_harness.py`'s `HarnessTimeout`/`SIGALRM`).
The same reasoning applies one level down, per-ticket.

**Diff sketch** (`skills/stage-3-build/SKILL.md`'s per-ticket claim loop, host-enforced not
prompt-enforced since a stuck subagent can't self-report):
```python
# console.py or the stage-3 dispatch helper, wrapping the per-ticket Task call
def dispatch_ticket_with_timeout(ticket, agent_fn, timeout_s=300):
    start = time.time()
    result = agent_fn(ticket)  # today: unconditional, unbounded
    # proposed: run under a bounded watch (subprocess.run(..., timeout=) for the native-Task
    # path, or a monitor thread comparing last-heartbeat-ts for the swarm path)
    if timed_out:
        TicketStore(...).add_note(ticket.id, "subagent timeout after {timeout_s}s — skipped, "
                                             "ticket left `in_progress` for manual pickup")
        return SKIPPED  # the wave continues with the remaining tickets, not a whole-stage crash
```
The key product decision this proposal forces: what does "skip" mean for a *ticket* (unlike
Hermes's disposable subagent call)? Recommendation: leave the ticket `in_progress` with a visible
note (not silently reverted to `open`, which would look like nothing happened) and let the
existing wave-boundary QA/review gate surface it as incomplete, rather than inventing a new
status.

**Expected effect on benchmark scores:** should reduce the frequency of whole-stage
`auto_resume_dead_stage`/`CRASHED` classifications caused by a single stuck ticket dragging down
an entire wave — converting some fraction of today's `CRASHED` outcomes into `DEPLOYED` (the
wave finishes minus one skipped ticket) or a more honest, smaller-blast-radius `BLOCKED`.

---

### Proposal 4 — Three-state silent-run classification in the production poller [M]

**Adopt from:** Paperclip's `ok`/`suspicious`/`critical`/`snoozed` output-silence classification,
which creates review work **without killing the process**.

**Why:** `console.stage_finished` (`console.py:296-324`) is binary — quiet collapses straight
into "finished," gated only by an mtime staleness threshold (120s/300s) plus an opencode-specific
session-terminal check. Its own comments cite two real incidents this exact logic has already
been patched around (`run-45b8c4d5`: a lingering opencode zombie process wedged auto-resume;
`run-5b7aef7a`: a live swarm pid quiet mid-Kimi-turn was nearly misjudged as finished). Both were
fixed reactively, per-incident, by adding more special-case branches to a binary check — exactly
the kind of accreting-special-cases problem a proper graded classification avoids. `run_autopsy.py`
already has the right *shape* of fix (`TIMEOUT_HOURS`/`STALL_HOURS` sub-classification) but it's
scoped to benchmark-owned runs only, run by an external cron script, not the production poller.

**Diff sketch** (`console/poller.py`, new tick alongside the existing reaper ticks):
```python
def _silence_tick(pid: str, console) -> str:
    """ok | suspicious | critical — never kills the process, only classifies it."""
    idle_s = time.time() - os.path.getmtime(log_path(pid))
    if idle_s < 180:
        return "ok"
    if idle_s < 900:
        return "suspicious"   # narrate once, no action
    return "critical"          # open a Recovery Action (Proposal 5) if not already open;
                                # still does NOT touch the live process
```
Wired into `_poll_transitions`'s per-project loop alongside `reap_completed_zombie`/
`enforce_budget`, but deliberately **inert** by default — it narrates/records, it does not kill
or relaunch. That's the whole point: today, every existing check that notices "quiet" is also the
check that decides to act (finish, kill, resume). This proposal separates *noticing* from
*acting*, matching Paperclip's design.

**Expected effect on benchmark scores:** primarily an *observability* improvement rather than a
score-mover per se — its measurable effect is fewer future incidents shaped like
run-45b8c4d5/run-5b7aef7a (both of which cost real debugging time, not benchmark dollars, but
both were the kind of thing that would show up as an inexplicable `CRASHED` or a wedged
`UNKNOWN` in a benchmark run if it happened to a scheduled run instead of an attended one).

---

### Proposal 5 — First-class Recovery Action entity (the missing middle tier) [L]

**Adopt from:** Paperclip's 3-tier recovery model's middle tier — a **named, owned,
policy-bearing** recovery object, distinct from both the bounded auto-retry and the terminal
human-escalation ticket.

**Why:** we already have tier 1 (`auto_resume_dead_stage`, bounded by `SF_AUTO_RESUME_MAX`) and
tier 3 (`mark_stage_crashed` → the Recovery-bar UI + email; or, for benchmark runs specifically,
SOF-93's `autopsy_and_file` → a Linear ticket). There is **no tier 2** — nothing in between is a
first-class entity with its own recovery-kind, owner, evidence, and resolution-outcome fields;
recovery today is a `phase` string (`"crashed"`, `"paused"`) plus whatever ad hoc mechanism
happens to consume that phase (a UI affordance for attended runs, a cron-filed Linear ticket for
benchmark runs — two different, unrelated mechanisms for what is conceptually the same event).
This is the deepest, most structural of the five proposals, and the one most likely to actually
unify SOF-93's benchmark-only autopsy pipeline with the production Recovery-bar into one real
primitive instead of two parallel ad hoc ones.

**Diff sketch** (new table + a thin service, not a new subsystem — Minimum Machinery: this is
the pipeline lifecycle's own money/reliability surface, exactly the class of thing CLAUDE.md
says machinery IS correct for):
```python
# migrations/versions/00XX_recovery_actions.py
recovery_actions = Table(
    "recovery_actions", metadata,
    Column("id", ...), Column("project_id", ...),
    Column("kind", Text),            # "dead_stage" | "silent_run" | "budget_exhausted" | ...
    Column("owner", Text),            # operator email, or "auto" while auto-recover is trying
    Column("cause", Text), Column("evidence", JSONB),
    Column("opened_at", ...), Column("resolved_at", nullable=True),
    Column("resolution", Text, nullable=True),  # restored|delegated|false_positive|blocked|escalated|cancelled
)

# console.py — replaces the ad hoc phase="crashed" + separate benchmark-only Linear filing
def open_recovery_action(self, project_id, kind, cause, evidence) -> int:
    """Idempotent per (project_id, kind) while unresolved — mirrors Paperclip's fingerprint
    rule so a repeated same-cause signal comments on the existing action instead of duplicating."""
    ...

def resolve_recovery_action(self, action_id, resolution: str) -> None:
    ...
```
`mark_stage_crashed` becomes a caller of `open_recovery_action(kind="dead_stage", ...)`; SOF-93's
`autopsy_and_file` becomes a **second caller of the same primitive** instead of its own parallel
Linear-filing pipeline (Linear filing itself can stay as one *resolution channel* a recovery
action may trigger, not the whole mechanism). The Recovery-bar UI reads `recovery_actions` instead
of just `phase`.

**Expected effect on benchmark scores:** the biggest structural win of the five, but indirect —
it doesn't change any individual run's classification, it changes whether the *same* underlying
signal (a dead stage, a budget exhaustion, a silent run) gets handled identically whether the run
is an attended customer run or an unattended benchmark run. Concretely: SOF-93's benchmark-only
autopsy dedup/filing logic (`RunAutopsyStore`, signature-based dedup) already does almost exactly
this for benchmark runs alone — this proposal is "stop maintaining two of these," which reduces
future maintenance burden more than it moves any one benchmark score.

---

## 7. Summary

| # | Proposal | Size | Primary evidence |
|---|---|---|---|
| 1 | Durable, self-healing stage-launch lock | M | SOF-92's own $25 orphan-run lesson, generalized past one harness |
| 2 | CAS ticket claim | S | Read-check-then-write race, currently safe by convention only |
| 3 | Per-subagent bounded timeout → skip | M | SOF-92's SIGALRM pattern, one level down; no per-subagent bound exists today |
| 4 | 3-state silent-run classification (production poller) | M | run-45b8c4d5, run-5b7aef7a — both real, both patched reactively into a binary check |
| 5 | First-class Recovery Action entity | L | SOF-93's benchmark-only autopsy pipeline duplicates what production's Recovery-bar does ad hoc |

Each is sized to become its own ticket on approval, per the AC. Proposal 5 is the one worth
sequencing last (it partially subsumes / cleanly hosts the outcome of 1 and 4 as recovery-action
*kinds*, so building it after 1 and 4 exist gives it real content to unify from day one rather
than a speculative schema).

**Feeds SOF-105 (C2):** §4 above — recommend making the pipeline's existing implicit,
convention-based file-passing into an explicit, checked manifest (a soft extension of Proposal
5's evidence-oriented posture) rather than adopting Hermes's fully-cumulative shared-context
object, which doesn't obviously solve a problem we have and would grow unboundedly across a
3-stage pipeline already budget-constrained.
