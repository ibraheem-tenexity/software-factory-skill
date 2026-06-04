# Phase 2 — Co-design: architecture + features/screens  (Proposal §3 Phase 2)

**Do:** the orchestrator spawns **two agents that converse** (over **`claude-peers`** — the live
bus, §5) to co-produce, from the PRD: (a) a **simple** architecture under fixed constraints —
**Railway** (backend), **Supabase** (auth + DB), **Vercel** (frontend) — and (b) the **feature +
screen list**. Dependencies between features are disclosed. The architecture is **exported as a
diagram** (Mermaid → image via `diagram.render(mermaid, "architecture.svg")`).

- The two co-design agents negotiate live via `claude-peers` ("two agents communicating exactly").
- Write the `architecture` page + diagram, `features`/`screens` list, and `dependencies` list to
  the brain (`memory.write(memory.run_ns(run_id), …)`) and commit them to the repo; `events.emit`
  an `artifact` for each.

**Out:** `architecture` page + `architecture.svg`, `features`/`screens` list, `dependencies` list
— all in the brain (pullable) and committed.

**Gate:** diagram renders; feature list maps to PRD scope; dependency list recorded.

Code: `diagram.py`, `memory.py`, `events.py`, `claude-peers` MCP.  → then **02b-provision-infra**.
