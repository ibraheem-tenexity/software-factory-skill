"""Scoped source-directory schema + migrate existing documents (SOF-251, epic SOF-238).

Adds the `directories` relation (the Files-browser tree, owned by the source-material/memory
capability) plus a nullable `blobs.directory_id`, then files every existing top-level source blob
under a single persisted per-scope root — WITHOUT touching blob IDs, storage keys, hashes,
document summaries, chunks, blob uses, scope, or access. Nothing is re-ingested.

Database-enforced invariants (see docs/schema-erd.dot / ARCHITECTURE.md):
  * A child directory shares its parent's scope/scope_id — the composite parent FK targets the
    (id, scope, scope_id) unique key, so a cross-scope parent cannot exist.
  * Sibling names are unique within a parent and scope, roots included — two partial unique
    indexes (parent present vs. NULL root), because SQL treats NULL parents as distinct.
  * A blob's directory shares the blob's scope/scope_id — the composite FK on `blobs`.
  * ON DELETE RESTRICT on the self-parent and blob FKs: deleting a directory that still owns
    descendants or member blobs is refused, never a silent cascade or orphan.
The top-level Files screen is virtual and mixed-scope, so it is never a stored row.

Migration backfill:
  * For every (scope, scope_id) that owns a top-level source blob (`source_blob_id IS NULL`),
    create or reuse exactly one root directory (name = project/org display name, or scope_id
    when that name is NULL *or empty* — many staging projects have a blank name, and a root
    literally named '' would surface as an empty label in the Files UI).
  * File each such top-level blob under that root. Extracted-child assets (`source_blob_id`
    NOT NULL) keep `directory_id` NULL — their membership stays provenance via source_blob_id.
  * Root summary state is initialized honestly: no directory-level rollup has ever been computed,
    so `summary_status='needs_refresh'`, `summary_md`/`summary_source_hash`/
    `last_successful_summary_at` NULL. The migration never fabricates a "ready" summary.

Idempotent under Alembic's one-time model: DDL is IF NOT EXISTS / constraint-guarded, the root
insert is ON CONFLICT DO NOTHING, and the blob assignment only touches rows still unfiled. The
whole upgrade runs in Alembic's single transaction; any failure logs a full traceback and rolls
back, so partial membership is never left behind.

Revision ID: 0034_source_directories
Revises: 0033_artifact_stage
Create Date: 2026-07-22

HELD for the integrator merge sequence: chains off #441/SOF-78's 0033_artifact_stage to keep a
single linear head, so it merges after that revision lands.
"""
import logging

from alembic import op

revision = "0034_source_directories"
down_revision = "0033_artifact_stage"
branch_labels = None
depends_on = None

logger = logging.getLogger("alembic.runtime.migration")


def upgrade() -> None:
    try:
        # ---- directories relation --------------------------------------------------------
        op.execute(
            """
            CREATE TABLE IF NOT EXISTS directories (
                id                         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                scope                      TEXT NOT NULL,
                scope_id                   TEXT NOT NULL,
                parent_id                  UUID,
                name                       TEXT NOT NULL,
                summary_md                 TEXT,
                summary_status             TEXT NOT NULL DEFAULT 'needs_refresh',
                summary_source_hash        TEXT,
                last_successful_summary_at TIMESTAMPTZ,
                created_at                 TIMESTAMPTZ NOT NULL DEFAULT now(),
                updated_at                 TIMESTAMPTZ NOT NULL DEFAULT now(),
                CONSTRAINT directories_scope_check CHECK (scope IN ('project', 'org')),
                CONSTRAINT directories_summary_status_check
                    CHECK (summary_status IN ('summarizing', 'ready', 'needs_refresh', 'failed')),
                CONSTRAINT uq_directories_id_scope UNIQUE (id, scope, scope_id),
                CONSTRAINT fk_directories_parent_scope
                    FOREIGN KEY (parent_id, scope, scope_id)
                    REFERENCES directories (id, scope, scope_id) ON DELETE RESTRICT
            )
            """
        )
        # Sibling-name uniqueness: children keyed by (scope, scope_id, parent, name); roots (NULL
        # parent) keyed by (scope, scope_id, name) — NULL parents are otherwise treated as distinct.
        op.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_directories_sibling_name "
            "ON directories (scope, scope_id, parent_id, name) WHERE parent_id IS NOT NULL"
        )
        op.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_directories_root_name "
            "ON directories (scope, scope_id, name) WHERE parent_id IS NULL"
        )
        # Traversal helpers: scope-root lookup and parent walk.
        op.execute(
            "CREATE INDEX IF NOT EXISTS ix_directories_scope_roots "
            "ON directories (scope, scope_id) WHERE parent_id IS NULL"
        )
        op.execute("CREATE INDEX IF NOT EXISTS ix_directories_parent ON directories (parent_id)")

        # ---- blobs.directory_id + composite membership FK --------------------------------
        op.execute("ALTER TABLE blobs ADD COLUMN IF NOT EXISTS directory_id UUID")
        # Constraint-guarded add (ALTER TABLE has no ADD CONSTRAINT IF NOT EXISTS).
        op.execute(
            """
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM pg_constraint WHERE conname = 'fk_blobs_directory_scope'
                ) THEN
                    ALTER TABLE blobs ADD CONSTRAINT fk_blobs_directory_scope
                        FOREIGN KEY (directory_id, scope, scope_id)
                        REFERENCES directories (id, scope, scope_id) ON DELETE RESTRICT;
                END IF;
            END $$
            """
        )
        op.execute("CREATE INDEX IF NOT EXISTS ix_blobs_directory_id ON blobs (directory_id)")

        # ---- backfill: one root per scope that owns top-level source blobs ---------------
        # DISTINCT collapses to one row per (scope, scope_id); ON CONFLICT makes a re-run reuse the
        # existing root instead of inserting a duplicate.
        op.execute(
            """
            INSERT INTO directories (scope, scope_id, parent_id, name, summary_status)
            SELECT DISTINCT b.scope, b.scope_id, NULL::uuid,
                   COALESCE(NULLIF(ps.name, ''), NULLIF(o.name, ''), b.scope_id) AS name,
                   'needs_refresh'
            FROM blobs b
            LEFT JOIN projectstate ps ON b.scope = 'project' AND ps.project_id = b.scope_id
            LEFT JOIN organizations o ON b.scope = 'org' AND o.id = b.scope_id
            WHERE b.source_blob_id IS NULL
            ON CONFLICT (scope, scope_id, name) WHERE parent_id IS NULL DO NOTHING
            """
        )
        # ---- backfill: file every still-unfiled top-level blob under its scope root ------
        # Only directory_id is written; IDs/keys/hashes/summaries/chunks/uses/scope are untouched.
        op.execute(
            """
            UPDATE blobs b
            SET directory_id = d.id
            FROM directories d
            WHERE d.parent_id IS NULL
              AND d.scope = b.scope
              AND d.scope_id = b.scope_id
              AND b.source_blob_id IS NULL
              AND b.directory_id IS NULL
            """
        )
    except Exception:
        logger.exception("SOF-251 0034_source_directories upgrade failed — rolling back")
        raise


def downgrade() -> None:
    try:
        # Unfile blobs before dropping the tree so the RESTRICT membership FK does not block us.
        op.execute("UPDATE blobs SET directory_id = NULL")
        op.execute("ALTER TABLE blobs DROP CONSTRAINT IF EXISTS fk_blobs_directory_scope")
        op.execute("DROP INDEX IF EXISTS ix_blobs_directory_id")
        op.execute("ALTER TABLE blobs DROP COLUMN IF EXISTS directory_id")
        op.execute("DROP TABLE IF EXISTS directories")
    except Exception:
        logger.exception("SOF-251 0034_source_directories downgrade failed — rolling back")
        raise
