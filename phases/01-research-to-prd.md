# Phase 1 — Research → PRD  (Pipeline 1; Proposal §3 Phase 1 + the previous version's named agents)

Spawn the named PRD agents **in order** (`emit agent_spawned`/`agent_done` each); they carry the
previous pipeline's contracts. Pull/write findings via ruflo (`memory`).

1. **HORIZON (pm.lead) — context assembly.** Normalize the extracted transcript → tight, ordered scope
   (customer, JTBD, success); cut non-load-bearing detail; list open questions. → `context_packet`.
2. **ARCHIVIST (scout.librarian) — reuse scan.** `memory.recall_precedent` over prior runs → fork /
   extend / standalone + reuse candidates. Don't rebuild what exists.
3. **VANGUARD (domain.expert) — pain, ≥2 solution paths, AND deep research.** Industry **gravity** +
   pushback; evaluate ≥2 solution paths w/ tradeoffs → recommend the MVP proof. **Web search REQUIRED:**
   `WebSearch` 4–6 queries → `WebFetch` 4–8 → **≥3 real products (name + URL + features + gaps)**; fewer
   ⇒ keep searching. → solution options, recommended MVP, research brief + source map.
4. **CHROMA (design.lead / pm-UI/UX) — design spec.** Journeys, screens, states, a11y; the primary
   **happy-flow click-path** Playwright will verify.
5. **HORIZON (pm.lead) — write the PRD** (`PRD.md`): product thesis; users/JTBD; journeys; competitor
   landscape (every product w/ URL); MVP scope; features; NFRs; **acceptance criteria
   (given/when/then/verification)**; out-of-scope; **ticket seeds**. Commit; `emit artifact {kind:"prd"}`.

**Done-gate (mechanical, autonomous):** `artifacts.prd_is_complete(PRD.md)` — ≥3 real URLs + acceptance
criteria + ticket seeds. Hollow/absent PRD does not advance (canvas shows it red). No human gate.

Code: `WebSearch`/`WebFetch`, `memory.py`, `events.py`, `artifacts.prd_is_complete`.
