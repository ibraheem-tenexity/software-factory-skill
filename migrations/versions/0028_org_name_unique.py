"""Unique index on active org name — SOF-196 PR B (defense-in-depth). GATED.

Revision ID: 0028_org_name_unique
Revises: 0027_fusion_quality_latest
Create Date: 2026-07-20

⚠️  DO NOT PROMOTE TO PROD until the operator-gated SOF-196 data-cleanup has removed the
existing duplicate org. A UNIQUE index cannot be built while two rows share the same
`lower(btrim(name))` — the CREATE fails, and (the SOF-47 pgvector lesson) a failed migration
crash-loops the deploy. Staging is dup-free, so it applies cleanly there; prod must be
de-duped first. Sequencing: PR A (#376, app-level guards) → prod … operator cleans the prod
dup … THIS migration → prod.

This is the durable backstop for PR A's per-path find-or-create / reject guards: even a future
code regression that bypasses those guards cannot re-create a duplicate active org, because the
DB rejects the second row. Normalization (`lower(btrim(name))`) matches
`repositories/users.py::org_by_name` so the guard and the constraint agree on what "same name"
means.

NOT auto-deduping existing rows here on purpose — which of two same-named orgs to keep (and which
members to preserve) is a human decision with data-loss risk, kept operator-gated (the SOF-196
data-cleanup step). `organizations` has no soft-delete (delete_org hard-deletes the row), so
"active org" == "row present", and a plain functional unique index is the whole guard.
"""
from alembic import op

revision = "0028_org_name_unique"
down_revision = "0027_fusion_quality_latest"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # IF NOT EXISTS makes re-runs idempotent, but does NOT weaken the guard: if the index is absent
    # while duplicates exist, the CREATE still fails (as intended — that's the prod gate).
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_organizations_name_ci "
        "ON organizations (lower(btrim(name)))")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_organizations_name_ci")
