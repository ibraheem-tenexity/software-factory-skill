# Guardrails  (Proposal §6 — cost & safety, mandatory)

- **Run-level budget ceiling = $100, HARD CUTOFF** (Q7). The orchestrator tallies real spend each
  `/loop` tick and **stops the run** the moment spend hits $100 — cutoff, not escalate-and-wait —
  then reports completed vs pending. → `budget.Budget.charge(Usage(...))` raises `BudgetExceeded`.
- **Accurate accounting:** read real model token usage (input/cached/output/reasoning) per call —
  never char-count estimates. → `budget.Usage`, `streamlog.cost_usd` (from the live claude stream).
- **Loop bounds:** per-ticket/per-phase attempt caps with backoff; a *blocked-but-not-failed* phase
  is bounded too (last run's gap).
- **No-op = no-op:** an empty agent turn is a retry/escalate signal, not success. → enforced by
  `repo.merge_if_green` (refuses empty diff) and `tickets.mark_done` (refuses hollow close).
- **Fully autonomous (Q8):** no human approval gates. The run goes to *done* (happy flow),
  *budget cutoff* ($100), or a *hard block*. A hard block (missing inputs/authority) **halts that
  ticket** (recorded, never merged-as-done); the run continues with the rest and reports blocks at
  the end.
- **Reversibility check:** before destructive/outward actions (infra teardown, prod deploy of a
  destructive migration), gate mechanically — but never wait on a human.

Code: `budget.py`, `streamlog.py`, `repo.py`, `tickets.py`, `gate.py`, `workspace.py` (safety-gated destroy).
