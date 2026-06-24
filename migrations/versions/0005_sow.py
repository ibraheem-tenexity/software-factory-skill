"""sow table: Statement of Work CRUD

Revision ID: 0005_sow
Revises: 0004_user_mgmt
Create Date: 2026-06-24

New global `sow` table for the SOW editor (wsp0uq99 FE task). IDEMPOTENT via
`create_all checkfirst=True` — no-op on a fresh DB, creates on a stamped-prod upgrade.
"""
from alembic import op

from software_factory import models

revision = "0005_sow"
down_revision = "0004_user_mgmt"
branch_labels = None
depends_on = None


def upgrade() -> None:
    models.metadata.create_all(
        op.get_bind(),
        tables=[models.sow],
        checkfirst=True,
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS public.sow")
