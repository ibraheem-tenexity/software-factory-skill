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
  - activity is inferred from EVIDENCE, not just set-phase rows: a deploy-kind artifact is deploy
    activity; a recorded verification is test activity;
  - a phase with its CLOSING SIGNAL is `done` regardless of position (deploy: deploy artifact;
    test: passing verification; stage phases: their stage flags);
  - the phase with the MOST RECENT unclosed activity is `active` — a test→build fix loop
    truthfully bounces the canvas back to build;
  - later phases that ran without closing are `pending` (they will run again);
  - earlier phases with NO activity are `skipped` (gray on the canvas), never stuck `pending`.
- The host records `extract: done` itself at `start_run` (the host performs extraction).
- The header/API `phase` is the derived current phase; `state.phase` persists only the terminal `done`.

## 2. Gates — mechanical, no human review

| Stage | Done-gate |
|---|---|
| 1 | `PRD.md` passes `artifacts.prd_is_complete` |
| 2 | PRD + architecture.md + architecture.svg exist AND TicketStore holds buildable tickets |
| 3 | (a) done tickets trace to recorded agents (native-Task on the claude runtime; logical agents on opencode, §9) AND (b) a recorded **passing Playwright happy-flow against the live URL** |

Deploying is NOT done. Merging is NOT done. A run reaches `done` only via gate 3(a)+(b).
The ONLY human pause in the pipeline: a required token whose disposition is `provide` (§3).
- **Brand canon:** `skills/tenexity-design/` (vendored from tenexity-design-master @624b8e4)
  ships into every stage workspace; built apps vendor its `tokens.css` and the stage-3 gate's
  result includes a `brand_tokens` check — deployed CSS must contain `--brand: 214 100% 55%`.

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

- One agent record per unit of work via `spawn-agent` / `finish-agent`: a native Task subagent on
  the claude runtime, a **logical agent** on the monolithic opencode runtime (§9). Same verbs,
  same ticket-claim contract, same gate semantics.
- Outcome vocabulary: `real_diff | success` (→ done) · `no_op` (→ failed) · `blocked` · `failed`.
  Anything else records as failed.
- **No phantom agents:** when a stage reaches `done` (or is budget-killed), the host finalizes any
  still-`running` agents of that run: outcome `unreported`; status `done` if the stage's gate passed,
  else `failed`.

## 6. Console truth & delivery

- The canvas/graph/header are a **pure projection of run.db**. Artifact paths resolve against both the
  run base and the workspace. Recorded-but-missing files render `missing` (hollow), never green.
- **Run STATE lives in Postgres when `SF_DB=postgres`** (`DATABASE_URL`, Supabase transaction
  pooler): one schema per run (`sf_run_<id>`) + a `public.sf_runs` registry for discovery; every
  boot self-backfills any sqlite-only runs from the volume (idempotent). Logs (`run.log`),
  chat (`chat.jsonl`) and workspaces STAY on the volume. Unset `SF_DB` = sqlite, exactly as before
  (rollback path; tests run hermetic on sqlite).
- **Result delivery is in the console only:** toolbar `demo ↗` / `repo ↗` links, the done banner, and
  **chat-panel messages** — the repo URL as soon as the repo exists, the deploy URL when deployed, and
  a final "✅ Live demo + 📦 repo" message at done. Never popups; all verification browsers headless.
- **Demo login:** an app with ANY sign-in seeds a throwaway demo account (never a real secret),
  records it as a `demo-creds` artifact (`demo_credentials.md`), runs the happy-flow signed in with
  it, and the done chat message (and its email) includes the demo login — an auth'd app the
  operator can't open is not delivered.
- The toolbar cost pill renders `spent $X / $Y cap` from `status.budget_ceiling` and is clickable
  at ANY time to raise the cap; raises and refused resumes give visible feedback (a state change
  the UI doesn't show is a bug by contract).
- The chat panel narrates progress: run started, stage transitions, deps auto-resolved (or what's
  needed from the operator), deployed-verifying, done, budget pauses, blockers. One message per event.
- **Operator email** (env-gated: `RESEND_API_KEY` + `SF_NOTIFY_EMAIL`, via Resend): the four
  operator-relevant events — run done, waiting-on-input at the deps gate, budget-stop, stage
  crash/auto-resume — also send an email, at most once per (run, event) (same dedup as the chat
  narration). Absent env = silent no-op; a send failure never breaks the poller.
- The activity feed renders human-readable lines (tool name + its description), never raw JSON,
  never prompt bodies, never absolute container paths.

- **Console auth** (env-gated: `SF_GOOGLE_CLIENT_ID` + `SF_AUTH_EMAILS`, optional
  `SF_AUTH_SECRET` for restart-surviving sessions): when enabled, the root serves a Google
  sign-in page and every other route requires a valid HMAC-signed session cookie; the ID token
  is validated server-side (audience + verified email + allowlist). Either var absent = the
  console is open (local dev/tests unchanged).

## 7. Models, MCP, deploy contract

- Models (claude runtime): Stage 1 & 2 orchestrators `claude-opus-4-8`; Stage 3 `claude-sonnet-4-6`;
  Task subagents sonnet. **Per-run picks:** the operator may pin a run's planning model
  (S1/S2: `claude-opus-4-8` | `claude-fable-5`) and implementation model (S3:
  `claude-sonnet-4-6` | `claude-opus-4-8`) at start; picks persist in RunState (retries keep
  them), beat the `SF_MODEL` env knob, and anything outside the offered sets is dropped. A
  non-default S3 pick is also mandated in-prompt for Task subagents (overriding the SKILL's
  sonnet pin). Opencode runtime: all stages `openrouter/moonshotai/kimi-k2.6` (§9).
- MCP (stage-aware workspace `.mcp.json`): playwright (headless) for all stages; Stage 3 additionally
  `railway` (local `railway mcp`, project-token auth — project-scoped tools only) and `supabase`
  (`@supabase/mcp-server-supabase`, `SUPABASE_ACCESS_TOKEN` from env).
- **Deploy project isolation:** built apps deploy into the `software-factory-projects` Railway
  project only — never into the factory's own project. The runner env's project-scoped
  `RAILWAY_TOKEN`/`RAILWAY_PROJECT_ID` define the target; agents never substitute another.
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

## 9. Agent runtimes — claude | opencode

- Every run is **pinned to one runtime at `start_run`** (`RunState.runtime`, persisted): the
  request's `runtime` field (the UI picker rides the chat body) wins; else `SF_RUNTIME`; default
  `claude`. All stages and retries of a run use its pinned runtime.
- **claude** (reference): headless `claude -p … --output-format stream-json`, orchestrator +
  native Task subagents, per-stage models (§7).
- **opencode** (monolithic): headless `opencode run … --format json --dangerously-skip-permissions
  --agent factory`, Kimi K2.6 via OpenRouter. ONE agent does the work, recording **logical agents**
  per unit (§5) so gates and the canvas keep per-unit accounting. The stage contract is
  `SKILL.opencode.md` (delivered as ws/SKILL.md + injected via opencode.json `instructions`).
- Opencode launch hygiene (each violated one of these broke a real run): the child env sets
  `PWD=<workspace>` (Popen does not update PWD; OpenCode trusts it for project resolution),
  `XDG_CONFIG_HOME=<ws>/.oc-config`, and `OPENCODE_DISABLE_{CLAUDE_CODE,EXTERNAL}_SKILLS=1`
  (the host's global opencode config and skill scans must never leak into stage runs).
  The steps cap (claude's `--max-turns` analogue) lives in the workspace `opencode.json`
  (`agent.factory.steps`, from `SF_MAX_TURNS` at workspace-prep time).
- Cost (§4) parses BOTH stream vocabularies per session: claude `result.total_cost_usd` +
  usage-tail; opencode per-`step_finish` `part.cost` (token-priced fallback at the Kimi rate).
  Both runtimes' gates are identical — gate 3(b)'s Playwright happy-flow is runtime-independent.
