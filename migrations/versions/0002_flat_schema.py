"""flat schema: all tables in one public schema, built from the SQLAlchemy models

Revision ID: 0002_flat_schema
Revises: 0001_baseline
Create Date: 2026-06-19

Postgres everywhere, no schema-per-run. Creates every table from `software_factory.models`
(the SINGLE schema definition the test suite also builds from, so they cannot drift): the flat
per-run tables (runstate, phases, artifacts, blockers, gates, verifications, deployments, tickets,
agents — keyed by run_id) plus the global directory tables (organizations, blobs). The `users`
table was created minimal by 0001; its onboarding profile columns are added here.

Idempotent (`checkfirst=True` + `ADD COLUMN IF NOT EXISTS`). The retired `sf_runs` /
`sf_run_schema_version` registry tables from 0001 are left in place; the one-time data-migration
script (sf_run_<id> schemas → these flat tables) drops them after copying every run's rows.
"""
from alembic import op

from software_factory import models

revision = "0002_flat_schema"
down_revision = "0001_baseline"
branch_labels = None
depends_on = None

_USER_PROFILE_COLS = (("org_id", "text"), ("designation", "text"),
                      ("role_description", "text"), ("tenexity", "integer"))


def upgrade() -> None:
    bind = op.get_bind()
    # users already exists from 0001 → create_all(checkfirst) skips it; everything else is created.
    models.metadata.create_all(bind, tables=list(models.ALL_TABLES), checkfirst=True)
    for col, typ in _USER_PROFILE_COLS:
        op.execute(f"ALTER TABLE public.users ADD COLUMN IF NOT EXISTS {col} {typ}")


def downgrade() -> None:
    bind = op.get_bind()
    drop = list(models.FLAT_TABLES) + [models.organizations, models.blobs]
    models.metadata.drop_all(bind, tables=drop)
    for col, _typ in _USER_PROFILE_COLS:
        op.execute(f"ALTER TABLE public.users DROP COLUMN IF EXISTS {col}")
