# Coordination — inter-agent

_Fresh as of 2026-06-17. Replaces the stale prior version. Append peer notes at the bottom._

## Who's who
- **software-factory-skill** (this repo) — owns `main` + the deployed Railway `factory-console`.
- **softwarefactory** (`~/softwarefactory`) — operator/coordinator + api-server session; relays
  operator decisions, owns Supabase credential rotation + the state-DB cutover + the prod-org audit.
- **sf-opencode** (`~/sf-opencode`, `opencode-kimi`) — the OpenCode/Kimi runtime work (now merged to main).

## Ownership right now
- **Main + factory-console deploy** → this session. Don't push `main` or `railway up` factory-console
  without syncing here.
- **Supabase credentials, the DB cutover, the prod-org audit** → operator (via softwarefactory session).

## Current state
- `main` = **`f3246fe`** — PR #3 (roles/ownership + Kimi K2.7 + env isolation) and PR #4 (Supabase
  removal + factory deploy-db) MERGED.
- **Live `factory-console` = `ee6aad4` — NOT yet deployed.** The merged work is not live.
- Deploy is gated (operator): needs `SF_AUTH_SECRET`, clear ghost `run-48133f03`, and the DB cutover.

## Live infra (shared awareness)
- **Railway**: `factory-console` (orchestrator + `/data` volume) + one `sf-<run_id>` service per built app.
- **Supabase**: `software-factory-state` (`uxlrlwxnhtphvddbgbge`, personal org) is the **current** console
  DB; `software-factory-as-a-skill` (`dbqgnwhshrskfnyqcewd`, Tenexity org) is the **intended** DB — cutover
  NOT live. Do **not** delete `software-factory-state` until after cutover+verify.
- **Langfuse** (traces), **Resend** (email).

## Standing rules (do not break)
1. **No new Supabase projects.** Use `software-factory-as-a-skill` for the console DB.
2. **Agents have no Supabase access** (no MCP, no token) — databases are factory-provisioned (Railway
   Postgres → `context/deploy-db.json`). Don't reintroduce the Supabase MCP into stage workspaces.
3. Don't push `main` or redeploy `factory-console` without posting here first.
4. Secrets via Doppler/Railway vars only — never in commits. The leaked PAT `sbp_4ed6…` is REVOKED.
5. `gh` pushes to the repo need the `ibraheem-tenexity` account (it drifts to `ibraheem-111`).

## Roles/ownership enforcement — rules for anyone touching the pipeline
- Enforcement lives **only at the HTTP boundary** (`console/server.py`: `_viewer`/`_can_see`/`_path_run_id`),
  keyed on the `/api/runs/<id>` and `/api/chat/<id>` path prefixes. **Console methods have NO ownership
  checks.** → Any NEW run-scoped route must be added to the gate; in-process callers (poller, the
  `db` CLI, the chat tools) bypass by design.
- **Stamp `owner` on every create** (from `viewer[0]`). A create path that forgets it → `owner=""` →
  the run is visible to **admins only** (members never see it).
- `release_run`/`retry_stage` don't self-check ownership — they trust the server gate; only ever reach
  them via the gated routes.
- **Known soft spot:** the chat concierge's tools take a `run_id` arg and call `Console` directly with no
  `_can_see`, so a member could read another tenant's run by passing a foreign id — harden the chat tools.
- **Service token + auth-disabled = admin** (full visibility, intentional for poller/babysitter/CI).

## Open coordination items
- [ ] Operator: deploy decision (now keep-old-DB vs deploy+cutover) + the new `DATABASE_URL` for the cutover.
- [ ] Operator: delete-side Supabase audit (did an agent delete a prod project) — dashboard audit log.
- [x] `software-factory-as-a-skill` provenance — confirmed intentional (the new console DB).
- [ ] In progress (peer `k7apqsug`): make the pipeline adhere to ownership rules (chat-tool hardening etc.).
- [ ] Next workstream: spec-to-demo harness (`feature/spec-to-demo-harness`) — plan only, not started.

## Peer responses (append-only)
<!-- peers: add dated notes below -->
