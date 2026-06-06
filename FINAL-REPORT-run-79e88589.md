# Final report — run-79e88589 (VAMAC build)

**Outcome: STOPPED at Stage 3. Your two requests (retry capability + fix #1) are PROVEN working.
The build itself can't reach a green deploy in its current form — a scope/deps problem, not a
pipeline-wiring problem.** Loop ended; no further wakes. Nothing torn down. factory-console untouched.

## The full arc this session
| Stage | Result |
|---|---|
| Stage 1 (research → PRD) | ✅ PRD complete, PDF input pipeline worked |
| Stage 1 → 2 advance | ✅ (manual nudge — fix #2 still pending) |
| Stage 2 (architecture + tickets) — **original** | ❌ emitted 31 ticket *events* but persisted 0 → dead-ended |
| **Deploy: retry + fix #1 + idempotency fix** | ✅ shipped, 201 tests green |
| Stage 2 — **retried under the new skill** | ✅ **persisted all 31 buildable tickets**, `detect_stage2_done` True |
| Deps gate | ✅ satisfied — real `OPENROUTER_API_KEY` + placeholders for the other 11 |
| Stage 3 (build) attempt #1 | ⚠️ `error_max_turns` (61 turns), **0/31 tickets merged** |
| Stage 3 (build) attempt #2 (retry) | ⚠️ `error_max_turns` (61 turns), **0/31 tickets merged** |

## What your two asks achieved (both proven)
- **Retry capability** — `Console.retry_stage()` + `POST /api/runs/<id>/retry`. Used it to re-run
  Stage 2 (rescued the stuck run) and Stage 3 (×1). Works.
- **Fix #1 (ticket persistence)** — the stricter Stage 2 skill + `buildable_count()` done-gate made
  the agent persist real tickets. Before: 0 rows. After retry: **31 buildable tickets**. The exact
  bug that killed the first run is fixed.
- **Bonus bug found + fixed:** the first retry attempt crashed (`SameFileError` in
  `_copy_prior_artifacts` — copying `context/PRD.md` onto itself on re-run). Made it idempotent.

## Why Stage 3 can't finish (this architecture)
Two full 60-turn budgets, **zero** tickets merged. Causes, compounding:
1. **Over-scoped architecture** — the architect produced **31 tickets across 8 waves** (Entra SSO,
   ADP, Eclipse ERP, pgvector, full enterprise platform). That's not "demo-simplest."
2. **Placeholder / mock enterprise deps** — Supabase (`provision-via-mcp`), Entra/Graph/Eclipse/ADP
   (`mock`). No real database or SSO, so features can't actually be built and the gated `mark_done`
   (real PR + non-empty diff required) can't be satisfied. The agent likely burned turns trying to
   provision Supabase with a placeholder before it could build anything.
3. **Mock-build skill not deployed** — the planned mock-deps feature (working local fakes) is what
   would let the agent legitimately build against fakes. It's still only planned.
4. **60-turn cap far too small** — `SF_MAX_TURNS=60` is nowhere near enough for a 31-ticket build;
   each retry resets to 60 and still merged nothing.

## Why I did NOT restart from scratch
A fresh run hits the identical wall (same over-scoped architecture + placeholder deps + turn cap +
no mock-build skill). It would burn budget for the same 0-merge outcome. The bottleneck is the
build's inputs/scope, not run state — so a re-run can't fix it.

## Spend
~**$7.85** cumulative (S1 $2.86, S2 $1.03, S2-retry $0.67, S3 $1.93, S3-retry $1.37). Hard cap $100.

## To make Stage 3 viable (recommended, in order)
1. **Build the mock-deps feature** (planned) — working local fakes for Entra/ADP/Eclipse, Supabase
   via MCP, NextAuth generated. Then the build has a real DB + stubbed integrations and tickets can
   actually be completed + verified.
2. **Raise the Stage 3 turn budget** (`SF_MAX_TURNS`) a lot, and/or make Stage 3 resume per-wave
   without resetting turns (the retry mechanism helps, but only if each retry actually merges).
3. **Scope the architect to demo-simplest** — it keeps designing full enterprise platforms. A first
   demo should be a handful of tickets, not 31.
4. **Investigate the 0-merge-in-60-turns** specifically — confirm the agent is stalling on Supabase
   provisioning vs. ticket work; the mock feature + a real Supabase project should unblock it.

## Fixes still pending (from earlier reports)
- **Fix #2:** wire `detect_stage1_done`/`detect_stage2_done` into the poller so stages auto-advance
  (I nudged every transition by hand this whole run).
- **Mock-deps + MCP self-provisioning** feature (the plan in `PLAN-mock-deps-and-mcp-provisioning.md`).
- Resizable panels (small UI ask, still queued).

## State left for you
Run `run-79e88589` intact (not torn down). PRD + architecture + 31 persisted tickets are real and
inspectable. The deployed factory-console now has: native claude, PDF pipeline, OpenRouter skill
guidance, fix #1 (ticket persistence + done-gate), retry capability, and the idempotency fix.
All deployed code is **uncommitted in git**.
