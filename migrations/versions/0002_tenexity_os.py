"""tenexity os + crud: agent_prompts / mcp_tools / agent_registry tables + users.status column

Revision ID: 0002_tenexity_os
Revises: 0001_project_baseline
Create Date: 2026-06-20

These tables/column are new in models.metadata AFTER the project rename baseline. On a FRESH DB the
baseline's create_all already builds them; but PROD is already stamped 0001_project_baseline (the
rename deploy ran it BEFORE these existed), so `alembic upgrade head` would no-op and they'd never be
created → the Tenexity OS / CRUD endpoints 500 in prod. This migration creates them on the upgrade
path. IDEMPOTENT (create_all checkfirst + ADD COLUMN IF NOT EXISTS) so it's a no-op on a fresh DB
where the baseline already built them.

Seeding: agent_registry / mcp_tools are seeded lazily by the app stores (ToolStore/AgentRegistryStore
._seed_if_empty on first read), so the tables start empty here and self-populate on first OS request.
"""
from alembic import op

from software_factory import models

revision = "0002_tenexity_os"
down_revision = "0001_project_baseline"
branch_labels = None
depends_on = None


def upgrade() -> None:
    models.metadata.create_all(
        op.get_bind(),
        tables=[models.agent_prompts, models.mcp_tools, models.agent_registry],
        checkfirst=True)
    op.execute("ALTER TABLE public.users ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'active'")


def downgrade() -> None:
    pass
