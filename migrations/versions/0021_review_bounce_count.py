"""Ticket review_bounce_count field (SOF-119): in-pipeline review agent bounce tracking

Revision ID: 0021_review_bounce_count
Revises: 0020_ticket_decision_log
Create Date: 2026-07-10

Adds `review_bounce_count` to `tickets` — how many times the new REVIEW stage (Stage 3, between
the shared deploy+happy-flow gate and the existing per-ticket QA loop) has bounced this ticket
back to `open` for a real, adversarially-found defect (a server-side gate that isn't actually
enforced, an unreachable declared role, unsubstituted template tokens, a WYSIWYG mismatch).

Unlike `design_refs`/`dependencies`/`decision_log` (0018/0020), this does NOT need a NULL-vs-'[]'
style distinction — a fresh ticket has genuinely never been bounced, so `0` is both the honest
starting value and the correct default (no "never addressed" ambiguity to preserve).

ADD COLUMN IF NOT EXISTS — idempotent, safe to re-run.

REHEARSAL PROTOCOL:
  1. alembic upgrade 0021_review_bounce_count (on a test DB stamped at 0020_ticket_decision_log)
  2. Assert: `tickets` has `review_bounce_count`, defaulting to 0 on existing rows.
  3. Deploy to staging only after rehearsal passes.
"""
from alembic import op

revision = "0021_review_bounce_count"
down_revision = "0020_ticket_decision_log"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE tickets ADD COLUMN IF NOT EXISTS review_bounce_count INTEGER NOT NULL DEFAULT 0"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE tickets DROP COLUMN IF EXISTS review_bounce_count")
