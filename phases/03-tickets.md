# Phase 3 — Tickets  (Proposal §3 Phase 3)

**Do:** derive **tickets/tasks** from features × architecture, in dependency (**wave**) order, each
with explicit **acceptance criteria** + **definition of done**. (Q2 resolved: the store is the
local **SQLite** `tickets.TicketStore` — `create_ticket(title, acceptance, dod, wave)`.) A PM-lead
angle divides the implementation into the steps/waves. `events.emit` a node per ticket.

**Gate:** every ticket has acceptance criteria; waves ordered; no orphan features.

Code: `tickets.py` (`TicketStore.create_ticket`), `events.py`.
