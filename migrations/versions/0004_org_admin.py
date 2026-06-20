"""org admin §2.3: knowledge-base doc metadata + reuse links + org billing fields

Revision ID: 0004_org_admin
Revises: 0003_drop_legacy_schema_per_run
Create Date: 2026-06-20

Adds what the Org Admin backend (PRD §2.3) needs on top of the flat schema:
  • blobs.name / blobs.tag           — display filename + category for the knowledge base
  • blob_uses (new)                  — one row per (org doc, project) → "used by N projects" count
  • organizations.plan / .monthly_budget_cap — Usage & billing plan + cap

Idempotent (ADD COLUMN IF NOT EXISTS / create_all checkfirst). Runs on deploy via
`alembic upgrade head`.
"""
from alembic import op

from software_factory import models

revision = "0004_org_admin"
down_revision = "0003_drop_legacy_schema_per_run"
branch_labels = None
depends_on = None

_BLOB_COLS = (("name", "text"), ("tag", "text"))
_ORG_COLS = (("plan", "text"), ("monthly_budget_cap", "double precision"))


def upgrade() -> None:
    for col, typ in _BLOB_COLS:
        op.execute(f"ALTER TABLE public.blobs ADD COLUMN IF NOT EXISTS {col} {typ}")
    for col, typ in _ORG_COLS:
        op.execute(f"ALTER TABLE public.organizations ADD COLUMN IF NOT EXISTS {col} {typ}")
    models.metadata.create_all(op.get_bind(), tables=[models.blob_uses], checkfirst=True)


def downgrade() -> None:
    models.metadata.drop_all(op.get_bind(), tables=[models.blob_uses])
    for col, _typ in _BLOB_COLS:
        op.execute(f"ALTER TABLE public.blobs DROP COLUMN IF EXISTS {col}")
    for col, _typ in _ORG_COLS:
        op.execute(f"ALTER TABLE public.organizations DROP COLUMN IF EXISTS {col}")
