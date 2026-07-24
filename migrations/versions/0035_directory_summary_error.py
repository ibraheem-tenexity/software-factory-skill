"""Add directories.summary_error for truthful directory-summary failure detail (SOF-254, epic SOF-238).

SOF-251 (0034) gave `directories` the summary state columns summary_md / summary_status /
summary_source_hash / last_successful_summary_at. SOF-254 generates the actual read-only rollup
summaries and needs one more truthful field: when the LATEST refresh fails, the row must retain
BOTH the last successful summary (in summary_md, untouched) AND the real reason the refresh failed.
Those cannot share a column, so `summary_error` is added. It is NULL whenever the summary is
current (cleared on every successful refresh) and holds the actual exception text while
summary_status='failed'.

No data backfill: existing rows have never had a summary generated, so they carry NULL error,
which is correct (no failure has occurred).

Revision ID: 0035_directory_summary_error
Revises: 0034_source_directories
Create Date: 2026-07-22

HELD for the integrator merge sequence: chains off SOF-251's 0034_source_directories (held PR
#444), which itself chains off #441/SOF-78's 0033_artifact_stage. Keeps a single linear head.
"""
import logging

from alembic import op

revision = "0035_directory_summary_error"
down_revision = "0034_source_directories"
branch_labels = None
depends_on = None

logger = logging.getLogger("alembic.runtime.migration")


def upgrade() -> None:
    try:
        op.execute("ALTER TABLE directories ADD COLUMN IF NOT EXISTS summary_error TEXT")
    except Exception:
        logger.exception("SOF-254 0035_directory_summary_error upgrade failed — rolling back")
        raise


def downgrade() -> None:
    try:
        op.execute("ALTER TABLE directories DROP COLUMN IF EXISTS summary_error")
    except Exception:
        logger.exception("SOF-254 0035_directory_summary_error downgrade failed — rolling back")
        raise
