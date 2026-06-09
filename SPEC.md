# Software Factory — Behavioral Specification

This is the contract the factory implements. Code and tests conform to THIS document; when behavior
and spec disagree, the behavior is the bug. Every section maps to enforcing code + tests.

## 1. Pipeline state machine

Phases, in order (stage boundaries marked):

```
Stage 1: extract → provision → research
Stage 2: architect → tickets        (then the deps gate)
Stage 3: build → deploy → test → teardown
```

**Phase states:** `pending | active | done | skipped | failed`
**Stage states:** `not_started | running | done`

Rules:
- **A stage is `done` only when BOTH:** its artifact gate passes (§2) **and** its orchestrator process
  has finished — evidenced by the tracked process having exited, or (no handle, e.g. after a server
  restart) the run.log being idle past a 2-minute grace. A crash/OOM therefore cannot wedge the run.
- **Stage N+1 may launch only when stage N is `done`.** Two stage orchestrators for one run must never
  run concurrently (double spend + workspace races).
- **Phase status is derived by the host from recorded signals** (phases table, stage flags, tickets,
  agents, artifacts, verifications) — agent `set-phase` calls are hints, never the source of truth:
  - the furthest phase with activity is `active` (or `done` when its closing signal exists);
  - every earlier phase with activity is `done`;
  - earlier phases with NO activity are `skipped` (gray on the canvas), never stuck `pending`;
  - later phases are `pending`.
- The host records `extract: done` itself at `start_run` (the host performs extraction).
- The header/API `phase` is the derived current phase; `state.phase` persists only the terminal `done`.

## 2. Gates — mechanical, no human review

| Stage | Done-gate |
|---|---|
| 1 | `PRD.md` passes `artifacts.prd_is_complete` |
| 2 | PRD + architecture.md + architecture.svg exist AND TicketStore holds buildable tickets |
| 3 | (a) done tickets trace to recorded native-Task agents AND (b) a recorded **passing Playwright happy-flow against the live URL** |

Deploying is NOT done. Merging is NOT done. A run reaches `done` only via gate 3(a)+(b).
The ONLY human pause in the pipeline: a required token whose disposition is `provide` (§3).

## 3. Autonomy

- The poller auto-launches Stage 2 when Stage 1 is `done` (§1 definition).
- After Stage 2, the host classifies required tokens (`provide | mock | mcp`). If **no token requires
  `provide`**, the host auto-satisfies deps and launches Stage 3 — no pause. If any token requires a
  human secret, the run waits at the deps gate until the operator submits it.
- No other human checkpoints exist anywhere in the pipeline.

## 4. Budget

- **Per-run ceiling** (not cumulative): default `$30`, env `SF_COST_CEILING`, per-run override
  `state.budget_ceiling`. A stage-launch reserve (`SF_STAGE_RESERVE`, default 5) guards launches.
- **Mid-stage teeth:** the poller monitors each live run's authoritative spend; at the ceiling it
  terminates the stage process, records a `budget` blocker, and preserves ALL state.
- **Recovery:** the operator raises the run's ceiling (`POST /api/runs/<id>/budget {"ceiling": X}`),
  which clears the blocker; the existing `/retry` resumes the stage against the preserved workspace.

## 5. Agent records

- One native Task subagent per unit of work; recorded via `spawn-agent` / `finish-agent`.
- Outcome vocabulary: `real_diff | success` (→ done) · `no_op` (→ failed) · `blocked` · `failed`.
  Anything else records as failed.
- **No phantom agents:** when a stage reaches `done` (or is budget-killed), the host finalizes any
  still-`running` agents of that run: outcome `unreported`; status `done` if the stage's gate passed,
  else `failed`.

## 6. Console truth & delivery

- The canvas/graph/header are a **pure projection of run.db**. Artifact paths resolve against both the
  run base and the workspace. Recorded-but-missing files render `missing` (hollow), never green.
- **Result delivery is in the console only:** toolbar `demo ↗` / `repo ↗` links, the done banner, and
  **chat-panel messages** — the repo URL as soon as the repo exists, the deploy URL when deployed, and
  a final "✅ Live demo + 📦 repo" message at done. Never popups; all verification browsers headless.
- The chat panel narrates progress: run started, stage transitions, deps auto-resolved (or what's
  needed from the operator), deployed-verifying, done, budget pauses, blockers. One message per event.
- The activity feed renders human-readable lines (tool name + its description), never raw JSON,
  never prompt bodies, never absolute container paths.

## 7. Models, MCP, deploy contract

- Models: Stage 1 & 2 orchestrators `claude-opus-4-8`; Stage 3 `claude-sonnet-4-6`; Task subagents sonnet.
- MCP (stage-aware workspace `.mcp.json`): playwright (headless) for all stages; Stage 3 additionally
  `railway` (local `railway mcp`, project-token auth — project-scoped tools only) and `supabase`
  (`@supabase/mcp-server-supabase`, `SUPABASE_ACCESS_TOKEN` from env).
- Stage-3 deploy playbook (the proven sequence): preflight `npm audit` + bump HIGH/CRITICAL CVEs +
  regen lockfile; Dockerfile with build-time placeholder env for module-load clients; build REMOTELY
  (never `npm run build` in the shared container); `create_service → set_variables → deploy →
  generate_domain` (no public URL exists until generate_domain); FINITE health-wait; on failure
  `get_logs`, diagnose, fix via a Task subagent, redeploy.
- The GitHub repo is created in Stage 1 and recorded immediately as a `repo` artifact with a **clean
  (token-free) https URL**; tokens never appear in remote URLs or recorded artifacts.

## 8. Run hygiene

- Each run deploys ONLY to its dedicated `sf-<run_id>` service — never the console service.
- A directory without recorded run.db artifacts is not a pipeline run (the poller ignores it).
- Workspace teardown happens after the verification is recorded; proof (run.db + run.log) survives.
