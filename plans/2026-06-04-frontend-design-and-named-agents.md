# Plan: frontend-design restyle (graph_viz port) + named PRD/architecture agents + two-pipeline boundary

## Context
Two requests, both grounded in existing work the user pointed to:
1. **Restyle the console** following the `frontend-design` skill
   (`/home/ibraheem/softwarefactory/.agents/skills/frontend-design/SKILL.md` — distinctive, non-AI-slop,
   bold-but-intentional; **forbids Inter**) and **port graph_viz's visual language**
   (`~/graph_viz/src/styles.css`: refined-professional Stripe/Linear/Notion — navy `#002b5c` / gold
   `#b18e04`, `#f8f9fb` bg, dotted-radial canvas, kind-badges, markdown-rendered artifacts, JetBrains Mono).
   The render core (fcose+cola+diff) was already ported; this is the **visual layer**.
2. **Restructure the product-definition pipeline around named agents** from the previous version —
   HORIZON (pm.lead), VANGUARD (domain.expert), ARCHIVIST (scout.librarian), CHROMA (design.lead) — and
   **add a new software-architect agent**. The user's SKILL.md now has TWO pipelines; **pipeline 1 ends at
   `architect`** and the orchestrator must not consider part 1 done before a validated PRD + architecture.

Confirmed: **elevated graph_viz LIGHT** aesthetic; **pipeline 1 ends at architect** (wait-for-deps bridges
to pipeline 2). Stays fully autonomous (decision #4) — the old HORIZON "approval gate" becomes a
**mechanical** PRD/architecture completeness gate, never a human pause.

---

## Part A — Console restyle (`console/index.html`)  (frontend-design + graph_viz port)

Keep the cytoscape render core; replace the visual layer. Aesthetic = **elevated graph_viz light**:
- **Token system** (CSS vars, from graph_viz): `--primary:#002b5c`, `--accent-gold:#b18e04`, `--bg:#f8f9fb`,
  `--card:#fff`, `--fg:#0f1729`, `--muted/-fg`, `--border`, radii, shadows.
- **Typography (frontend-design — NOT Inter):** a distinctive **display** face for brand/headings (e.g.
  *Fraunces* or *Instrument Serif*) + a **refined body** sans (e.g. *Public Sans*) + **JetBrains Mono** for
  data/run-ids/code (graph_viz already uses it). Load via Google Fonts `<link>`.
- **Atmosphere/depth:** dotted-radial canvas backdrop (graph_viz), a subtle grain/blueprint overlay, soft
  shadows, gold brand dot. **Motion:** one orchestrated page-load with staggered reveals (`animation-delay`)
  on toolbar → canvas → panel; hover transitions on chips/buttons.
- **Chrome:** sticky toolbar (brand + run picker + phase + live cost), left build form, dotted canvas center,
  right inspect **sidebar** as a `detail-panel` with **kind-badge**, **agent/status chips**, and
  **markdown-rendered artifacts** (add `marked` via CDN to render PRD/architecture.md; SVG inline as today).
- **Cytoscape stylesheet → graph_viz palette:** per-type muted tokens (orchestrator/phase/agent/artifact/
  blocker/gate mapped onto navy/green/amber/purple/teal/red), `text-outline` for legibility, active-run
  green border, `.faded`/`.highlighted` classes; keep `missing` artifact = red (artifact-truth).
- Keep persistence (run picker + localStorage), live cost, the diff/applyGraphUpdate position stability.

### Live activity feed (you asked — visibility while waiting)
A persistent **activity pane** (bottom strip or a docked column) that makes the wait legible — you see the
agent *working live*, not a frozen canvas:
- Polls `/api/runs/<id>/log` (the captured claude stream) + `/api/runs/<id>/events` every ~1.5–2s and renders
  the **latest actions in human-readable form**, auto-scrolling: `🔧 WebSearch "guestbook competitors"`,
  `🔧 Bash python-docx …`, `💬 <assistant text>`, and event lines (`▸ phase: research`, `✦ artifact: PRD`,
  `⛔ blocker: …`). A small **"● live"** pulse + the current tool/phase so it's obvious work is happening.
- Reuses the existing `/log` + `/events` endpoints (no backend change) plus the **already-committed
  Railway-logs tee** (agent stream → container stdout) so the same activity is also in `railway logs`.
- Parser mirrors the readable transform I already use when tailing run.log (assistant text + tool_use names).

Frontend → verified by serving + visual check on deploy (no unit test for HTML/CSS).

---

## Part B — Named agents in research + architect; pipeline-1 boundary  (SKILL.md + phases/)

Rewrite the **research** and **architect** phases (in `SKILL.md` and `phases/01-research-to-prd.md`,
`phases/02-codesign-architecture.md`) around the named agent roster, restoring the two gaps the user
flagged (domain-expert "gravity"; reuse scout) and adding the architect:

| Agent (codename) | Role in our skill | Output contract |
|---|---|---|
| **HORIZON** (pm.lead) | Context assembly: from `extract`, normalize transcript → tight ordered scope; define the problem (customer, JTBD, success). Later: write the PRD. | context_packet, open questions; then the PRD |
| **VANGUARD** (domain.expert) | **Restored as its own role.** Industry "gravity" + pushback; evaluate **≥2 solution paths** + tradeoffs → recommend the MVP proof. **Also deep web research** — `WebSearch`/`WebFetch`, **≥3 real products w/ URLs** (the existing hard bar). | pain, solution options+tradeoffs, recommended MVP, research brief + source map |
| **ARCHIVIST** (scout.librarian) | **New role.** Scan prior runs / **ruflo precedent** (`memory.recall_precedent`) → fork / extend / standalone reuse candidates. | reuse candidates |
| **CHROMA** (design.lead = pm-UI/UX) | Design spec: journeys, screens, states, a11y — the happy-flow click-path Playwright will verify. | design spec |
| **software-architect** (NEW) | From PRD + design spec: fewest-services architecture (Railway/Supabase/Vercel), data model, dependency list, required-token list; build Mermaid → `diagram.render` → `architecture.svg`. | `architecture.md` + `architecture.svg` |

- **HORIZON PRD contract (rigor restored):** product thesis, users/JTBD, journeys, MVP scope, features, NFRs,
  **acceptance criteria (given/when/then/verification)**, out-of-scope, **ticket seeds**, competitor landscape
  (≥3 real products w/ URLs). This is what makes the PRD actually drive pipeline 2.
- **Two-pipeline structure (SKILL.md):** Pipeline 1 = extract→provision→research→**architect** (product
  definition). **Pipeline-1 done-gate (mechanical, autonomous):** `PRD.md` exists + cites ≥3 real products +
  has acceptance criteria + ticket seeds, AND `architecture.md` + `architecture.svg` exist non-empty. The
  orchestrator **must not** start pipeline 2 (wait-for-deps→tickets→build→deploy→test) until that passes.
- Reconcile decision #4: keep "fully autonomous, no **human** gates"; clarify the PRD/architecture gate is a
  **mechanical** completeness check (the old approval gate's teeth, no human).

### `make_prompt` runbook (`console.py`)
Update the research/architect steps to **name + spawn these agents in order** (HORIZON→VANGUARD→ARCHIVIST→
CHROMA→HORIZON-PRD; then software-architect), emit an `agent_spawned/agent_done` per role, and **block
pipeline 2 behind the mechanical pipeline-1 gate**.

---

## Part C — Deterministic pipeline-1 gate  (new `artifacts.py` or extend, TDD)
A small tested helper the orchestrator (and console) call so part 1 can't be faked:
- `artifacts.verify(run_dir, paths) -> (ok, missing)` — each path exists + non-empty.
- `artifacts.prd_is_complete(text) -> (ok, reasons)` — PRD cites ≥3 URLs, has an "acceptance"/"given/when/then"
  section and a "ticket" seeds section. Pure text checks, TDD.
- Reuse the artifact-existence check already added to `console.graph` (missing=red) — same source of truth.
- Add the new module to `tests/unit/test_boundary.py` CORE.

---

## Verification
- `make test` green incl. new `tests/unit/test_artifacts.py` (verify + prd_is_complete) and boundary update.
- Console: serve locally + on deploy; visual check — distinctive fonts (no Inter), graph_viz palette/dotted
  canvas, staggered load, markdown artifacts in the inspector, missing artifacts red.
- Skill: read SKILL.md + the two phase files — the five named agents + software-architect with contracts;
  pipeline-1 mechanical gate present; `make_prompt` names/spawns them; decision #4 reconciled.
- (Live proof of the agents actually doing the work needs a real run on the deployed runner — separate, costs budget.)

## Notes / honest boundaries
- The Part 1 "integrate with Postgres/MCP/cockpit/Linear/Symphony" material is **context about the OLD system**;
  our clean-room version maps the named agents onto the existing ruflo/console/phases — not a Symphony reintegration.
- `marked` (CDN) is the one new front-end dep for markdown rendering in the inspector.
- Font choice is a creative call finalized in implementation (distinctive display + refined body + JetBrains Mono),
  per frontend-design's "don't converge / avoid Inter & Space Grotesk".
