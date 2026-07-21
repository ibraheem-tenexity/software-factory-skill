"""Recipes (CBT-9): `recipes` table

Revision ID: 0029_recipes_table
Revises: 0028_org_name_unique
Create Date: 2026-07-21

Fresh global table (operator-adjudicated — not an extension of `sow`) backing the repo-backed
recipes feature: admin-authored customer-facing fields (name/tagline/category/capabilities/images),
the concierge/brief input (body_md), and the build-seed repo (repo_url, nullable until connected).
No index/tree column — the build clones repo_url fresh at workspace-prep time; the validation
clone (recipes/store.py) is discarded after its one AGENTS.md/CLAUDE.md fact-check.

Additive + idempotent (IF NOT EXISTS), no backfill, no new Python dependency.

REHEARSAL PROTOCOL: alembic upgrade 0029_recipes_table on a DB stamped at 0028_org_name_unique;
assert `recipes` exists with the status CHECK constraint and the name UNIQUE constraint; assert no
other table's rows changed.
"""
from alembic import op

revision = "0029_recipes_table"
down_revision = "0028_org_name_unique"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS recipes (
            id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            name         TEXT NOT NULL UNIQUE,
            tagline      TEXT,
            category     TEXT,
            capabilities JSONB NOT NULL DEFAULT '[]'::jsonb,
            body_md      TEXT,
            repo_url     TEXT,
            images       JSONB NOT NULL DEFAULT '[]'::jsonb,
            status       TEXT NOT NULL DEFAULT 'draft',
            created_at   TIMESTAMPTZ DEFAULT now(),
            updated_at   TIMESTAMPTZ DEFAULT now(),
            CONSTRAINT recipes_status_check CHECK (status IN ('draft','published','archived'))
        )
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS recipes")
