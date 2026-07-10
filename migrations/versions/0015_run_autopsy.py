"""Run autopsy (SOF-93): autopsy_processed_runs + autopsy_signatures

Revision ID: 0015_run_autopsy
Revises: 0014_memory_halfvec3072
Create Date: 2026-07-10

Two global tables, both empty at creation (no seed data):
- autopsy_processed_runs: per-run idempotency ledger (project_id PK) — a re-scan of an
  already-processed benchmark run is a no-op.
- autopsy_signatures: cross-run dedup ledger (signature PK) — a repeated failure signature
  comments on its existing linear_issue_id instead of filing a duplicate. linear_issue_id/
  linear_issue_identifier are nullable — filing degrades honestly when LINEAR_API_KEY is unset,
  and the signature is still recorded so occurrence counting works from day one.

REHEARSAL PROTOCOL: alembic upgrade 0015_run_autopsy on a DB stamped at 0014_memory_halfvec3072;
assert both tables exist, empty, with the PKs above.
"""
from alembic import op

revision = "0015_run_autopsy"
down_revision = "0014_memory_halfvec3072"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS autopsy_processed_runs (
            project_id      TEXT PRIMARY KEY,
            signature       TEXT NOT NULL,
            classification  TEXT NOT NULL,
            processed_at    DOUBLE PRECISION NOT NULL
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS autopsy_signatures (
            signature               TEXT PRIMARY KEY,
            classification          TEXT NOT NULL,
            linear_issue_id         TEXT,
            linear_issue_identifier TEXT,
            first_project_id        TEXT NOT NULL,
            last_project_id         TEXT NOT NULL,
            occurrences             INTEGER NOT NULL DEFAULT 1,
            first_seen_at           DOUBLE PRECISION NOT NULL,
            last_seen_at            DOUBLE PRECISION NOT NULL
        )
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS autopsy_processed_runs")
    op.execute("DROP TABLE IF EXISTS autopsy_signatures")
