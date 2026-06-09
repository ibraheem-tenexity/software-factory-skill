# Babysit runbook — run-cdf0993f (fresh VAMAC run, validates mock-deps + fix #2)

RUN = run-cdf0993f. CONSOLE = https://factory-console-software-factory-as-skill.up.railway.app
Deps source: /home/ibraheem/software-factory-skill/env_text.txt (OpenRouter key = sk-or-v1-…).
SSH prefix: `SSH_ASKPASS= DISPLAY=`. Do NOT redeploy factory-console.

## What's different now (latest deploy)
- **Fix #2 is live**: the server poller auto-advances Stage 1→2 and calls detect_stage2_done.
  So you do NOT manually nudge Stage 1→2 anymore — just watch.
- **Mock-deps is live**: deps have smart defaults (Supabase/DB/Railway/NextAuth→mcp,
  OpenAI/Anthropic→env, OpenRouter→provide, externals→mock). Stage 3 gets mock-build +
  MCP-provision guidance in its prompt.

## Each wake
1. `curl -s $CONSOLE/api/runs/run-cdf0993f` → phase, stage, stage2_done, deps_required,
   deps_satisfied, done, deploy_url, spent. Plus `railway ssh … "ps aux|grep -c '[c]laude -p'; tail -3 /data/runs/run-cdf0993f/events.jsonl"`.
2. **done / deploy_url set** → verify URL, STOP (no reschedule), success report.
3. **stage 1 or 2, process running** → just reschedule (auto-advance handles it).
4. **stage2_done True and deps NOT satisfied** (Stage 2 finished, deps gate reached) → SUBMIT DEPS:
   read OpenRouter key from env_text.txt; for each name in deps_required send a disposition —
   OPENROUTER_API_KEY→{disposition:provide,value:<key>}; SUPABASE_*/DATABASE_URL/RAILWAY_*/NEXTAUTH_*→
   {disposition:mcp}; OPENAI_API_KEY/ANTHROPIC_API_KEY→{disposition:env}; everything else→{disposition:mock}.
   POST to `$CONSOLE/api/chat/run-cdf0993f/deps` with `{"deps":{name:{disposition,value?},...}}`
   (auto-starts Stage 3). Verify stage→3 next wake.
   (If stage2_done is False but a buildable ticket store exists, the poller will flip it; if it
   stays False, check `TicketStore.buildable_count()` — if 0, Stage 2 didn't persist; retry stage 2.)
5. **stage 3 running** → monitor. On `error_max_turns` (process exits, not done): retry Stage 3 —
   POST `$CONSOLE/api/runs/run-cdf0993f/retry` `{"stage":3,"creds":{OPENROUTER_API_KEY:<key>}}`.
   This time mock-build guidance is in the skill, so watch `TicketStore.done_tickets()` — if it
   CLIMBS across retries, keep going (up to ~4 retries); if it stays 0 after 2 full retries, STOP
   and report (still not viable — needs higher turn cap / simpler scope).
6. Reschedule ~900s unless done / hard-blocked / spent ≥ ~$95.

## This run is the end-to-end validation of mock-deps + fix #2. Report what worked/didn't.
