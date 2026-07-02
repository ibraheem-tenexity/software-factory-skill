"""Assumptions rename + user-deposited document artifacts

Revision ID: 0011_assumptions_and_document_artifacts
Revises: 0010_org_secrets
Create Date: 2026-07-01

Two changes (SOF-60 / concierge memory substrate):
1. `doc_summary.key_facts` -> `doc_summary.assumptions` — the entries are draft assumptions the
   customer confirms or corrects in the Interview step ("Let's confirm what I learned"), not
   settled facts. Pure rename, data intact.
2. `artifacts` gains three nullable/defaulted columns so user-deposited documents can live
   alongside agent-produced artifacts: `content` (the full converted markdown, inline),
   `source_blob_id` (FK to the uploaded document's blobs row), and `origin`
   ('agent' | 'user' — existing rows are all agent-produced, hence the default backfill).

ADDITIVE apart from the column rename (which preserves data). No row rewrites, no drops.

REHEARSAL PROTOCOL:
  1. alembic upgrade 0011_assumptions_and_document_artifacts  (on a DB stamped 0010_org_secrets)
  2. Assert doc_summary.assumptions exists and rows that had key_facts data kept it.
  3. Assert artifacts has content/source_blob_id/origin and every pre-existing row reads
     origin='agent'.
  4. Insert an origin='user' artifacts row with content + source_blob_id set; read it back.
  5. Deploy to prod only after rehearsal passes.
"""
from alembic import op

revision = "0011_assumptions_and_document_artifacts"
down_revision = "0010_org_secrets"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE doc_summary RENAME COLUMN key_facts TO assumptions")
    op.execute("ALTER TABLE artifacts ADD COLUMN IF NOT EXISTS content TEXT")
    op.execute("ALTER TABLE artifacts ADD COLUMN IF NOT EXISTS source_blob_id INTEGER "
               "REFERENCES blobs(id) ON DELETE CASCADE")
    op.execute("ALTER TABLE artifacts ADD COLUMN IF NOT EXISTS origin TEXT NOT NULL DEFAULT 'agent'")
    op.execute("CREATE INDEX IF NOT EXISTS artifacts_source_blob_id ON artifacts (source_blob_id)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS artifacts_source_blob_id")
    op.execute("ALTER TABLE artifacts DROP COLUMN IF EXISTS origin")
    op.execute("ALTER TABLE artifacts DROP COLUMN IF EXISTS source_blob_id")
    op.execute("ALTER TABLE artifacts DROP COLUMN IF EXISTS content")
    op.execute("ALTER TABLE doc_summary RENAME COLUMN assumptions TO key_facts")
