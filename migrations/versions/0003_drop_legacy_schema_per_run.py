"""drop the legacy schema-per-run artifacts (no data migration — operator chose to discard)

Revision ID: 0003_drop_legacy_schema_per_run
Revises: 0002_flat_schema
Create Date: 2026-06-19

The old model gave every run its own `sf_run_<id>` schema, tracked in `public.sf_runs` +
`public.sf_run_schema_version`. The flat schema (0002) replaces all of it. The operator chose NOT
to migrate existing run data, so this revision simply drops every `sf_run_*` schema and the two
registry tables. Runs automatically on deploy via `alembic upgrade head`. Irreversible.
"""
from alembic import op

revision = "0003_drop_legacy_schema_per_run"
down_revision = "0002_flat_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        DO $$
        DECLARE s text;
        BEGIN
          FOR s IN SELECT schema_name FROM information_schema.schemata
                   WHERE schema_name ~ '^sf_run_' LOOP
            EXECUTE format('DROP SCHEMA IF EXISTS %I CASCADE', s);
          END LOOP;
        END $$;
        """
    )
    op.execute("DROP TABLE IF EXISTS public.sf_run_schema_version")
    op.execute("DROP TABLE IF EXISTS public.sf_runs")


def downgrade() -> None:
    pass  # the legacy schema-per-run model is gone for good
