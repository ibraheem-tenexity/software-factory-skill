"""project baseline — the entire flat project schema, from scratch.

Big-bang run->project rename (operator directive: drop ALL existing schema, no data, no migration,
no back-compat). This single revision REPLACES the pre-rename 0001-0004 chain. ``upgrade()`` wipes
the public schema and rebuilds every table directly from ``models.metadata`` — ``projectstate`` plus
the project_id-keyed canvas tables (phases/artifacts/blockers/gates/verifications/deployments/
tickets/agents/blob_uses) and the global directory tables (organizations/users/blobs). Irreversible.

Revision ID: 0001_project_baseline
Revises: (none — fresh baseline)
"""
from alembic import op

from software_factory import models

revision = "0001_project_baseline"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Build the full project-named schema from the ORM. The total wipe of any pre-rename schema
    # happens in migrate.py BEFORE Alembic runs (DROP SCHEMA public CASCADE when the DB carries a
    # stale pre-rename stamp) — doing the drop here would also drop Alembic's own alembic_version
    # table mid-run and break the stamp. On a freshly-wiped/empty public this is the whole schema.
    models.metadata.create_all(op.get_bind())


def downgrade() -> None:
    # Irreversible by design — the pre-rename schema is gone for good.
    pass
