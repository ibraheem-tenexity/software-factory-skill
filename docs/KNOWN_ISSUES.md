# Known Issues & Unimplemented Work

Open factory issues that are **not yet implemented** — diagnosed, parked, in-flight, or
backlog. Items that have shipped are tracked in git history and the task board, not here.

- **As of:** `main` @ `5a8f757` (2026-06-29)
- **Scope:** the autonomous build pipeline (`src/software_factory`, `console/`, the stage
  SKILLs), not the customer/OS frontends.
- **Legend:** 🔴 blocker · 🟠 reliability/quality · 🟡 low / nice-to-have ·
  ⏸ parked for ibraheem's gate · 🔧 in-flight.

> Convention: numbers in `#NN` refer to internal task-board ids. PR numbers are written
> as `PR #NNN` where they exist.

---

## ⏸ Parked for ibraheem's gate

These are diagnosed (or fully written) and waiting only for a go.

### #127 — Demo credentials are instructed but not *gated* 🔴⏸
**Symptom.** A run whose app has a sign-in can reach `done` and deploy with **no demo
credentials**, leaving the app undemoable. Hit live on `project-67f3711d` (deployed, login
redirect `307 → /login`, but no creds produced).

**Root cause (two defects).**
1. `record-artifact` does **not** verify the file exists at the recorded path. A "Demo
   credentials" artifact row was written while `demo_credentials.md` was never on disk, so
   `demo_credentials()` later returned `None` — a phantom artifact.
2. The done-gate accepts a sign-in-*less* happy-flow. When auth is present the gate is meant
   to require (a) the demo-creds file **and** (b) a Playwright happy-flow that actually signs
   in; it green-lit a post-login flow with no sign-in step. The "seed demo account →
   `demo_credentials.md` → `record-artifact demo-creds` → signed-in happy-flow" instruction
   (`console.py:251`) is conditional and unenforced.

**Fix.**
- `record-artifact` must `stat` the path and fail if the file is absent (no phantom rows).
- When auth is detected, the done-gate hard-requires the demo-creds artifact **and** a
  happy-flow containing a real sign-in step.

**Status.** Fully diagnosed, ready to implement. Highest-value open item — it closes the
"ran but gave me no way in" failure.

### Stage-3 resume-awareness — `PR #168` 🟠⏸  *(addresses #111)*
**Symptom.** Stage-3 re-plans and rebuilds from scratch on every (re)launch instead of
detecting "build already complete" and doing deploy-only. Proven: a stage-3 run rebuilt from
scratch on all 3 launches.

**Root cause.** The stage-3 SKILL has no "assess prior progress on entry" instruction —
Phase 0 always writes `build-plan.md` then re-enters the build loop.

**Fix.** SKILL must, on entry, inspect existing workspace / completed tickets / repo / DB /
deploy state and skip straight to deploy when the build is already done. `PR #168` is the
implementation. **SKILL behavior change** — held because it changes how *every* future build
behaves, so it deserves a read before landing. (Backlog id for the underlying gap: **#111**.)

### OS markdown-editor — `PR #169` 🟡⏸
Smaller operating-system-stage change (the md-editor), from `vr3lprd8`. Held alongside
`PR #168` for one consolidated SKILL/OS gate rather than landing piecemeal.

---

### #129 — Completed Stage-1 wedges when the claude process exits into a zombie 🔴
**Symptom.** A run finishes Stage 1 successfully but never advances — sits idle for hours with
`stage1_done=false`, `phase` stale at `"provision"`, 0 tickets, no Stage 2. Observed on
`project-1bd88040d75846e9`: Stage 1 emitted a clean terminal `result:success`, committed
`PRD.md` (`ff8b6e3`), passed the gate, spent $3.085 — then nothing for ~9h. factory-console
(uvicorn, PID 1) had been up 2d22h with **no restart**, and showed **two zombie
`[claude] <defunct>`** children (the original stage-1 proc + a later failed auto-resume kick).

**Root cause.** `detect_stage1_done()` (`console.py:1493`) only flips when `stage_finished()`
is true. `stage_finished()` (`console.py:351-359`) returns **False** for a `claude` run whose
in-memory handle still reads not-exited — but the stage-1 `claude` had actually **exited into a
zombie** that was never reaped, so the accounting is stuck on "process still running." The #104
watchdog `reap_completed_zombie()` (`console.py:694`) only fires on a **live tracked handle**
and reaps via `_kill_stage_process` — it cannot clear a reparented/defunct zombie, so the wedge
persists indefinitely (the two un-reaped zombies are the proof).

**Relationship to #104/#108.** New variant. #104 assumed a *live, hung* handle (exa remote-MCP
teardown hang); #129 is the *cleanly-exited-into-zombie* case — the process is gone but the
console still blocks the advance and the reaper can't reap it.

**Fix.** Make `stage_finished` zombie-aware: treat a defunct/`Z`-state stage process (or one
whose `project.log` ends in a terminal `result` and is idle past the grace) as finished even
with no live handle, and reap it. Broaden `reap_completed_zombie` to reap reparented zombies,
not only live tracked handles.

**Immediate unwedge.** Stage 1 is genuinely complete (PRD committed) — the run can be advanced
by reaping the zombie / manually launching Stage 2; no rework needed.

---

## 🔧 In-flight

### #105 — Exa MCP teardown hang (root fix) 🟠🔧
**Symptom.** Every claude stage incurs a ~60s hang at exa remote-MCP teardown. The acute
case (stage-1 writing a complete PRD, logging `result`, then hanging on teardown so
`stage_finished` never flipped → permanent stall) is already mitigated by the **#104
watchdog** (reaps the completed-but-hung process). #105 is the *root* fix.

**Fix.** Lazy-connect the exa MCP (open the connection only on the first `web_search`) and
add a teardown/disconnect timeout on the MCP client, so a stage that never searches never
pays the teardown cost and one that does can't block on it.

**Status.** In progress. Watchdog (#104) is the live safety net until this lands.

### #107 — LLM provider keys misclassified as "mock" 🔴🔧
**Symptom.** `OPENROUTER_API_KEY` (and similar provider keys) are classified as "mock" by
`deps.classify_dep`, auto-satisfied with **no real key**, and the operator is never asked —
so the deployed app's core AI feature is **dead on arrival**.

**Fix.**
- Classify LLM/provider keys as **Tenexity-platform-provided** (inject a real key onto the
  app service) **or** as a "provide" dep that **pauses for the operator** — never silently
  mock.
- Surface per-dep disposition in the UI (e.g. `DB: factory-provisioned` /
  `OPENROUTER: mocked ⚠️`) so the operator can see what's real before launch.

**Status.** In progress.

### #97 — GitHub-repo reaper arming 🟠🔧
**Symptom.** The factory creates orphan GitHub repos; the reaper service exists but is not
yet armed in prod.

**Plan.** Dry-run → ibraheem approves the kill-list → flip `SF_GITHUB_REPO_REAPER` on. The
arming is deliberately gated on a human-approved kill-list (don't delete what you didn't
create / contradicts the description).

**Status.** In progress, awaiting the dry-run review + flag flip. Depends on / pairs with #95.

---

### #128 — Dashboard status pill shows "Building" for stopped/crashed/paused runs 🟠
**Symptom.** A single project card shows contradictory states at once — e.g. a blue
**"Building"** pill next to the text **"stopped"** (observed on `project-67f3711d`, which is
stopped, `done=false`, `deploy_url=null`).

**Root cause.** `statusOf()` in `console/web/src/components/Dashboard.tsx:16-22` has no branch
for `phase` of `stopped` / `crashed` / `paused`; those fall through to the default
`return … "Building"`. The card separately renders the raw `phase` text, so the two
derivations disagree on the same card. State derivation is **duplicated**: the project detail
view (`FactoryConsole.tsx:35-37`) maps `stopped/crashed→danger`, `paused→warning`, `done→success`
correctly — the dashboard card was never updated to match. (Dashboard-card sibling of #106,
which fixed the detail view's label lag.)

**Fix.** Add `stopped` / `crashed` / `paused` cases to `statusOf()` (mirror `FactoryConsole`'s
`tone()`), so a halted run reads "Stopped"/"Crashed"/"Paused" instead of "Building". Consider
extracting one shared status-derivation helper used by both surfaces to stop the drift
recurring. FE-only; no backend change.

> Note: the underlying "this run isn't actually `done`" is **#127** — it deployed but was
> stopped before the done-gate flipped (no demo creds). #128 is only the badge mislabel.

---

## 🟡 Backlog (low priority)

### #87 — `/api/version` + re-assert `railway link` before verify
**Symptom.** Link-drift produces false-negative verifies (the verify runs against the wrong
linked project/SHA).

**Fix.** Add a `/api/version` endpoint exposing the running git SHA, and re-assert
`railway link` before verification so a drifted link can't silently invalidate a check.

### #95 — Harden the repo-reaper with an exact-name handle
**Symptom.** The reaper matches orphan repos heuristically, which is fuzzy.

**Fix.** Record the **exact** repo name at Stage-3 creation so the reaper matches the precise
handle instead of pattern-guessing. Pairs with #97 (makes the kill-list unambiguous).

---

## Cross-cutting notes / latent risks

- **Migrations.** Baseline is `create_all`; every backend schema change needs an idempotent
  incremental migration + a rehearsed prod-upgrade path. No schema change is "free."
- **Connection budget.** Direct `_pg_connect` callers must route through the #120 pool;
  the pooler ceiling is 200 (Supabase 6543 transaction pooler). The #126 leak fix is in, but
  any *new* direct connector reintroduces the EMAXCONN risk — see `vault.py`, `blobs.py`,
  `agent_prompts.py` for the call sites that historically bypassed the pool.
- **Root launcher.** factory-console runs as root and `claude` ≥ v2.1.195 refuses
  `--dangerously-skip-permissions` as root (fixed by dropping to the `node` user, #125).
  The claude-code binary version is pinned in the Dockerfile so a silent bump can't
  reintroduce the breaking flag change — **keep the pin**.
- **Deploy-DB move + exa wiring (#100) — shipped, watch the regression.** The plan at
  `~/.claude/plans/precious-roaming-kazoo.md` (move deploy-DB provisioning into the stage-3
  agent + broaden Railway-MCP latitude + wire exa web-search into all stages) corresponds to
  **#100, which has landed.** Its one known fallout is the exa stage-1 teardown stall —
  mitigated by the #104 watchdog and getting its root fix in **#105 (in-flight, above)**.
  Any broader research-decentralization beyond #100 was explicitly out of scope and is not
  started.
