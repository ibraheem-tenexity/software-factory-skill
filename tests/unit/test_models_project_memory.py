"""Schema tests for SOF-26/T0.1 (doc_summary, chunk, conversation, blobs provenance).

NOT EXECUTED IN THIS SANDBOX. Per an explicit operator hard constraint, this worktree must
never run a DB-connecting test here — this repo's conftest.py bootstraps a real Postgres
connection (`_create_private_db` + `models.metadata.create_all`) at COLLECTION time for every
single test file, regardless of which test is selected, and doing that against a schema that
now includes pgvector `Vector` columns is exactly the flagged OOM-risk operation. These tests
were written to satisfy the ticket's acceptance criteria and verified line-by-line against a
DB-free `python -c` check of the compiled DDL (see the PR description) — but pytest was never
invoked against them here. The integrator validates off-box (scratch DB) before merge.
"""
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable

from software_factory import models


def test_new_tables_are_registered_in_all_tables():
    assert models.doc_summary in models.ALL_TABLES
    assert models.chunk in models.ALL_TABLES
    assert models.conversation in models.ALL_TABLES


def test_doc_summary_columns_match_the_ticket_spec():
    cols = {c.name for c in models.doc_summary.columns}
    assert cols == {
        "blob_id", "scope", "scope_id", "summary_md", "assumptions", "outline",
        "embedding", "token_count", "content_sha256", "status", "updated_at",
    }
    assert list(models.doc_summary.primary_key.columns)[0].name == "blob_id"


def test_chunk_columns_match_the_ticket_spec_and_has_no_sparse_column():
    cols = {c.name for c in models.chunk.columns}
    assert cols == {
        "id", "blob_id", "scope", "scope_id", "ordinal", "section_path",
        "content", "dense", "fts", "token_count",
    }
    # SOF-26 explicitly defers learned-sparse — the column must not exist yet.
    assert "sparse" not in cols


def test_chunk_fts_is_a_generated_column_not_a_writable_one():
    ddl = str(CreateTable(models.chunk).compile(dialect=postgresql.dialect()))
    assert "GENERATED ALWAYS AS (to_tsvector('english', content)) STORED" in ddl


def test_conversation_columns_and_unique_constraint_match_the_ticket_spec():
    cols = {c.name for c in models.conversation.columns}
    assert cols == {
        "id", "session_id", "seq", "user_id", "project_id", "org_id", "role",
        "input", "json_blob", "tool_name", "tool_call_id", "tool_result",
        "referenced_artifact", "model", "provider", "input_tokens",
        "output_tokens", "cost_usd", "created_at", "updated_at",
    }
    uniques = {tuple(c.name for c in uc.columns) for uc in models.conversation.constraints
               if uc.__class__.__name__ == "UniqueConstraint"}
    assert ("session_id", "seq") in uniques


def test_blobs_gained_provenance_columns_without_losing_existing_ones():
    cols = {c.name for c in models.blobs.columns}
    assert {"source_blob_id", "source_page", "provenance"} <= cols
    # Pre-existing columns must still be present — an additive change, not a replacement.
    assert {"id", "scope", "scope_id", "storage_key", "sha256"} <= cols


def test_doc_summary_and_chunk_cascade_delete_from_blobs():
    for fk in models.doc_summary.foreign_keys:
        if fk.column.table is models.blobs:
            assert fk.ondelete == "CASCADE"
    for fk in models.chunk.foreign_keys:
        if fk.column.table is models.blobs:
            assert fk.ondelete == "CASCADE"


# ---- DB round-trip smoke test (AC: "Smoke test inserts + selects a Vector(1024) row and a
# to_tsvector-generated fts row") — written per the acceptance criteria, NEVER RUN in this
# sandbox (see module docstring). Requires `CREATE EXTENSION vector` on the target Postgres.

def test_smoke_insert_and_select_a_vector_and_generated_fts_row():
    # dbshim.connect(path)'s `path` arg is unused for the actual connection target (it just
    # os.makedirs's it, a legacy artifact of the old per-project-sqlite convention) — the real
    # target is DATABASE_URL, which conftest points at the private test DB.
    from software_factory import dbshim
    conn = dbshim.connect(".")
    try:
        blob_row = conn.execute(
            "INSERT INTO blobs (scope, scope_id, storage_key) VALUES (?, ?, ?) RETURNING id",
            ("project", "project-smoke-test", "smoke/doc.md"),
        ).fetchone()
        blob_id = blob_row["id"]
        conn.execute(
            "INSERT INTO chunk (blob_id, scope, scope_id, ordinal, content, dense) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (blob_id, "project", "project-smoke-test", 0, "hello world", [0.0] * 1024),
        )
        row = conn.execute(
            "SELECT content, fts, dense FROM chunk WHERE blob_id = ?", (blob_id,)
        ).fetchone()
        assert row["content"] == "hello world"
        assert row["fts"] is not None          # Postgres generated it from `content`
        # Without pgvector.psycopg.register_vector() on the connection, `dense` reads back as
        # the raw string Postgres serializes it as (len 2049, not 1024) — confirmed empirically
        # during #237's review. SOF-29 moved that registration into dbshim._StatePool._configure
        # (every dbshim connection gets it, once, at creation), which is what makes this a real
        # array of length 1024 rather than a string.
        assert len(row["dense"]) == 1024
    finally:
        conn.close()
