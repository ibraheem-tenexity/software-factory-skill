# CBT Wave 1 — implementation design

**Date:** 2026-07-21 · **Status:** operator-approved design, pre-plan
**Source design:** PR #379 (`design/TICKETS.md`, `design/PRD.md` §2.3/§2.4/§2.8/§6 entries 33–38, 41)
**Structure authority:** `docs/STRUCTURE.md` (PR #382, merged) — followed strictly per operator directive.

## Goal

All four Wave-1 features live on the staging deployment for the CBT Company intro on the 27th:

1. **Wow prefill** — CBT-1/3/4 (company enrichment: endpoint, UI, concierge tool)
2. **Codebase discovery** — CBT-6/7 (repo crawl → AGENTS.md/CLAUDE.md/integrations.md into the org KB)
3. **Recipes** — CBT-9 (repo-backed recipes: admin loader, concierge input, fork-and-extend build seed)
4. **Engine trio** — CBT-13/14 + SOF-200 (Codex as a fully functional third runtime; Kimi K3 bump)

Out of scope: CBT-10 recipe *content* (admin-panel data, added by whoever operates the panel);
CBT-12 Explore gallery beyond the intake picker (Wave 2); all Wave-2/3 tickets; the repo
restructure itself (operator-sequenced AFTER Wave 1 — new code follows STRUCTURE.md ownership,
legacy code does not move).

## Operator decisions recorded (2026-07-21)

| Decision | Ruling |
|---|---|
| Demo bar for the 27th | **All of Wave 1 live** on staging — not canvas-only. |
| Codex | Runs headlessly; ships as a **fully functional** engine card (no gated state). SOF-200 tracks the adapter plan/outcomes. |
| Confidence display | **Sources only, product-wide — no confidence pills/tiers anywhere** (Principle 4). Design archive already swept (PR #379 commits `aac5660`, `913d9c0`). |
| Recipe runtime mechanism | Recipe **text replaces SOW** as concierge intake input → brief built on it; recipe **repo is the build seed**; stage skills **fork-and-extend**, never greenfield when a recipe is picked. |
| Recipe storage | **Fresh `recipes` table** — not an extension of `sow`. |
| Structure | Follow STRUCTURE.md **as strictly as possible**. Discovery → `ingestion/`. Restructure of legacy code AFTER Wave 1. |
| Build shape | Four features in parallel worktrees; backend merges before the UI that calls it; recipes backend merges earliest (widest blast radius, longest staging soak). |

## Prerequisites (outside the four lanes)

- **Staging `DATABASE_URL` fixed** (currently down) — every AC is a live-staging verification.
- **PR #379 merged** so the design archive/PRD are on `staging`.
- **Codex API access proven from the deploy environment** — day-1 step of the engines lane; the
  binary/API version gets pinned in the Dockerfile (the claude-code root-flag pin lesson,
  KNOWN_ISSUES "Root launcher").

---

## Feature 1 — Wow prefill (CBT-1/3/4)

**Owning context:** `research/` (facade already effectively exists: `research.py` + the SOF-155
`console/routers/research.py` router). No new packages.

**CBT-1 endpoint.** `POST /api/research/company` on the existing research router.
Body: `{name? | website? | email_domain?}` (≥1 required); query `depth=quick|deep`
(quick = Exa, deep = OpenRouter Fusion — both already implemented in `research.py`).
Response: the `CompanyProfile` fields, each as

```json
{ "value": "Industrial Distribution — MRO",
  "source": { "url": "https://acme-industrial.com/about", "label": "acme-industrial.com/about" } }
```

**No confidence field** — sources only. Read-only (no DB writes). Auth: normal session gate.
Errors are honest and actionable: missing `EXA_API_KEY` / Fusion config / provider failure return
the actual reason with the appropriate 4xx/5xx, never a fabricated guess. `depth=quick` is
latency-bounded (single Exa pass).

**CBT-4 concierge tool.** `enrich_company` in `concierge_tools.py`, calling the **same function**
the route calls and surfacing the **same errors** (philosophy §4: tool and button mirror one
function). The concierge offers lookup conversationally and must state which fields came back
without a source rather than asserting them.

**CBT-3 UI.** Fresh-mode intake leads with "Start with your website" (prefilled from the signup
email domain when not a public provider): lookup mini-log → found-company card (per-field value +
source label, per design `913d9c0`) → **"Use these details" is the only write path** (accept →
`PATCH /api/org` + form fill; nothing persists before accept). Same panel in Org admin as
"Enrich from web". Skeleton loading during lookup per the design-system rule.

**AC (live staging):** curl returns a real profile for `cbtcompany.com`; UI flow
domain→card→accept persists the org profile; wrong-guess path leaves fields editable; missing
provider key shows the real reason in both UI and tool result.

## Feature 2 — Codebase discovery (CBT-6/7)

**Owning context:** **`ingestion/`** (operator-adjudicated) — the capability is "acquire org
knowledge," whether from uploads (existing pipeline) or a repo crawl (new). Created per
STRUCTURE.md protocol #3 with the smallest coherent owner module: `src/software_factory/ingestion/discovery.py`
(+ `__init__.py`). Existing upload/extraction modules do **not** move in Wave 1.

**Mechanism.**
- Input: repo URL + PAT. PAT stored **write-only in the existing org-secrets vault** (`org_secrets`
  + `vault.py` pattern); never echoed back.
- Run: shallow clone (`--depth 1`) to a scratch dir → launch **one headless agent** (`claude -p`
  with a discovery SKILL prompt over the tree: framework, package manifests, CI, integrations,
  conventions) using the same child-owns-its-log launch pattern as stages (`_default_launch`
  shape) → agent writes `AGENTS.md`, `CLAUDE.md`, `integrations.md`.
- Output: the three files land as **org-scope knowledge-base blobs** (`blobs` scope='org' +
  `doc_summary` ingestion), so they flow into every future project's context through existing
  org-KB machinery — no new consumption path.
- Money/lifecycle (machinery is correct here): its own budget cap (`SF_DISCOVERY_COST_CEILING`,
  default 10) enforced by a supervisor check inside the module parsing the discovery log with the
  existing `streamlog.cost_usd`; kill at ceiling, record the honest state. Org jobs deliberately
  do **not** enter the project poller.
- Failure honesty: bad PAT / unreachable repo → the verbatim git error to UI and API.
- Re-run: allowed anytime; new artifacts version over the old (newest-wins, same as `product_brief`).

**Routes:** `POST /api/org/discovery` (start), `GET /api/org/discovery` (status + log tail,
plain polling — no new SSE surface). Transport stays thin; policy lives in
`ingestion/discovery.py`.

**CBT-7 UI.** Org-admin "Codebase discovery" section per design: repo connect form, live crawl
log, generated-docs list (source labels, no pills), each opening in the Artifact Viewer; re-run
action.

**AC (live staging):** run against a real test repo → three markdown artifacts on the org KB;
generated AGENTS.md opens in the viewer; bad PAT surfaces the actual git error; spend recorded
and capped.

## Feature 3 — Recipes (CBT-9)

**Owning context:** **`recipes/`** — a new bounded context (own table, own admin surface, consumed
by conversation + projects + execution; cross-context consumption is exactly what earns a context).
Smallest coherent owner: `src/software_factory/recipes/store.py` (table CRUD + validation policy +
the queries other contexts call). Routes stay in existing routers (thin transport).

**Storage — fresh `recipes` table** (operator-adjudicated; one Alembic revision):

```
recipes(id uuid PK, name text UNIQUE, tagline text, category text,
        capabilities jsonb,          -- customer-facing bullet list
        body_md text,                -- the recipe text (concierge/brief input)
        repo_url text,               -- the build-seed repo (nullable until connected)
        repo_tree jsonb,             -- indexed listing captured at validation
        images jsonb,                -- [{url, public: bool}]
        status text CHECK (draft|published|archived) DEFAULT 'draft',
        created_at, updated_at)
```

`sow` table and `SowStore` are **left untouched** (legacy; the OS panel swap + retirement is the
restructure's cleanup, flagged not smuggled). The scope-genre fallback (`_genre_recipes`)
continues to work unchanged for projects with **no** selected recipe.

**Authoring (Tenexity OS, staff-gated).** Recipes panel per design entry 31: edit customer-facing
fields + internal `repo_url`/images/body; status cycle draft→published→archived. **On save with a
`repo_url`: shallow-clone and require `AGENTS.md` or `CLAUDE.md` at the repo root — refuse the
save with exactly that reason if absent** (gate checks a fact, not judgment); capture `repo_tree`.
Customers only ever see the light fields of `published` recipes.

**Intake.** The picker sets `recipe_id` on the draft (`ProjectState.recipe_id`, JSON-blob field —
no schema change). From then on the **concierge context carries that recipe's `body_md` in place
of the SOW/genre text** (the existing injection point in `services/conversation.py` ~152: selected
recipe wins; scope-matching only when none selected). The interview and brief are built on the
recipe's frame.

**Promote.** `promote_draft` → `_provision_and_launch` passes the recipe body into
`input_pipeline.persist_and_compose` → written as `recipe.md` in `input/` (the existing
`genre_recipes_md` seam, renamed usage). PRD synthesis treats the recipe as the baseline: the PRD
specifies deltas/configuration on top of it.

**Build.** For a recipe project, `prepare_workspace` (workspace_setup.py) gains a `recipe`
parameter: (a) clone `repo_url` into the stage-3 workspace as the **starting tree**; (b) append
the fork-and-extend block to the stage SKILL contract: *"this app is forked from the recipe repo —
read its AGENTS.md, keep its architecture, implement tickets as extensions/modifications; never
scaffold from scratch."* Stages 1–2 receive the recipe's `AGENTS.md` as context so tickets target
real extension points. Everything downstream (deploy, QA loop, done-gates, budget, SOF-186
accounting) is untouched — a recipe build is an ordinary build with a non-empty starting tree.

**Honesty invariants:** no recipe selected → exactly today's behavior; draft/archived recipes are
never offered; a repo that fails validation can never become published, so a published recipe's
build seed is valid by construction.

**AC (live staging):** admin adds a repo-backed recipe (repo without AGENTS.md refused with that
reason); intake with the recipe selected produces a brief framed on it; a promoted run's stage-3
workspace starts from the recipe tree and the deployed app demonstrably extends it; a no-recipe
project behaves exactly as before.

## Feature 4 — Engine trio (CBT-13/14, SOF-200)

**Owning context:** existing seams — `console.py` is the sanctioned compatibility facade during
migration (STRUCTURE.md consolidation table), so the codex branch mirrors the opencode branch
in place; no new package.

**Adapter (CBT-13).**
- `_launch_stage`: `runtime == "codex"` argv branch — headless codex invocation (exact argv/flags
  resolved by the SOF-200 day-1 spike), model pinned to Codex 5.6, cwd = workspace so the SKILL
  contract loads.
- `_runner_key`: `codex → OPENAI_API_KEY` (BYOK-else-platform, existing precedence logic);
  `env.py` allowlist gains the key.
- `streamlog.py`: third event vocabulary (session keying + authoritative per-run cost when codex
  reports it, else token-estimate through a new `constants.PRICES` entry). SOF-186's monotonic
  accumulator applies unchanged — it is runtime-agnostic by construction.
- MCP: if codex cannot drive the required `.mcp.json` (playwright happy-flow hard gate), that is
  a **blocking finding reported to the operator** — not a silently skipped gate.
- Dockerfile: codex binary installed + version-pinned.
- **Kimi K3**: opencode model-id bump + `PRICES` entry (rider).

**UI (CBT-14).** EnginePicker → three cards (Claude Code default / Codex 5.6 / Kimi K3), value
shape `{provider, keySource, key}`; opencode's model sub-pick removed; console header badge +
process-tree label follow. UI merges **only after** the adapter runs a real stage (fully
functional button — no dead affordance in between).

**AC (live staging):** draft promoted with `runtime=codex` (via `create_draft`,
`budget_ceiling=10`) runs a real stage end-to-end with codex doing the coding; spend meters
against the cap; invalid key → honest error in UI and log; picker selection drives the real
runtime and BYOK state survives provider switches.

---

## `console.py` delta (complete list)

1. `_launch_stage`: codex argv branch + `_runner_key` map entry (~30 lines, mirrors opencode).
2. `promote_draft`/`_provision_and_launch`: when `state.recipe_id` is set — fetch recipe, pass
   `body_md` into `persist_and_compose`, stamp linkage (~10 lines at the existing call site).
3. Nothing else. Discovery never touches `console.py`; enrich never touches `console.py`;
   recipe workspace mechanics live in `workspace_setup.py`.

## Sequencing & merge order

Four worktrees in parallel (enrich / discovery / recipes / engines), integrator serializes
staging merges. Within each: backend PR → live-verify → UI PR. **Recipes backend merges first**
(concierge input + workspace prep + skills = widest shared surface; longest soak before the
27th). Engines UI merges last-in-lane (gated on a proven adapter run). Deploys avoid in-flight
runs (SOF-116).

## Verification policy

Per operator directive (no unit/integration tests): compile/build + exercise the real flow on
staging — curl for endpoints, `software-qa` browser runs for UI, one real budget-capped pipeline
run each for discovery, recipes, and codex. Every lane reports pass/fail against its AC lines
above; unverified items are reported as unverified, never claimed.

## Risks

- **Codex unknowns** (headless contract, MCP support, cost reporting) — day-1 spike gates the
  lane; findings land on SOF-200.
- **Staging down** — hard prerequisite; all ACs blocked until `DATABASE_URL` is fixed.
- **Recipe-seeded builds change stage-skill behavior** — the fork-and-extend SKILL block applies
  only when a recipe is selected, so non-recipe runs are provably unaffected; still the reason
  this lane merges first and soaks.
- **Supabase Storage egress quota (402)** — discovery artifacts persist via `artifacts.content` /
  blob manifest regardless; large-file storage writes may fail until quota resets — surfaced
  honestly, not retried into a wall.
