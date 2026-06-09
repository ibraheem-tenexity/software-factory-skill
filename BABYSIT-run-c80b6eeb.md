# Babysit runbook — run-c80b6eeb (VAMAC, turn cap 200, budget $25)

RUN = run-c80b6eeb. CONSOLE = https://factory-console-software-factory-as-skill.up.railway.app
Deps: /home/ibraheem/software-factory-skill/env_text.txt (OpenRouter = sk-or-v1-…).
SSH prefix: `SSH_ASKPASS= DISPLAY=`. Do NOT redeploy factory-console.

Now deployed: SF_MAX_TURNS=200 (stages should finish within turns), budget=$25 (HARD), python3
emit fixed, mock-deps + fix #1/#2 live. So Stage 1→2 auto-advances; Stage 2 persists tickets +
poller flips stage2_done + surfaces deps; submit deps → Stage 3 builds with mock/MCP guidance.

## Each wake
1. `curl $CONSOLE/api/runs/run-c80b6eeb` → stage, phase, stage2_done, deps_required, deps_satisfied,
   done, deploy_url, spent. + `railway ssh … "ps aux|grep -c '[c]laude -p'; tail -3 /data/runs/run-c80b6eeb/events.jsonl"`.
2. done / deploy_url → verify URL, STOP, success report.
3. stage 1/2 with process running → reschedule (auto-advance handles it).
4. stage2_done True and deps NOT satisfied → SUBMIT DEPS to `$CONSOLE/api/chat/run-c80b6eeb/deps`
   `{"deps":{name:{disposition[,value]}}}`: OPENROUTER_API_KEY→provide+value(from env_text.txt);
   SUPABASE_*/DATABASE_URL/RAILWAY_*/NEXTAUTH_*→mcp; OPENAI_API_KEY/ANTHROPIC_API_KEY→env; else→mock.
   (auto-starts Stage 3.)
5. stage 3 running → monitor `TicketStore.done_tickets()` (should CLIMB now: 200 turns + mock-build).
   On error_max_turns + not done → retry: POST `$CONSOLE/api/runs/run-c80b6eeb/retry`
   `{"stage":3,"creds":{"OPENROUTER_API_KEY":<key>}}`. Keep retrying while done_tickets climbs.
6. Max-turns fallback (any stage): if process exited on error_max_turns but the stage's WORK is
   actually complete — Stage 1: PRD passes `artifacts.prd_is_complete`; Stage 2: buildable_count>=1
   + architecture.md/svg exist — emit the stage_done marker so the poller advances. Else retry.
7. Reschedule ~900s unless done / hard-blocked / spent ≥ ~$23 (budget is $25).
