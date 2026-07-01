"""Durable conversation store: `conversation` table + scoped indexes

Revision ID: 0009_conversation
Revises: 0008_project_memory
Create Date: 2026-07-01

ADDITIVE / idempotent ONLY. Adds one new table (`conversation`) with its unique constraint and
scoped lookup indexes. Zero contact with any existing table.

REHEARSAL PROTOCOL:
  1. alembic upgrade 0009_conversation  (on the stamped test DB at 0008_project_memory)
  2. Assert `conversation` exists with the (session_id, seq) unique constraint and the
     project_id/org_id/user_id indexes.
  3. Assert no other table's rows changed.
  4. Deploy to prod only after rehearsal passes.
"""
from alembic import op

revision = "0009_conversation"
down_revision = "0008_project_memory"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS conversation (
            id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            session_id          UUID NOT NULL,
            seq                 INTEGER NOT NULL,
            user_id             UUID REFERENCES users(id),
            project_id          TEXT,
            org_id              TEXT,
            role                TEXT NOT NULL,
            input               TEXT,
            json_blob           JSONB NOT NULL DEFAULT '[]'::jsonb,
            tool_name           TEXT,
            tool_call_id        TEXT,
            tool_result         JSONB,
            referenced_artifact INTEGER REFERENCES blobs(id),
            model               TEXT,
            provider            TEXT,
            input_tokens        INTEGER DEFAULT 0,
            output_tokens       INTEGER DEFAULT 0,
            cost_usd            FLOAT DEFAULT 0,
            created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_conversation_session_seq UNIQUE (session_id, seq)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS conversation_project_id ON conversation (project_id)")
    op.execute("CREATE INDEX IF NOT EXISTS conversation_org_id ON conversation (org_id)")
    op.execute("CREATE INDEX IF NOT EXISTS conversation_user_id ON conversation (user_id)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS conversation")
