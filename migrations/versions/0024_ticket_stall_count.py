"""Ticket stall_count field (SOF-163): orphaned in_progress ticket reclaim tracking

Revision ID: 0024_ticket_stall_count
Revises: 0023_eval_scores
Create Date: 2026-07-12

Adds `stall_count` to `tickets` — how many times the host has reclaimed this ticket back to
`open` because it was `in_progress` with no live path forward: either its claimed agent's own
runtime_agents row is already terminal (done/failed) with the ticket never reverted, or that
agent has been `running` past a generous staleness bound (SF_TICKET_STALL_HOURS, default 6 —
matches run_autopsy's own TIMEOUT_HOURS). Same shape as `review_bounce_count` (0021): `0` is
both the honest starting value and the correct default, no NULL-vs-'[]' ambiguity to preserve.

ADD COLUMN IF NOT EXISTS — idempotent, safe to re-run.

REHEARSAL PROTOCOL:
  1. alembic upgrade 0024_ticket_stall_count (on a test DB stamped at 0023_eval_scores)
  2. Assert: `tickets` has `stall_count`, defaulting to 0 on existing rows.
  3. Deploy to staging only after rehearsal passes.
"""
from alembic import op

revision = "0024_ticket_stall_count"
down_revision = "0023_eval_scores"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE tickets ADD COLUMN IF NOT EXISTS stall_count INTEGER NOT NULL DEFAULT 0"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE tickets DROP COLUMN IF EXISTS stall_count")
