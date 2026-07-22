"""Drop the sow table — the SOW/genre-recipes concept is fully retired in favor of repo-backed
recipes (operator directive 2026-07-22). The recipes table (0029) is the sole framing source:
recipe body_md drives the concierge context and Stage-1 input; nothing reads sow anymore
(SowStore, the admin SOW routes, the scope-genres route, and both context injectors are removed
in the same deploy). Destructive by design: existing sow rows are not migrated — the operator
retired the concept, and the recipes that matter were re-authored as recipes rows.

Revision ID: 0031_drop_sow
Revises: 0030_pin_playwright_mcp_version
"""
from alembic import op

revision = "0031_drop_sow"
down_revision = "0030_pin_playwright_mcp_version"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DROP TABLE IF EXISTS sow")


def downgrade() -> None:
    # The concept is retired; recreating the empty shell keeps downgrade honest without
    # pretending the data can come back.
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS sow (
            id SERIAL PRIMARY KEY,
            title TEXT NOT NULL,
            org TEXT,
            project TEXT,
            value TEXT,
            file TEXT,
            version INTEGER NOT NULL DEFAULT 1,
            status TEXT NOT NULL DEFAULT 'Draft'
                CHECK (status in ('Template','Draft','In review','Sent','Signed')),
            body TEXT,
            created_at TIMESTAMPTZ DEFAULT now(),
            updated_at TIMESTAMPTZ DEFAULT now()
        )
        """
    )
