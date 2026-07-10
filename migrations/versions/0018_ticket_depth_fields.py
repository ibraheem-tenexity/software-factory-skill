"""Ticket depth fields (SOF-100): goal, design_refs, dependencies, scope_genre, implementation_notes

Revision ID: 0018_ticket_depth_fields
Revises: 0017_seed_design_agent
Create Date: 2026-07-10

Adds five columns to `tickets` so a build ticket can carry more than title/acceptance/dod:
- `goal` (text, default '') — one-sentence purpose, in addition to the mechanical acceptance/dod.
- `design_refs` (text, nullable, NO default) — JSON array of PRD v1 screen IDs this ticket
  implements (e.g. '["SCR-02"]'). NULL means the ticket-writing agent never addressed the
  question; '[]' means it explicitly decided this ticket has no screen (a real, honest state for
  a backend-only ticket) — the depth gate treats these differently, so no default is set.
- `dependencies` (text, nullable, NO default) — JSON array of other tickets this one depends on
  (title or in-batch reference), same NULL-vs-'[]' distinction as design_refs.
- `scope_genre` (text, nullable) — the PRD genre-module heading this ticket's screens belong to,
  when the project selected scope genres (SOF-96/108); null for genre-less/free-form tickets.
- `implementation_notes` (text, default '') — concrete build guidance beyond acceptance/dod.

All ADD COLUMN IF NOT EXISTS — idempotent, safe to re-run.

REHEARSAL PROTOCOL:
  1. alembic upgrade 0018_ticket_depth_fields (on a test DB stamped at 0017_seed_design_agent)
  2. Assert: `tickets` has all 5 new columns; existing rows have goal='' and
     implementation_notes='' (server defaults), design_refs/dependencies/scope_genre NULL.
  3. Deploy to staging only after rehearsal passes.
"""
from alembic import op

revision = "0018_ticket_depth_fields"
down_revision = "0017_seed_design_agent"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE tickets ADD COLUMN IF NOT EXISTS goal TEXT NOT NULL DEFAULT ''")
    op.execute("ALTER TABLE tickets ADD COLUMN IF NOT EXISTS design_refs TEXT")
    op.execute("ALTER TABLE tickets ADD COLUMN IF NOT EXISTS dependencies TEXT")
    op.execute("ALTER TABLE tickets ADD COLUMN IF NOT EXISTS scope_genre TEXT")
    op.execute("ALTER TABLE tickets ADD COLUMN IF NOT EXISTS implementation_notes TEXT NOT NULL DEFAULT ''")


def downgrade() -> None:
    op.execute("ALTER TABLE tickets DROP COLUMN IF EXISTS implementation_notes")
    op.execute("ALTER TABLE tickets DROP COLUMN IF EXISTS scope_genre")
    op.execute("ALTER TABLE tickets DROP COLUMN IF EXISTS dependencies")
    op.execute("ALTER TABLE tickets DROP COLUMN IF EXISTS design_refs")
    op.execute("ALTER TABLE tickets DROP COLUMN IF EXISTS goal")
