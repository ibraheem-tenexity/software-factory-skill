"""Add artifacts.stage — the producing stage of each factory artifact (SOF-78)

Revision ID: 0033_artifact_stage
Revises: 0032_seed_concierge_prompt
Create Date: 2026-07-23

The Documents tab design (docs/design/orgproject.jsx) labels each produced-artifact tile with the
stage that produced it, but no backend field carried it — `agent`/`kind` are free text a stage's
own SKILL.md-driven CLI call chose, not a controlled "which stage produced this" (SOF-78, split
from SOF-70 Part B). Add a nullable `stage` INTEGER, stamped at `record_artifact()` time from the
run's current `ProjectState.stage` (which `_launch_stage` sets before each stage runs, so it IS the
producing stage). Nullable + additive: pre-existing rows, and any record path that can't resolve a
stage (draft-phase concierge output, a state-read hiccup), stay NULL — a pure capability add, no
behavior change for existing callers (mirrors the SOF-62 additive-column pattern).

REHEARSAL: `alembic upgrade 0033_artifact_stage` on a DB stamped at 0032 → assert `artifacts` has a
nullable `stage` column; re-running is a no-op (ADD COLUMN IF NOT EXISTS).
"""
from alembic import op

revision = "0033_artifact_stage"
down_revision = "0032_seed_concierge_prompt"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE artifacts ADD COLUMN IF NOT EXISTS stage INTEGER")


def downgrade() -> None:
    op.execute("ALTER TABLE artifacts DROP COLUMN IF EXISTS stage")
