# Software Factory — Product Requirements (screen spec)

> Source of truth for build agents. Describes every screen in the prototype
> (`Software Factory Onboarding.html`), what it does, its components, data, and
> interactions. Visual system = Tenexity design system (see §1).
>
> **Authority (SOF-224):** this document is the **single product-requirements
> authority** for the Software Factory. Every requirement change updates this
> file in the same change. When sources disagree, the order is: 1) operator
> directives in `CLAUDE.md`, 2) dated operator-approved decisions, 3) **this
> file**, 4) architecture/implementation docs, 5) visual artboards (future
> concepts explicitly labeled). Documents that once carried requirements —
> `docs/product-spec-software-factory.md` (deleted; folded in here), the CBT
> Wave-1 design doc, the project-memory build plan (both kept as records) —
> are consolidated below (§8 metrics/priorities/risks, §9 adjudication log)
> and no longer define requirements.

---

## 0. Product in one paragraph

Software Factory turns a described business problem into shipped software. A
customer (an industrial / IT-distribution company) creates a project, gives the
factory context (company profile, business process, documents, connected
systems), and an agent pipeline researches → writes a PRD → architects → designs
screens → generates tickets → builds → tests → deploys. A **Concierge** agent
guides the customer through intake and stays with them through the build,
relaying progress and letting them steer the build agents. **Tenexity OS** is the
internal operator portal over all tenants, projects, agents, and tools.

There are two audiences / two app surfaces:
- **Customer product** — login, projects dashboard, org admin, project onboarding, project dashboard, factory console.
- **Tenexity OS** — internal operator portal (platform staff).

### 0.1 Product principles (the test every feature is checked against)

1. **Never a blank, silent screen.** Loading shows a shaped placeholder; long
   work shows visible, specific progress — never a spinner for an unknown wait.
2. **One assistant, one identity, everywhere.** The Concierge is the same
   character with the same voice on every project screen; only its focus changes.
3. **Nothing is created by accident.** State-changing actions are explicit, named, and confirmed.
   Project creation belongs only to **Create project**. A build may start from the named **Hand off
   to factory** button or from the Concierge's real handoff tool after clear conversational
   agreement; a successful handoff always moves the UI to the Factory Console. Navigation and
   unrelated Concierge messages never create or start anything.
4. **Show sources, don't invent a score.** Every inferred fact is traceable to
   exactly where it came from (file, upload, answer, url) — the system never
   asserts a confidence level it has no real way to compute.
5. **Progress is resumable, never fragile.** Everything produced is saved as
   it's produced; a failure or pause never means starting over.
6. **Momentum beats completeness.** The job is a *good* brief fast, not a
   perfect interrogation — the customer's own "that's enough, build it" decides
   readiness.

### 0.2 Personas

| Persona | Who | What they need |
|---|---|---|
| **Operator / Owner** | Runs a piece of the business (ops, sales, IT); not a developer | Describe a problem in their own words and trust it was understood |
| **Org Admin** | Sets up the company once — profile, systems, team, billing | A one-time setup, never repeated, visibly reused |
| **Returning user** | Has shipped projects | Zero repetition of anything already known; a 90-second path to the next project |
| **Internal Operator** | Tenexity staff | Fleet-wide visibility; unblock/support any customer directly; control over agents and tools |

---

## 1. Design system (apply to every screen)

- **Brand** `#1A7BFF` (deep `#0958C9`, soft `#E8F1FF`). Bg `#FAFAFA`, raised `#FFF`, sunken `#F4F4F5`.
- **Type**: Hanken Grotesk (UI/sans), Georgia (display/headlines), JetBrains Mono (data, labels, technical).
- **Category labels**: 11px, uppercase, letter-spacing 0.12em, tertiary color.
- **Sources, not confidence tiers** (operator ruling, 2026-07-21; product Principle 4): AI-derived values NEVER show an asserted confidence level — we have no evidence-derived way to compute one. Every AI-derived value carries a **source label** instead (mono, link icon; url, file name, or crawl step). The former Exact/High/Medium/Low/Unknown pill cascade is retired product-wide.
- **AI tell**: AI-derived/unconfirmed values get a faint brand tint + inset brand bar + sparkle (`.ai-tint`).
- **Conversation**: single bubble shape, identified by avatar + name, never by left/right alternation. The two speakers are distinguished by **fill color**: the **Concierge/agent** bubble is a solid brand-soft fill (`T.brandSoft`) with a brand left-accent bar (inset `3px` `T.brand`) and a brand-tinted border; the **user** bubble is a solid neutral fill (`T.sunken`) with a default border. (These replaced the near-identical near-white treatments that made the two speakers hard to tell apart.)
- **Focus ring**: 2px offset white + brand ring on all interactive elements.
- Radii 6/8/12/16px. Tasteful shadows only (xs/sm/md). No gradients-as-decoration, no emoji.

### 1.1 Loading & fetch states (apply to every data-bound surface)

Everything read from the database renders a **skeleton** while in flight, then swaps to real content. The rule: **no list, table, card, or fetched field ever appears empty or pops in without a placeholder.** One shimmer treatment (`.sf-skel`) under a kit of typed placeholders in `skeletons.jsx`; each skeleton **mirrors the exact shape and size** of what it replaces so layout never shifts.

- **Primitives:** `Skel` (base shimmer block), `SkelLine`, `SkelCircle` (avatar), `SkelPill`, `SkelChip`, `SkelBar` (progress), `SkelInput`, `SkelBtn`, `SkelBadge`, plus `Spinner` (inline circular — for **action-level** waits like a Save button, *not* for list loads).
- **Field types:** `SkelText` (paragraph), `SkelKV` (one label/value), `SkelField` (form field), `KVGridSkel` (profile / detail grids).
- **Per-surface composites:** `MetricCardSkel`, `ProjectRowSkel` (dashboard list), `FileTileSkel` (documents), `TableRowSkel` (generic data table — pass the column template + per-cell shapes: `user` / `pill` / `badge` / `menu` / number-width), `ListRowSkel` (systems · team · agents), `KanbanCardSkel`, `MessageSkel` (Concierge), `PanelBodySkel` (zone panels).
- **Component contract:** data-bound screens take a **`loading`** prop and render their matching skeletons when true — wired into `Dashboard`, `OrgAdmin`, `ProjectDashboard`, and `UsersManagement`. `FetchDemo` (showcase only) replays a real fetch so the loading→loaded swap is reviewable.
- **Reduced motion:** the shimmer sweep is replaced by a gentle opacity pulse on the static block.

Shared primitives (in `shared.jsx`): `Btn`, `TextInput`, `TextArea`, `Field`,
`Chip(s)`, `IndustryTile`, `Dropzone` (+ per-file description & scope), `IntegrationRow`,
`StatusPill`, `Avatar`, `AiTint`, `Message`, `Composer`, `Wordmark`,
`CategoryLabel`, `SectionDivider`, `ScopeToggle`, `Icon`, `Sparkle`.

---

## 2. CUSTOMER PRODUCT

### 2.1 Login  (`login.jsx` → `Login`, gated by `AppRoot`)
**Purpose:** authenticate and enter the product.
**Layout:** two-pane. Left = dark brand panel (wordmark, value prop, decorative
process-node graph). Right = auth form.
**Auth options — current vs future (SOF-15 adjudication):**
- **Current (shipping):** **Google** (official mark) and **email + password**
  (show/hide toggle). These are the only paths that are real and verified today.
- **Future — do NOT build until a real provider verifies them:** **Microsoft**,
  **organization SSO** (SAML/OIDC work-domain entry), the **forgot-password**
  link, and the **SOC-2 trust line**. Per operator directive (SOF-15): never
  render provider-replica sign-in buttons, mock SSO/credential affordances, or
  unverifiable trust badges — a dead affordance is a dishonest one (Principle:
  honest errors, everywhere).
**Footer:** "Request access" for users not yet on the allow-list.
**Behavior:** any successful auth → projects dashboard — **except an invited user's first sign-in**, which routes to first-time onboarding (§3.7 chain, §2.4 fresh mode, website prefilled from the email domain). Sign-in is gated by the
allow-list managed in Tenexity OS (§3.7).

### 2.2 Projects dashboard  (`dashboard.jsx` → `Dashboard`; nav shell `FactoryApp`)
**Purpose:** the home screen after login; list the org's projects.
**Top bar:** wordmark · org switcher (→ Org admin) · search · user avatar.
**Body:**
- Header "Your projects" + **New project** CTA + **Explore** (compass icon) — the recipe
  inspiration gallery (§2.8), a destination separate from starting a project.
- **Pulse strip** (4 metric cards): Active projects / In build / Deployed / Spend this month.
- **Org admin preview** (admins only): a compact, clickable preview of the organization (industry, scale, knowledge-base count, connected systems, team) with **Manage organization →** to the org admin page. Gated on `isAdmin` — **non-admin users see nothing in its place** (the list simply moves up). Replaces the former Concierge brief.
- **Project list**, in **collapsible groups** ordered **Deployed** (top), then **In progress**, then **Archived** (only when non-empty). Each group header is a click-to-toggle button with a rotating chevron; the group's count stays in the header while collapsed. Each row: owner avatar, name, status pill, phase + progress bar, agents (avatar stack), last activity, spend, and an overflow (⋯) menu. A **team-member filter** ("All team members") in the header filters all groups by project owner.
- **Archive / delete a project** — each row's ⋯ menu offers **Archive project**; archiving (after a **confirmation modal**) moves it to an **Archived** section, stops running agents, and pauses the automation. Archived rows get a ⋯ menu with **Restore project** (non-destructive, no confirm) and **Delete permanently** (destructive — guarded by a confirmation modal that names the project; removes it and its build history). The Archived section only appears once something is archived.
**Statuses:** Building, Researching, Needs input, Draft, Deployed.
**Behavior:** click a project → its **project view** (Overview tab). Draft → onboarding (§2.4). New project → onboarding. Org switcher → Org admin.

### 2.3 Organization admin  (`orgproject.jsx` → `OrgAdmin`)
**Purpose:** the org's context + org-scoped documents, reused by every project.
**Layout:** left sub-nav + content. Sections:
- **Company profile** — canonical org context (name, industry, sub-focus, HQ, founded, headcount, revenue, website, footprint). Editable. Note: Concierge reuses this to skip questions on new projects. Header action **Enrich from web** opens the same web-prefill flow as first-time intake (§2.4, `EnrichFromWeb`): look the company up → confirm the ai-tint found-card → profile fields update. Nothing writes until the user accepts.
- **Brand & theme** (`ThemeSection`, `discovery.jsx`) · **WAVE 2 — designed, not yet shipping** — the org's look as a token pack. **Process theme from my website**: domain → `MiniLog` of the crawl (palette/type/logo) → found pack: color rows (swatch + role + hex + source label), type stack, logo tile, and a **live preview** strip rendering a generated app shell in the found theme. Copy states the pack is applied to every Kimi K3 mockup (§2.6 design review) and every app the factory builds for the org; an existing `brand-guidelines.pdf` in the knowledge base is named as the fallback source.
- **Knowledge base** — org-scoped documents (price book, line card, policies, brand, SOPs) as file tiles; each shows reuse count. Upload action.
- **Connected systems** — org-level integrations (Epicor connected as primary; others linkable). Reused across projects.
- **Codebase discovery** (`DiscoverySection`, `discovery.jsx`) · **WAVE 1 — shipping** — the on-ramp for companies already doing custom dev. Input a GitHub repo + **GitHub PAT** (write-only → org vault as `GITHUB_PAT`, never readable back; agents are **read-only**) → **Run discovery** → `MiniLog` crawl (clone → file map → manifests/CI → integrations detected → drafts written) → generated **AGENTS.md**, **CLAUDE.md**, **integrations.md** rows (ai-tint + source label) saved into the knowledge base and reused on every project. Re-run / add-another actions.
- **Dev conventions** (`ConventionsSection`, `discovery.jsx`) · **WAVE 2 — designed, not yet shipping** — for technical users: primary repo, framework & runtime, install/test commands, coding standards (or a standards doc in the knowledge base). A live **"What every build agent receives"** preview (ai-tint, mono) shows the compiled org AGENTS.md; Save flashes confirmation. Injected into every build agent's context so the factory builds to the org's conventions.
- **Secrets** — the organization **secret vault** (`ORG_SECRETS`): API keys, tokens, endpoints stored once at the org level. Each row shows the secret **name** (mono, e.g. `EPICOR_API_KEY`), a masked value (`••••••<last4>`), **used-by** project count, last-updated, and a **Rotate** action; **Add secret** in the header. Values are **encrypted and write-only** — once saved the raw value can't be read back (by anyone), projects reference secrets **by name**, and rotating/revoking here propagates to every project that imported the secret. Projects pull from this vault during the build's wait-for-deps step (§2.6).
- **Team & access** — members with roles; invite.
- **Usage & billing** — plan, spend, per-project spend breakdown.

### 2.4 Project onboarding  (`optionC.jsx` → `OptionC`)
**Purpose:** collect project context with a docked **Concierge**. This is the single, finalized intake design — the earlier alternate option studies (A · Guided Stepper, B · Context Workspace) have been **removed** to eliminate duplication; only this Concierge-led flow remains. Two modes via header toggle:
- **First-time** (fresh org, nothing on file): **Start with your website** · **WAVE 1 — shipping** — the first card is
  the **web prefill** (`EnrichFromWeb`, `discovery.jsx`): a domain input (pre-fill from the
  signup email domain when it isn't a public provider) and **Find my company**. The lookup
  runs as a visible `MiniLog` ("Reading acme-industrial.com… checking the careers page for
  systems…"), then reveals the **found-company card**: ai-tint rows (company, industry, HQ,
  headcount, systems-in-use, brand palette) each with a **source label** (url; never an asserted confidence level),
  and **Use these details** / "Not right — look again". Accepting fills the industry tiles,
  sub-focus chips, profile fields, and connected systems below; the card collapses to a green
  confirmation ("Pulled from the web — review and adjust anything"). **Nothing writes until
  the user accepts** — unconfirmed AI values keep the ai-tint treatment (the sources-not-tiers
  contract from §1). Then company setup (industry, profile, systems) **then** first project.
  Copy promises "we'll remember this." **Technical setup (optional, collapsed
  by default — `TechSetupCard`, inside the Connect-your-systems card):** a
  technical user declares **"bring my own repo & conventions"** — GitHub repo
  link (the build seed: the factory clones THEIR codebase), **GitHub PAT**
  (write-only → org vault as `GITHUB_PAT`, never readable back; read access
  suffices), framework & runtime, install/test commands, coding standards.
  Saved to the **organization** — the same data as §2.3 Codebase discovery /
  Dev conventions — reused on every project, with a pointer to run discovery
  after setup. A non-technical user never sees it as required.
- **Returning** (org on file): company context shown as **"on file · reused"** (collapsible, Manage to edit); only project questions are asked.
**Section separation:** a labeled `SectionDivider` splits **per-tenant (org)**
data from **this-project** data.
**Project inputs:** project name, "what are you building" (goal), **project budget cap**, **recipe** (optional blueprint), scope-of-work chips, build engine, materials.
- **Recipe** (`RecipePicker`, from `recipes.jsx`) is an **optional** starting blueprint the customer picks from the Published entries of the OS recipe library (§3.4b). The picker shows only the light customer-facing fields (category, name, tagline, a few capabilities); the recipe's GitHub repos, image artifacts, and internal notes are **not** shown. A **No template** card is always present — the customer can build purely from their brief. Lives in the "This project" section (inside `LockedGroup`, so it unlocks after the project is created); the value is a recipe id or `null`. Arriving from the **Explore** gallery (§2.8) preselects the recipe (`initialRecipe` prop).
  - **Recipe at runtime (how a recipe drives the build):** the recipe's text (name, tagline, capabilities, description) **replaces the SOW as the Concierge's intake input** — delivered via the existing conversation-context seam, and `recipe.md` becomes the **stage-1 (research) input** — the interview starts from what the recipe already knows instead of a blank brief. The pipeline receives the recipe's **linked GitHub repo as the build seed**: cloned into the **stage-3 (build) workspace**, the factory's skills **fork-and-extend** it (a dedicated SKILL block) — never greenfield when a recipe is selected — and the repo's `AGENTS.md`/`CLAUDE.md` teaches the build agents its architecture and conventions. A recipe without a valid repo/AGENTS.md is refused at load time (§3.4b).
  - **Concierge recipe suggestion:** · **WAVE 2 — designed, not yet shipping** · when the goal text matches a Published recipe and none is picked, the intake Concierge rail shows an inline **"Recipe match"** card (ai-tint; name, tagline, builds count, **Use this recipe** / **No thanks**, dismissible ×). Accepting sets the picker's value and the card flips to a green "Building from the `<name>` recipe" confirmation; dismissing suppresses it for the session (no nagging). The prototype matcher is `suggestRecipe(goal)` (keyword overlap); the live version is a concierge tool over recipe taglines (see `TICKETS.md` CBT-11).
- **Create the project first (gate).** The **very first action** in intake is naming the
  **project** and clicking **Create project** (`SaveBasics`, in `optionC.jsx`). This is a real
  creation event: it fires a **`POST` that writes the project to the database in `draft`
  state** — it is **not** merely a local “save for later.” Everything the user does afterward
  (scope, engine, materials, the processing + interview steps) **enriches that existing
  project and advances its state** (`draft` → *collecting information* → `building`). Until the
  project is created, **every downstream card — Scope of work, Build engine, Project
  materials — is grayed out and non-interactive** (wrapped in `LockedGroup`, which dims to 40%
  opacity, removes pointer events, and shows a centered “Create the project above to unlock”
  pill). The button is disabled until a name is entered (`canSaveDraft`). On success the button
  is replaced by a green “Project created” confirmation. This is distinct from **Save & finish
  later** (footer), which persists the whole in-progress intake and leaves.
  **Chat never creates a project.** Sending the Concierge a message before
  creation collects information conversationally only — it must never insert a
  row (no silent `Untitled project` drafts, Principle 3). The only creation
  path is the named **Create project** action above.
- **Project budget cap** (`BudgetPicker`) is the **absolute total spend ceiling for the whole project** (not a monthly figure) — presets ($30 / $60 / $120 / $250) plus a custom amount. The build pauses for approval when cumulative spend reaches the cap. **The cap is REQUIRED — the money-safety promise: there is no "optional" / uncapped option anywhere in copy or behavior; Continue cannot enable without one.** The chosen value flows into the project Overview and the factory-console header (`spent <x> / $<cap> cap`).
- **Scope of work** chips are multi-select with a **"+ Add"** affordance — the operator/customer can type a **custom scope or type of software** not in the preset list; it's added as a selected chip.
- **Build engine** (`EnginePicker`) · **WAVE 1 — shipping** — choose the coding agent that builds the project — **Claude Code** (Anthropic, default), **Codex 5.6** (OpenAI), or **Kimi K3** (Moonshot AI; also the design-generation model, §2.6). Three provider cards (name, vendor, description); the downstream factory + console look identical either way — providers plug in, nothing downstream keys on a specific one. An **API key** segment: **Use Tenexity's key** (billed through the plan) or **Bring your own key** (key input). The chosen engine surfaces in the factory console header badge (`engine · <name> · TENEXITY KEY / BYO KEY`) and the process-tree orchestrator label. Value shape: `{ provider: 'claude'|'codex'|'kimi', keySource, key }` (the earlier `claude|opencode` + model-subpick shape was replaced).
**Materials (`Dropzone` with `describe`):** walkthrough video + documents. Each uploaded file has:
  - a **description input** (free text) with **AI auto-summarize** button;
  - a **scope toggle**: **Project** or **Org-wide** (org-wide → saved to knowledge base, reused everywhere).
- **Import from organization** picker — attach existing knowledge-base docs to the project.
**Concierge rail (right):** greets user (fresh vs returning), tracks checklist
("On file · reused" vs "This project · to do"), asks the next gap question, and
states it stays on through the build. Composer at bottom.
**Behavior:** the CTA is now **Continue** (was "Hand off to factory"). It is enabled when the required fields are done and it does **NOT** start the build — it begins the **three-step intake sequence** described in §2.4a (Intake → Processing → Interview → Handoff). Alternatively **Save & finish later** stores the project as a **draft** (status `Draft / Needs input`) the user can resume and run later from the Projects dashboard / project Overview (§2.5a). A persistent **← Projects** back/exit control in the header lets the user leave intake at any point and return to the Projects dashboard without handing off (wired in the connected flow and in the standalone onboarding artboard via `OnboardingStandalone`).

---

### 2.4a Intake → Processing → Interview → Handoff (the Concierge flow)  (`concierge.jsx`, `optionC.jsx`)

> **READ THIS WHOLE SECTION BEFORE TOUCHING THE FLOW.** This is the spine of the
> product: the user does NOT jump straight from the creation form to the build.
> After they submit the form, the Concierge **ingests their uploads**, then
> **interviews them**, and only then is the build handed off. The same Concierge
> assistant then stays visible on every project screen forever.

#### Runtime flow and handoff contract

`OnboardingScreen` owns the three pre-build views: `intake` → `processing` → `interview`.
`App` owns the post-handoff destination. There is no question counter, `interviewDone` flag, or
agent-generated readiness state in application code.

Readiness is the Concierge's judgment in its database-backed system prompt. The only mechanical
handoff gate is the factual one: a `product_brief` artifact exists. The source-backed **What I
learned** reflection remains required: every stated fact names its source and any unsourced claim
is asked as a question rather than presented as truth.

There are exactly two valid handoff initiators:

1. The user clicks **Hand off to factory**, which calls `POST /api/projects/{id}/promote`.
2. After clear agreement in the conversation, the Concierge calls `hand_off_to_factory`, which
   invokes the same `promote_draft` function.

On a completed Concierge turn the server returns factual `handed_off` state derived from the real
project phase. `handed_off: true` and a successful button response both invoke the same completion
callback and navigate immediately to the Factory Console. A refusal or failure leaves the user in
the interview and shows the real reason. The UI never infers handoff from assistant prose and never
issues a second promotion request after the tool succeeds.

**The transitions, in order:**

1. **`intake` → `processing`** — the green **Continue** button calls `setView('processing')`.
   (File: `optionC.jsx`, the intake footer button. It was previously `setView('build')`; do not revert that.)
2. **`processing` → `interview`** — `ProcessingScreen` calls its `onDone` prop when the
   ingest log finishes (or the user clicks **Start the interview**). `OptionC` passes
   `onDone={() => setView('interview')}`.
3. **`processing` → background (project home)** — `ProcessingScreen` also takes an
   `onBackground` prop. In the standalone artboard this is wired to jump to the **project
   home** (`ProjectViewStandalone`) with its live "processing in background" banner. See
   "Backgrounding" below.
4. **`interview` → Factory Console** — either valid handoff path above calls the shared completion
   callback with the promoted project id. The Factory Console opens immediately.

#### Step 2 — `ProcessingScreen`  (`concierge.jsx`)

**Why it exists:** uploaded materials can be heavy (a long screen-recording video, a big
price spreadsheet). We must never silently freeze on a blank screen while parsing — the
user sees exactly what is being read.

**Failure honesty (SOF-224 #4):** a failed ingest **never advances the flow**. A document
list or parse that fails surfaces the **actual error and a retry** — an empty or failed
load is never treated as "nothing to process," and `onDone` never fires on a failure
path (honest-errors principle; evidence ingestion cannot be bypassed by an error).

**Props:** `projectName` (string, shown in the top bar), `onDone()` (called when ingest
completes, ~900 ms after 100 %), `onBackground()` (optional; if present, renders the
"Continue in background" button).

**What it renders (top to bottom):**
- A top bar: `Wordmark` + `/` + project name on the left, a `WorkingPill` labeled
  "Processing" on the right.
- A `CategoryLabel` reading **"Step 2 of 3 · Processing your materials"** (`tone="brand"`),
  a Georgia (`T.display`) headline, and a one-line explanation that big files take a moment.
- **Progress bar:** a track (`background: T.sunken`, height 8, radius 5) with a fill whose
  `width` is the live `pct` and whose color is `T.brand` while running and `T.success` when
  done. Above it: the current file name + `pct% · ETA` in mono (`T.mono`).
- **Ingest log:** a dark panel (`background: T.ink`) with a header dot and a scrolling list
  of mono lines. Each completed line gets a green `✓` (`T.success`); the active line gets a
  `›` and white text; an unfinished spinner row (`.sf-spin` class + `refresh` icon) sits at
  the bottom while running. Lines animate in with the `sfRise` keyframe.
- **Footer:** an info note ("Big upload? … send this to the background…") plus two buttons —
  **Continue in background** (`Btn variant="secondary"`, only if `onBackground` given) and
  the primary action, which reads **"Processing…"** (disabled) until done, then flips to
  **"Start the interview"** on a `T.success` background.

**The data that drives it** is the module-level constant `INGEST_STEPS` (array of
`{file, size, kind, lines[]}`). To change what files/steps are "processed," edit that array
— nothing else. Each string in `lines[]` becomes one log row; the progress percentage is
simply `processedLines / totalLines`.

**IMPLEMENTATION LANDMINE (do not re-introduce):** the progress is driven by **one** state
variable, `logN` (how many log lines have appeared). Everything else — `pct`, which file is
active (`fileN`), `done` — is **derived** from `logN` on each render. Do **NOT** call
`setState` for `pct`/`fileN` from inside the `setLogN` updater; React batches/drops nested
state updates and the bar freezes mid-way (this exact bug happened and was fixed). The
`onDone` call fires from a `useEffect` that watches `done`, guarded by a `firedDone` ref so
it cannot fire twice. A `setInterval` ticks `logN` up by 1 every 720 ms; clear it on unmount.

> **Preview caveat for QA:** browser timers throttle when the tab is backgrounded or the
> design-canvas artboard is zoomed out / not focused, so the bar appears to crawl. Open the
> artboard **fullscreen and keep it focused** and it completes in ~10 s. This is a browser
> behavior, not a bug.

#### Backgrounding (large files → project home)

If the user clicks **Continue in background**, we do not make them wait. In the standalone
artboard, `OnboardingStandalone` (`optionC.jsx`) switches its own stage to `home`, rendering
`ProjectViewStandalone` (`orgproject.jsx`) with two props: `ingesting={true}` and
`onResumeInterview={…}`. While `ingesting` is true, `ProjectDashboard` shows a **live banner**
at the top of the Overview (a `.sf-spin` refresh icon + "Processing your materials in the
background" + a **Resume interview** button). The promise to the user: the project home keeps
updating as results land, and they can pick the interview back up anytime. The persistent
Concierge dock on that page also switches to its `ingesting` context (see §2.4b).

#### Step 3 — `InterviewView`

The interview is one full-height Concierge conversation, not a scripted question-counter UI.

- The top bar contains **← Setup**, the wordmark, project name, online/thinking status, and
  **STEP 3 OF 3 · INTERVIEW**.
- The Concierge asks exactly one useful question per turn, using the project, recipe, processed
  documents, memory, and conversation history already available to it.
- The final reply streams as prose plus optional single- or multi-select responses. The free-text
  composer remains available so the customer can correct, add, or stop the interview naturally.
- Source-backed learned facts are shown before handoff; the customer can correct them in the same
  conversation. There is no confidence score and no fixed `INTERVIEW_Q`/`LEARNED` array.
- The footer contains the composer, honest handoff/error status, and **Hand off to factory**. The
  server's `product_brief EXISTS` check is authoritative; client state never fabricates readiness.
- When the Concierge tool hands off, the completed turn carries `handed_off: true`; when the button
  hands off, the promote response carries the project id. Both open the Factory Console.

#### Product Brief content contract

The Concierge writes the Product Brief as detailed, readable Markdown in the newest
`kind='product_brief'` artifact. It must communicate enough for the factory and customer to share
an unambiguous understanding of the business problem, intended users and their needs, desired
outcome, and first-release scope. Constraints, assumptions, and unresolved questions appear when
they are relevant to that project.

This is a semantic minimum, not a section schema. The Concierge chooses the headings and depth that
best fit the project; neither the prompt nor application code requires an eight-, eleven-, or any
other fixed-part template. The project UI derives its contents navigation from the headings that
actually exist. Readiness remains Concierge judgment, with only the factual artifact-exists gate in
code (§2.4a).

The live `system_agents(callsign='CONCIERGE').prompt` must instruct the Concierge to draft, read back,
and revise this brief with the user before handoff, preserving the user's language and distinguishing
source-backed facts from questions. This requirement belongs in the operator-editable database prompt;
do not add a code-default prompt, section validator, readiness tracker, or new state machine.

---

### 2.4b The persistent Concierge — `ProjectConcierge`  (`concierge.jsx`)

**The one rule:** there is **one** Concierge, and it looks and behaves the same everywhere.
The project home, Product Brief, Factory outputs, Factory console, Files, and conditional
post-delivery Maintenance view together are the **"Project Console,"** and `ProjectConcierge` is
the shared dock (`width: 340`, right-hand, `borderLeft`) on every view. Same full shell
(`ConciergeHeader` + scrolling detailed message history + working/tool activity + contextual
material + suggestion chips + unrestricted `Composer`); only the **context** changes.

The open conversation is primary. Suggested prompts and document actions accelerate common work;
they never replace free text, hide the transcript, or reduce the Concierge to an About panel or
shortcut list.

**Minimize without reserving space:** the header has one **Minimize Concierge** control. Minimized
state removes the 340px dock from layout entirely and leaves a 44px floating sparkle button over the
bottom-right edge of the current project view. Working or unread activity is a status dot on this
button. Reopening restores the same transcript, unsent draft, selected context, and scroll position;
switching peer views preserves the minimized preference for that project visit. The floating button
is not a narrow rail and consumes no permanent content width.

**One chronological conversation:** customer messages, Concierge messages, and meaningful system
events share one ordered timeline. Routine lifecycle events are compact neutral rows with time,
icon, and label. Attention and failure events add a restrained warning/danger marker and expandable
truthful detail. Artifact-created events have **Open output**. Consecutive retries may be summarized
as one entry only when their individual timestamps remain available. There is no detached **Recent
activity** block and no Feed / Tray / Latest switch inside the conversation.

**Single prop drives everything:** `context` is one of:
- `'overview'` — project home. Subtitle "Watching this project"; suggestions are progress
  questions ("How's the build going?", "What's left to do?", "Any blockers?"). It can relate
  the current status to the Product Brief or the factory output that best explains it.
- `'brief'` — Product Brief. Subtitle "Working from your brief"; receives the selected heading
  and current brief version as context. The open composer supports explanation and revision in the
  user's own words. Direct edits and Concierge edits target the same canonical artifact.
- `'outputs'` — Factory outputs. Subtitle "Across the factory's work"; receives the selected
  artifact and producing stage. It explains decisions, relates an output back to the brief, and
  accepts steering requests without replacing the artifact reader.
- `'build'` — factory console. Subtitle "Relaying the build"; shows a **"Steer the build"**
  helper card and interleaves relevant system events with the conversation; a `WorkingPill` shows
  while the build runs. Takes a `build={{done,total,allDone}}` prop and an `onOpen` callback for
  artifact-created events.
- `'files'` — source files and directories. Subtitle "Across your source material"; receives the
  selected directory summary or file and suggestion chips ask about that specific context
  (`docChips`). The Concierge and other agents read directory summaries before querying individual
  documents so they can narrow retrieval to the relevant subtree. The selected file or directory is
  passed as structured `sourceContext`; the prototype reply reads its current summary and surfaces a
  failed or stale status instead of bypassing it with a filename match. **Document Q&A with inline
  citations is a later feature** — current replies name their source context but do not fabricate
  section-level citations.
- `'maintenance'` — post-delivery maintenance. Preserves the existing delivered-project context
  and open composer; this information-architecture change does not redesign that workflow.
- `'ingesting'` — shown on the project home while uploads process in the background. Subtitle
  "Processing in background."

**Where it is wired:**
- Factory console: `buildprogress.jsx` (`BuildProgress`) renders
  `<ProjectConcierge context="build" build={{…}} onOpen={…} />` on the right. (The old
  left-hand `ConciergeRail` was replaced by this right-hand dock so the assistant is in the
  same place on every screen.)
- Project home / Product Brief / Factory outputs / Files: `projectknowledge.jsx` extends the
  existing `orgproject.jsx` `ProjectDashboard` entrypoint, maps the active peer view to the matching
  context, and passes the selected heading, artifact, or file when one is active.

**Shared chat engine:** all Concierge surfaces (interview rail + persistent dock) use the
`useConciergeChat(seed, replyFor)` hook in `concierge.jsx`. It owns the message list, the
draft, the "thinking" label rotation, auto-scroll, and timer cleanup. `seed` is the opening
messages; `replyFor(userText)` returns the scripted reply (`conciergeReply` handles the
persistent dock). **This hook is design-canvas simulation only. The implemented app uses the live
LangChain Concierge and durable conversation store; do not reproduce this script in runtime.**

---

### 2.4c Markdown in the project goal — `GoalMarkdown`  (`shared.jsx`)

The "what are you building" goal is free text the customer typed, and they may write
markdown in it. `GoalMarkdown` (exported from `shared.jsx`) renders it: it detects markdown
via `looksLikeMarkdown()` and, if present, renders `**bold**`, `*italic*`, `` `code` ``,
`[links](url)`, and `-`/`1.` lists; if there's no markdown it renders the text verbatim, so
plain prose is unaffected. It is used in the project **brief** (Overview, `orgproject.jsx`)
and the interview **"This project"** card (`optionC.jsx`). The compact dashboard list row
strips markdown to a single ellipsised line instead (regex strip in `dashboard.jsx`).

> **NAME CLASH WARNING:** there is a *different* full-document `Markdown` renderer in
> `artifactviewer.jsx` (headings/tables/code-fences for the Artifact Viewer, §2.7). They are
> **not** the same component and must not be merged — the goal renderer is deliberately named
> `GoalMarkdown` to avoid the collision (which previously broke the page when both defined a
> global `Markdown`).

### 2.5 Project view: project knowledge shell  (`orgproject.jsx` + `projectknowledge.jsx` → `ProjectDashboard`; standalone wrapper `ProjectViewStandalone`) · **DESIGN TARGET**

The shipping shell currently has Overview, Factory console, and Documents. The design target keeps
that shell and extends it into five core peer views: **Overview · Product brief · Factory outputs ·
Factory console · Files**. A completed project also retains the conditional **Maintenance** peer.
None is nested under another; all share **← Projects** and the persistent detailed Concierge.

The **Factory console remains the existing real component**, not a copied board. Opening it renders
the same `ProjectViewStandalone` shell, landing on `initialTab="build"`; its peer tabs return to the
other project views through the existing callback.

**2.5a Overview:** an understandable snapshot, not an inventory of every subsystem:
- One plain-language status sentence states what finished, what is happening, and the next useful
  event or requested input. It is derived from real run state, never filler.
- Product Brief preview: the project goal, current version/source note, and **Open brief**.
- Build status: percentage, current phase, tickets, agents, spend/cap, and **Open factory console**.
  Existing editable budget behavior remains part of the implemented surface.
- Project knowledge: a short preview of useful brief sections and newest factory outputs with clear
  routes into their full views.
- Services, individual agents, uploads, and inherited organization context are not equal Overview
  panels. Operational detail belongs in Factory console; source material belongs in Files.
- Draft projects retain the honest setup/resume path from §2.4a. Missing outputs use one explanatory
  state saying which factory stage will create them, not a grid of empty cards.

**2.5b Product Brief:** renders the canonical newest `product_brief` inside the project shell. A
compact contents rail is derived from the Markdown headings that actually exist; there is no fixed
section count. The center is a readable document, and the full Concierge remains present in `brief`
context.

**Edit document** is a document-first editor for headings, paragraphs, lists, and links, with a
compact formatting toolbar and visible Saving / Saved / Save failed state. It is a **target
extension** of the canonical artifact path: implementation must add an authenticated write that
creates a new `product_brief` artifact version. It must not reuse the current `PUT /brief` goal/scope
projection as if that endpoint edited the artifact. **Add section** inserts another heading in the
same Markdown document. **History** lists real artifact versions; viewing an older version is
read-only, while restore—when implemented—creates a new latest version rather than mutating history.
The Concierge's `finalize_product_brief` remains the conversational edit path. Both paths converge
on the same newest-wins artifact.

**2.5c Factory outputs:** factory-produced artifacts grouped by their real producing stage with
customer-readable titles. Selecting one renders it inside the project shell through the existing
Markdown/typed artifact body. The underlying id, kind, path, agent, and stage are unchanged. The
standalone Artifact Viewer remains available through **Open in new tab**.

**2.5d Files:** a hierarchical source-material browser. Factory outputs do not appear here, and the
Product Brief is not duplicated as a source file. The existing project-vs-organization scope remains
real: every persisted directory belongs to exactly one scope and all descendants inherit that
scope. The top-level **Files** screen is a virtual presentation that combines the project and
organization roots; it is not a mixed-scope directory and has no directory id. Its recent-file
section links to files in their real scoped directories rather than containing duplicate blob
memberships. Moving a document across the two persisted roots performs the existing scope change;
it is not a cosmetic drag between labels.

The default Files surface is recognizable as a file browser rather than a grid of blank cards:

- a directory tree and breadcrumbs expose the current path;
- folders use folder silhouettes, counts, scope, and a short summary preview;
- PDF, spreadsheet, document, image, and video files use large typed file icons, with the filename,
  size/duration, updated time, and ingest status as secondary information;
- selecting a source file exposes its existing document summary and actions without treating it as a
  factory artifact; and
- **New folder** creates a real directory in the current scoped root, while uploads and existing
  files may be assigned or moved to a real directory. Empty directories say that they contain no
  indexed material; no plausible summary is fabricated. Rename and directory deletion are not part
  of this design increment.

**Generated directory summaries are read-only.** Each directory has a generated Markdown summary
derived from the current summaries of every document and child directory in its subtree. It states
what the directory contains, which questions it can help answer, and the notable files an agent may
need. There is no manual edit action and no parallel user-authored folder note. Adding, removing,
moving, or re-ingesting a descendant mechanically makes ancestor summaries stale; the background
ingestion path regenerates affected summaries bottom-up. The UI exposes the truthful state
**Summarizing**, **Ready**, **Needs refresh**, or **Failed**, plus the last successful refresh. A
failed child document does not disappear: the directory summary names the incomplete coverage and
the UI retains the child's failure state.

**Agent retrieval contract:** agents start from the root directory summaries, choose the smallest
likely subtree, then search/fetch within that directory id. A directory-scoped query includes all
descendants; agents do not receive an invented claim that the chosen directory is sufficient. Search
results retain their source document id and path. Direct file selection remains available when the
agent already knows the source.

**Required backend/database extension (not present in the current flat document API):** add a scoped
directory relation with `id`, `scope`, `scope_id`, nullable `parent_id`, `name`, `summary_md`,
`summary_status`, `summary_source_hash`, and timestamps; add nullable `directory_id` to source blobs.
The database enforces that parent and child directories share a scope and that sibling names are
unique. The project documents projection returns a directory tree plus file rows rather than three
flat arrays. Authenticated mutations create a scoped directory, upload a material into a directory,
and reassign an existing blob's `directory_id`; a cross-scope reassignment uses the existing scope
change and validates the destination belongs to the new scope. The memory/query tools accept an
optional directory id that filters to its subtree. The Files Concierge receives a structured
`sourceContext` (`type`, `id`, `scope`, `name`, `summary_md`, `summary_status`) rather than only a
display label. Existing project and org documents migrate into their corresponding scope roots
without changing their blob ids, summaries, storage keys, or access rules. This is deliberately a
material backend, database, ingestion, API, and agent-tool change; the design must not imply it
already ships.

**2.5e Maintenance:** preserves the implemented post-delivery Maintenance tab and lifecycle. It is
conditional on a completed/deployed project and is not redesigned by this information architecture.

### 2.6 Factory console (build board) — THE CORE SCREEN  (`buildprogress.jsx` → `BuildProgress`; `buildboard.jsx`, `nodemap.jsx`, `artifacts.jsx`)
**Purpose:** show and steer the agent pipeline building the project. Most
important screen in the product.
**Top bar:** ← Projects · wordmark · project name · phase pill · spend/cap. Peer tab strip when opened from a project. The `spend / $<cap> cap` reflects the project's editable **budget cap** (total spend ceiling, §2.4 / §2.5a).
**Right: persistent Concierge dock** (`ProjectConcierge context="build"`, §2.4b) — the same
assistant that appears on every Project Console screen and can be minimized without reserving
layout width. It interleaves relevant operational events with messages, shows a **"steer the
build"** helper card, and has a composer to **steer the build team**. Factory outputs remain in
their project view; the exhaustive event record lives in Activity below.
**Main column:**
- **Pipeline stage-rail** — the full pipeline as chips with Stage gates (diamonds): `extract → provision → research → [Stage 1] → architect → design(NEW) → tickets → [Stage 2] → wait-for-deps → build → test → deploy`. Done = checked, active = pulsing, deps = amber.
- **Crash / pause recovery** — each completed node writes **immutable checkpoint artifacts** (the files in the Artifact Viewer); the run's durable state is the set of completed checkpoints, not in-memory progress. When a run **crashes** (node failure) or is **paused**, the stage-rail marks the halt node (red / amber) and downstream nodes fade to `queued`, and a **Recovery bar** appears: **Resume from `<node>`** (re-runs the halt node onward, reusing every upstream checkpoint — no re-research/re-architecting), **Retry `<node>`** (re-run just the halt node, e.g. after a transient failure or a now-provided key), or **Rewind to…** an earlier checkpoint (click any completed node, or pick from the dropdown — that node + downstream are invalidated and recomputed, upstream reused). The build Kanban is idempotent per-ticket, so a resumed build picks up only the not-done tickets. Header shows `run crashed` / `run paused`; the **Pause** control drives the paused state in the demo (a crash sets the same recovery flow at runtime).
- **Wait-for-deps action** — **stage-triggered inside Activity**: appears *only after* the build reaches the wait-for-deps stage (not shown the rest of the run), marked with a `STAGE-TRIGGERED` badge and copy explaining why it surfaced now. The dependency set is **derived from the project's architecture**, so the **count varies per project** (factory + app design); the layout is an auto-wrapping grid that **scales to any number** of dependencies. Header tracks `resolved / total` and flips to "Dependencies resolved — build unblocked" when complete. Each dependency offers **3 resolution options**: **Get from MCP**, **Mock it**, or **Input key**. Build is gated until all are resolved. **Input key** additionally offers **Import from org secrets** (§2.3): a picker of the organization vault (`ORG_SECRETS`) with the best name/kind match badged `MATCH`; choosing one wires the dependency to that secret **by reference** (`org:<NAME>`) — the raw value is never shown — or the operator can still paste a key manually.
- **Design review action** (`DesignReviewBar`, `buildprogress.jsx`) · **WAVE 2 — designed, not yet shipping** — **stage-triggered inside Activity** like the deps action: surfaces only once the **design** node has completed. The design node (Kimi K3) generates high-fidelity screens from the PRD + the org's brand theme (§2.3 Brand & theme), then waits for the customer. The action shows the generated screens as clickable mockup tiles (each opens the `screens` fig artifact in the Artifact Viewer), header `design · Kimi K3 · on your brand theme`, and copy explaining the two paths: **Approve & continue** locks the look (action flips to a green "Design locked — tickets and the build proceed from these N screens", with **Re-open review**) — or **iterate via the Concierge** ("denser quote table", "approvals first"), which re-generates only the affected screens.
- **View toggle: Activity · Kanban · Tree · Map**
  - **Activity** (`concierge.jsx` → `FactoryActivity`): the exhaustive chronological operational
    record for stage transitions, agent actions, retries, interventions, failures, and produced
    artifacts. It uses the same event records rendered in the Concierge conversation. Opening the
    console from an alert selects Activity and scrolls to that event; ordinary entry remembers the
    user's last console mode during the current project visit. First entry retains the existing
    Kanban default. Activity is a mode, not a permanent split rail. Design review and wait-for-deps
    action panels render inside Activity so they never push the switcher or another selected view
    below the viewport.
  - **Kanban**: columns Backlog → Claimed → Building (WIP cap) → Testing → Done; ticket cards show id, title, assigned agent (avatar), tags (bug / needs-key / e2e). "Run agents" advances the live sim; bugs in Testing loop back to Building.
  - **Tree**: process tree — orchestrator root → each pipeline node → its spawned sub-agent → the artifacts it produced (clickable).
  - **Map**: force-graph layout of the same pipeline with curved edges, the active path highlighted, satellites for sub-agents/deps.
- **Delivery footer**: when 100%, deploy unlocks → Repository + Open live app.
**Artifacts (`artifacts.jsx`, `artifactviewer.jsx`):** nodes produce real documents — research `.md` files,
**PRD.md** (product council), **architecture.svg** (architect), screen designs
(design step), the **GitHub repo** (provision). In the design target, customer project links select
the artifact in Factory outputs; **Open in new tab**, Tenexity OS, and external deep links use the
standalone Artifact Viewer (§2.7).
The Concierge surfaces them as an "Artifacts produced" list with open-links.

### 2.7 Artifact Viewer  (`ArtifactViewer.html` → `ArtifactViewer`; `artifactviewer.jsx`)
**Purpose:** the existing standalone, full-page viewer remains the authoritative cross-project and
deep-link presentation for everything the factory produces or operators author. The project shell's
Product Brief and Factory outputs views reuse its typed body behavior as an in-project presentation;
they do not introduce another artifact format or parser. Standalone entry remains
`openArtifact(id)` → `ArtifactViewer.html?doc=<id>`.
**Layout:** left **file rail** (all artifacts, grouped by project, searchable) + topbar (breadcrumb project ▸ node, file name, type badge, updated, Copy / Download) + typed body.
**Supported types** (`ART` registry): **md** → real markdown renderer (`Markdown`) in a reading column with an **"On this page" TOC** (recipe descriptions register as `md`); **svg** → architecture diagram; **code** → line-numbered source (sql/bash/etc.); **fig** → frame grid; **image**. **Current vs future (SOF-224):** the shipping app's viewer renders **json / csv / repo** through the generic `<pre>` — the typed **json** tree, **csv** table, and **repo** file-tree views below are the *designed* target, labeled future until implemented. Selecting a file in the rail updates the URL so it's linkable.
**Markdown renderer** (`Markdown`, exported): headings, lists (ordered/unordered), tables, fenced code, blockquotes, rules, inline bold/italic/code/links. Reused by the recipe editor's live preview.

---

## 2.8 Explore — recipe inspiration gallery  (`recipes.jsx` → `ExploreRecipes`)  ·  **WAVE 2 — designed, not yet shipping**

> **Status label (SOF-224):** this destination is **Wave 2 / future** per the
> operator-approved Wave-1 scope (2026-07-21). The recipe surface shipping today
> is the intake `RecipePicker` (§2.4). Everything in this section is the design
> target; do not treat the gallery as current product.

**Purpose:** let customers browse what the factory can build **without starting a
project** — inspiration first, commitment second. Reached from the Projects dashboard
(**Explore** button, §2.2) and renders its own destination with a slim top bar
(**← Projects** back · wordmark · `/ Explore`).
**Body:** headline "See what the factory can build — then make it yours" + a card grid of
every **Published** recipe (§3.4b): preview area (the recipe's first **public** image
artifact — images stay internal-only unless flagged **Public** in the OS editor's image
tile, which gained a Public/Internal toggle), category + builds count, name, tagline,
capability chips, systems, and a **Start from this →** primary action that enters intake
(§2.4) with that recipe preselected (`initialRecipe`). A dashed **No template — start
blank** card closes the grid (enters intake with no recipe).
**Navigation (how a user reaches it):** ① the **Explore** button (compass icon) in the
Projects dashboard header, next to **New project**; ② the **"Browse the gallery"** link
inside the intake **Recipe** card (§2.4, both modes). **← Projects** returns to the
screen you came from (`FactoryApp` tracks `route.from`; dashboard ⇄ intake round-trip —
the real implementation preserves in-progress intake state; the prototype remounts).
**Start from this →** always lands in intake with the recipe preselected.
**Connected flow:** `FactoryApp` route `explore` (dashboard.jsx).

---

## 3. TENEXITY OS — internal operator portal  (`admin.jsx` → `AdminPortal`)

Distinct mono/terminal aesthetic. App shell = left sidebar + top **Factory
Pulse** bar (AGENTS_ACTIVE, TASKS_RUNNING, AVG_FRICTION, TODAY_BURN, PROJECTS) +
search (⌘K) + **Back to console** + an **account avatar menu** (top-right): operator name/email + OPERATOR chip, Account settings, Switch to console, and **Sign out** (→ signed-out screen with "Sign back in"). Nav: Overview, Organizations, Users, Projects, New Project, Recipes, Artifacts, Agents, Tools, Factories, Settings.

### 3.1 Overview
Platform-wide pulse (tenants, projects, agents active, today burn) + most-active
projects + agent workforce snapshot.

### 3.2 Organizations (tenants)
Table of every org ("organization" is the canonical term for a customer — used everywhere, never "client"): initials, name, active projects, in-flight tickets, total
spend, last activity. **All computed columns are system-derived** — initials come from the name, and projects/tickets/spend/activity are live aggregates; they are **never hand-entered**. **+ New organization** opens the **invite modal** (§3.7): the operator may pre-seed the org's **identity/context fields** (name, website, industry) and invites its admin in the same action — the invited user always gets onboarding either way (§3.7 chain), with whatever the operator provided already on file. There is no telemetry entry form anywhere.

**Projects (all)**
Every project across all clients. Filters (organization, factory, **user/owner**, status, mode) +
REAL/DEMO toggle. The **user filter** ("All users") narrows the table to a single owner; each row shows the owning operator (avatar + name) under the organization. Columns: project (+ WORKSPACE badge), organization + owner, factory, phase
(REVIEW/PLANNING/BUILDING/TRIAGE/INTAKE), tasks, friction (F), autonomy (Auto), last activity.
**Click any project row** (here or in the Overview "most active" list) → the operator opens **that project's dashboard** (`AdminProjectView` → `ProjectDashboard`): Overview, Documents, and **Factory console** tabs, with **← back** to the OS list. The OS project shape is mapped to the customer dashboard shape.

### 3.4a Users — the master users table  (`users.jsx` → `UsersManagement`)
**Purpose:** the single master table of every person allowed to sign in — across every **organization** plus internal Tenexity staff. One table underneath the whole platform.
**Table:** name + email, organization, **role** badge, **sign-in method** badge, **status**, last active. Audience toggle (**All / Organizations / Internal**), search, status filter.
**Add user** (`AddUserModal`): pick **Belongs to** = An organization **or** Tenexity · internal; email; optional name; **role** (org: Admin/Member · internal: **Operator / Admin** — internal Admin = full platform read/write, shown as a purple `TENEXITY ADMIN` badge); **sign-in method** (Google / Microsoft / **Email & password** / Org SSO). For email-password, an optional **initial password** — set one to **provision the account directly** (active immediately) or leave blank to send a **set-password invite link**.
**Invite flow:** added users sit as `invited` with a copyable **invite link**; the flag flips to `active` on first sign-in.
**Edit drawer** (`UserDrawer`): change role / method / designation, copy or resend the invite, and a danger zone (disable / re-enable / remove). Operators have full read/write.

### 3.4b Recipes — recipe library  (`recipes.jsx` → `RecipeLibrary`; data in `recipedata.jsx`)
**Purpose:** the master list of reusable **build blueprints** the internal Tenexity team curates. Each recipe carries a **customer-facing summary** (name, tagline, category, systems, "what the customer gets") plus **internal-only build assets** — linked **GitHub repos** and **image artifacts** — and an internal markdown description. Customers pick from these during intake (§2.4) and see only the light summary fields; the repos, images, and notes stay OS-side.
**Layout:** left master list (name, status pill, category, build count) + right **editor**: editable name + tagline, a status toggle, **Classification** (category chips + a systems tag editor), **What the customer gets** (capability tag editor), **Linked GitHub repos** (name / url / description rows, add/unlink — internal), **Image artifacts** (named striped-placeholder tiles, add/remove — internal), and a **Description** markdown body with **Write · Split · Preview** live preview (shared `Markdown`). **Save** + **Open in viewer ↗** (opens the description in the Artifact Viewer, new tab). **+ New recipe** seeds a blank Draft.
**Status cascade:** Draft / Published / Archived — **only Published recipes appear in the customer picker.** Data lives in `recipedata.jsx` (`RECIPES`, `RECIPE_STATUS`, `RECIPE_CATEGORIES`); each recipe's description registers into the artifact registry (type `md`, project "Recipes").

> **SOW → Recipes — current state:** **Recipes are the only library.** The legacy `sow` table,
> `SowStore`, routes, UI, and scope-genre fallback are retired. A project with no selected recipe
> proceeds from its own intake and brief; it never falls back to SOW data. Storage is the standalone
> `recipes` table; no `repo_tree`/index column exists because validation and build preparation clone
> the repository when needed.
**Customer picker** (`RecipePicker`, exported from `recipes.jsx`, used in `optionC.jsx` intake): a grid of Published-recipe cards (category, name, tagline, first few capabilities) plus an always-present **No template** card (build purely from the brief). Selection is optional and toggleable; value is a recipe id or `null`.

### 3.4c Artifacts index  (`admin.jsx` → `AdminArtifacts`)
Every file the factory produced or operators authored, grouped by project, each a card that **opens in the Artifact Viewer** (new tab, §2.7). Recipe descriptions are registered here too (project "Recipes").

### 3.5 Agents (roster + prompt editing)
Card grid of every agent: name, status dot, callsign badge, description,
callsign, model, cost dots, autonomy/success bar. Drift-detection banner.
**Click a card → prompt panel** (right drawer): editable **system prompt**
(mono textarea + "suggest improvements"), **Tools** tab (tools available to the
agent), **Activity** tab. Save/cancel.

### 3.6 Tools & MCP registry
Every tool/MCP server/connector. Metric cards (registered / connected / MCP
servers / available). Table: tool, type (MCP/API/native/HTTP), provider, scope,
auth, used-by count, status (live / connect). Register-tool + sync actions.

**Tool editor (click a row → right drawer)** — the per-tool settings surface.
**Logical separation:** a tool's config and secrets live **on the tool's row here**,
never in platform Settings (§3.8); platform knobs never appear here.
- **Config fields** — per-tool JSON config (the existing DB-editable pattern: e.g.
  `fusion`'s `analysis_models` / `judge_model`). Editable inline, validated, audited.
- **Secret fields** (e.g. Exa's API key) — **write-only**: a paste input that stores
  masked (`••••••` + last4 shown), **Rotate** replaces, and the raw value is never
  readable back by anyone — the same contract as the org secret vault (§2.3).
- **`env_key`** — shown as a mono badge: "injected as `EXA_API_KEY` at console
  startup" (see §3.8 Startup hydration). This is how DB-stored secrets reach the
  code that reads env today.
- **Attached to** — the agent call-signs this tool is wired to.
- **Status, honest** — `live` only after a real call with the stored key succeeded;
  otherwise the actual state: `missing key`, or `failing — <real error>` (e.g.
  "Exa returned 401 — rotate the key"). Never a plausible-looking mock status —
  agents read this too, and act on it.

### 3.7 Provide access (invite)  (`InviteModal`)
Triggered from the top-bar **Provide access** button and from **+ New organization** (§3.2). This is the ONLY way an organization or user comes into being — the invited person gets the full onboarding experience, never a hand-entered row. Form:
- **Email** address.
- **Access type** dropdown: **New org** or **Tenexity**.
  - **New org** → the operator may **pre-seed the org's identity/context fields**: **organization name** (prefilled from the invite email's domain — `nick@cbtcompany.com` → "Cbtcompany"; editable), **website** (optional; prefilled with the domain itself; editable), **industry** (optional). Common mailbox providers yield no guesses. The invited user becomes the **admin of that new org**; whatever was provided here is **on file for their onboarding — provided once, never asked twice**. A **"What happens next"** strip spells out the flow below.
  - **Tenexity** → internal operator with full cross-tenant access.
- On send → email is **added to the sign-in allow-list** (status `invited` → `active` after first sign-in). Login (§2.1) only admits allow-listed emails.
**Allowed sign-ins** list shown in the modal: email, org, role, status.

**The invite → onboarded chain (wire exactly like this):**
1. Operator sends the invite; the person gets the email (requires the verified sending domain — `TICKETS.md` CBT-29) with a link to the app.
2. They sign in **with their preferred method** — Google / Microsoft / email+password / org SSO (§2.1 — all four stay equal citizens). First sign-in flips them to `active`.
3. First sign-in routes to **first-time onboarding** (§2.4 fresh mode) — **always, whether the operator pre-seeded fields or not**. The website field is prefilled from their email domain (or the operator-provided website), and any operator-provided fields (name, website, industry) are already on file and editable. The **web prefill** researches the remainder with them: lookup → found-card with source labels → they confirm → the org profile (industry, scale, systems) is completed *with* them, not typed by anyone twice.
4. They continue through context gathering (materials, systems, recipes) and **start their first project** on the same sitting — intake → processing → interview → handoff (§2.4a). The Concierge carries the whole way.

---

### 3.8 System settings — the console's own settings  (`admin.jsx` → `AdminSettings`)

**Purpose:** every operational setting of the **factory console software itself** is
editable in one place — no operational setting lives only in deploy env. **Logical
separation:** this page owns the console platform; a tool's own config/secrets live on
that tool's row (§3.6), never here.

#### Storage & precedence (implement exactly)

- **Table** `system_settings(key text primary key, value text, secret bool not null default false, updated_by text, updated_at timestamptz)`. Secrets in this table follow the §2.3 vault contract (write-only, masked `••••••<last4>`, never readable back).
- **Read path:** one accessor — `settings.get(key)` is **DB-first, env fallback**. A real env var is a disaster-recovery override, not the norm.
- **Startup hydration:** at console boot, every stored tool secret (§3.6) is injected into the process env under its `env_key` via `os.environ.setdefault(env_key, value)` — existing env readers keep working untouched, and stage children still inherit through the `_STAGE_ESSENTIAL` allowlist in `env.py` (the stage scrub is unchanged; the key simply arrives from the DB now instead of the deploy env).
- **Apply semantics:** settings marked **hot** apply in-process on save; others are persisted and the row shows an honest **"applies on restart"** badge until the next boot. Never claim a setting is live when it isn't.
- **Audit & validation:** every row shows `updated_by` + `updated_at`; values are validated client- and server-side; a refusal states the actual reason (repo rule: honest errors).

#### Layout (one page, OS shell; left-aligned groups)

1. **Runtime** — the lifecycle knobs (money/lifecycle machinery — hard invariants live here):
   - **Max retries** (`SF_AUTO_RESUME_MAX`, default 6, int 0–25) — retries beyond the cap pause the run for input.
   - **Stage reserve** (`SF_STAGE_RESERVE`, default 5, int 0–50) — stage slots held back from general use.
   - **Reaper interval** (`SF_REAPER_INTERVAL_TICKS`, default 7200, seconds, floor 300).
   - **GitHub reaper interval** (`SF_GITHUB_REAPER_INTERVAL_TICKS`, default 7200, seconds, floor 300).
2. **Deployment — default run-app targets** — where apps get deployed by default:
   - **Railway project IDs** (`SF_RUNAPP_RAILWAY_PROJECT_IDS`, comma list, each validated as a UUID).
   - **Railway environment IDs** (`SF_RUNAPP_RAILWAY_ENVIRONMENT_IDS`, comma list of UUIDs).
   - **Guard:** if any entered ID matches the console's own project (`SF_CONSOLE_RAILWAY_PROJECT_IDS` — **env-only, shown read-only here**), saving requires an explicit typed confirmation: pointing credentialed run-apps at the console project is a trust-boundary break (see `env.py`).
3. **Notifications** —
   - **Notify-from** (`SF_NOTIFY_FROM`) — validated `Name <email>` format.
   - **Notify recipient** (`SF_NOTIFY_EMAIL`) — where platform alerts go.

Save is per-section with an inline ✓; failed saves surface the server's actual error text.

---

## 4. Agent pipeline (data model for the build)

Pipeline nodes (each spawns a sub-agent that produces artifacts):
`extract, provision, research, [Stage 1 gate], architect, design, tickets,
[Stage 2 gate], wait-for-deps, build, test, deploy`.

- **provision** → GitHub repo. **research** → research `.md` files.
- **product council** → `PRD.md`. **architect** → `architecture.svg` + data model.
- **design** (the step previously missing) → screen designs.
- **tickets** → build backlog. **build** → agents (Opus/Sonnet) claim & implement.
- **test** → Playwright e2e; failures loop back to build. **deploy** → live app + repo.

Agents (callsigns): Orchestrator·ATLAS, Product Manager·HORIZON, Design·CHROMA,
Marketing·SIREN, Proposal·TENDER, DevOps·FORGE, Operations·GARRISON, Data·MATRIX,
EDI·LEDGER, ERP·CONDUIT, WMS·CARGO, Pricing·PROFIT. Each has a model, cost band,
success rate, and an editable system prompt (see §3.4).

---

## 5. Build notes / non-goals for the prototype
- All data is mock but representative; wire to real services when implementing.
- The design canvas uses scripted Concierge replies for visual demonstration only. The implemented
  app uses the live LangChain Concierge described in §2.4a and `docs/ARCHITECTURE.md`; never port the
  prototype script into runtime behavior.
- `Factories` (OS) is a placeholder. `Settings` (OS) is specced — §3.8.
- The canvas (`Software Factory Onboarding.html`) is a presentation shell only;
  the real app should route these screens with a router and real auth/state.

---

## 6. Design changes this iteration — where to find each

> Step-by-step click paths to review everything added since the **Tenexity admin
> role** work. The prototype opens as a pan/zoom canvas of artboards; double-click
> an artboard (or use its focus control) to open it full-screen. Files that
> "open in a new tab" launch `ArtifactViewer.html`.

**Starting point — make someone a Tenexity admin** (§3.4a)
1. Open the **Tenexity OS · admin portal** artboard → sidebar **Users**.
2. Click **+ Add user** → toggle **Belongs to → Tenexity · internal**.
3. In **Role**, choose **Admin** (= full platform read/write). Note the purple `TENEXITY ADMIN` badge it earns in the table vs an org-level Admin.

**1 · Master users table & email-password provisioning** (§3.4a) — OS → **Users**. Audience toggle (All / Organizations / Internal), add via Google / Microsoft / **Email & password** / Org SSO; for email-password set an initial password to provision directly, or leave blank for an invite link. Row kebab / edit drawer = disable / re-enable / remove / resend.

**2 · client → organization rename** — everywhere in OS (nav **Organizations**, the Projects table's organization column, Overview metric). The word "client" no longer appears in customer-facing copy.

**3 · Account menu & sign out** (§3) — OS top-right **avatar** → menu → **Sign out** → signed-out screen → **Sign back in**.

**4 · Asana import removed** (§3.2) — OS → **Organizations**: the old "Import from Asana" button + error banner are gone; just **+ New organization**.

**5 · Recipes library** (§3.4b) — OS → **Recipes**. Pick a recipe in the left list → edit its name/tagline/category/systems, the customer-facing capability list, the **linked GitHub repos** and **image artifacts** (internal), and the markdown description (**Write · Split · Preview**); cycle its status (Draft/Published/Archived); **+ New recipe** seeds a blank Draft; **Open in viewer ↗** opens the description in the Artifact Viewer (new tab). Customers select from Published recipes during intake (see #31).

**6 · Artifact Viewer + markdown viewer** (§2.7) — OS → **Artifacts** (index of every file) → click any card to open `ArtifactViewer.html` in a new tab. Also reachable from a project's **Produced documents** / **Documents** tab and the console tree/map/concierge. Markdown files render as formatted content with an "On this page" TOC; SVG/code/JSON/CSV/repo/image each get a typed view.

**7 · Operators open any project's dashboard** (§3.3) — OS → **Projects** (or the Overview "most active" list) → **click a project row** → its Overview / Documents / Factory-console tabs, with **← Projects** back.

**8 · Filter projects by user** (§2.2, §3.3) — OS → **Projects** → **All users** dropdown (each row shows its owning operator). Customer side: **Dashboard** artboard → **All team members** dropdown (owner avatar on each row).

**9 · Draft → start building** (§2.5a) — **Dashboard** → open the **Sales commission calculator** (Draft) project → Overview shows the "Finish setup to start building" banner + setup checklist → **Complete setup & start building** resumes intake → **Hand off to factory**.

**10 · Build engine selector** (§2.4) — **New project** intake (Option C artboard) → **Build engine** card: **Claude** vs **OpenCode** (→ Kimi K2.7 / GLM 5.2), each with **Use Tenexity's key** / **Bring your own key**. The choice shows in the factory-console header badge.

**11 · Save & finish later** (§2.4) — Option C footer → **Save & finish later** (stores a draft) alongside **Hand off to factory**.

**12 · Scope of work "+ Add"** (§2.4) — Option C → **Scope of work** card → **+ Add** chip to type a custom scope / software type.

**13 · Edit org fields in place** (§2.4) — Option C (returning mode) → on-file org card → **Manage** turns every cell into an inline input.

**14 · Concierge artifact display + working indicator** (§2.6) — open the **Factory console** artboard → left **Concierge** rail: switch artifact view **Feed · Tray · Latest**; type in the composer and **Send** to see the **typing/working** indicator; header shows a live **Working** chip while the build runs. **(Superseded by entry 21 — the Concierge moved to a right-hand dock on every Project Console surface. The left rail no longer exists; the one-Concierge rule and its placement are §2.4b.)**

**15 · Crash / pause recovery** (§2.6) — Factory console → header **Pause** → the stage-rail flags the halt node and the **Recovery bar** appears: **Resume from `<node>`**, **Retry `<node>`**, or **Rewind to…** (also click any completed stage chip to rewind).

**16 · Exit onboarding / go back** (§2.4) — **New project** intake (Option C artboard or Dashboard → New project) → header **← Projects** leaves intake and returns to the Projects dashboard at any time, without handing off. The standalone onboarding artboard is wrapped in `OnboardingStandalone` so the back control has a real exit target there too.

**17 · Project budget cap** (§2.4, §2.5a, §2.6) — the project's **total spend ceiling** (absolute, not monthly). Set during intake via the **Project budget cap** field (`BudgetPicker`: $30 / $60 / $120 / $250 + custom). Update it later from the project **Overview → Build status** panel: the `$<cap> total` chip → pencil → inline editor. The value drives the factory-console header `spent … / $<cap> cap`.

**18 · Loading & fetch states** (§1.1) — open the **Loading & fetch states** section. The **Loading kit** artboard catalogs every skeleton / field / list / table / card type. The four **Live** artboards (projects dashboard, project overview, organization admin, users table) replay a real fetch — hit the **Reload** chip (top-right) to watch lists/tables/fields shimmer then resolve. All data-bound screens accept a `loading` prop and render their matching skeletons.

**19 · Archive / delete a project** (§2.5) — Projects dashboard → any project row's **⋯** menu → **Archive project** (confirm modal) moves it to the **Archived** section. From there the **⋯** menu offers **Restore project** and **Delete permanently** (confirm modal, destructive).

**21 · Concierge interview flow + persistent dock** (§2.4a, §2.4b) — historical design milestone.
The intake CTA became **Continue**, not "Hand off to factory." Flow: **Intake form → Processing
screen (`ProcessingScreen`, ingest progress bar + live log + ETA) → live Concierge interview →
Hand off to factory.** The current gate and the two valid handoff initiators are defined only in
§2.4a; the former fixed-question completion gate is superseded. Large uploads can be sent to the
**background** (project home with a live "processing" banner + **Resume interview**). One
persistent `ProjectConcierge` dock (right side, `width 340` when open) now appears across the
Project Console and can be minimized without reserving width. It is driven by the current project
view's `context` prop. Files: `concierge.jsx`, `optionC.jsx`
(state machine + `InterviewView`), `orgproject.jsx` (dock + background banner),
`buildprogress.jsx` (dock on console). Document Q&A with **citations is a later feature** —
groundwork only.

**23 · Interview answers are single/multi-select check lists** (§2.4a) — historical prototype
milestone, superseded by the live interview. The agent may still offer single- or multi-select
options, but there is no fixed `INTERVIEW_Q` list or client-side question counter.

**24 · Create the project first (intake gate)** (§2.4) — the first thing the user does in intake
is name the project and click **Create project** (`SaveBasics`). This is a real creation event
— a **`POST` that writes the project to the DB in `draft` state** (not a local draft-save).
Everything after **enriches that project and advances its state** (`draft` → collecting
information → building). Until it's created, Scope / Build engine / Materials stay grayed out
and inert (`LockedGroup`). Files: `optionC.jsx` (`draftSaved` state, `SaveBasics`, `LockedGroup`,
both fresh & returning modes); new `lock` icon in `shared.jsx`.

> **Implementation note:** the prototype models the creation with a local `draftSaved` boolean;
> wire `Create project` to the real `POST /projects` (returns the new project id, state
> `draft`) and have the subsequent steps `PATCH` that project as they enrich it.

**25 · Voice dictation on every text field** (§1) — every text input/textarea now has a **mic
button** for speech-to-text, powered by a shared `useDictation` hook + `MicButton` (Web Speech
API, `shared.jsx`). Built into the shared `TextInput`, `TextArea`, and `Composer` primitives
(so it propagates everywhere automatically), plus the upload-description box, the agent
system-prompt editor (`admin.jsx`), the former SOW title + body (later removed with `sow.jsx`), inline org-cell edits,
and the file/user search boxes. Tapping the mic turns it red and appends transcribed speech to
the field's current value; tapping again stops. On browsers without SpeechRecognition the mic
**renders nothing** and fields are unchanged (no layout shift). Password fields are excluded.

**26 · Organization secret vault + import into projects** (§2.3, §2.6) — new **Secrets** section in
Org admin (`orgproject.jsx`, `ORG_SECRETS`): encrypted, write-only org-level API keys/tokens
referenced by name, with masked values, used-by counts, and Rotate/Add. Projects import them at
the build's **wait-for-deps** step: the **Input key** option now has **Import from org secrets**
(`DepRow` in `buildprogress.jsx`) that wires a dependency to a vault secret by reference
(`org:<NAME>`), with a `MATCH` badge on the best-fitting secret. Manual paste still available.

**27 · Intake reduced to the single finalized flow** (§2.4) — the alternate onboarding **option
studies (A · Guided Stepper, B · Context Workspace) were removed** to eliminate duplication;
only the Concierge-led intake remains. Deleted `optionA.jsx` / `optionB.jsx` and their imports;
the New-project-intake section now holds one artboard (`OnboardingStandalone`).

**28 · Factory console is a tab, not a separate screen** (§2.5) — the standalone console artboard
now renders the full tabbed project shell (`ProjectViewStandalone initialTab="build"`) landing
on the **Factory console** tab, instead of a bare `BuildProgress`. Tabs are live, so it matches
the connected flow and you can switch to Overview / Documents in place. `ProjectViewStandalone`
gained an `initialTab` prop.

**29 · Distinct chat-bubble colors** (§1) — Concierge/agent and user bubbles are now clearly
distinguishable: agent = solid `T.brandSoft` fill + brand left-accent bar + brand-tinted border;
user = solid `T.sunken` fill + default border (previously both were near-white and hard to tell
apart). Single change in the shared `Message` component (`shared.jsx`) so it applies to every
chat surface — interview rail and the persistent dock.

**30 · Collapsible, reordered dashboard project groups** (§2.2) — the Projects dashboard groups
(**Deployed**, **In progress**, **Archived**) now have collapsible headers (click-to-toggle
button + rotating chevron; count persists while collapsed), and **Deployed is ordered above
In progress**. Files: `dashboard.jsx` (`collapsed` state, `SectionHeader` helper).

**31 · SOW → Recipes** (§2.4, §3.4b) — the "Statement of Work" concept is replaced by **Recipes**:
reusable build blueprints the internal team curates. OS **Recipes** library (`recipes.jsx` →
`RecipeLibrary`, data in `recipedata.jsx`) lets operators attach **customer-facing** fields
(name, tagline, category, systems, capability list) plus **internal-only build assets** — linked
**GitHub repos** and **image artifacts** — and a markdown description; status is Draft / Published
/ Archived. Customers pick from **Published** recipes during intake via `RecipePicker` (a card grid
showing only the light fields, plus a **No template** option — value is a recipe id or `null`);
they never see the repos/images/notes. Deleted `sow.jsx` / `sowdata.jsx`; renamed OS nav item and
`ArtifactViewer.html` / `Software Factory Onboarding.html` imports; added `github` / `image` /
`book` icons (`shared.jsx`, `admin.jsx` NAV_PATHS). Recipe descriptions register into the artifact
registry as type `md` (project "Recipes"). Files: `recipedata.jsx` *(new)*, `recipes.jsx` *(new)*,
`optionC.jsx` (recipe card in both intake modes), `admin.jsx`.

**32 · Org documents in the project Documents tab** (§2.5b) — the Documents tab now shows a **"From
your organization"** group (the org knowledge-base docs, `ORG_DOCS`, reused across projects) between
"Uploaded by you" and "Produced by the factory"; the header count includes it. File:
`orgproject.jsx` (`ProjectDashboard` docs tab).

**33 · Web prefill — "we already know you"** (§2.4, §2.3) — **the wow feature.** First-time intake now
leads with **Start with your website**: type a domain → **Find my company** → a `MiniLog` of the
lookup runs visibly → the **found-company card** appears: ai-tint rows for company / industry / HQ /
headcount / systems-in-use / brand palette, each with a **source label**. **Use these
details** fills the whole setup form (industry tiles, sub-focus, profile, Epicor connection); the card
collapses to a green confirmation. Nothing writes until the user accepts — the sources-not-tiers
contract (§1). Same flow lives in Org admin → Company profile as **Enrich from web**. Files: `discovery.jsx`
(`EnrichFromWeb`, `FoundCompanyCard`, `MiniLog`), `optionC.jsx` (fresh-mode card + `applyEnrich`),
`orgproject.jsx` (profile enrich panel).

**34 · Codebase discovery + Development conventions** (§2.3) — the on-ramp for companies that already
ship software (CBT's case). Org admin gains two sections. **Codebase discovery**: point discovery
agents at a GitHub repo → crawl log → generated **AGENTS.md / CLAUDE.md / integrations.md** (ai-tint
rows + source labels) saved into the knowledge base; read-only agents, tokens live in Secrets.
**Dev conventions**: primary repo, framework, install/test commands, and coding standards with a live
**"What every build agent receives"** compiled-AGENTS.md preview — injected into every build agent's
context. Files: `discovery.jsx` (`DiscoverySection`, `ConventionsSection`), `orgproject.jsx` (sub-nav
+ sections).

**35 · Brand & theme** (§2.3, §2.6) — Org admin → **Brand & theme**: **Process theme from my website**
→ crawl log → token pack (palette rows with hex + source label, type stack, logo tile) and
a **live preview** of a generated app shell rendered in the found theme. The pack is what the design
node's Kimi K3 mockups (§2.6 design review) and every generated app are themed by; the knowledge-base
`brand-guidelines.pdf` is the named fallback. Files: `discovery.jsx` (`ThemeSection`), `orgproject.jsx`.

**36 · Engine trio** (§2.4, §2.6) — the build-engine picker is now **Claude Code** (default) /
**Codex 5.6** / **Kimi K3** — three provider cards with vendor labels; BYOK segment unchanged. The
`opencode` provider + model sub-pick is gone; value shape is `{ provider, keySource, key }`. Console
header badge + process-tree label follow the choice. Files: `optionC.jsx` (`ENGINES`, `engineLabel`,
`EnginePicker`), `buildprogress.jsx` (`engShort`).

**37 · Concierge recipe suggestion + Explore gallery** (§2.4, §2.8, §2.2) — when the goal matches a
Published recipe and none is picked, the intake concierge rail offers an inline **Recipe match** card
(ai-tint; Use this recipe / No thanks; dismiss = no nag); accepting sets the picker and flips the card
to a green confirmation. **Explore** is a new top-level destination (dashboard button, §2.2): the
inspiration gallery of Published recipes with public preview images, **Start from this →** preselecting
the recipe in intake, and a dashed **start blank** card. Recipe image artifacts gained a **Public /
Internal** toggle (only public images show in Explore). Four recipes added toward the five-tool goal:
**Vendor Scorecard, Rebate Tracker, Order Entry Automation, Quote Follow-Up** (all Published, repos
under `tenexity-factory/`). Files: `optionC.jsx` (`suggestRecipe`, rail card), `recipes.jsx`
(`ExploreRecipes`, image public toggle), `recipedata.jsx` (new recipes, `public` flags),
`dashboard.jsx` (Explore button + route), `Software Factory Onboarding.html` (Explore artboard).

**38 · Design review stage-gate** (§2.6) — the pipeline's design node now **waits for the customer**:
once design completes, a `STAGE-TRIGGERED` **Design review** bar appears in the factory console —
mockup tiles of the Kimi K3–generated screens (click → the `screens` fig artifact), **Approve &
continue** (locks the look, green "Design locked" state, re-openable) or **iterate via the Concierge**
(re-generates only affected screens). Copy ties the screens to the org's brand theme (entry 35).
File: `buildprogress.jsx` (`DesignReviewBar`).

**39 · OS System settings — the console's own settings leave the env** (§3.8) — new OS **Settings**
page: **Runtime** (max retries, stage reserve, reaper + GitHub-reaper intervals, with floors),
**Deployment** (default run-app Railway project/environment IDs, UUID-validated, typed-confirm guard
when an ID matches the console project), **Notifications** (notify-from, notify recipient). Storage is
`system_settings` (DB-first, env fallback); hot settings apply on save, others get an honest "applies
on restart" badge; every row is audited. Bootstrap floor stays env (DATABASE_URL, crypto roots,
deployment identity); the console-project allowlist is env-only by design (trust boundary).

**40 · Tool editor: per-tool config + write-only secrets, injected into env at startup** (§3.6) —
clicking a tool row opens its editor: per-tool JSON config (the existing `fusion` pattern), **secret
fields** (e.g. Exa's API key) with the write-only/masked/rotate vault contract, an **`env_key`** mono
badge ("injected as `EXA_API_KEY` at console startup" — startup hydration, §3.8), **Attached to**
agent list, and **honest status** (`live` only after a real call succeeded; otherwise `missing key` /
`failing — <real error>`). Logical separation: tool settings live on the tool, platform settings live
in §3.8 — never mixed.

**41 · Confidence pills retired product-wide — sources, not tiers** (§1; operator ruling, 2026-07-21)
— no asserted confidence level appears anywhere: we have no evidence-derived way to compute one
(Principle 4). Stripped from: the **enrichment surfaces** (found-company card, discovery generated
docs, theme token pack — entry 33/34/35 surfaces), the **interview LEARNED rows** (per-fact
source-file chip stays — the §2.4a trace contract is unchanged), **concierge message pills**
(interview rail + persistent dock seeds), **kanban ticket confidence** (Building tickets show the
working dot), the **artifact topbar** band, the PRD-artifact mock content, and the **agent prompt
texts** in the OS roster (they now instruct "cite the source — never assert a confidence tier").
Every AI-derived value carries a **source label** (mono + link icon: url, file, or crawl step). The
`ConfidencePill` primitive remains in `shared.jsx` for now but renders nowhere; §1 documents the rule.
Files: `discovery.jsx`, `optionC.jsx`, `concierge.jsx`, `buildprogress.jsx`, `buildboard.jsx`,
`artifactviewer.jsx`, `artifacts.jsx`, `admin.jsx`, `shared.jsx` (comments), `PRD.md` (§1, §2.4a,
§2.6, §2.7, this entry).

**42 · Invite-led organization onboarding — the full experience from one email** (§3.2, §3.7, §2.1)
— organizations are created **by inviting their admin**, never by hand-entering telemetry:
the old "New organization" form (which asked operators to type *computed* values — spend, active
projects, tickets, last activity) is gone from the spec; those columns are system-derived. The
**Provide access** modal (now actually wired — top-bar button + the §3.2 button; it previously
existed unrendered) lets the operator **pre-seed identity/context fields** (name + website prefilled
from the invite email's domain, industry optional — all editable) and shows a **"What happens next"**
strip: invite email → sign in **with their preferred method** (Google / Microsoft / email / SSO, all
equal) → first sign-in **always** routes to **first-time onboarding** — operator-provided fields
already on file, the web prefill (entry 33) researches the rest **with them** → they confirm →
context → **first project**, one sitting, Concierge the whole way. Nobody fills anything in twice.
Files: `admin.jsx` (`guessOrgFromEmail` + domain prefill, modal fields, wiring), `PRD.md` (§2.1
routing, §3.2 computed columns, §3.7 chain).

**43 · Technical-user flow (repo + PAT + conventions) & Explore navigation** (§2.4, §2.3, §2.8) —
**Technical setup:** first-time intake gains a collapsed **"I'm a technical user — bring my own
repo & conventions"** card (`TechSetupCard`, inside Connect-your-systems): GitHub repo link (the
build seed), **GitHub PAT** (write-only → org vault as `GITHUB_PAT`), framework & runtime,
install/test commands, coding standards — saved to the **organization** (same data as §2.3
Codebase discovery / Dev conventions, which is where it lives for existing orgs). The Org-admin
discovery section now shows the **PAT field explicitly** (write-only, read-only agents). Collapsed
by default — non-technical users never see it as required. **Explore navigation:** the gallery
(§2.8) is reachable from ① the dashboard **Explore** button (entry 37) and now ② a **"Browse the
gallery"** link inside the intake **Recipe** card (both modes); ← Projects returns to the
originating screen (`route.from`); the canvas artboard shows the back chrome. Files: `optionC.jsx`
(`TechSetupCard`, `onExplore` prop, gallery links), `discovery.jsx` (PAT field), `dashboard.jsx`
(explore round-trip), `Software Factory Onboarding.html` (artboard chrome), `PRD.md` (§2.3, §2.4,
§2.8, this entry).

---

## 7. File map for this iteration (quick reference)

- **`TICKETS.md`** *(new)* — the CBT design-partner sprint: 31 tickets (CBT-1…31) across four lanes
  (DSN design / WEB console frontend / PIPE pipeline-backend / OPS infra), grounded in a recon of the
  real codebase; wave-ordered for the 27th. File into Linear (team SOF).
- **`discovery.jsx`** *(new — loaded in `Software Factory Onboarding.html` right after `concierge.jsx`)*
  — `MiniLog` (compact streaming agent log), `EnrichFromWeb` + `FoundCompanyCard` (web prefill),
  `DiscoverySection` (repo crawl → agent files), `ConventionsSection` (org AGENTS.md compiler),
  `ThemeSection` (brand token pack + preview). One interaction contract everywhere: visible agent
  work → ai-tint findings with a source label per field → user confirms.
- **`optionC.jsx`** — fresh-mode **Start with your website** card (`applyEnrich`), `suggestRecipe` +
  the concierge-rail **Recipe match** card, engine **trio** (`ENGINES`/`engineLabel`/`EnginePicker`
  restructured to `{ provider, keySource, key }`), `initialRecipe` prop (Explore preselect).
- **`orgproject.jsx`** — OrgAdmin sub-nav + sections: **Brand & theme**, **Codebase discovery**,
  **Dev conventions**; Company profile **Enrich from web** panel.
- **`recipes.jsx`** — `ExploreRecipes` gallery (§2.8); ImageEditor **Public/Internal** toggle.
- **`recipedata.jsx`** — four new Published recipes (Vendor Scorecard, Rebate Tracker, Order Entry
  Automation, Quote Follow-Up); `public` flags on preview images.
- **`dashboard.jsx`** — **Explore** header button; `FactoryApp` gains the `explore` route and passes
  `initialRecipe` into `OptionC`.
- **`buildprogress.jsx`** — `DesignReviewBar` (stage-triggered design gate, §2.6); `engShort` maps the
  engine trio.
- **`shared.jsx`** — three new icons: `globe`, `palette`, `compass`.
- **`Software Factory Onboarding.html`** — loads `discovery.jsx`; new **Explore** artboard in the
  product-flow section.

**Settings work (entries 39–40) — design files + the real-code targets for implementers:**
- **`admin.jsx`** — `AdminSettings` page (§3.8) + the tool editor drawer on the Tools registry (§3.6);
  the OS **Settings** nav item is no longer a placeholder.
- Real-code targets (for the implementing agent — do not guess paths): `ToolStore` +
  `src/software_factory/services/admin_service.py` (existing DB-config + OS routes — extend with
  `system_settings` + secret rows), `src/software_factory/env.py` (startup hydration hook; keep
  `_STAGE_ESSENTIAL` semantics), `console/routers/*` (OS endpoints), `console/web/src/admin/*`
  (the real Settings/Tools screens).

**Tokens used by the new screens** (all from the `T` object in `shared.jsx`): `T.brand`
`#1A7BFF`, `T.brandSoft` `#E8F1FF`, `T.brandDeep` `#0958C9`, `T.success` `#059669`,
`T.successSoft` `#E4F8EF`, `T.bg` `#FAFAFA`, `T.raised` `#FFF`, `T.sunken` `#F4F4F5`,
`T.ink` `#060709` (the dark ingest-log panel), `T.borderSubtle` `#E7E7E9`, `T.fg`/`T.secondary`/`T.tertiary`
text ramp, radii `T.rMd`/`T.rLg`/`T.rXl`, `T.shadowXs`, fonts `T.sans` (Hanken Grotesk) /
`T.display` (Georgia) / `T.mono` (JetBrains Mono). Animations: `sfRise` (log/message entrance),
`sfPulse` (live status dot), `.sf-spin` / `sfSpin` (processing spinner) — all defined in the
`<style>` block of `Software Factory Onboarding.html`.

---

## 8. Success metrics, priorities & risks (folded in from the retired product spec)

> Consolidated here during SOF-224 from `docs/product-spec-software-factory.md`
> (since deleted) so its content survives without a second requirements document.

### 8.1 Success metrics

- **Activation:** % of new organizations completing first-project intake (create →
  confirm interview → hand off) without abandoning; time from account creation to
  first hand-off; second-project intake time vs. first (proves org-context reuse).
- **Trust & comprehension:** accept-vs-correct rate on system-inferred facts (healthy
  = trends toward accept because extraction improved, not because customers stopped
  checking); Concierge-escalation rate during builds.
- **Delivery reliability:** % of builds reaching 100% without customer-visible
  manual recovery; of stalled builds, % resumed vs. restarted; % of projects inside
  their spend cap, and how often approval pauses are granted (a very low grant rate
  means the cap UX is miscalibrated).
- **Business outcomes:** deployed-project rate (created → Deployed); cap-vs-actual
  spend variance; operator leverage (orgs per Tenexity operator, tracked alongside
  manual-rescue rate so it can't be gamed).

### 8.2 Prioritization

- **P0 (nothing works without these):** sign-in & access control; explicit
  create-gate (§2.4); processing & interview before any build (§2.4a); the build
  board with stage progress, crash recovery, dependency resolution (§2.6); the
  persistent Concierge (§2.4b); basic cross-tenant visibility + sign-in management
  (§3.2/§3.4a).
- **P1 (complete, not just functional):** org shared context & hierarchical knowledge base
  (§2.3, §2.5d); projects dashboard w/ archive/delete (§2.2); project overview (§2.5a); Artifact
  Viewer (§2.7); extra build-board views; agent roster (§3.5); tools registry (§3.6).
- **P2 (high value, can trail):** the full produced-files index (§3.4c); markdown
  polish in the goal field.
- **Deferred by design (not deprioritized):** inline document-citation Q&A in the
  Concierge (§2.4b groundwork only) — never smuggle it early.
- **Background processing during ingest is CURRENT** (§2.4a) — the retired spec's
  P2 label for it was its own internal contradiction; the §2.4a capability spec
  (background banner + resume) is the rule.

### 8.3 Risks & open questions (kept visible on purpose)

1. **Reflection-step trust risk.** A wrong uncaught "what I learned" fact poisons the
   whole build. Correction must stay cheap and obvious (§2.4a) — it is the single
   biggest trust risk in the product.
2. **Question fatigue vs. brief quality.** Who/what decides "enough" — and is the
   threshold the same for a 5-minute and a 5-week project? (Principle 6 is the
   current answer: the customer decides.)
3. **Budget-cap trust runs both directions.** Too aggressive pauses feel naggy; too
   permissive erodes the promise. Should the default adapt to project size?
4. **Single-voice intake.** Is there real demand for a second stakeholder on one
   brief — and would that live inside or outside the Concierge conversation?
5. **Internal rescue as a crutch.** If staff can too easily save stuck projects, the
   platform never learns whether self-serve works. Guardrail = track unassisted
   build rate and operator leverage together (§8.1).

---

## 9. Adjudication log — SOF-224 consolidation

> Every conflict the consolidation review found, the ruling, and where it now
> stands. "WEB" = implementation fix owned by the console-frontend lane (filed in
> Linear, not this PR); "DONE" = already correct in this file before SOF-224.

| # | Conflict | Ruling | Status |
|---|---|---|---|
| 1 | Concierge chat could silently create an `Untitled project` draft | Chat collects locally; creation is ONLY the named **Create project** action (Principle 3) | Spec'd §2.4; app bug → WEB |
| 2 | App's interview and handoff behavior diverged across prototype, prompt, and UI | Source-backed reflection remains required; readiness = agent judgment + `product_brief EXISTS`; button or Concierge tool may hand off after agreement; either success navigates to Factory Console | Reconciled §2.4a; reflection presentation remains WEB |
| 3 | Budget labeled "optional" yet required by readiness | Cap is **required** — money-safety; no uncapped copy anywhere | Spec'd §2.4; app copy → WEB |
| 4 | Failed doc-list load auto-advanced as "nothing to process" | A failed ingest never advances; real error + retry; `onDone` never fires on failure | Spec'd §2.4a; app → WEB |
| 5 | Confidence pills both required (old §1) and forbidden (operator ruling) | **Sources only, product-wide** — the dated ruling wins; pills stripped from archive (entry 41) | DONE here; residual app rendering (ticket confidence) → WEB |
| 6 | Concierge placement: left on console, right elsewhere; entry 14 vs 21 | **Right-hand dock everywhere**, context-specific copy (§2.4b); entry 14 marked superseded | DONE here; app console placement/contexts → WEB |
| 7 | Engine design one generation behind (Claude/OpenCode+subpick) | **Trio:** Claude Code / Codex 5.6 / Kimi K3 (entry 36) | DONE here; app picker → WEB (shipped w/ Wave 1) |
| 8 | Auth spec promised Microsoft/SSO/recovery/SOC-2 the app deliberately omits (SOF-15) | Current = Google + email/password; the rest marked **future — never render unverified affordances** | Spec'd §2.1 |
| 9 | Recipes vs SOW: replaced here, still a library in the old spec | Recipes are the sole library; SOW storage, routes, UI, and fallbacks are retired | Reconciled §3.4b |
| 10 | Artifact Viewer promised typed json/csv/repo; app uses generic `<pre>` | Typed views = designed/future; current = generic renderer | Spec'd §2.7 |
| 11 | Future artboards (Explore, Brand & theme, Dev conventions) looked current | Labeled **WAVE 2 — designed, not yet shipping** (§2.3, §2.8, canvas labels); prefill/discovery/engines labeled **WAVE 1 — shipping** | DONE here |
| 12 | This archive was missing `TICKETS.md`, §2.8, entries 33–41 referenced by the Wave-1 doc | Landed via PR #379 (design archive now tracked in git) | DONE |
| 13 | Project overview mixed user direction, source files, factory outputs, services, and agents as equal cards | Keep one project shell; separate Product Brief, Factory outputs, Factory console, and Files; preserve the full Concierge; fixed brief templates are forbidden | Designed §2.4a–§2.7; app implementation → WEB |
| 14 | The source-material API and Files screen are flat, so neither people nor agents can narrow retrieval by directory | Add real scoped directories, read-only generated subtree summaries, directory-first agent retrieval, and an icon-led browser; this requires database, ingestion, API, tool, and frontend work | Designed §2.5d; app implementation → WEB |

**Docs disposition:** completed product specs, Concierge/project-memory designs, and Wave-1
implementation plans were consolidated into this PRD and `docs/ARCHITECTURE.md`, then deleted.
Git and Linear retain their historical decisions; the working tree keeps only current guidance.
