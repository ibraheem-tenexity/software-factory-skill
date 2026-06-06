# Plan: Mockable deps + MCP self-provisioning + MCP-aware Stage 2/3 prompts

Status: **awaiting approval** (you chose "plan now, build on your go"). Nothing here is built or deployed yet.

## Goal

At the deps gate, every required token gets a **disposition** instead of being a mandatory paste-in:

- **Provide** — operator types a real value (existing secure path: value → env, never disk; only the name is persisted).
- **Mock** — the build agent builds a **working local fake** of that capability (seeded data, demo login, emails-to-table) so the happy-flow demo passes end-to-end without the real integration.
- **Auto (via MCP)** — the build agent provisions it itself using the **Supabase + Railway MCP** it has access to (create Supabase project, read URL/service key; generate `NEXTAUTH_SECRET`; set `NEXTAUTH_URL` from the deploy URL).
- **Env** — inherited from the runner service (LLM keys already set there).

`deps_satisfied` becomes true once **every** required dep has a resolved disposition — so with smart defaults pre-filled you can usually just click **Save & Launch Build**.

## Smart defaults (the classifier)

A pure function `classify_dep(name) -> "provide" | "mock" | "mcp" | "env"`:

| Pattern | Default | Rationale |
|---|---|---|
| `SUPABASE_*`, `DATABASE_URL` | `mcp` | agent creates/reads via Supabase MCP |
| `NEXTAUTH_SECRET` | `mcp` | agent generates a random secret |
| `NEXTAUTH_URL`, `*_URL` for own service | `mcp` | derived from the Railway deploy URL |
| `RAILWAY_*` | `mcp` | agent has the Railway MCP/token |
| `OPENAI_API_KEY`, `ANTHROPIC_API_KEY` | `env` | already on the runner service |
| everything else (`AZURE_ENTRA_*`, `ADP_*`, `SENDGRID_*`, …) | `mock` | external integrations → working local fake by default |

Every default is overridable in the UI. (For the VAMAC run this means: Supabase/DB/NextAuth = Auto, OpenAI/Anthropic = Env, Azure/ADP/SendGrid = Mock — **zero** mandatory paste-ins.)

## What "Mock" instructs the build agent to produce (working local fake)

Per-capability, wired into the real app so the demo flow works:

- **Auth (Azure Entra / NextAuth)** → a "Sign in as demo admin / demo manager" path that creates a real session; no external IdP.
- **HR/ERP (ADP)** → seed realistic employee/cert rows into Supabase; the real UI reads them.
- **Email (SendGrid)** → write "sent" emails to a table/log and surface them in the UI instead of sending.

The Stage 3 done-gate (Playwright happy-flow on the live URL) still applies — the mock must make the journey pass.

---

## File-by-file changes

### 1. `src/software_factory/runstate.py`
- Add persisted field `deps_disposition: dict[str,str]` (name → `provide|mock|mcp|env`). Dispositions are **metadata, not secrets** → safe on disk. Provided **values** still go to env only.

### 2. New: `src/software_factory/deps.py` (or fold into `input_pipeline.py`)
- `classify_dep(name) -> str` (table above), pure + unit-tested.
- `resolve_satisfied(required, disposition, provided_names) -> bool` — satisfied when every required dep is `mock`/`mcp`/`env`, or `provide` with a provided value.

### 3. `src/software_factory/console.py`
- `stage2_artifacts(run_id)` (≈338): also return `disposition` map (defaults from `classify_dep`, merged with any saved overrides) so the UI can pre-fill.
- `submit_deps(run_id, deps)` (the deps handler): accept per-dep `{disposition, value?}`. Provide→set env + record name; mock/mcp/env→record disposition only. Recompute `deps_satisfied` via `resolve_satisfied`. (Keep the no-secrets-on-disk rule.)
- `start_stage3(...)`: pass the disposition map into the Stage 3 prompt.

### 4. `console/server.py`
- `/api/runs/<id>/deps` POST: pass through the richer payload `{name: {disposition, value?}}` to `submit_deps`.

### 5. `console/index.html` — deps inspector (≈337-360, `submitDeps` ≈384)
- Render each missing dep as a row with a 3-way segmented control **Provide | Mock | Auto**, defaulted from the returned disposition. "Provide" reveals the secure input; Mock/Auto hide it and show a tag.
- "Save & Launch Build" sends `{name:{disposition,value?}}`.

### 6. `skills/stage-2-design/SKILL.md` + `make_prompt_stage2` (`console.py:73`-ish)
- State explicitly: **the Stage 3 build agent has Supabase MCP + Railway MCP** (and the Railway/Supabase tokens in env). So:
  - Architect for Supabase (DB/auth/storage) + Railway (compute) as **agent-provisionable** — do **not** require the operator to supply Supabase/Railway/NextAuth creds.
  - In `## Required Tokens`, tag each token with its category (`provide` / `mcp` / `mock-able`) so the deps list is smart from the source.

### 7. `skills/stage-3-build/SKILL.md` + `make_prompt_stage3`
- Receive the disposition map. Instructions:
  - `mock` deps → build the **working local fake** (seeded data / demo-login / email-to-table); happy-flow must pass against it.
  - `mcp` deps → provision via Supabase/Railway MCP (create project, read URL+service-role key; generate `NEXTAUTH_SECRET`; set `NEXTAUTH_URL` from deploy URL; set vars on the `sf-<run_id>` service).
  - `env`/`provide` → real values already in the environment.

### 8. Companion wiring fix (REQUIRED for this to work unattended)
The deps gate is only reachable today because I nudged `detect_stage1_done`/`detect_stage2_done` by hand (they're never called in the live loop — see `GRAPH-RENDER-EXPLAINED.md` flaw #4). To make runs reach the deps gate on their own:
- Call `detect_stage1_done` / `detect_stage2_done` from `server.py:_poll_transitions` (or `status()`), so `stage1_done`/`stage2_done` flip automatically and the existing browser auto-advance fires.
- Either wire the static gate node's "Continue" to actually advance, or stop rendering a Continue on it (it currently posts `gate=undefined`).

### 9. (Separate, also pending) Resizable panels — `console/index.html`
- CSS vars on the layout: `.main{--chat-w:400px;--inspect-w:420px}`, `.canvas-area{--activity-h:150px}`; `.chat-panel`/`.sidebar` widths + `#cy` bottom + `.activity` height read the vars.
- Drag handles on the inner edges (pointer events) update the vars; call `cy.resize()` on change; clamp to sane min/max; persist to `localStorage`. Inspector handle lives on `.main` (not inside `#inspect`, whose innerHTML is rebuilt).

---

## Tests (TDD, before code)
- `classify_dep` table (each pattern → expected disposition).
- `resolve_satisfied` (mock/mcp/env satisfy; provide needs a value).
- `submit_deps` with mixed dispositions → correct `deps_satisfied`, **no secret value written to disk**, dispositions persisted.
- `stage2_artifacts` returns defaulted dispositions.
- Prompt builders include the MCP-availability + disposition text (string assertions).

## Secrets invariant (unchanged)
Provided values: env only, names in state. Dispositions: metadata, safe on disk. Mock/MCP/env deps never carry a user value.

## Deploy
Per your instruction: implement + run the full suite + local Playwright check first; **do not redeploy** until you approve (a redeploy restarts the container — the current run's state survives on the volume, but its live deps session ends).

## Open question for you
The architect over-asked (Azure Entra SSO + ADP for a first demo). With these defaults, those become Mocks automatically — good. But do you also want a **"don't even list a dep unless it's `provide`"** mode (hide mcp/env/mock-by-default deps entirely, show only what truly needs you)? Or keep all 14 visible with their pre-set dispositions so you can see/override everything? (Plan assumes the latter — full visibility.)
