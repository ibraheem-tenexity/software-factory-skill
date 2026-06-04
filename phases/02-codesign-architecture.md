# Phase 2 — Architecture  (END OF PIPELINE 1; Proposal §3 Phase 2 + the new software-architect agent)

- **software-architect (NEW agent)** — from the PRD + CHROMA's design spec, design the **demo-simplest**
  architecture: YAGNI hard, **fewest services possible**. Fixed constraints: **Railway** compute,
  **Supabase** storage + auth, **Vercel** frontend if needed. Produce the service list, **data model**,
  **dependency list** between features, and the **required-token list** (provider/service tokens the app
  needs at runtime, so `wait-for-deps` can require them). CHROMA may consult on screen↔component mapping.
- Write `architecture.md`; build the Mermaid; `diagram.render(mermaid, ".../architecture.svg")` (mmdc →
  SVG). Commit both; `emit artifact` for each so they render on the canvas.

**Done-gate = PIPELINE-1 COMPLETE (mechanical).** `artifacts.verify(run_dir, ["…/PRD.md",
"…/architecture.md", "…/architecture.svg"])` must pass (all exist, non-empty) AND the PRD gate held.
**The orchestrator must NOT begin pipeline 2 (wait-for-deps → tickets → build → deploy → test) until this
passes** — product definition is finished first. This is the first part of the pipeline; nothing
downstream is considered done before it.

Code: `diagram.py`, `memory.py`, `events.py`, `artifacts.verify`.
