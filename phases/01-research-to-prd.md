# Phase 1 — Deep research → PRD  (Proposal §3 Phase 1)

**Do:** the **research agent** runs deep research on the proposed app **and similar products on
the web** (Claude `WebSearch`/`WebFetch` — the unify-on-Claude resolution of Q4), writes findings
into the brain, then synthesizes a **PRD** (problem, users, value, MVP scope, feature candidates,
competitor landscape, risks/unknowns).

- **Web search is REQUIRED.** Run `WebSearch` on 4–6 queries about the solution + competitors;
  `WebFetch` the top 4–8 and read them. Surface **≥3 real existing products** (name + URL + what
  they do + gaps). Fewer than 3 ⇒ search more. A PRD with no researched products is a FAILED phase.
- A **PM-lead** angle defines the feature set; a **PM-UI/UX** angle defines screens + the primary
  user journey (the happy-flow the Playwright gate will verify).
- Write findings + the PRD to the brain (`memory.write(memory.run_ns(run_id), "prd", …)`) **and**
  commit `PRD.md` to the repo; `events.emit(... "artifact", {"title":"PRD","kind":"prd", …})`.

**Out:** `PRD` page in the brain (pullable) + `PRD.md` in the repo.

**Gate:** PRD covers problem + users + MVP scope + a feature list, cites **≥3 real products with
URLs**, and is coherent (a judge/self-check pass).

Code: `WebSearch`/`WebFetch` (built-in), `memory.py`, `events.py`.
