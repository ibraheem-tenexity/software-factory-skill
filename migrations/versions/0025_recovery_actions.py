"""Recovery actions (SOF-165): recovery_actions

Revision ID: 0025_recovery_actions
Revises: 0024_ticket_stall_count
Create Date: 2026-07-12

One global table + one PARTIAL unique index, empty at creation (no seed data):
- recovery_actions: the tier-2 recovery entity (SOF-104 Proposal 5). One row per recovery event;
  mark_stage_crashed, autopsy_and_file, and the SOF-164 silence seam all open() into it. `evidence`
  JSONB holds the cause specifics; `resolution` is the terminal outcome (NULL while open).
- uq_recovery_open_project_kind: PARTIAL unique index on (project_id, kind) WHERE resolved_at IS
  NULL → at most one OPEN action per (project_id, kind). It is the arbiter the open() upsert's
  ON CONFLICT must match (same columns + same predicate), so a repeated same-cause signal refreshes
  the open row instead of duplicating; a re-open after resolution is a fresh row.

Additive + idempotent (IF NOT EXISTS), no backfill, no new Python dependency.

REHEARSAL PROTOCOL: alembic upgrade 0025_recovery_actions on a DB stamped at 0024_ticket_stall_count;
assert recovery_actions + the partial index exist; open two same-kind rows → the 2nd upserts (one
open row); resolve → a 3rd open of that kind inserts a fresh row. Verified on staging before any
prod-promote (standing schema gate).
"""
from alembic import op

revision = "0025_recovery_actions"
down_revision = "0024_ticket_stall_count"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS recovery_actions (
            id           BIGSERIAL PRIMARY KEY,
            project_id   TEXT   NOT NULL,
            kind         TEXT   NOT NULL,
            owner        TEXT   NOT NULL DEFAULT 'auto',
            cause        TEXT   NOT NULL DEFAULT '',
            evidence     JSONB  NOT NULL DEFAULT '{}'::jsonb,
            opened_at    DOUBLE PRECISION NOT NULL,
            resolved_at  DOUBLE PRECISION,
            resolution   TEXT
        )
    """)
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_recovery_open_project_kind
            ON recovery_actions (project_id, kind)
            WHERE resolved_at IS NULL
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS recovery_actions")
