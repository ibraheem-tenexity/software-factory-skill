# Known Issues & Unimplemented Work

Open factory issues that are **not yet implemented** — diagnosed, parked, or a standing risk.
Shipped work is tracked in git history, [`ARCHITECTURE.md`](ARCHITECTURE.md), and the Linear
tracker (project "Software Factory", team SOF) — **not here**. This doc keeps only what those do
not capture: an operator runbook for a feature whose *arming* is a manual step, and standing
latent-risk notes.

- **As of:** `staging` @ `c0469d3` (2026-07-21)
- **Scope:** the autonomous build pipeline (`src/software_factory`, `console/`, the stage SKILLs),
  not the customer/OS frontends.

> The bulk of this file (a 2026-06-29 snapshot) has been retired: every code-level issue it listed
> as "parked" or "in-flight" has since shipped and is tracked in Linear. See the traceability map
> at the bottom before assuming an old `#NN` is still open.

---

## Genuinely open

### #97 (SOF-7) — GitHub-repo reaper: arming is a manual operator step
**Status.** *Mechanism complete and tested; the reaper is intentionally OFF in prod.* The only
action that arms it is the operator flipping `SF_GITHUB_REPO_REAPER=on` — no code path in this repo
sets or defaults that variable to `on`. This runbook is the unique value that lives nowhere else.

**Mechanism (already shipped, stays dry-run until armed).**
- `src/software_factory/reap_github_repos.py` — CLI entrypoint. With no `--apply` flag it forces
  `dry_run=True` regardless of `SF_GITHUB_REPO_REAPER`, so it is safe to run any time, including in
  prod, without arming anything.
- `Console.reap_github_repos(org, dry_run=True)` — builds the candidate list: lists real org repos
  via `gh`, matches each to a project by the exact recorded repo URL (SOF-8) first, falling back to
  the `<name>-<hex>` suffix heuristic only when no exact record exists. Repos matching neither are
  returned in `unknown_repos` (log-only, never a delete candidate). `Console._bulk_repo_signals`
  batches the per-project link/owner-shared lookups into one query (SOF-7 perf fix).
- `github_repo_reaper.reap()` — applies the policy gate per candidate and returns
  `{armed, mode, reaped, kept, would_reap, failed, unknown_repos}`. **`would_reap` is the
  kill-list** — each entry is `{project_id, repo, phase, archived, has_verified_deploy, reason}`.
- **Owner-shared exclusion.** `_reap_reason()` checks `owner_repo_shared` FIRST and returns `None`
  (keep) before the archived/stopped checks, so a repo the project owner has a real collaborator
  invite on can never appear in `would_reap`.
- Once armed, the background poller (`console/poller.py::_github_reaper_tick`) sweeps on its normal
  interval and deletes only what the same policy gate would have put in `would_reap`.

**Arming runbook — the ONLY step that arms is flipping the env var.**
1. **Dry-run, on the deployed service** (the CLI reads real project state + lists real org repos
   via `gh` — data that does not exist in a local checkout):
   ```
   railway run --service factory-console python -m software_factory.reap_github_repos
   ```
   (Omit `--apply` — that is itself the dry-run gate.) Prefix `SF_GITHUB_ORG=<org>` to target an
   org other than the default `ibraheem-tenexity`.
2. **Produce the kill-list.** The command prints the full JSON report; the kill-list is the
   `would_reap` array. Cross-check `unknown_repos` too (factory-looking repos with no DB match —
   never delete candidates, but worth eyeballing).
3. **Review and approve.** Sanity-check each `would_reap` entry against the real project; confirm no
   entry you'd expect to be owner-shared shows up (it shouldn't).
4. **Only after approval, flip `SF_GITHUB_REPO_REAPER=on`** on the `factory-console` Railway
   service. This is the sole arming action.
5. To disarm, unset `SF_GITHUB_REPO_REAPER` (or set it to anything other than `on`) — the reaper
   reverts to dry-run/log-only immediately, no restart beyond the env change taking effect.

### OS markdown-editor — `PR #169` (needs confirmation)
A small operating-system-stage change (the md-editor, from `vr3lprd8`) was historically held
alongside the now-landed stage-3 resume work. **Unverified:** no md-editor reference remains in this
repo's code and there is no SOF ticket for it (memory notes a `TEN-140` on the separate Tenexity
tracker). Flagged rather than removed — confirm whether it landed before deleting this entry.

---

## Cross-cutting notes / latent risks

- **Migrations.** Baseline `0001` is frozen inline DDL; every backend schema change needs an
  idempotent incremental migration + a rehearsed prod-upgrade path. No schema change is "free."
- **Connection budget.** Direct `_pg_connect` callers must route through the pool (SOF/#120); the
  pooler ceiling is 200 (Supabase 6543 transaction pooler). The leak fix is in, but any *new* direct
  connector reintroduces the max-connections risk — see `vault.py`, `blobs.py`, and the agent-table
  modules (`system_agents.py` / `runtime_agents.py`, formerly `agent_prompts.py`) for the call sites
  that historically bypassed the pool.
- **Root launcher.** factory-console runs as root and `claude` ≥ v2.1.195 refuses
  `--dangerously-skip-permissions` as root (fixed by dropping to the `node` user, #125). The
  claude-code binary version is pinned in the Dockerfile so a silent bump can't reintroduce the
  breaking flag change — **keep the pin.**
- **Deploy DB + exa wiring (#100).** Deploy-DB provisioning lives in the stage-3 agent, Railway-MCP
  latitude is broadened, and exa web-search is wired into all stages. Any broader
  research-decentralization beyond #100 was explicitly out of scope and is not started.

---

## Traceability — retired issues (shipped, now tracked in Linear)

The 2026-06-29 snapshot listed these as open; all have shipped. Look in Linear / git history, not
here.

| Old id | Ticket | What shipped |
|---|---|---|
| #127 demo-creds not gated | SOF-4 | Done-gate hard-requires a sign-in step + reads artifact content (no phantom rows). |
| PR #168 / #111 stage-3 resume | SOF-2 | Stage-3 SKILL runs a resume assessment on entry (deploy-only when built). |
| #129 stage-1 zombie wedge | — | `_proc_state()` / `_reap_if_os_zombie()` OS-level zombie reap. |
| #105 exa teardown grace | — | `SF_STAGE_REAP_GRACE_SEC` default cut 60s→5s. |
| #107 LLM keys "mock" | SOF-5 | Resolved the opposite way: a built app must never inherit the runner's keys; LLM keys default to `mock`, real keys only via explicit operator `provide`. |
| #128 dashboard status pill | SOF-10 | `statusOf()` handles stopped/crashed/paused. |
| #87 `/api/version` + link re-assert | SOF-24 (TEN-151) | `GET /api/version`; RAILWAY_GIT_COMMIT_SHA precedence; `assert_link`. |
| #95 reaper exact-name handle | SOF-8 | Exact `repo_full_name → project` index checked before the suffix heuristic. |
| SOF-23 poller auto-resume guard | SOF-23 | `auto_resume_dead_stage` requires `launch_attempted` or an existing `project.log`. |
