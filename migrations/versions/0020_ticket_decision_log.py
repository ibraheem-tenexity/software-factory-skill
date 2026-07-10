"""Ticket decision_log field (SOF-118): per-ticket assumptions/shortcuts/known-gaps

Revision ID: 0020_ticket_decision_log
Revises: 0019_seed_tickets_agent
Create Date: 2026-07-10

Adds `decision_log` to `tickets` — a JSON-encoded array of `{type, statement, reason,
affected_surface}` entries (type is one of `assumption` | `shortcut` | `known-gap`), the build
agent's own disclosure of what it assumed/shortcut/left-undone while implementing THIS ticket.

Same NULL-vs-'[]' convention as SOF-100's `design_refs`/`dependencies` (0018): NULL means the
closing agent never addressed the question — `TicketStore.mark_done()` now refuses to close a
ticket in that state (same mechanical honesty gate that already refuses a hollow provenance/diff).
`'[]'` means an explicit, honest "nothing to declare" — a real, gate-passing answer, not an
omission. No server_default, so the column starts NULL for existing rows (which is the correct,
honest "never addressed" state for tickets that predate this migration).

ADD COLUMN IF NOT EXISTS — idempotent, safe to re-run.

REHEARSAL PROTOCOL:
  1. alembic upgrade 0020_ticket_decision_log (on a test DB stamped at 0019_seed_tickets_agent)
  2. Assert: `tickets` has `decision_log`, NULL on existing rows.
  3. Deploy to staging only after rehearsal passes.
"""
from alembic import op

revision = "0020_ticket_decision_log"
down_revision = "0019_seed_tickets_agent"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE tickets ADD COLUMN IF NOT EXISTS decision_log TEXT")


def downgrade() -> None:
    op.execute("ALTER TABLE tickets DROP COLUMN IF EXISTS decision_log")
