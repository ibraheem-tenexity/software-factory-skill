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

### #129 — Completed Stage-1 wedges when the claude process exits into a zombie 🟢✅
**Symptom.** A run finishes Stage 1 successfully but never advances — sits idle for hours with
`stage1_done=false`, `phase` stale at `"provision"`, 0 tickets, no Stage 2. Observed on
`project-1bd88040d75846e9`: Stage 1 emitted a clean terminal `result:success`, committed
`PRD.md` (`ff8b6e3`), passed the gate, spent $3.085 — then nothing for ~9h. factory-console
(uvicorn, PID 1) had been up 2d22h with **no restart**, and showed **two zombie
`[claude] <defunct>`** children (the original stage-1 proc + a later failed auto-resume kick).

**Root cause.** `detect_stage1_done()` only flips when `stage_finished()` is true.
`stage_finished()` returns **False** for a `claude` run whose in-memory handle still reads
not-exited — but the stage-1 `claude` had actually **exited into a zombie** that was never
reaped, so the accounting is stuck on "process still running." `p.poll()` was observed to
persistently report "not exited" for hours for a process `ps` independently showed as
`<defunct>` — a stuck/stale Popen handle can't be the only signal.

**Relationship to #104/#108.** New variant. #104 assumed a *live, hung* handle (exa remote-MCP
teardown hang, fixable by SIGTERM→SIGKILL); #129 is the *cleanly-exited-into-zombie* case — the
process is already dead, no kill needed, it just needs an OS-level check + a real reap.

**Fix.** Added `_proc_state(pid)` — reads `/proc/{pid}/stat`'s state char directly ('Z' = zombie,
`None` = pid already fully gone) as an independent, OS-level signal alongside `Popen.poll()`.
New `Console._reap_if_os_zombie(p)` cross-checks it whenever `poll()` says "still running" and,
if the OS disagrees, reaps via the real `Popen.wait()` (not a raw `os.waitpid` — keeps that same
object's internal bookkeeping consistent for every other caller that later calls `.poll()`/`.wait()`
on it). Wired into both `stage_finished()` and `_stage_process_alive()` so the fix also protects
the "never two stage orchestrators" guard on `start_stage2`/`start_stage3`, not just the
detect_stageN_done path. Left `reap_completed_zombie` (#104) unchanged — it's a genuinely
different mechanism (kill a still-alive-but-hung process) for a different symptom; this fix
reaps an already-dead one, no kill required.

**Immediate unwedge (historical).** Stage 1 was genuinely complete (PRD committed) — the run
was advanced by reaping the zombie / manually launching Stage 2; no rework needed. Going
forward, `stage_finished` self-heals this within one poller tick (~3s) instead of needing a
manual unwedge.

---

## 🔧 In-flight

### #105 — Exa MCP teardown hang (shrink the reap grace) 🟢✅
**Symptom.** Every claude stage incurs a ~60s hang at exa remote-MCP teardown. The acute
case (stage-1 writing a complete PRD, logging `result`, then hanging on teardown so
`stage_finished` never flipped → permanent stall) is already mitigated by the **#104
watchdog** (reaps the completed-but-hung process).

**Investigated, not achievable as originally framed.** The original fix idea — lazy-connect
exa (open the connection only on the first `web_search`) and/or a teardown/disconnect timeout
on the MCP client — turns out to require capabilities Claude Code CLI doesn't expose. Confirmed
against upstream: Claude Code eagerly connects every configured MCP server at session start
regardless of use (lazy-connect is an open, unimplemented feature request,
[anthropics/claude-code#31198](https://github.com/anthropics/claude-code/issues/31198)), and
there is no config/env var bounding exit-time MCP teardown — `MCP_TIMEOUT`/`MCP_TOOL_TIMEOUT`
cover startup-connect and per-tool-call timeouts only ([#1935](https://github.com/anthropics/claude-code/issues/1935),
[#41024](https://github.com/anthropics/claude-code/issues/41024) track the unbounded-teardown gap
itself). Also checked: dropping exa from stages 2/3's `.mcp.json` (config-gating it to stage 1
only) was considered, but `skills/stage-{1,2,3}-build|design|research/SKILL.md` all carry the
identical "use exa whenever live web results help" line — there's no SKILL-level signal that
any one stage is exa-free, so narrowing the wiring would be guessing, not evidence, and would
reverse #100's deliberate "every stage gets exa" decision.

**Fix shipped instead.** `reap_completed_zombie` (#104) only ever fires *after* the
orchestrator's own terminal `result` event, so it can never preempt real work — the grace
window before reaping exists only to let a clean exit land on its own, and observed exa
teardown hangs never resolve on their own. Cut `SF_STAGE_REAP_GRACE_SEC`'s default from 60s to
5s (just above the poller's 3s tick) — a finished-but-hung stage is now reaped in ~5-8s instead
of up to a minute, on every claude+exa stage.

**Verification.** Unit-level only: `test_reap_completed_zombie_default_grace_is_short_not_60s`
pins the new default (idle-10s zombie reaped with no env override). Not verified via a live
in-container `claude -p` run — that would need an exa-wired stage to actually search and exit,
which wasn't exercised here; the by-code-inspection + reap-unit-test evidence is what backs this
status, not an end-to-end timing measurement.

**Status.** Shipped. The #104 watchdog remains the mechanism — this just makes it fire fast.

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

**Mechanism (already shipped, `SF_GITHUB_REPO_REAPER` stays off).** The dry-run/kill-list
path already exists end-to-end and never deletes anything:
- `src/software_factory/reap_github_repos.py` — CLI entrypoint. With no `--apply` flag it
  forces `dry_run=True` regardless of `SF_GITHUB_REPO_REAPER`, so it is safe to run at any
  time, including in prod, without arming anything.
- `Console.reap_github_repos(org, dry_run=True)` — builds the candidate list: lists real org
  repos via `gh`, matches each to a project by the #95/SOF-8 EXACT recorded repo URL first,
  falling back to the `<name>-<hex>` suffix heuristic only when no exact record exists.
  Repos matching neither are returned in `unknown_repos` (log-only, never a delete
  candidate).
- `github_repo_reaper.reap()` — applies the policy gate per candidate and returns a
  structured report: `{armed, mode, reaped, kept, would_reap, failed, unknown_repos}`.
  **`would_reap` is the kill-list** — each entry is
  `{project_id, repo, phase, archived, has_verified_deploy, reason}` where `reason` is
  `"archived"` or `"stopped-without-deploy"`.
- **Owner-shared exclusion (#210/#217 guard, honored).** `_reap_reason()` checks
  `owner_repo_shared` FIRST and returns `None` (keep) before the archived/stopped checks —
  so a repo the project owner has a real GitHub collaborator invite on can never appear in
  `would_reap`, regardless of archived/stopped state. `Console.reap_github_repos` sets this
  flag from `repo_shared_with_owner(project_id)`, a durable `repo-shared` artifact Stage 1
  records when the invite succeeds. Covered by
  `test_reap_github_repos_exact_match_still_honors_owner_shared_guard` and
  `test_reap_reason_owner_shared_keeps_even_when_archived` /
  `..._when_stopped_without_deploy` in `tests/unit/test_github_repo_reaper.py`.
- **Perf fix (SOF-7 fast-follow).** #95/SOF-8's exact-match index building called
  `project_links(pid)` + `repo_shared_with_owner(pid)` inside the per-project loop — each
  opens a FRESH `ProjectStore` (a pooler connection) — so a real prod run with N projects
  cost O(2N) round-trips against the Supabase pooler. Observed live: a dry-run ran 9 minutes
  in-container with zero output, then timed out. `Console._bulk_repo_signals(project_ids)`
  batches both into ONE query (mirrors the existing `_load_states` batch pattern); combined
  with `_load_states` instead of per-pid `_load_state`, the whole sweep is now a small
  constant number of queries regardless of project count. Also added a `KEEP` log line to
  `github_repo_reaper.reap()` so every candidate (not just would-reap/reaped/failed) logs as
  it's evaluated — the sweep is observable in real time rather than one buffered blob at the
  end. Regression-tested by counting `dbshim.connect` calls across 8 test projects (asserts
  a small constant, not scaling with project count).

**Arming runbook — the ONLY step that arms is ibraheem flipping the env var. Nothing in this
runbook or its tooling flips it.**
1. **Dry-run, on the deployed service** (the CLI reads real project state from
   `SF_PROJECTS_DIR` + the live registry/DB, and lists real org repos via `gh` — data that
   does not exist in a local dev checkout):
   ```
   railway run --service factory-console python -m software_factory.reap_github_repos
   ```
   (Omit `--apply` — omitting it is itself the dry-run gate; the script forces
   `dry_run=True` whenever `--apply` is absent, so this is safe to run at any time.)
   Add `SF_GITHUB_ORG=<org>` before the command to target an org other than the default
   `ibraheem-tenexity`.
2. **Produce the kill-list.** The command prints the full JSON report to stdout. The
   kill-list ibraheem reviews is the `would_reap` array — one entry per repo the reaper would
   delete if armed, each carrying `{project_id, repo, phase, archived, has_verified_deploy,
   reason}`. Cross-check `unknown_repos` too (repos that look factory-made but have no DB
   match) — these are never delete candidates, but worth eyeballing for surprises.
3. **ibraheem reviews and approves the kill-list.** Sanity-check each `would_reap` entry
   against the real project — confirm it should really be gone, and confirm no entry you'd
   expect to be owner-shared shows up (it shouldn't; the guard excludes those before they
   ever reach `would_reap`).
4. **Only after approval, ibraheem flips `SF_GITHUB_REPO_REAPER=on`** on the `factory-console`
   Railway service. This is the sole arming action in the whole runbook — no code path in
   this repo sets or defaults this variable to `on`. Once armed, the background poller
   (`console/poller.py::_github_reaper_tick`) sweeps on its normal interval and deletes only
   what the same policy gate would have put in `would_reap`.
5. To disarm again, unset `SF_GITHUB_REPO_REAPER` (or set it to anything other than `on`) —
   the reaper reverts to dry-run/log-only immediately, no restart required beyond the env
   change taking effect.

**Status.** Mechanism complete and tested; awaiting ibraheem to run the dry-run on the live
service, review the real kill-list, and — separately — flip the flag. Depends on / pairs
with #95.

---

### #128 — Dashboard status pill shows "Building" for stopped/crashed/paused runs 🟢✅
**Symptom.** A single project card shows contradictory states at once — e.g. a blue
**"Building"** pill next to the text **"stopped"** (observed on `project-67f3711d`, which is
stopped, `done=false`, `deploy_url=null`).

**Root cause.** `statusOf()` in `console/web/src/components/Dashboard.tsx:16-22` had no branch
for `phase` of `stopped` / `crashed` / `paused`; those fell through to the default
`return … "Building"`. The card separately renders the raw `phase` text, so the two
derivations disagreed on the same card. State derivation is **duplicated**: the project detail
view (`FactoryConsole.tsx`'s `phaseTone()`) maps `stopped/crashed→danger`, `paused→warning`,
`done→success` correctly — the dashboard card had drifted out of sync. (Dashboard-card sibling
of #106, which fixed the detail view's label lag.)

**Fix.** Added `stopped` / `crashed` / `paused` cases to `statusOf()` (mirroring
`FactoryConsole`'s `phaseTone()`): stopped/crashed → "Stopped"/"Crashed" (danger tone),
paused → "Paused" (warning tone), inserted after the existing `needs-input` check so a
budget-stopped/held run still reads "Needs input" first. Bonus: the pill's live pulsing dot
(`live = key === "building" || "researching"`) and the archive-confirm copy ("Any running
agents stop...") both implicitly stopped misfiring on halted runs too, since they derive from
the same `statusOf()` key. Did **not** extract a shared status-derivation helper across
Dashboard.tsx/FactoryConsole.tsx — the two return different shapes (a label+tone+key triplet vs.
a bare tone) and unifying them is a larger refactor than this bug warrants; flagging the drift
risk here instead. FE-only; no backend change. Verified live via a mocked-API Playwright render
(stopped/crashed pills now red, paused amber, no more contradictory "Building" pill).

> Note: the underlying "this run isn't actually `done`" is **#127** — it deployed but was
> stopped before the done-gate flipped (no demo creds). #128 is only the badge mislabel.

---

## 🟡 Backlog (low priority)

### #87 — `/api/version` + re-assert `railway link` before verify
**Symptom.** Link-drift produces false-negative verifies (the verify runs against the wrong
linked project/SHA).

**Fix.** Add a `/api/version` endpoint exposing the running git SHA, and re-assert
`railway link` before verification so a drifted link can't silently invalidate a check.

**Resolved (TEN-151).** `GET /api/version` (`console/routers/open_routes.py` → `software_factory.version.version_info`) returns `{sha, short, dirty}`, sourced from `SF_GIT_SHA` (baked onto the service by `scripts/deploy.sh`) → `RAILWAY_GIT_COMMIT_SHA` → `git rev-parse` fallback. Link re-assertion: `software_factory.railway_link.assert_link` parses `railway status` and fails loudly on any project/env/service drift — run it before verifying via `make verify-link` (`scripts/assert-railway-link.sh`).

### #95 — Harden the repo-reaper with an exact-name handle 🟢✅
**Symptom.** The reaper matches orphan repos heuristically (a `<name>-[0-9a-f]{8,16}` suffix
guessed from the project_id), which is fuzzy.

**Fix.** Stage 3 already records the real, exact repo via
`record-artifact("GitHub Repo", <clean url>, kind="repo")` (read back through
`Console.project_links`) — the data just wasn't being used by the reaper. `Console.reap_github_repos`
now builds an exact `repo_full_name → project` index from that recorded artifact and checks it
FIRST; the old suffix-pattern guess is now only a fallback for projects with no exact record
(older runs, or a Stage-3 that skipped the record step). No new schema, no new CLI verb — the
exact handle was already being written, just not read. Pairs with #97 (makes the kill-list
unambiguous).

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
