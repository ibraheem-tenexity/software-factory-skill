# CBT design-partner sprint — tickets & division of work

> Product breakdown of Nick's 2026-07-20 email (CBT Company intro on the 27th).
> Source design rationale: the journey mapping in this repo's design archive
> (see `PRD.md`). File into Linear (team SOF, project "Software Factory") and
> link each ticket to the CBT-* id here. Classification `existing`/`new` is
> grounded in a 2026-07-20 recon of `src/software_factory` + `console/web/src`
> on `staging` — quoted code is real, not assumed.

## What the recon found (grounds every ticket below)

- **Company enrichment ALREADY EXISTS backend-side, unwired.** `research.py`:
  *"Company research — enrich a company profile via Exa (quick) or OpenRouter
  Fusion (deep)"* with `CompanyProfile` + `_exa_search`. No console route, no
  `api.ts` entry, no UI. Nick's "plug the Fusion + Exa research into the UI" is
  literal — the wow feature is mostly a wiring job.
- **Engine picker exists** (`OnboardingScreen.tsx`): `provider=claude|opencode`,
  `model=kimi|glm`, BYOK persists via `/creds`, runtime write-through at promote.
  **Codex: zero occurrences anywhere** — fully new.
- **Recipes exist** (SOF-108: DB-seeded "genre" recipes authored on the SOW
  screen) but are text blueprints — **not repo-backed**. Design archive has the
  repo+images model already spec'd.
- **`MaintenanceTab.tsx` is a "coming soon" placeholder** listing the right
  capabilities (log watching, feedback ingestion, patches).
- **`eval_judge.py` exists** (research evaluation) — the pattern to reuse for
  the context-quality judge; a context-scoring judge itself is new.
- **No customer-repo discovery** (crawl their codebase → AGENTS.md/CLAUDE.md)
  exists — new. `agents.md` generation appears only inside `research.py`.
- Interview/concierge intake exists (`input_pipeline.py`, `concierge_tools.py`,
  `chat_agent.py`).

## Division of work — four lanes

| Lane | Owns | Surface |
|---|---|---|
| **DSN** — design (this session) | Design-archive screens, PRD spec, this ticket doc | `design/` |
| **WEB** — console frontend | Customer-facing implementation of approved designs | `console/web/src` |
| **PIPE** — pipeline/backend | Agents, tools, endpoints, engine adapters, discovery | `src/software_factory` |
| **OPS** — infra/ops | GitHub org, domain, Railway, email | infra |

Dependency rule: DSN specs first (fast), PIPE endpoints before WEB wiring where
the UI calls live data. No time estimates — order by wave; report done/not-done
against acceptance criteria (AC).

**Wave 1 — demo-critical for the 27th:** CBT-1–4 (wow prefill), CBT-6/7
(discovery), CBT-9/10 (repo-backed recipes), CBT-13/14 (engines).
**Wave 2 — partner onboarding depth:** CBT-5/8 (conventions), CBT-11/12
(suggestion + Explore), CBT-15–18 (design-gen + theme), CBT-19/20 (judge).
**Wave 3 — after the demo:** CBT-21–25 (UI polish batch), CBT-26/27
(maintenance & feedback), CBT-28–30 (infra tail + 8090 depth).

Nick's standing priority: **pipeline before UI polish** — Waves 1–2 pipeline
tickets outrank all of Wave 3.

---

## A. Wow prefill — "We already know you"

**CBT-1 · PIPE · existing-machinery/new-route — Company-enrich endpoint**
Expose `research.py`'s enrich as `POST /api/research/company` (body: `{name? |
website? | email_domain?}`, query `depth=quick|deep`; quick = Exa, deep =
Fusion). Returns the `CompanyProfile` fields + per-field confidence + source
URLs. Honest errors: missing `EXA_API_KEY`/Fusion config returns the real
reason, never a guess.
AC: curl against staging returns profile JSON for a real company (e.g.
`cbtcompany.com`); `depth=quick` bounded; failure modes return actionable error
text; no DB writes (read-only enrichment).

**CBT-2 · DSN · this session — Prefill UX spec + screens**
First-time intake leads with "Company website" (prefilled from signup email
domain when not a public provider) → lookup mini-log → ai-tint "We found your
company" confirm card (ConfidencePill per field + source label; accept-all or
edit inline; nothing writes silently). Org-admin "Enrich from web" entry.
AC: artboards in the canvas; PRD §2.4 updated. *(done in this PR)*

**CBT-3 · WEB · new — Wire prefill into onboarding + org admin**
Implement CBT-2 against CBT-1 in `OnboardingScreen.tsx` (fresh mode) and the
org profile screen. Skeleton loading during lookup (per design-system rule),
confidence pills on unconfirmed values, edit-before-accept.
AC: browser-verified live: type a domain → found-card → accept → org profile
persisted; wrong guess → "not right" path leaves fields editable; slow path
shows skeleton, not a frozen form.

**CBT-4 · PIPE · new — Concierge `enrich_company` tool**
Concierge tool wrapping CBT-1 so it can offer lookup conversationally ("want me
to look you up?") and speak the results with sources.
AC: in a live concierge session the tool returns profile + sources; concierge
states uncertainty on low-confidence fields instead of asserting.

## B. Discovery + technical-user setup (the CBT on-ramp)

**CBT-5 · DSN · this session — Org sections spec**
Org-admin sections: "Codebase discovery" (connect repo → crawl log → generated
docs into knowledge base) and "Development conventions" (repo, framework,
integrations, coding standards → org AGENTS.md). *(done in this PR)*

**CBT-6 · PIPE · new — Repo discovery pipeline**
Input: repo URL + PAT (stored in org vault, write-only). Shallow clone, run
discovery agent(s) over the tree (framework, package manifests, CI,
integrations, conventions) → emit `AGENTS.md`, `CLAUDE.md`, `integrations.md`
as org knowledge-base artifacts with confidence markers. Budget-capped,
checkpointed like other pipelines.
AC: run against a real test repo (budget_ceiling=10, via `create_draft` flow —
never a seeded row): three markdown artifacts land on the org; re-run reuses
checkpoints; failure (bad PAT/private repo) surfaces the actual git error.

**CBT-7 · WEB · new — Codebase discovery UI**
Org section per CBT-5: repo connect form, live crawl log (ProcessingScreen
pattern), generated-docs list with confidence pills; "re-run" action.
AC: browser-verified against CBT-6 on staging; log lines stream; generated
AGENTS.md opens in the artifact viewer.

**CBT-8 · PIPE+WEB · new — Development conventions**
Org-level fields (primary repo, framework, package manager, coding standards
doc upload, integration notes) compiled into the org's AGENTS.md and injected
into every build's agent context (build to *their* conventions).
AC: conventions saved at org level appear verbatim in the build agents' context
on the next run (verify via a real stage log); edit → next run picks it up.

## C. Recipes (the big one)

**CBT-9 · PIPE+WEB · existing-upgrade — Repo-backed recipe loader**
Admin loads a recipe = GitHub repo link + description (not just a prompt).
On save: clone/index the repo, **require** `AGENTS.md` or `CLAUDE.md` (refuse
with the honest reason if absent), register repo contents as build-seed assets.
Upgrades today's DB-seeded genre recipes to the design-archive model (repos +
images + markdown, internal-only).
AC: admin adds a repo URL → recipe persists with repo tree indexed; repo
without AGENTS.md is refused with that exact reason; picker still shows only
customer-facing fields.

**CBT-10 · PIPE/OPS · new — Author the five recipe repos**
In the Tenexity Factory org (CBT-28): **vendor scorecard, rebate tracker,
order entry, quote follow-up** + keep quote-ERP. Each: working boilerplate app,
`AGENTS.md` (architecture, conventions, extension points), README.
AC: five repos exist, each clones + runs; each AGENTS.md passes CBT-9
validation; each registered recipe shows in the OS library as Published.

**CBT-11 · PIPE+WEB · new — Concierge recipe suggestion**
When a project's goal text matches a Published recipe and none is picked, the
concierge offers it inline ("This sounds like Quote-to-ERP — 12 builds. Use
it?"). Tool-side matcher (cheap model or embedding over recipe taglines) +
suggestion card UX; accept → recipe applied; dismiss → remembered, not nagged.
AC: live intake: goal about vendor scorecards → suggestion appears → accept
preselects the recipe; dismiss persists for the session.

**CBT-12 · DSN+WEB · new — Explore / Inspiration gallery**
Top-level customer destination separate from New project: Published recipes as
rich cards (preview image, tagline, capabilities, builds, industry tags);
"Start from this →" enters intake with the recipe preselected. Image artifacts
gain a `public` flag (today they're internal-only). DSN specs, WEB builds.
AC: gallery reachable from the dashboard without starting a project; CTA lands
in intake with that recipe selected; non-public images never render.

## D. Multiple coding agents

**CBT-13 · PIPE · new — Codex adapter + Kimi K3**
Add `provider=codex` (Codex 5.6) to the engine layer (`swarm_adapter.py`,
`constants.py`, model mapping) alongside claude + opencode; update Kimi id to
K3. Keep it model-flexible: provider selected per project, BYOK honored.
AC: a draft promoted with `runtime=codex` runs a real stage end-to-end on
staging with Codex doing the coding; spend meters against the project cap;
honest error if the key is invalid.

**CBT-14 · WEB · existing-delta — Engine trio UI**
EnginePicker → Claude Code (default) / Codex 5.6 / Kimi K3 cards, same BYOK
segment; console header badge reflects the choice (already does).
AC: browser-verified selection persists (write-through), badge matches, and
switching providers doesn't drop BYOK state (existing behavior preserved).

## E. Design generation + theme

**CBT-15 · DSN · this session — Stage-gate + theme spec**
Design-node review gate (mockups as `fig` frames, approve / iterate-via-
concierge) and Org "Brand & theme" section ("process theme from my website").
*(done in this PR)*

**CBT-16 · PIPE · existing-upgrade — Kimi K3 mockup generation**
Design node generates high-fidelity interface mockups from the PRD + theme
pack; artifacts registered as `fig` frames; pipeline pauses at a design-review
gate; concierge iterate-requests re-generate affected screens only.
AC: a run reaches the design gate with ≥3 screen mockups openable in the
artifact viewer; "iterate" via concierge produces a new version of one screen
without redoing the set; approve resumes the pipeline.

**CBT-17 · PIPE · new — Design-theme agent**
Crawl the org's website → extract palette, type, logo → store a token pack on
the org (overrides on the `T` system); injected into design-gen (CBT-16) and
the app scaffold so every app ships on-brand. Manual upload fallback (brand
guidelines PDF in the knowledge base).
AC: "process theme from my website" on a real domain produces a token pack with
sources; a generated mockup visibly uses it; failure (unreachable site) says so.

**CBT-18 · WEB · new — Gate + theme UI**
Design-review bar in the factory console (stage-triggered, like wait-for-deps)
and the Brand & theme org section per CBT-15.
AC: browser-verified: gate appears only at the design node; approve/iterate
both work live; theme section shows pack + preview after processing.

## F. Context judge

**CBT-19 · PIPE · new — Context-score judge**
Sonnet/Haiku judge scores org+project context (0–100) and returns the single
highest-value missing item ("price book → +12"). Reuse `eval_judge.py`
patterns; prompt-level judgment, no state machine (repo philosophy §1).
AC: for a real draft, the tool returns score + next-best-action; adding the
suggested item on the next call raises the score; cheap model, metered.

**CBT-20 · WEB · new — Score + nudge UI**
Intake concierge rail and the draft setup-checklist show the score and the
nudge; soft nudge only, never a hard gate.
AC: browser-verified score updates as materials are added; nudge text matches
the judge's output; hand-off is never blocked by score.

## G. UI polish batch (Nick's demo list — Wave 3)

**CBT-21 · WEB** — Services/Agents strip atop project: connected GitHub repo,
Railway env, live status + links. AC: real links, real status, honest
"not connected" states.
**CBT-22 · WEB** — Dropzone: fix the drop itself; remove a file after upload.
AC: drag-drop works on Chrome+Safari; remove deletes server-side too.
**CBT-23 · WEB** — Kanban columns scroll independently. AC: long columns scroll
without moving the board header.
**CBT-24 · WEB** — Node-map nodes clickable → detail drill-in. AC: click opens
the node's detail (artifacts, logs) without leaving the map.
**CBT-25 · WEB** — PRD opens in the artifact viewer, not duplicated as GitHub
markdown. AC: one canonical render path; no duplicate pane.

## H. Maintenance & feedback loop (Wave 3)

**CBT-26 · PIPE · new — Feedback inbox**
Feedback mailbox → agent reads, asks clarifying questions by reply, files a
triaged backlog it can execute against. AC: an email to the box gets a
clarifying reply and produces a backlog item with the original thread linked.
**CBT-27 · PIPE+WEB · new — Maintenance agent + slider**
Replaces the placeholder `MaintenanceTab`: aggressiveness none/light/heavy/
proactive (cost tradeoff shown), log watching, patches, weekly/monthly
regression runs folding in the QA agent. AC: slider persists and changes the
agent's schedule; a regression run on a deployed test app reports pass/fail
honestly.

## I. Infra / housekeeping

**CBT-28 · OPS** — Move project repos + default recipes to the Tenexity Factory
org; entities connect their own org later. AC: new projects provision under the
org; existing personal-account repos still linked (no broken deploys).
**CBT-29 · OPS** — Verify the domain so app email works. AC: verification
record live; test email delivered to a real inbox (not spam).
**CBT-30 · PIPE+DSN · new — 8090 structural borrow**
Interview skeleton business-problem → current-state → personas → metrics;
wiki-style artifact folders (Research / PRD / Architecture / Screens /
Tickets); industry preload packs via recipes. AC: interview questions follow
the skeleton; artifact rail groups by folder; selecting an industry recipe
preloads its pack.

**CBT-31 · WEB · existing-replacement — Invite-led organization onboarding**
The live OS "New organization" dialog is a manual CRUD form asking operators
to type **computed** values (total spend, active projects, in-flight tickets,
last activity) — replace it with the invite-led chain (PRD §3.7): "New
organization" and "Provide access" open one invite modal (email + access
type; operator may **pre-seed identity/context fields** — name + website
prefilled from the email domain, industry optional, all editable); send →
allow-list `invited`; invite email (CBT-29) → sign-in with the user's
preferred method (Google / Microsoft / email / SSO) → first sign-in
**always** routes to fresh-mode onboarding (blank or pre-seeded alike) →
web prefill (CBT-3) fills the remainder with the user → confirm → first
project. Organization table columns are system-derived, never editable.
AC: no telemetry entry form exists anywhere; inviting a real email produces
an `invited` allow-list row; operator-provided name/website/industry appear
on file in the invited user's onboarding; first sign-in lands in fresh
onboarding (not the dashboard) whether pre-seeded or not; preferred-method
sign-in works for all four methods; nothing is asked of the user twice.
Depends: CBT-29 (verified domain), CBT-1/3 (prefill wiring).

---

## Session output (this PR)

- This ticket doc (`design/TICKETS.md`).
- DSN tickets CBT-2, CBT-5, CBT-12 (design), CBT-14 (design), CBT-15 —
  screens + PRD spec in the design archive.

Filing note: no Linear tooling in this session — create SOF tickets from this
doc (each CBT-* = one ticket, lane = assignee pool, wave = priority) and set
the mapping in the ticket description.
