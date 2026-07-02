"""sow table: Statement of Work CRUD

Revision ID: 0005_sow
Revises: 0004_user_mgmt
Create Date: 2026-06-24

New global `sow` table for the SOW editor (wsp0uq99 FE task). IDEMPOTENT via
`CREATE TABLE IF NOT EXISTS` — no-op on a fresh DB, creates on a stamped-prod upgrade.

SOF-61: frozen to inline DDL (was `models.metadata.create_all(..., tables=[models.sow])`) — the
byte-for-byte schema `models.metadata` produced for `sow` at commit 185c9de7 (the commit that added
this migration).
"""
from alembic import op

revision = "0005_sow"
down_revision = "0004_user_mgmt"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS sow (
            id          SERIAL PRIMARY KEY,
            title       TEXT NOT NULL,
            org         TEXT,
            project     TEXT,
            value       TEXT,
            file        TEXT,
            version     INTEGER NOT NULL DEFAULT 1,
            status      TEXT NOT NULL DEFAULT 'Draft',
            body        TEXT,
            created_at  TIMESTAMPTZ DEFAULT now(),
            updated_at  TIMESTAMPTZ DEFAULT now(),
            CONSTRAINT sow_status_check CHECK (status in ('Template','Draft','In review','Sent','Signed'))
        )
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS public.sow")
