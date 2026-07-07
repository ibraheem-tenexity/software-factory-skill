"""Project Memory: chunk.dense / doc_summary.embedding -> halfvec(3072) (SOF-84)

Revision ID: 0014_memory_halfvec3072
Revises: 0013_tools_registry
Create Date: 2026-07-02

SOF-84 found two compounding bugs in `memory/embed.py`: (1) the openai SDK's implicit
`encoding_format=base64` default breaks against this model on OpenRouter (200 + empty `data`),
and (2) `google/gemini-embedding-2`'s real output is 3072-dim, not the 1024 these columns were
declared as. Because bug (1) blocked most calls outright and bug (2) would have failed insertion
on the rare success, NO valid embedding is expected to exist in either column today — this
migration clears both with `USING NULL` rather than attempting a same-dimension cast, which
would be wrong anyway (1024-dim data is not valid 3072-dim data). Any `doc_summary`/`chunk` rows
affected simply get re-embedded by the ingestion pipeline on next run.

`vector(3072)` cannot be HNSW-indexed directly — pgvector caps `vector` HNSW/IVFFlat indexes at
2000 dimensions (confirmed empirically: `ERROR: column cannot have more than 2000 dimensions for
hnsw index`). `halfvec` (half-precision, pgvector >=0.7) raises that cap to 4000, so `chunk`'s
HNSW index is rebuilt as `halfvec_cosine_ops` over the new column type. `doc_summary.embedding`
has no index (per 0008: one row per document, a few hundred rows at most — exact scan).

REHEARSAL PROTOCOL:
  1. alembic upgrade 0014_memory_halfvec3072 on a DB stamped at 0013_tools_registry.
  2. Assert `chunk.dense` and `doc_summary.embedding` are `halfvec(3072)` (\\d chunk / \\d doc_summary).
  3. Assert `chunk_dense_hnsw` exists and uses `halfvec_cosine_ops` (\\d+ chunk or pg_indexes).
  4. Insert a 3072-dim halfvec row into each table and confirm `<=>` ordering works.
  5. Deploy to prod only after rehearsal passes.
"""
from alembic import op

revision = "0014_memory_halfvec3072"
down_revision = "0013_tools_registry"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # The existing HNSW index is bound to vector_cosine_ops, which rejects halfvec — must drop
    # it before the ALTER COLUMN TYPE below, not after (confirmed: Postgres raises
    # "operator class vector_cosine_ops does not accept data type halfvec" otherwise).
    op.execute("DROP INDEX IF EXISTS chunk_dense_hnsw")
    op.execute("ALTER TABLE doc_summary ALTER COLUMN embedding TYPE halfvec(3072) USING NULL")
    op.execute("ALTER TABLE chunk ALTER COLUMN dense TYPE halfvec(3072) USING NULL")
    op.execute("CREATE INDEX IF NOT EXISTS chunk_dense_hnsw ON chunk USING hnsw (dense halfvec_cosine_ops)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS chunk_dense_hnsw")
    op.execute("ALTER TABLE chunk ALTER COLUMN dense TYPE vector(1024) USING NULL")
    op.execute("ALTER TABLE doc_summary ALTER COLUMN embedding TYPE vector(1024) USING NULL")
    op.execute("CREATE INDEX IF NOT EXISTS chunk_dense_hnsw ON chunk USING hnsw (dense vector_cosine_ops)")
