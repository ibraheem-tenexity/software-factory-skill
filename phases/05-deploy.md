# Phase 5 — Deploy  (Proposal §3 Phase 5)

**Do:** deploy backend → **Railway** (the dedicated `sf-<run_id>` service, NEVER the console's),
frontend → **Vercel**, DB/auth wired to **Supabase**, via the deploy wiring (`gh` CD + provider
MCP). Secrets flow through one sanctioned store (env injection), never hard-coded.

- `deploy.deploy("railway", dir)` (runs `railway up --service sf-<run_id>` then returns the public
  domain) and/or `deploy.deploy("vercel", dir)`; the repo's CD is wired with `gh` so merges to
  `main` redeploy.
- `deploy.healthy(url)` must return True before advancing. `events.emit(... "deployed", {"url":…})`.

**Gate:** all surfaces deploy green; health checks pass; public URL up and recorded in run state.

Code: `deploy.py` (`deploy`, `healthy`), `gh` CD.
