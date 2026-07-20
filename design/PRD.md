# Software Factory — Product Requirements (screen spec)

> Source of truth for build agents. Describes every screen in the prototype
> (`Software Factory Onboarding.html`), what it does, its components, data, and
> interactions. Visual system = Tenexity design system (see §1).

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

---

## 1. Design system (apply to every screen)

- **Brand** `#1A7BFF` (deep `#0958C9`, soft `#E8F1FF`). Bg `#FAFAFA`, raised `#FFF`, sunken `#F4F4F5`.
- **Type**: Hanken Grotesk (UI/sans), Georgia (display/headlines), JetBrains Mono (data, labels, technical).
- **Category labels**: 11px, uppercase, letter-spacing 0.12em, tertiary color.
- **Confidence cascade** for AI-derived values: Exact (green) / High (teal) / Medium (amber) / Low (red) / Unknown (grey), shown as a pill with a 4-point sparkle.
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
`StatusPill`, `ConfidencePill`, `Avatar`, `AiTint`, `Message`, `Composer`, `Wordmark`,
`CategoryLabel`, `SectionDivider`, `ScopeToggle`, `Icon`, `Sparkle`.

---

## 2. CUSTOMER PRODUCT

### 2.1 Login  (`login.jsx` → `Login`, gated by `AppRoot`)
**Purpose:** authenticate and enter the product.
**Layout:** two-pane. Left = dark brand panel (wordmark, value prop, decorative
process-node graph, SOC-2 trust line). Right = auth form.
**Auth options (all required):**
1. Continue with **Google** (official multicolor mark).
2. Continue with **Microsoft** (4-square mark).
3. **Email + password** (show/hide toggle, forgot-password link).
4. **Organization SSO** — toggles to a work-domain entry (SAML/OIDC), with a back link.
**Footer:** "Request access" for users not yet on the allow-list.
**Behavior:** any successful auth → projects dashboard. Sign-in is gated by the
allow-list managed in Tenexity OS (§3.6).

### 2.2 Projects dashboard  (`dashboard.jsx` → `Dashboard`; nav shell `FactoryApp`)
**Purpose:** the home screen after login; list the org's projects.
**Top bar:** wordmark · org switcher (→ Org admin) · search · user avatar.
**Body:**
- Header "Your projects" + **New project** CTA.
- **Pulse strip** (4 metric cards): Active projects / In build / Deployed / Spend this month.
- **Org admin preview** (admins only): a compact, clickable preview of the organization (industry, scale, knowledge-base count, connected systems, team) with **Manage organization →** to the org admin page. Gated on `isAdmin` — **non-admin users see nothing in its place** (the list simply moves up). Replaces the former Concierge brief.
- **Project list**, in **collapsible groups** ordered **Deployed** (top), then **In progress**, then **Archived** (only when non-empty). Each group header is a click-to-toggle button with a rotating chevron; the group's count stays in the header while collapsed. Each row: owner avatar, name, status pill, phase + progress bar, agents (avatar stack), last activity, spend, and an overflow (⋯) menu. A **team-member filter** ("All team members") in the header filters all groups by project owner.
- **Archive / delete a project** — each row's ⋯ menu offers **Archive project**; archiving (after a **confirmation modal**) moves it to an **Archived** section, stops running agents, and pauses the automation. Archived rows get a ⋯ menu with **Restore project** (non-destructive, no confirm) and **Delete permanently** (destructive — guarded by a confirmation modal that names the project; removes it and its build history). The Archived section only appears once something is archived.
**Statuses:** Building, Researching, Needs input, Draft, Deployed.
**Behavior:** click a project → its **project view** (Overview tab). Draft → onboarding (§2.4). New project → onboarding. Org switcher → Org admin.

### 2.3 Organization admin  (`orgproject.jsx` → `OrgAdmin`)
**Purpose:** the org's context + org-scoped documents, reused by every project.
**Layout:** left sub-nav + content. Sections:
- **Company profile** — canonical org context (name, industry, sub-focus, HQ, founded, headcount, revenue, website, footprint). Editable. Note: Concierge reuses this to skip questions on new projects.
- **Knowledge base** — org-scoped documents (price book, line card, policies, brand, SOPs) as file tiles; each shows reuse count. Upload action.
- **Connected systems** — org-level integrations (Epicor connected as primary; others linkable). Reused across projects.
- **Secrets** — the organization **secret vault** (`ORG_SECRETS`): API keys, tokens, endpoints stored once at the org level. Each row shows the secret **name** (mono, e.g. `EPICOR_API_KEY`), a masked value (`••••••<last4>`), **used-by** project count, last-updated, and a **Rotate** action; **Add secret** in the header. Values are **encrypted and write-only** — once saved the raw value can't be read back (by anyone), projects reference secrets **by name**, and rotating/revoking here propagates to every project that imported the secret. Projects pull from this vault during the build's wait-for-deps step (§2.6).
- **Team & access** — members with roles; invite.
- **Usage & billing** — plan, spend, per-project spend breakdown.

### 2.4 Project onboarding  (`optionC.jsx` → `OptionC`)
**Purpose:** collect project context with a docked **Concierge**. This is the single, finalized intake design — the earlier alternate option studies (A · Guided Stepper, B · Context Workspace) have been **removed** to eliminate duplication; only this Concierge-led flow remains. Two modes via header toggle:
- **First-time** (fresh org, nothing on file): set up company (industry, profile, systems) **then** first project. Copy promises "we'll remember this."
- **Returning** (org on file): company context shown as **"on file · reused"** (collapsible, Manage to edit); only project questions are asked.
**Section separation:** a labeled `SectionDivider` splits **per-tenant (org)**
data from **this-project** data.
**Project inputs:** project name, "what are you building" (goal), **project budget cap**, **recipe** (optional blueprint), scope-of-work chips, build engine, materials.
- **Recipe** (`RecipePicker`, from `recipes.jsx`) is an **optional** starting blueprint the customer picks from the Published entries of the OS recipe library (§3.4b). The picker shows only the light customer-facing fields (category, name, tagline, a few capabilities); the recipe's GitHub repos, image artifacts, and internal notes are **not** shown. A **No template** card is always present — the customer can build purely from their brief. Lives in the "This project" section (inside `LockedGroup`, so it unlocks after the project is created); the value is a recipe id or `null`.
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
- **Project budget cap** (`BudgetPicker`) is the **absolute total spend ceiling for the whole project** (not a monthly figure) — presets ($30 / $60 / $120 / $250) plus a custom amount. The build pauses for approval when cumulative spend reaches the cap. The chosen value flows into the project Overview and the factory-console header (`spent <x> / $<cap> cap`).
- **Scope of work** chips are multi-select with a **"+ Add"** affordance — the operator/customer can type a **custom scope or type of software** not in the preset list; it's added as a selected chip.
- **Build engine** (`EnginePicker`): choose the coding agent that builds the project — **Claude** or **OpenCode**. The downstream factory + console look identical either way. Selecting **OpenCode** reveals a model choice (**Kimi K2.7** / **GLM 5.2**). For either engine, an **API key** segment: **Use Tenexity's key** (billed through the plan) or **Bring your own key** (key input). The chosen engine surfaces in the factory console header badge (`engine · <name> · TENEXITY KEY / BYO KEY`) and the process-tree orchestrator label.
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

#### The state machine (where it lives, exactly)

All four steps are one React component, `OptionC` in `optionC.jsx`. It holds a single
state variable that decides which screen renders:

```
const [view, setView] = React.useState('intake');
//  'intake'      → the creation form (the original Option C screen)
//  'processing'  → <ProcessingScreen/>           (from concierge.jsx)
//  'interview'   → <InterviewView/>               (defined at the bottom of optionC.jsx)
//  'build'       → <BuildProgress/>               (the factory console; build starts here)
```

There is also `const [interviewDone, setInterviewDone] = React.useState(false)` — it is
**false** until the user answers every interview question, and the **Hand off to factory**
button is disabled while it is false. This is the gate that stops people from skipping the
interview.

**The transitions, in order — wire them exactly like this:**

1. **`intake` → `processing`** — the green **Continue** button calls `setView('processing')`.
   (File: `optionC.jsx`, the intake footer button. It was previously `setView('build')`; do not revert that.)
2. **`processing` → `interview`** — `ProcessingScreen` calls its `onDone` prop when the
   ingest log finishes (or the user clicks **Start the interview**). `OptionC` passes
   `onDone={() => setView('interview')}`.
3. **`processing` → background (project home)** — `ProcessingScreen` also takes an
   `onBackground` prop. In the standalone artboard this is wired to jump to the **project
   home** (`ProjectViewStandalone`) with its live "processing in background" banner. See
   "Backgrounding" below.
4. **`interview` → handoff** — `InterviewView`'s interview rail calls `onComplete`, which sets
   `interviewDone = true`; that un-disables **Hand off to factory**, whose click calls
   `onHandoff` → `setView('build')`. **The build only starts here.**

#### Step 2 — `ProcessingScreen`  (`concierge.jsx`)

**Why it exists:** uploaded materials can be heavy (a long screen-recording video, a big
price spreadsheet). We must never silently freeze on a blank screen while parsing — the
user sees exactly what is being read.

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

#### Step 3 — `InterviewView` + `InterviewRail`  (interview defined in `optionC.jsx`; rail in `concierge.jsx`)

**Layout:** two columns. The **main column** is a calm review of what the Concierge learned
from the uploads; the **right rail** (`InterviewRail`, fixed `width: 340`) is the active Q&A
the user must finish.

**Main column (`InterviewView`):**
- Top bar with a **← Setup** back button (`setView('intake')`), wordmark, project name, and a
  mono badge reading **"STEP 3 OF 3 · INTERVIEW"**.
- A **"What I learned from your materials"** card: each row is an `.ai-tint` block (the
  standard AI-tell treatment from §1) carrying a learned fact, the source file name (with a
  `file` icon, in mono), and a `ConfidencePill` whose band is `exact`/`high`/`medium`. The
  rows come from the `LEARNED` constant at the top of the interview code — edit that array to
  change them.
- A **"This project"** card echoing the project name and the goal, rendered through
  `GoalMarkdown` (see §2.4c) so markdown in the goal shows formatted.
- A sticky bottom action bar: a status line (turns green and reads "Interview complete" once
  done) + the **Hand off to factory** button, disabled until `done` is true.

**Right rail (`InterviewRail`):**
- Uses the shared `ConciergeHeader` (subtitle shows `Interview · <answered>/<total>`) and a
  segmented **progress strip** (one bar segment per question: green = answered, brand =
  current).
- Asks the questions in the `INTERVIEW_Q` constant **one at a time**. Each question is
  answered through a **checkable option list** (`ChoiceList`, in `concierge.jsx`) plus a
  free-text `Composer` — both call the same `answer()` function. **Every question declares a
  `select` mode** that the model picks per question:
  - **`'single'`** — radio-style rows (round check indicator); clicking a row submits that
    answer immediately. Header label "Choose one."
  - **`'multi'`** — checkbox-style rows (square check indicator); the user ticks several, then
    a **Confirm (n)** button submits the joined set. Header label "Select all that apply."
  Each option renders as a full-width selectable row with a check mark when chosen (brand fill
  + white `check` icon), **not** as a plain pill. The `ChoiceList` is keyed by question index
  so its selection resets between questions. After each answer the agent says "Got it." and
  posts the next question (uses `setTimeout`; all timers cleared on unmount).
- When the last question is answered it posts a closing message, shows a green **"Ready to
  build"** confirmation card, and calls `onComplete()` → which flips `interviewDone` upstream.

**To change the interview:** edit `INTERVIEW_Q` (array of `{q, select, opts[]}` where `select`
is `'single'` or `'multi'`) and `LEARNED`. The number of progress segments and the gating all
derive from `INTERVIEW_Q.length` automatically — you don't touch anything else. (The pill-style
`QuickReplies` component still exists and is used for *suggested prompts* on the persistent
dock — it is **not** the interview answer control; interview answers use `ChoiceList`.)

---

### 2.4b The persistent Concierge — `ProjectConcierge`  (`concierge.jsx`)

**The one rule:** there is **one** Concierge, and it looks and behaves the same everywhere.
The factory console + project overview + documents screen together are the **"Project
Console,"** and `ProjectConcierge` is the always-visible dock (`width: 340`, right-hand,
`borderLeft`) that appears on **all three**. Same shell (`ConciergeHeader` + scrolling message
list + suggestion chips + `Composer`); only the **context** changes.

**Single prop drives everything:** `context` is one of:
- `'overview'` — project home. Subtitle "Watching this project"; suggestions are progress
  questions ("How's the build going?", "What's left to do?", "Any blockers?").
- `'build'` — factory console. Subtitle "Relaying the build"; shows a **"Steer the build"**
  helper card and the `ConciergeArtifacts` list (artifacts produced by completed nodes); a
  `WorkingPill` shows while the build runs. Takes a `build={{done,total,allDone}}` prop and an
  `onOpen` callback to open an artifact in the Artifact Viewer.
- `'docs'` — documents screen. Subtitle "Across every document"; suggestion chips ask about
  specific uploaded files (passed via the `docChips` prop). **Document Q&A with citations is
  a later feature** — the groundwork is here (`conciergeReply` matches a question against the
  `window.PROJ_MATERIALS` file list and answers from it) but inline source citations are
  explicitly deferred, and the copy says so.
- `'ingesting'` — shown on the project home while uploads process in the background. Subtitle
  "Processing in background."

**Where it is wired:**
- Factory console: `buildprogress.jsx` (`BuildProgress`) renders
  `<ProjectConcierge context="build" build={{…}} onOpen={…} />` on the right. (The old
  left-hand `ConciergeRail` was replaced by this right-hand dock so the assistant is in the
  same place on every screen.)
- Project home / documents: `orgproject.jsx` (`ProjectDashboard`) renders
  `<ProjectConcierge context={tab==='docs' ? 'docs' : (ingesting ? 'ingesting' : 'overview')} … />`.

**Shared chat engine:** all Concierge surfaces (interview rail + persistent dock) use the
`useConciergeChat(seed, replyFor)` hook in `concierge.jsx`. It owns the message list, the
draft, the "thinking" label rotation, auto-scroll, and timer cleanup. `seed` is the opening
messages; `replyFor(userText)` returns the scripted reply (`conciergeReply` handles the
persistent dock). **Replies are scripted in the prototype — connect to the live model when
implementing.**

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

### 2.5 Project view: Overview + Factory console + Documents  (`orgproject.jsx` → `ProjectDashboard`; standalone wrapper `ProjectViewStandalone`)
The project has **peer views** switched by a tab strip (Overview · Factory
console · Documents). Neither is nested under the other; shared **← Projects** exit.
The **Factory console is a tab within this shell, not a separate destination** — opening it (from a project row, the dashboard, or a standalone entry) renders the same `ProjectViewStandalone` shell with the tab strip intact, simply landing on the **Factory console** tab (`initialTab="build"`). The tabs stay live so the user can switch back to Overview / Documents in place.

**2.5a Overview (canvas):** mission-control board of zone panels over a dotted canvas:
- **Draft resolution:** when the project is still a **draft** (hasn't been handed off), the Overview leads with a **"Finish setup to start building"** banner and the Build-status panel becomes a setup checklist (Brief / Scope / Build engine / Materials) with a primary **"Complete setup & start building"** action that resumes intake (§2.4) → Hand off to factory. Services / agents / produced-docs panels show empty states until the build starts.
- **Project brief** (goal, scope chips, owner/created/phase).
- **Build status** (% complete, tickets done, agents, spend) + **Open factory console**. The **budget cap** (project-wide total spend ceiling) is shown here as `spend / $<cap>` and is **editable in place** — a `$<cap> total` chip with an edit (pencil) affordance opens an inline editor (presets + custom) so the cap can be updated any time after creation. Updates propagate to the factory-console header.
- **Services at work** (Epicor/OpenAI/Supabase/Playwright/Vercel with live status + metric).
- **Agents on this project** (who + current task + live dot).
- **Uploaded materials** (project files).
- **Produced documents** (artifact chips → open in the **Artifact Viewer**, new tab — §2.7).
- **Inherited org context** (reused-from-org summary).

**2.5b Documents tab:** all project documents in three groups — **"Uploaded by you"** (project materials) + **"From your organization"** (the org knowledge-base docs, `ORG_DOCS`, reused across projects) + **"Produced by the factory"** (artifacts) — as file tiles; produced ones open in the **Artifact Viewer** (new tab — §2.7). The header count includes all three groups.

### 2.6 Factory console (build board) — THE CORE SCREEN  (`buildprogress.jsx` → `BuildProgress`; `buildboard.jsx`, `nodemap.jsx`, `artifacts.jsx`)
**Purpose:** show and steer the agent pipeline building the project. Most
important screen in the product.
**Top bar:** ← Projects · wordmark · project name · phase pill · spend/cap. Peer tab strip when opened from a project. The `spend / $<cap> cap` reflects the project's editable **budget cap** (total spend ceiling, §2.4 / §2.5a).
**Right: persistent Concierge dock** (`ProjectConcierge context="build"`, §2.4b) — the
same always-visible assistant that appears on every Project Console screen. Relays live build
updates (e.g. "Playwright caught a tax-rounding bug, Sonnet's fixing it"), shows a **"steer
the build"** helper card and the **Artifacts produced** list, and has a composer to **steer
the build team**. (This replaced the former *left*-hand `ConciergeRail` so the Concierge sits
in the same spot — right side — on the overview, console, and documents screens alike.)
**Main column:**
- **Pipeline stage-rail** — the full pipeline as chips with Stage gates (diamonds): `extract → provision → research → [Stage 1] → architect → design(NEW) → tickets → [Stage 2] → wait-for-deps → build → test → deploy`. Done = checked, active = pulsing, deps = amber.
- **Crash / pause recovery** — each completed node writes **immutable checkpoint artifacts** (the files in the Artifact Viewer); the run's durable state is the set of completed checkpoints, not in-memory progress. When a run **crashes** (node failure) or is **paused**, the stage-rail marks the halt node (red / amber) and downstream nodes fade to `queued`, and a **Recovery bar** appears: **Resume from `<node>`** (re-runs the halt node onward, reusing every upstream checkpoint — no re-research/re-architecting), **Retry `<node>`** (re-run just the halt node, e.g. after a transient failure or a now-provided key), or **Rewind to…** an earlier checkpoint (click any completed node, or pick from the dropdown — that node + downstream are invalidated and recomputed, upstream reused). The build Kanban is idempotent per-ticket, so a resumed build picks up only the not-done tickets. Header shows `run crashed` / `run paused`; the **Pause** control drives the paused state in the demo (a crash sets the same recovery flow at runtime).
- **Wait-for-deps bar** — **stage-triggered**: appears *only after* the build reaches the wait-for-deps stage (not shown the rest of the run), marked with a `STAGE-TRIGGERED` badge and copy explaining why it surfaced now. The dependency set is **derived from the project's architecture**, so the **count varies per project** (factory + app design); the layout is an auto-wrapping grid that **scales to any number** of dependencies. Header tracks `resolved / total` and flips to "Dependencies resolved — build unblocked" when complete. Each dependency offers **3 resolution options**: **Get from MCP**, **Mock it**, or **Input key**. Build is gated until all are resolved. **Input key** additionally offers **Import from org secrets** (§2.3): a picker of the organization vault (`ORG_SECRETS`) with the best name/kind match badged `MATCH`; choosing one wires the dependency to that secret **by reference** (`org:<NAME>`) — the raw value is never shown — or the operator can still paste a key manually.
- **View toggle: Kanban · Tree · Map**
  - **Kanban**: columns Backlog → Claimed → Building (WIP cap) → Testing → Done; ticket cards show id, title, assigned agent (avatar), tags (bug / needs-key / e2e), confidence. "Run agents" advances the live sim; bugs in Testing loop back to Building.
  - **Tree**: process tree — orchestrator root → each pipeline node → its spawned sub-agent → the artifacts it produced (clickable).
  - **Map**: force-graph layout of the same pipeline with curved edges, the active path highlighted, satellites for sub-agents/deps.
- **Delivery footer**: when 100%, deploy unlocks → Repository + Open live app.
**Artifacts (`artifacts.jsx`, `artifactviewer.jsx`):** nodes produce real documents — research `.md` files,
**PRD.md** (product council), **architecture.svg** (architect), screen designs
(design step), the **GitHub repo** (provision). **Any artifact / `.md` file, at any stage, opens in the Artifact Viewer in a new browser tab** (§2.7) via `openArtifact(id)`.
The Concierge surfaces them as an "Artifacts produced" list with open-links.

### 2.7 Artifact Viewer  (`ArtifactViewer.html` → `ArtifactViewer`; `artifactviewer.jsx`)
**Purpose:** a standalone, full-page file viewer for everything the factory produces or operators author. Opened in a **new browser tab** from anywhere a file is clickable (project docs, console tree/map/concierge, OS Artifacts index, recipe editor) via `openArtifact(id)` → `ArtifactViewer.html?doc=<id>`.
**Layout:** left **file rail** (all artifacts, grouped by project, searchable) + topbar (breadcrumb project ▸ node, file name, type badge, confidence, updated, Copy / Download) + typed body.
**Supported types** (`ART` registry): **md** → real markdown renderer (`Markdown`) in a reading column with an **"On this page" TOC** (recipe descriptions register as `md`); **svg** → architecture diagram; **code** → line-numbered source (sql/bash/etc.); **json**; **csv** → table; **repo** → file tree; **fig** → frame grid; **image**. Selecting a file in the rail updates the URL so it's linkable.
**Markdown renderer** (`Markdown`, exported): headings, lists (ordered/unordered), tables, fenced code, blockquotes, rules, inline bold/italic/code/links. Reused by the recipe editor's live preview.

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
spend, last activity. **+ New organization**.

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

### 3.7 Provide access (invite)  (`InviteModal`)
Triggered from the top-bar **Provide access** button. Form:
- **Email** address.
- **Access type** dropdown: **New org** or **Tenexity**.
  - **New org** → also capture organization name; the invited user becomes the **admin of that new org**.
  - **Tenexity** → internal operator with full cross-tenant access.
- On send → email is **added to the sign-in allow-list** (status `invited` → `active` after first sign-in). Login (§2.1) only admits allow-listed emails.
**Allowed sign-ins** list shown in the modal: email, org, role, status.

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
- Concierge replies are scripted in the prototype; connect to the live model.
- `Factories`, `Settings` (OS) are placeholders.
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

**6 · Artifact Viewer + markdown viewer** (§2.7) — OS → **Artifacts** (index of every file) → click any card to open `ArtifactViewer.html` in a new tab. Also reachable from a project's **Produced documents** / **Documents** tab and the console tree/map/concierge. `.md`/SOW files render as formatted markdown with an "On this page" TOC; SVG/code/JSON/CSV/repo/image each get a typed view.

**7 · Operators open any project's dashboard** (§3.3) — OS → **Projects** (or the Overview "most active" list) → **click a project row** → its Overview / Documents / Factory-console tabs, with **← Projects** back.

**8 · Filter projects by user** (§2.2, §3.3) — OS → **Projects** → **All users** dropdown (each row shows its owning operator). Customer side: **Dashboard** artboard → **All team members** dropdown (owner avatar on each row).

**9 · Draft → start building** (§2.5a) — **Dashboard** → open the **Sales commission calculator** (Draft) project → Overview shows the "Finish setup to start building" banner + setup checklist → **Complete setup & start building** resumes intake → **Hand off to factory**.

**10 · Build engine selector** (§2.4) — **New project** intake (Option C artboard) → **Build engine** card: **Claude** vs **OpenCode** (→ Kimi K2.7 / GLM 5.2), each with **Use Tenexity's key** / **Bring your own key**. The choice shows in the factory-console header badge.

**11 · Save & finish later** (§2.4) — Option C footer → **Save & finish later** (stores a draft) alongside **Hand off to factory**.

**12 · Scope of work "+ Add"** (§2.4) — Option C → **Scope of work** card → **+ Add** chip to type a custom scope / software type.

**13 · Edit org fields in place** (§2.4) — Option C (returning mode) → on-file org card → **Manage** turns every cell into an inline input.

**14 · Concierge artifact display + working indicator** (§2.6) — open the **Factory console** artboard → left **Concierge** rail: switch artifact view **Feed · Tray · Latest**; type in the composer and **Send** to see the **typing/working** indicator; header shows a live **Working** chip while the build runs.

**15 · Crash / pause recovery** (§2.6) — Factory console → header **Pause** → the stage-rail flags the halt node and the **Recovery bar** appears: **Resume from `<node>`**, **Retry `<node>`**, or **Rewind to…** (also click any completed stage chip to rewind).

**16 · Exit onboarding / go back** (§2.4) — **New project** intake (Option C artboard or Dashboard → New project) → header **← Projects** leaves intake and returns to the Projects dashboard at any time, without handing off. The standalone onboarding artboard is wrapped in `OnboardingStandalone` so the back control has a real exit target there too.

**17 · Project budget cap** (§2.4, §2.5a, §2.6) — the project's **total spend ceiling** (absolute, not monthly). Set during intake via the **Project budget cap** field (`BudgetPicker`: $30 / $60 / $120 / $250 + custom). Update it later from the project **Overview → Build status** panel: the `$<cap> total` chip → pencil → inline editor. The value drives the factory-console header `spent … / $<cap> cap`.

**18 · Loading & fetch states** (§1.1) — open the **Loading & fetch states** section. The **Loading kit** artboard catalogs every skeleton / field / list / table / card type. The four **Live** artboards (projects dashboard, project overview, organization admin, users table) replay a real fetch — hit the **Reload** chip (top-right) to watch lists/tables/fields shimmer then resolve. All data-bound screens accept a `loading` prop and render their matching skeletons.

**19 · Archive / delete a project** (§2.5) — Projects dashboard → any project row's **⋯** menu → **Archive project** (confirm modal) moves it to the **Archived** section. From there the **⋯** menu offers **Restore project** and **Delete permanently** (confirm modal, destructive).

**21 · Concierge interview flow + persistent dock** (§2.4a, §2.4b) — **NEW, the big one.** The
intake CTA is now **Continue**, not "Hand off to factory." Flow: **Intake form → Processing
screen (`ProcessingScreen`, ingest progress bar + live log + ETA) → Concierge interview
(`InterviewView` + `InterviewRail`, an active Q&A you must finish) → Hand off to factory
(gated on the interview being complete) → build starts.** Large uploads can be sent to the
**background** (project home with a live "processing" banner + **Resume interview**). One
persistent `ProjectConcierge` dock (right side, `width 340`) now appears on all three Project
Console surfaces — overview / factory console / documents — driven by a `context` prop
(`overview` / `build` / `docs` / `ingesting`). Files: `concierge.jsx` (new), `optionC.jsx`
(state machine + `InterviewView`), `orgproject.jsx` (dock + background banner),
`buildprogress.jsx` (dock on console). Document Q&A with **citations is a later feature** —
groundwork only.

**23 · Interview answers are single/multi-select check lists** (§2.4a) — interview questions are
no longer answered with plain pill bubbles. Each `INTERVIEW_Q` entry declares a `select` mode
(`'single'` = radio rows, submit on click; `'multi'` = checkbox rows + **Confirm**). Rendered by
the new `ChoiceList` component (`concierge.jsx`) as full-width rows with check marks. The model
chooses the mode per question based on the information it needs. Pill `QuickReplies` is retained
only for *suggested prompts* on the persistent dock.

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
system-prompt editor (`admin.jsx`), the SOW title + body (`sow.jsx`), inline org-cell edits,
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

---

## 7. File map for this iteration (quick reference)

- **`concierge.jsx`** *(new)* — `useConciergeChat` hook, `ConciergeHeader`, `QuickReplies`,
  `ProcessingScreen`, `InterviewRail`, `ProjectConcierge`. Constants to edit: `INGEST_STEPS`
  (processing log), `INTERVIEW_Q` (questions). Loaded in `Software Factory Onboarding.html`
  right after `artifacts.jsx`.
- **`optionC.jsx`** — `OptionC` state machine (`view`: intake/processing/interview/build +
  `interviewDone` gate), `InterviewView` (+ `LEARNED` constant), `OnboardingStandalone`
  (artboard wrapper that wires backgrounding to the project home).
- **`orgproject.jsx`** — `ProjectDashboard` now takes `ingesting` + `onResumeInterview` props,
  renders the background banner and the right-hand `ProjectConcierge`; `ProjectViewStandalone`
  forwards those props.
- **`buildprogress.jsx`** — `BuildProgress` renders `ProjectConcierge context="build"` on the
  right (replaced the left `ConciergeRail`).
- **`shared.jsx`** — `GoalMarkdown` + `looksLikeMarkdown` (exported on `window`).

**Tokens used by the new screens** (all from the `T` object in `shared.jsx`): `T.brand`
`#1A7BFF`, `T.brandSoft` `#E8F1FF`, `T.brandDeep` `#0958C9`, `T.success` `#059669`,
`T.successSoft` `#E4F8EF`, `T.bg` `#FAFAFA`, `T.raised` `#FFF`, `T.sunken` `#F4F4F5`,
`T.ink` `#060709` (the dark ingest-log panel), `T.borderSubtle` `#E7E7E9`, `T.fg`/`T.secondary`/`T.tertiary`
text ramp, radii `T.rMd`/`T.rLg`/`T.rXl`, `T.shadowXs`, fonts `T.sans` (Hanken Grotesk) /
`T.display` (Georgia) / `T.mono` (JetBrains Mono). Animations: `sfRise` (log/message entrance),
`sfPulse` (live status dot), `.sf-spin` / `sfSpin` (processing spinner) — all defined in the
`<style>` block of `Software Factory Onboarding.html`.
