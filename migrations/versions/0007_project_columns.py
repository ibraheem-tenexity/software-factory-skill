"""promote project name + summary to real projectstate columns

Revision ID: 0007_project_columns
Revises: 0006_checkpoints
Create Date: 2026-06-30

ADDITIVE / idempotent ONLY. Adds two nullable columns to `projectstate` (`name`, `summary`) and
backfills `name` out of the existing JSON `data` blob so the move is lossless. `name` becomes the
authoritative column (the store stops writing it into `data`); `summary` is new and starts NULL.
No table drops, no row deletes — `ADD COLUMN IF NOT EXISTS` is a no-op on a fresh DB where
`create_all` already built the columns, and a pure addition on a stamped-prod upgrade.

REHEARSAL PROTOCOL:
  1. alembic upgrade 0007_project_columns  (on the stamped test DB at 0006_checkpoints)
  2. Assert `projectstate` has `name` + `summary` columns and existing rows' `name` is backfilled.
  3. Assert no other projectstate data changed.
  4. Deploy to prod only after rehearsal passes.
"""
from alembic import op

revision = "0007_project_columns"
down_revision = "0006_checkpoints"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE projectstate ADD COLUMN IF NOT EXISTS name TEXT")
    op.execute("ALTER TABLE projectstate ADD COLUMN IF NOT EXISTS summary TEXT")
    # Backfill the new authoritative `name` column from the JSON blob for existing rows.
    op.execute(
        "UPDATE projectstate SET name = data::jsonb->>'name' "
        "WHERE name IS NULL AND data IS NOT NULL AND (data::jsonb ? 'name')"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE projectstate DROP COLUMN IF EXISTS summary")
    op.execute("ALTER TABLE projectstate DROP COLUMN IF EXISTS name")
