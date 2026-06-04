# Phase 2b — Provision infra  (Proposal §3 Phase 2, "then infra is provisioned")

**Do:** provision the infrastructure the architecture needs, via the provider MCPs / CLIs, and
**wait for it to be ready before building** (the "wait-for-deps" step):
- **Railway** — a **dedicated** service `sf-<run_id>` for this app (NEVER the console's own
  service); **Supabase** — project/branch for auth + Postgres; **Vercel** — frontend project if used.
- For each dependency not yet ready: `events.emit(... "blocker", {"what":…, "blocks":"wait-for-deps"})`;
  poll until healthy then `events.emit(... "blocker_cleared", …)`. The wait is on **infrastructure
  readiness, not a human** (fully autonomous). A surface needing absent authority = hard block.
- Record the live infra handles (project IDs, URLs) to the brain
  (`memory.write(memory.run_ns(run_id), "infra", {…})`).

**Out:** live infra handles in the brain.

**Gate:** infra projects exist and are reachable; no open dep blockers.

Code: provider MCP/CLI (Railway/Supabase/Vercel), `events.py`, `memory.py`.
