# Phase 6 — Test → fix loop  (Proposal §3 Phase 6)

**Do:** the **Playwright agent** drives the deployed app through the **primary user journey** and
reports pass/fail + bugs to the **orchestrator**. The orchestrator routes feedback (via
`claude-peers`) and spawns **fix agents** for each bug; redeploy; re-test. Loop.

- `gate.happy_flow_passed(playwright_result)` → the verdict; `gate.bugs_from(result)` → the fix
  list. Each fix agent: spawn → patch → `merge_if_green` → redeploy (Phase 5) → re-test.
- Bounded by per-phase attempt caps + the budget ceiling. No human in the loop.

**DONE:** the **happy flow passes end-to-end** in the browser (within the budget ceiling).
`events.emit(... "done")`.

Code: Playwright MCP, `gate.py` (`happy_flow_passed`, `bugs_from`), `deploy.py`, `claude-peers`.
