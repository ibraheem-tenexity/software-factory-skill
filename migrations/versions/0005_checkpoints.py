"""crash/pause recovery: immutable per-node checkpoint table

Revision ID: 0005_checkpoints
Revises: 0004_user_mgmt
Create Date: 2026-06-24

ADDITIVE / idempotent ONLY.  Adds one new table (`checkpoint`) with a unique index.
Zero contact with existing tables (projectstate, phases, tickets, agents, etc.) — this
is the safest possible migration: CREATE TABLE IF NOT EXISTS + CREATE UNIQUE INDEX IF
NOT EXISTS.  Stamped-prod upgrade is a pure schema addition; no backfill, no ALTER.

REHEARSAL PROTOCOL:
  1. uv run alembic upgrade 0005_checkpoints  (on the stamped test DB)
  2. Assert `checkpoint` table exists with the unique index.
  3. Assert projectstate / phases rows are unchanged.
  4. Deploy to prod only after rehearsal passes.
"""
from alembic import op

revision = "0005_checkpoints"
down_revision = "0004_user_mgmt"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS checkpoint (
            id          BIGSERIAL PRIMARY KEY,
            project_id  TEXT    NOT NULL,
            node        TEXT    NOT NULL,
            output      JSONB   NOT NULL DEFAULT '{}'::jsonb,
            stamped_at  FLOAT   NOT NULL
        )
    """)
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_checkpoint_project_node
            ON checkpoint (project_id, node)
    """)


def downgrade() -> None:
    # Downgrade drops the table (safe — no FK references it yet).
    op.execute("DROP TABLE IF EXISTS checkpoint")
