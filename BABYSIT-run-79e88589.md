# Overnight babysit runbook — run-79e88589 (VAMAC build)

You (a future wake of this session) are driving `run-79e88589` on **factory-console** to
completion while the user sleeps. Started 2026-06-06. This file is the source of truth across
context resets. Deps source: `/home/ibraheem/software-factory-skill/env_text.txt`.

CONSOLE = https://factory-console-software-factory-as-skill.up.railway.app
RUN = run-79e88589

## Goal
Drive the run all the way to a deployed app with a green happy-flow (phase=done, deploy_url set),
OR stop and report a hard blocker/budget exhaustion. Do NOT redeploy factory-console (it would
kill the run). All actions are runtime nudges only.

## Why manual nudges are needed
The live loop never calls `detect_stage1_done`/`detect_stage2_done`, so stages don't auto-advance
(see GRAPH-RENDER-EXPLAINED.md flaw #4). So at each stage boundary YOU advance it.

## Each wake — do this in order

1. **Check status:**
   `curl -s $CONSOLE/api/runs/run-79e88589` → look at `phase`, `stage`, `stage1_done`,
   `stage2_done`, `deps_required`, `deps_satisfied`, `deploy_url`, `done`, `spent_usd`.
   Also check process + last events via:
   `railway ssh --service factory-console "ps aux | grep -c '[c]laude -p'; tail -3 /data/runs/run-79e88589/events.jsonl"`
   (SSH needs: `SSH_ASKPASS= DISPLAY=` prefix; key already registered.)

2. **If `done` or `phase==done` or `deploy_url` set:** verify the URL responds, STOP the loop
   (do NOT reschedule), and report success with the URL + spent.

3. **If Stage 1 finished but not advanced** (events has `stage_done{stage:1}` AND `stage1_done`
   is False, OR stage==1 with no claude process running):
   ```
   railway ssh --service factory-console "cd /app && PYTHONPATH=/app/src python3 -c \"from software_factory.console import Console; c=Console('/data/runs'); print(c.detect_stage1_done('run-79e88589'))\""
   curl -s -X POST $CONSOLE/api/runs/run-79e88589/stage2 -H 'Content-Type: application/json' -d '{}'
   ```
   (The POST may 502 because the server blocks on the MCP health check during launch — that's OK,
   it still launches. Verify next wake that stage==2 and a claude process is running.)

CURRENT STATE (updated): Stage 2 was **retried** (`retry-stage-2` event) after deploying fix #1
(ticket persistence enforcement) + the `_copy_prior_artifacts` idempotency fix. We are now
waiting for the retried Stage 2 to finish and — crucially — to persist BUILDABLE tickets this time.

4. **If Stage 2 finished** (events has a NEW `stage_done{stage:2}` after the latest `retry-stage-2`):
   - Set stage2_done + surface required tokens, AND check buildable tickets:
     ```
     railway ssh --service factory-console "cd /app && PYTHONPATH=/app/src python3 -c \"from software_factory.console import Console; from software_factory.tickets import TicketStore; c=Console('/data/runs'); print('buildable:', TicketStore(c._paths('run-79e88589')['tickets_db']).buildable_count()); print('detect2:', c.detect_stage2_done('run-79e88589')); print('deps:', c.status('run-79e88589')['deps_required'])\""
     ```
   - **If `detect2` is still False / buildable == 0** (the retry STILL didn't persist tickets):
     that's "it didn't work" → **RESTART FROM SCRATCH**: start a brand-new run with the same PDF
     (POST /api/runs with the base64 PDF, description "Build the application described in the
     attached VAMAC Employee Experience Platform proposal, then deploy it.", target railway),
     update this runbook's RUN id to the new run, and babysit that one from Stage 1. Report the
     switch. Do this restart at most ONCE; if the fresh run also dead-ends at Stage 2 tickets,
     STOP and report (the skill fix isn't taking — needs investigation, not more runs).
   - **If `detect2` is True:** proceed to deps below.
   - Build the deps dict (see mapping below) and submit — this AUTO-STARTS Stage 3:
     POST `$CONSOLE/api/chat/run-79e88589/deps` with body `{"deps": { "<NAME>":"<value>", ... }}`.
     Every required name must have a value or the gate won't satisfy. Use python urllib for the POST.
   - Verify next wake: stage==3, a claude process running, spent climbing.

5. **If Stage 3 running:** monitor. Watch `deploy_url`, `done`, `blocker`, budget. Stage 3
   deploys to a NEW service `sf-run-79e88589` (not factory-console).
   **STAGE 3 PROGRESS GATE (important):** Stage 3 attempt #1 hit `error_max_turns` (60-turn cap)
   with **0/31 tickets merged**. A Stage 3 retry was launched as a bounded test. On the next wake
   check done-ticket progress:
   `railway ssh --service factory-console "cd /app && PYTHONPATH=/app/src python3 -c \"from software_factory.console import Console; from software_factory.tickets import TicketStore; c=Console('/data/runs'); t=TicketStore(c._paths('run-79e88589')['tickets_db']); print('done:',len(t.done_tickets()))\""`
   - **done > 0 and climbing** → real progress; keep retrying Stage 3 (creds payload below) when it
     hits max-turns, up to ~3 more times, watching budget.
   - **done still 0 after this retry's full turn-budget (another error_max_turns, 0 merged)** →
     STOP. Do NOT restart from scratch (a fresh run hits the same wall: over-scoped 31-ticket
     enterprise architecture + placeholder Supabase/Entra/ADP/Eclipse + 60-turn cap + no mock-build
     skill deployed). Write the final report: Stage 2 fix proven, Stage 3 not viable for this
     architecture without the mock-deps feature + higher turn cap / demo-simpler scope.

   Stage 3 retry creds payload (POST /api/runs/run-79e88589/retry with {"stage":3,"creds":{...}}):
   OPENROUTER_API_KEY from env_text.txt; SUPABASE_*='provision-via-mcp'; ENTRA_*/GRAPH_*/ECLIPSE_*/ADP_*='mock'.

6. **Reschedule** another wake (~900s) UNLESS done or hard-blocked or `spent_usd` >= ~95 (budget
   is $100 hard cap) — then STOP and report.

## Dep value mapping (read REAL values from env_text.txt at deps time; never write them to a file)
`env_text.txt` has real: OpenAI key, Anthropic/Claude key, OpenRouter key (`sk-or-v1-…`),
Railway token (`80477516-…`), Supabase access token (`sbp_…`). Map by required name:

| Required token (examples) | Value to send |
|---|---|
| `OPENAI_API_KEY` | OpenAI key from env_text.txt |
| `ANTHROPIC_API_KEY` | Claude key from env_text.txt |
| `OPENROUTER_API_KEY` | OpenRouter key from env_text.txt |
| `RAILWAY_TOKEN` / `RAILWAY_API_TOKEN` | railway_token from env_text.txt |
| `SUPABASE_*` access/token | supabase `sbp_…` from env_text.txt |
| `NEXTAUTH_SECRET` | generate a random 32-byte hex string |
| `NEXTAUTH_URL` | `https://sf-run-79e88589.up.railway.app` (best guess; agent may override) |
| `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `DATABASE_URL` | **placeholder** `"provision-via-mcp"` (agent has Supabase MCP) — no real value available |
| `AZURE_ENTRA_*`, `ADP_*`, `SENDGRID_API_KEY`, any other unknown | **placeholder** `"mock"` — not available; agent should stub/mock |

Record in the morning report which deps were REAL vs placeholder/mock.

## Morning report should include
- Final phase / done? / deploy_url (and whether it responds).
- Total spent.
- Which deps were real vs placeholdered.
- Any blockers, fix-loop behavior, or budget cutoff.
- The fact that the mock-deps feature was NOT deployed, so placeholdered enterprise integrations
  (Azure/ADP/SendGrid) likely had to be stubbed by the build agent or caused happy-flow failures.
