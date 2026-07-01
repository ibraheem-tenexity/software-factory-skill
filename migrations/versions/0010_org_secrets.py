"""Org secrets metadata: `org_secrets` table + org_id index

Revision ID: 0010_org_secrets
Revises: 0009_conversation
Create Date: 2026-07-01

ADDITIVE / idempotent ONLY. Adds one new table (`org_secrets`) with its unique constraint and an
org_id lookup index. Zero contact with any existing table. Metadata only — the plaintext secret
value is never stored here; `vault_id` is a pointer into Supabase Vault (pgsodium), resolved via
`vault.py`'s vault_store/vault_retrieve_many/vault_delete_many.

REHEARSAL PROTOCOL:
  1. alembic upgrade 0010_org_secrets  (on the stamped test DB at 0009_conversation)
  2. Assert `org_secrets` exists with the (org_id, name) unique constraint and the org_id index.
  3. Assert no other table's rows changed.
  4. Deploy to prod only after rehearsal passes.
"""
from alembic import op

revision = "0010_org_secrets"
down_revision = "0009_conversation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS org_secrets (
            id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            org_id      TEXT NOT NULL,
            name        TEXT NOT NULL,
            kind        TEXT,
            vault_id    TEXT NOT NULL,
            last4       TEXT,
            used_by     INTEGER NOT NULL DEFAULT 0,
            created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_org_secrets_org_name UNIQUE (org_id, name)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS org_secrets_org_id ON org_secrets (org_id)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS org_secrets")
