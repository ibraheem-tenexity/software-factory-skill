# Phase 0 — Provision / bootstrap  (Proposal §3 Phase 0)

**In:** the customer's context (uploaded — text/pdf/docx) + a GitHub repo (created fresh, or a
URL + creds: PAT+username+email, or OAuth).

**Do:**
- **Extract** the uploaded context to usable text (install packages if needed for pdf/docx), Or if the user input text then use that as input.
- Create/connect the repo via `gh` — `repo.GitHub.create_repo(name)`.
- Verify every surface has its creds first — `creds.check_all(target, env)`; any failure is a
  **hard block** (recorded, never guessed/hard-coded).
- Instantiate run state + budget — `runstate.RunState.load(run_id)`, `budget.Budget(100)`.
- Stand up **ruflo** (swarm runtime + memory) as MCP; **seed ruflo** with the extracted context
  (`memory.MemoryStore.write(memory.run_ns(run_id), "context", …)`).
- `workspace.create(runs_dir, run_id)` — isolated, disposable build dir; proof lives at the base.
- `events.emit(... "phase", {"name":"provision"})` and an `artifact` for the input.

**Out:** repo handle, run state, budget, workspace, ruflo seeded with context.

**Gate:** repo reachable + writable; brain + swarm MCP reachable; budget set; workspace created.

Code: `creds.py`, `repo.py`, `runstate.py`, `budget.py`, `workspace.py`, `memory.py`, `events.py`.
