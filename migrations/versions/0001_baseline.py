"""baseline: global public tables (sf_runs registry + users directory)

Revision ID: 0001_baseline
Revises:
Create Date: 2026-06-18

Captures the GLOBAL schema as it exists today. Per-run schemas (sf_run_<id>) are managed separately
by software_factory.migrate's per-run fan-out, not by Alembic revisions. Idempotent (IF NOT EXISTS)
so it is safe to run against a DB whose global tables were already self-created.
"""
from alembic import op

revision = "0001_baseline"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "CREATE TABLE IF NOT EXISTS public.sf_runs ("
        " run_id text PRIMARY KEY,"
        " schema_name text NOT NULL,"
        " created_at timestamptz NOT NULL DEFAULT now())"
    )
    op.execute(
        "CREATE TABLE IF NOT EXISTS public.users ("
        " email text PRIMARY KEY,"
        " role text NOT NULL DEFAULT 'member',"
        " created_at timestamptz DEFAULT now(),"
        " created_by text)"
    )
    # Per-run schema version registry (stamped by dbshim on schema creation + by the fan-out).
    op.execute(
        "CREATE TABLE IF NOT EXISTS public.sf_run_schema_version ("
        " run_id text PRIMARY KEY,"
        " version text NOT NULL,"
        " updated_at timestamptz NOT NULL DEFAULT now())"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS public.sf_run_schema_version")
    op.execute("DROP TABLE IF EXISTS public.users")
    op.execute("DROP TABLE IF EXISTS public.sf_runs")
