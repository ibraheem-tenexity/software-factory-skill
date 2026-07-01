"""Project Memory: doc_summary + chunk tables, pgvector extension, blobs provenance columns

Revision ID: 0008_project_memory
Revises: 0007_project_columns
Create Date: 2026-07-01

ADDITIVE / idempotent ONLY. Adds two new tables (`doc_summary`, `chunk`), the `vector` extension,
and three nullable columns on `blobs` (`source_blob_id`, `source_page`, `provenance`). Zero
contact with existing rows in any table — no ALTER on a NOT NULL column, no backfill, no drop.

Requires the target Postgres to have the pgvector extension available (CREATE EXTENSION IF NOT
EXISTS vector). Confirm this before running against a new environment — if the extension is
absent this migration fails loudly rather than silently degrading.

REHEARSAL PROTOCOL:
  1. Confirm `CREATE EXTENSION IF NOT EXISTS vector` succeeds on the target Postgres.
  2. alembic upgrade 0008_project_memory  (on the stamped test DB at 0007_project_columns)
  3. Assert `doc_summary` and `chunk` exist with their indexes; assert `blobs` gained the three
     new (nullable) columns and every existing `blobs` row is otherwise unchanged.
  4. Insert + select a Vector(1024) row and confirm `chunk.fts` is populated by Postgres from
     `content` (GENERATED ALWAYS AS ... STORED) without the migration writing it directly.
  5. Deploy to prod only after rehearsal passes.
"""
from alembic import op

revision = "0008_project_memory"
down_revision = "0007_project_columns"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.execute("""
        CREATE TABLE IF NOT EXISTS doc_summary (
            blob_id         INTEGER PRIMARY KEY REFERENCES blobs(id) ON DELETE CASCADE,
            scope           TEXT NOT NULL,
            scope_id        TEXT NOT NULL,
            summary_md      TEXT,
            key_facts       JSONB NOT NULL DEFAULT '{}'::jsonb,
            outline         JSONB NOT NULL DEFAULT '[]'::jsonb,
            embedding       vector(1024),
            token_count     INTEGER,
            content_sha256  TEXT,
            status          TEXT NOT NULL DEFAULT 'pending',
            updated_at      TIMESTAMPTZ DEFAULT now()
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS chunk (
            id            SERIAL PRIMARY KEY,
            blob_id       INTEGER NOT NULL REFERENCES blobs(id) ON DELETE CASCADE,
            scope         TEXT NOT NULL,
            scope_id      TEXT NOT NULL,
            ordinal       INTEGER NOT NULL,
            section_path  TEXT,
            content       TEXT NOT NULL,
            dense         vector(1024),
            fts           tsvector GENERATED ALWAYS AS (to_tsvector('english', content)) STORED,
            token_count   INTEGER
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS chunk_dense_hnsw ON chunk USING hnsw (dense vector_cosine_ops)")
    op.execute("CREATE INDEX IF NOT EXISTS chunk_fts_gin ON chunk USING gin (fts)")
    op.execute("CREATE INDEX IF NOT EXISTS chunk_scope ON chunk (scope, scope_id)")
    op.execute("CREATE INDEX IF NOT EXISTS chunk_blob_id ON chunk (blob_id)")
    op.execute("CREATE INDEX IF NOT EXISTS doc_summary_scope ON doc_summary (scope, scope_id)")

    op.execute("ALTER TABLE blobs ADD COLUMN IF NOT EXISTS source_blob_id INTEGER REFERENCES blobs(id)")
    op.execute("ALTER TABLE blobs ADD COLUMN IF NOT EXISTS source_page INTEGER")
    op.execute("ALTER TABLE blobs ADD COLUMN IF NOT EXISTS provenance JSONB DEFAULT '{}'::jsonb")


def downgrade() -> None:
    op.execute("ALTER TABLE blobs DROP COLUMN IF EXISTS provenance")
    op.execute("ALTER TABLE blobs DROP COLUMN IF EXISTS source_page")
    op.execute("ALTER TABLE blobs DROP COLUMN IF EXISTS source_blob_id")
    op.execute("DROP TABLE IF EXISTS chunk")
    op.execute("DROP TABLE IF EXISTS doc_summary")
