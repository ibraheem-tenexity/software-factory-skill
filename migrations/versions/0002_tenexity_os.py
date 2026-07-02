"""tenexity os + crud: agent_prompts / mcp_tools / agent_registry tables + users.status column

Revision ID: 0002_tenexity_os
Revises: 0001_project_baseline
Create Date: 2026-06-20

These tables/column are new in models.metadata AFTER the project rename baseline. On a FRESH DB the
baseline's create_all already builds them; but PROD is already stamped 0001_project_baseline (the
rename deploy ran it BEFORE these existed), so `alembic upgrade head` would no-op and they'd never be
created → the Tenexity OS / CRUD endpoints 500 in prod. This migration creates them on the upgrade
path. IDEMPOTENT (CREATE TABLE IF NOT EXISTS + ADD COLUMN IF NOT EXISTS) so it's a no-op on a fresh
DB where the baseline already built them.

Seeding: agent_registry / mcp_tools are seeded lazily by the app stores (ToolStore/AgentRegistryStore
._seed_if_empty on first read), so the tables start empty here and self-populate on first OS request.

SOF-61: frozen to inline DDL (was `models.metadata.create_all(..., tables=[models.agent_prompts,
models.mcp_tools, models.agent_registry])`) — commit c97c7eb dropped `models.agent_prompts` and
`models.agent_registry` from the live module (consolidated into `system_agents`, migrated
separately, later revision), which broke a from-scratch `alembic upgrade head` right here with
`AttributeError`. This is the byte-for-byte schema `models.metadata` produced for these three
tables at commit a16a7824 (the commit that added this migration) — freezing it here is correct
regardless of what the live models module looks like today; renaming/dropping these tables for
real is a separate, later migration's job, not this one's.
"""
from alembic import op

revision = "0002_tenexity_os"
down_revision = "0001_project_baseline"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS agent_prompts (
            callsign    TEXT PRIMARY KEY,
            prompt      TEXT NOT NULL,
            version     INTEGER NOT NULL DEFAULT 1,
            updated_by  TEXT,
            updated_at  TIMESTAMPTZ DEFAULT now()
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS mcp_tools (
            id          SERIAL PRIMARY KEY,
            name        TEXT NOT NULL,
            type        TEXT,
            provider    TEXT,
            scope       TEXT,
            status      TEXT NOT NULL DEFAULT 'available',
            auth        TEXT,
            created_at  TIMESTAMPTZ DEFAULT now()
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS agent_registry (
            callsign    TEXT PRIMARY KEY,
            name        TEXT NOT NULL,
            role        TEXT,
            model       TEXT,
            cost_tier   INTEGER NOT NULL DEFAULT 1,
            descr       TEXT,
            created_at  TIMESTAMPTZ DEFAULT now()
        )
    """)
    op.execute("ALTER TABLE public.users ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'active'")


def downgrade() -> None:
    pass
