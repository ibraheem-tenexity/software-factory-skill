# Phase 4 — Build swarm  (Proposal §3 Phase 4)

**Do:** **ruflo spawns Claude build agents** per ticket; they **pull** context from the brain (not
injected), **communicate** via the swarm channel + shared brain namespace (`coordination`), and
via `claude-peers` for live "I'm blocked / here's feedback" pings; implement; open PRs.

**Assembly:** serialize per **wave**; **merge-on-green** so `main` accumulates and later tickets
build on merged work. **No-op turns retry/escalate, never auto-complete.**

- `tickets.claim` → `agents.AgentRegistry.spawn` → dispatch (pull from `memory`, write status to
  `memory.COORDINATION` as `swarm/<agent>/{status,progress,complete}`) → `agents.record(outcome)`.
- Merge only via `repo.GitHub.merge_if_green(pr, diff_lines)` (refuses red/empty); then
  `tickets.mark_done(pr, diff_lines)` (refuses a hollow close).
- **ReasoningBank:** write each agent's trajectory→verdict back —
  `memory.record_precedent(store, memory.project_ns(pid), trajectory, verdict, confidence)`; later
  agents `memory.recall_precedent(...)` for "how was this handled". `memory.consolidate(...)` between waves.

**Gate:** ticket DoD met + a real diff + PR merged; budget within ceiling.

Code: `tickets.py`, `repo.py`, `agents.py`, `memory.py` (precedent), `events.py`, `claude-peers`.
