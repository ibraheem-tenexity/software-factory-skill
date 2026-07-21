# CBT Wave 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **VERIFICATION OVERRIDE (operator directive 2026-07-08, CLAUDE.md):** NO unit/integration
> tests — do not write or run them. Each task's cycle is: implement → compile/build → exercise
> the real flow (curl / browser / real pipeline run) → commit. The TDD steps normally required
> by plan format are replaced by real-flow verification steps below.

**Goal:** All four CBT Wave-1 features live on staging for the 27th: company-enrich wow prefill, codebase discovery, repo-backed recipes with fork-and-extend builds, and the engine trio.

**Architecture:** Four independent lanes in parallel worktrees (PRs → `staging`; backend merges before the UI that calls it; recipes backend merges first). New code follows `docs/STRUCTURE.md` ownership: `recipes/` (new context), `ingestion/` (new context), `research/` capability stays at its existing seams, engines extend the sanctioned `console.py` facade.

**Tech Stack:** FastAPI + psycopg3/SQLAlchemy-core (Alembic), LangChain concierge (`@tool`), React/Vite/TS console, `claude -p` headless agents.

**Spec:** `docs/superpowers/specs/2026-07-21-cbt-wave1-design.md` — its **Philosophy audit** section binds every task: fork-and-extend / discovery analysis / concierge behavior are PROMPT-delivered; the only machinery allowed is money caps, file-EXISTS fact gates, cost accounting, and data filters. No state machines, no readiness flags, no compliance checkers.

## Global Constraints

- PRs target `staging`; never push `staging`/`main` directly; worktrees under `.claude/worktrees/`.
- Every PR description states its owning context (STRUCTURE.md parallel-dev protocol #2).
- Test/verify projects ONLY via `Console.create_draft()` + promote, `budget_ceiling=10` (SOF-23 — a seeded row costs real money).
- New Python deps (if any) go in `pyproject.toml` AND nothing else (SOF-48); lazy imports get added to `scripts/verify_deps.py`.
- Every migration is idempotent-safe incremental Alembic; rehearse per the seed+stamp recipe (SOF-61: full-chain on fresh DB is broken — do not "fix" it in these lanes).
- Sources only, product-wide: no confidence field, pill, or tier anywhere.
- Honest errors: tool and route call the same function and surface the same error text.
- Prerequisites before any live-verify AC: staging `DATABASE_URL` fixed; PR #379 merged.

---

# LANE A — Recipes (owning context: `recipes/`, merges first)

### Task A1: `recipes` table + store

**Files:**
- Modify: `src/software_factory/models.py` (add table after the `sow` table definition)
- Create: `migrations/versions/0029_recipes_table.py`
- Create: `src/software_factory/recipes/__init__.py`
- Create: `src/software_factory/recipes/store.py`

**Interfaces:**
- Produces: `RecipeStore.list_all() -> list[dict]`, `get(recipe_id: str) -> dict|None`,
  `create(name: str, **fields) -> dict`, `update(recipe_id: str, fields: dict) -> dict|None`
  (raises `recipes.store.RecipeValidationError(reason)` when publishing/saving with a bad repo),
  `published() -> list[dict]` (light fields only: id, name, tagline, category, capabilities,
  public images), `body(recipe_id: str) -> str|None`, `repo_url(recipe_id: str) -> str|None`.

- [ ] **Step 1: models.py table** (mirror the existing `sow` Table style exactly):

```python
recipes = Table(
    "recipes", metadata,
    Column("id", Uuid, primary_key=True, server_default=text("gen_random_uuid()")),
    Column("name", Text, nullable=False, unique=True),
    Column("tagline", Text),
    Column("category", Text),
    Column("capabilities", JSONB, server_default=text("'[]'::jsonb")),  # customer-facing bullets
    Column("body_md", Text),          # recipe text — concierge/brief input
    Column("repo_url", Text),         # build-seed repo (nullable until connected)
    Column("images", JSONB, server_default=text("'[]'::jsonb")),  # [{url, public: bool}]
    Column("status", Text, nullable=False, server_default=text("'draft'")),
    Column("created_at", DateTime(timezone=True), server_default=func.now()),
    Column("updated_at", DateTime(timezone=True), server_default=func.now(), onupdate=func.now()),
    CheckConstraint("status IN ('draft','published','archived')", name="recipes_status_check"),
)
```

- [ ] **Step 2: migration 0029** — `down_revision = "0028_org_name_unique"` (verify with
  `ls migrations/versions/`), explicit `op.create_table(...)` matching Step 1 exactly (frozen DDL
  like every post-baseline revision; NEVER via `create_all`).

- [ ] **Step 3: `recipes/store.py`** — follow `sow.py::SowStore`'s repository/exec pattern
  (GlobalExec-backed, parameterized SQL only). Validation policy — the ONE fact gate:

```python
class RecipeValidationError(Exception):
    """Raised with the honest, user-visible reason a recipe save was refused."""

def _validate_repo(repo_url: str) -> None:
    """Shallow-clone to a temp dir; require AGENTS.md or CLAUDE.md at the root.
    File-EXISTS fact check only (philosophy: gates check facts). Clone is discarded."""
    with tempfile.TemporaryDirectory() as tmp:
        r = subprocess.run(["git", "clone", "--depth", "1", repo_url, tmp],
                           capture_output=True, text=True, timeout=120)
        if r.returncode != 0:
            raise RecipeValidationError(
                f"could not clone {repo_url}: {(r.stderr or r.stdout).strip()[-500:]}")
        if not (os.path.exists(os.path.join(tmp, "AGENTS.md"))
                or os.path.exists(os.path.join(tmp, "CLAUDE.md"))):
            raise RecipeValidationError(
                f"{repo_url} has no AGENTS.md or CLAUDE.md at the repo root — a recipe repo "
                f"must document its architecture/extension points before it can be saved")
```

`create`/`update` call `_validate_repo` whenever `repo_url` is set/changed. `published()` is a
`WHERE status='published'` returning ONLY light fields + `[i for i in images if i.get("public")]`.

- [ ] **Step 4: compile + migration rehearsal** —
  `PYTHONPATH=src .venv/bin/python -c "import software_factory.recipes.store, software_factory.models"`;
  rehearse 0029 against a scratch DB via the seed+stamp recipe (stamp 0028 → upgrade head →
  `\d recipes` shows the table).

- [ ] **Step 5: Commit** `feat(recipes): recipes table + store with repo fact-gate validation (CBT-9)`

### Task A2: admin + customer routes

**Files:**
- Modify: `console/routers/admin_os.py` (beside the `/api/admin/sow` block, ~line 152)
- Modify: `console/routers/projects.py` (customer-facing published list)
- Modify: `console/schemas.py` (RecipeIn body)
- Modify: `console/state.py::reset()` (wire `state.recipes = RecipeStore()`)

**Interfaces:**
- Consumes: `RecipeStore` (A1). Produces routes:
  `GET/POST /api/admin/recipes`, `GET/PATCH /api/admin/recipes/{id}` (staff-gated,
  `Depends(require_staff)`, mirror the sow handlers 1:1);
  `GET /api/recipes` → `state.recipes.published()` (any authed viewer — the intake picker source).

- [ ] **Step 1: routes** — thin transport only; `RecipeValidationError` maps to HTTP 400 with the
  exception's own message (register alongside the `services/errors.py` handler pattern in
  `console/app.py` — one `@app.exception_handler(RecipeValidationError)` returning
  `{"detail": str(exc)}`, status 400). The refusal text the admin sees is EXACTLY the store's reason.
- [ ] **Step 2: verify live-shape locally** — boot the console against local PG, then:
  `curl -X POST :8000/api/admin/recipes -d '{"name":"t","repo_url":"https://github.com/org/repo-without-agents-md"}'`
  → expect 400 with the "no AGENTS.md or CLAUDE.md" reason verbatim; a repo WITH AGENTS.md → 200.
- [ ] **Step 3: Commit** `feat(recipes): admin CRUD + published picker routes (CBT-9)`

### Task A3: recipe → draft → concierge → stage-1 input

**Files:**
- Modify: `src/software_factory/projectstate.py` (`recipe_id: str = ""` dataclass field + add `"recipe_id"` to `_PERSISTED`)
- Modify: `console/routers/projects.py` (draft PATCH accepts `recipe_id`; validate it names a `published` recipe, else 400 with the real reason)
- Modify: `src/software_factory/services/conversation.py:146-155`
- Modify: `src/software_factory/console.py::_provision_and_launch` (the `persist_and_compose` call, ~line 1394)
- Modify: `src/software_factory/input_pipeline.py::persist_and_compose` (new `recipe_md: str | None = None` param)

**Interfaces:**
- Consumes: `RecipeStore.body(recipe_id)`, `get(recipe_id)` (A1).
- Produces: `input/recipe.md` in the Stage-1 composition; recipe body in concierge context.

- [ ] **Step 1: conversation context swap** — at the existing injection point (`### Statement of
  Work` at line 146 / genre recipes at 148–155): when `state.recipe_id` is set, fetch the body and
  emit **instead of** the SOW + genre sections:

```python
recipe_body = state.recipe_id and RecipeStore().body(state.recipe_id)
if recipe_body:
    r = RecipeStore().get(state.recipe_id)
    sections.append(f"### Recipe: {r['name']} (this project builds FROM this recipe)\n"
                    f"{recipe_body}")
else:
    # unchanged legacy path: SOW section + _genre_recipes(scope)
```

  The framing sentence is the prompt doing the work — no brief-matches-recipe validator exists.
- [ ] **Step 2: stage-1 input** — `persist_and_compose(..., recipe_md=...)` writes `recipe.md`
  verbatim into `input/` (mirror the `genre_recipes_md` block); `_provision_and_launch` passes
  `recipe_md=RecipeStore().body(state.recipe_id) if state.recipe_id else None`.
- [ ] **Step 3: verify locally** — mint an authed session (memory: `auth.sign_session` trick),
  create a draft, `PATCH` a published `recipe_id` onto it, hit `/api/chat` once → the model
  context (log the composed sections at debug) carries the Recipe section; promote a
  budget-capped draft → `input/recipe.md` exists with the body.
- [ ] **Step 4: Commit** `feat(recipes): selected recipe drives concierge context + stage-1 input (CBT-9)`

### Task A4: build seed + fork-and-extend SKILL block

**Files:**
- Modify: `src/software_factory/workspace_setup.py::prepare_workspace` (signature at line 245: add `recipe: dict | None = None`)
- Modify: `src/software_factory/console.py::_launch_stage` (~line 1235, the `prepare_workspace(...)` call: resolve `state.recipe_id` → `RecipeStore().get(...)` → pass through)

**Interfaces:**
- Consumes: `RecipeStore.get()` → `{name, repo_url, body_md, ...}`.
- Produces: stage-3 workspace pre-seeded with the recipe tree; SKILL contract appended for all stages of a recipe project.

- [ ] **Step 1:** in `prepare_workspace`, after the SKILL contract is written (including any
  `skill_override`), when `recipe` is set append to `ws/SKILL.md`:

```python
if recipe:
    block = (f"\n\n## RECIPE BUILD — {recipe['name']}\n"
             f"This app is FORKED from the recipe repository ({recipe['repo_url']}). "
             f"Its working tree is already in this workspace. Read its AGENTS.md first; keep its "
             f"architecture and conventions; implement the tickets as extensions and modifications "
             f"of this codebase. Never scaffold a new app from scratch.\n")
    with open(os.path.join(ws, "SKILL.md"), "a") as f:
        f.write(block)
    if stage == 3 and recipe.get("repo_url") and not os.path.exists(os.path.join(ws, "AGENTS.md")):
        subprocess.run(["git", "clone", "--depth", "1", recipe["repo_url"], ws + "/seed"],
                       check=True, timeout=180)
        # move seed/* into ws root, drop seed/.git (fresh history — the factory pushes its own repo)
```

  Stages 1–2: also copy the seed's `AGENTS.md` into `ws/context/recipe-AGENTS.md` so tickets
  target real extension points. Clone failure at launch = honest launch refusal with the git
  error recorded as a blocker (same shape as MCP hard-gate refusals).
- [ ] **Step 2: verify** — promote a $10-capped draft with a recipe against a tiny real seed repo;
  confirm the stage-3 workspace starts from the seed tree and `SKILL.md` carries the block. There
  is deliberately NO code checking the agent "really forked" — outcome gates are the proof.
- [ ] **Step 3: Commit** `feat(recipes): recipe repo as build seed + fork-and-extend SKILL block (CBT-9)`

### Task A5 (WEB, merges after A1–A4): intake recipe picker

**Files:**
- Modify: `console/web/src/components/onboarding/OnboardingScreen.tsx`
- Modify: `console/web/src/api.ts` (`listRecipes(): Promise<RecipeLight[]>` → `GET /api/recipes`; draft PATCH gains `recipe_id`)

Visual source: `design/optionC.jsx` `RecipePicker` (card grid, light fields + "No template",
value = recipe id or null). Skeleton while loading (design-system rule). Selecting a card PATCHes
`recipe_id` onto the draft immediately (it's a draft-enrichment write, not a silent side effect —
the card shows the selected state as confirmation).

- [ ] Implement, build (`npm run build` in `console/web`), browser-verify on the live flow:
  picker renders published recipes only; select → PATCH fires → reload shows it selected.
- [ ] Commit `feat(web): recipe picker in intake (CBT-9)`

### Task A6: lane AC (live staging)

- [ ] Admin adds a repo-backed recipe; repo without AGENTS.md refused with exactly that reason.
- [ ] Intake with recipe selected → interview/brief framed on it (read the brief artifact).
- [ ] Promoted $10-cap run: stage-3 workspace starts from the recipe tree; deployed app extends it.
- [ ] A NO-recipe project behaves byte-identically to today (SOW/genre path untouched).

---

# LANE B — Wow prefill (owning context: `research/` seams)

### Task B1: `POST /api/research/company`

**Files:**
- Modify: `console/routers/research.py` (beside `research_fusion`, line 22)
- Modify: `console/schemas.py` (`CompanyEnrichIn`)
- Modify: `src/software_factory/research.py` (deep-mode synthesis prompt: per-field sources)

**Interfaces:**
- Consumes: `research.research_company(name, *, website=None, extra=None, mode="quick"|"deep") -> CompanyProfile` (raises `ResearchError` with the honest reason — e.g. "EXA_API_KEY is not set — required for mode='quick'").
- Produces: JSON = `CompanyProfile.to_dict()` + optional `field_sources: dict[str, str]`.

- [ ] **Step 1: route** — body `{name?, website?, email_domain?}` (≥1 required, else 422);
  `name` defaults to the domain stem when only a domain is given; `?depth=quick|deep` maps to
  `mode`. `ResearchError` → HTTP 502 `{"detail": str(exc)}` (provider truth, never a guess).
  Read-only — no DB writes. NOTE: deep mode measures 165–180s (SOF-79) — set the route's own
  timeout tolerance accordingly; the UI only ever calls `quick`.
- [ ] **Step 2: per-field sources, prompt-side (max-prompt)** — in the deep-mode Fusion synthesis
  prompt (where `_synthesized_profile` output is specified), add: *"for each profile field you
  fill, also emit `field_sources: {<field>: <url you actually used>}` — omit any field you cannot
  attribute to a specific consulted URL; never invent one."* Parse it if present; the endpoint
  passes it through. Quick mode gets no per-field map — the overall `sources` list serves. No
  parser heuristics, no fabrication.
- [ ] **Step 3: verify** — `curl -X POST :8000/api/research/company?depth=quick -d '{"website":"cbtcompany.com"}'`
  with a real `EXA_API_KEY` → profile JSON with `sources`; unset key → 502 with the exact
  ResearchError text.
- [ ] **Step 4: Commit** `feat(research): company-enrich endpoint, sources only (CBT-1)`

### Task B2: concierge `enrich_company` tool

**Files:**
- Modify: `src/software_factory/concierge_tools.py` (inside `build_project_tools`, one more `@tool`)
- Modify: `src/software_factory/chat_agent.py::CONCIERGE_INSTRUCTIONS`

- [ ] **Step 1: tool** — wraps the SAME `research_company` call with the SAME error surface:

```python
@tool
def enrich_company(name: str = "", website: str = "") -> str:
    """Look a company up on the web (quick mode). Returns profile fields + the source URLs
    consulted. Use when the user hasn't described their company yet and agrees to a lookup."""
    try:
        p = research_company(name or website, website=website or None, mode="quick")
        return json.dumps(p.to_dict())
    except ResearchError as e:
        return f"lookup failed: {e}"   # truth degrades the answer, never kills the conversation
```

- [ ] **Step 2: prompt lines** (judgment lives HERE, not in code) — append to
  `CONCIERGE_INSTRUCTIONS`: offer a lookup when company context is missing ("want me to look you
  up?"); present results with their sources; say plainly which fields came back without a source
  instead of asserting them; never write org fields without the user's explicit confirmation.
- [ ] **Step 3: verify** — live concierge session: ask "look up cbtcompany.com" → tool fires,
  reply cites sources and flags unsourced fields.
- [ ] **Step 4: Commit** `feat(concierge): enrich_company tool + instruction lines (CBT-4)`

### Task B3 (WEB, after B1): found-company card

**Files:**
- Modify: `console/web/src/components/onboarding/OnboardingScreen.tsx` (fresh mode)
- Modify: org-admin profile screen component (locate: `grep -rn "Enrich" console/web/src` after PR #379's WEB groundwork; else the org profile section component)
- Modify: `console/web/src/api.ts` (`enrichCompany(body): Promise<Profile>` → B1, always `depth=quick`)

Visual source: `design/discovery.jsx` `EnrichFromWeb`/`FoundCompanyCard`/`MiniLog` **as amended
by commits `aac5660`/`913d9c0`** — per-field source label, NO pills. Behavior contract: lookup
shows the mini-log (skeleton rule); results render as the found-card; **"Use these details" is
the only write** (`PATCH /api/org` + form fill); "not right" leaves fields editable; fields
without a per-field source show the overall-sources chip.

- [ ] Implement, `npm run build`, browser-verify the full accept and reject paths + slow-lookup skeleton.
- [ ] Commit `feat(web): wow prefill found-company card, sources only (CBT-3)`

### Task B4: lane AC (live staging)

- [ ] curl returns a real profile for `cbtcompany.com` (quick, bounded).
- [ ] Intake: domain → card → accept persists org profile; reject leaves editable; no write before accept.
- [ ] Missing provider key: UI and tool both show the real reason.

---

# LANE C — Codebase discovery (owning context: `ingestion/` — NEW package, smallest coherent owner)

### Task C1: discovery module

**Files:**
- Create: `src/software_factory/ingestion/__init__.py` (empty)
- Create: `src/software_factory/ingestion/discovery.py`

**Interfaces:**
- Produces: `start(org_id: str, repo_url: str, pat_secret: str | None) -> dict` (refuses with the
  honest reason if one is already running for the org); `status(org_id: str) -> dict`
  (`{running: bool, log_tail: str, artifacts: list[dict], spent_usd: float}` — a PROJECTION of
  the live process + log + blobs; no stored state machine).

- [ ] **Step 1: the run** — module-level `_procs: dict[str, subprocess.Popen]` +
  `/data/org/<org_id>/discovery/` scratch (log + clone). Flow: resolve PAT from the org-secrets
  vault (existing `org_secrets` + `vault.py` retrieve pattern — never logged, never echoed) →
  `git clone --depth 1` (authed URL) → launch ONE headless agent with stdout appended directly
  to `discovery.log` (copy `_default_launch`'s child-owns-fd + drop-privileges pattern from
  `console.py:232` — do NOT import console; this is an org job, not a stage):

```python
argv = ["claude", "-p", DISCOVERY_PROMPT, "--model", "claude-sonnet-4-6",
        "--dangerously-skip-permissions", "--output-format", "stream-json", "--verbose"]
# cwd = the clone dir; DISCOVERY_PROMPT (module constant) instructs the agent to WRITE
# AGENTS.md, CLAUDE.md, integrations.md at the clone root describing framework, install/test
# commands, CI, integrations, conventions, extension points — citing file paths as sources.
# ALL analysis judgment lives in this prompt. Code never parses manifests.
```

- [ ] **Step 2: money (sanctioned machinery)** — a `threading.Timer`-driven check every 15s:
  `streamlog.cost_usd(open(log).read())` ≥ `float(os.environ.get("SF_DISCOVERY_COST_CEILING", "10"))`
  → SIGTERM→5s→SIGKILL, final line appended to the log stating the cap stop. On process exit
  (watcher thread `p.wait()`): read the three files from the clone root; any missing file is
  simply absent from results (the log shows why — no completeness gate); persist each present
  file via the org-KB write path — mirror the persistence block of the org knowledge-base upload
  route in `console/routers/org.py` (BlobStore + `blobs` scope='org' + the same memory-ingestion
  call it makes), then delete the clone.
- [ ] **Step 3: verify locally** — run `start()` against a small real repo with a real key;
  watch `status()` progress; confirm 3 blobs land org-scoped; bad PAT → the verbatim git error
  in the returned refusal.
- [ ] **Step 4: Commit** `feat(ingestion): codebase discovery pipeline — prompt-driven, budget-capped (CBT-6)`

### Task C2: routes

**Files:**
- Modify: `console/routers/org.py` — `POST /api/org/discovery {repo_url, pat_secret?}` → `ingestion.discovery.start(...)`; `GET /api/org/discovery` → `status(...)`. Org-admin authz same as other org-mutation routes in that file. Thin transport.

- [ ] Implement; curl-verify start/status/refusal shapes locally; commit `feat(ingestion): discovery routes (CBT-6)`

### Task C3 (WEB, after C1/C2): org discovery section

**Files:**
- Modify: org-admin screen (`console/web/src/` — the §2.3 sub-nav component) + `api.ts` (`startDiscovery`, `discoveryStatus` with 3s polling while `running`)

Visual source: `design/discovery.jsx` `DiscoverySection` (913d9c0 state — sources, no pills):
repo form, live crawl log, generated-docs list opening in the Artifact Viewer, re-run action.

- [ ] Implement, build, browser-verify against a real local run; commit `feat(web): codebase discovery UI (CBT-7)`

### Task C4: lane AC (live staging)

- [ ] Real test repo → three markdown artifacts on the org KB; AGENTS.md opens in the viewer.
- [ ] Bad PAT surfaces the actual git error in the UI.
- [ ] Spend visible; cap kill works (set `SF_DISCOVERY_COST_CEILING=0.05` once to prove the brake, then restore).

---

# LANE D — Engine trio (owning context: existing `console.py` facade + `streamlog`)

> **D-gate:** the Codex research (headless invocation, event stream, cost signal, MCP/SKILL
> compatibility) is owned by a SEPARATE agent on **SOF-200**. Tasks D2–D4 consume its findings;
> do not duplicate the research. D1 is independent — start immediately.

### Task D1: Kimi K3 bump (independent)

**Files:**
- Modify: `src/software_factory/console.py` `_OPENCODE_MODEL_IDS` (alias `kimi` → the K3 OpenRouter id from SOF-200/operator; keep `glm` untouched)
- Modify: `src/software_factory/constants.py` `PRICES` (K3 entry) + `src/software_factory/streamlog.py::OPENCODE_FALLBACK_MODEL`

- [ ] Implement; verify by launching one $10-capped opencode draft on staging and reading the
  model id in `project.log`; commit `feat(engines): Kimi K3 model bump (CBT-13 rider)`

### Task D2 (gated on SOF-200): codex adapter

**Files:**
- Modify: `src/software_factory/console.py::_launch_stage` — third argv branch (`runtime == "codex"`), mirroring the opencode branch's shape: argv from SOF-200's invocation contract, `_runner_key` gains `codex → OPENAI_API_KEY`, model pinned to Codex 5.6.
- Modify: `src/software_factory/env.py` — `OPENAI_API_KEY` joins the stage-env allowlist for codex runs only.
- Modify: `src/software_factory/streamlog.py::cost_usd` — third event vocabulary per SOF-200's log contract (session keying + authoritative cost else token-estimate via a new `PRICES` entry). SOF-186's accumulator applies unchanged.
- Modify: `Dockerfile` — codex binary installed and **version-pinned** (the claude-code pin lesson).
- Modify: `src/software_factory/projectstate.py` runtime docstring + promote-path provider→runtime mapping: UI providers `claude|codex|kimi` map to runtimes `claude|codex|opencode(K3)`.

- [ ] If SOF-200 finds codex cannot drive `.mcp.json`/playwright: STOP, report to the operator
  (blocking finding — the happy-flow gate is never silently skipped).
- [ ] Verify: `create_draft` → promote with `runtime=codex`, `budget_ceiling=10`, real stage
  end-to-end on staging; spend meters; invalid key → honest error. Commit
  `feat(engines): codex runtime adapter (CBT-13, SOF-200)`

### Task D3 (WEB, only after D2 proven live): engine trio picker

**Files:**
- Modify: `console/web/src/components/onboarding/OnboardingScreen.tsx:136-180` — `EngineValue` becomes `{ provider: "claude" | "codex" | "kimi"; keySource: "tenexity" | "byok"; key: string }`; three cards (Claude Code default / Codex 5.6 / Kimi K3, vendor labels per design entry 36); opencode model sub-pick removed; BYOK segment unchanged (key cleared when BYOK left — preserve the existing focus-loss comment's constraints); console header badge + process-tree label follow (`buildprogress` equivalent in the live console).

- [ ] Implement, build, browser-verify: selection persists write-through, badge matches, provider
  switches don't drop BYOK state. Commit `feat(web): engine trio picker (CBT-14)`

### Task D4: lane AC (live staging)

- [ ] Codex draft runs a real stage end-to-end; spend meters against the cap; picker drives it.

---

# Coordination

**Merge order:** A1→A4 (recipes backend) FIRST, then B/C/D backends as ready, each lane's WEB PR
after its backend is live-verified; D3 strictly after D2's live run. Integrator serializes staging
deploys; avoid pushing while a watched run is mid-stage (SOF-116).

**Dispatch:** one session per lane in its own worktree off current `origin/staging`
(`.claude/worktrees/cbt-w1-{recipes,enrich,discovery,engines}`), each PR naming its owning
context. Each session receives: this plan (its lane section + Global Constraints + Coordination),
the spec, and the design-archive file paths named in its tasks.

**Done reporting:** each lane reports pass/fail per its AC checklist — unverified is reported as
unverified, never claimed.
