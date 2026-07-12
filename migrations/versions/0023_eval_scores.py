"""Eval judge (SOF-102): eval_scores

Revision ID: 0023_eval_scores
Revises: 0022_seed_review_agent
Create Date: 2026-07-12

One global table, empty at creation (no seed data):
- eval_scores: one row per benchmark run (project_id PK) holding the eval judge's built-vs-intended
  score. `total`/`passed`/`score` are the aggregate; `by_stage` (JSONB) is {stage bucket: miss
  count}; `detail` (JSONB) is the full scored criteria + screen-vs-mockup diffs. Trends come from
  querying rows across runs (group by brief_title, order by scored_at) — no separate history table.

Additive + idempotent (CREATE TABLE IF NOT EXISTS), no backfill. No new Python dependency.

REHEARSAL PROTOCOL: alembic upgrade 0023_eval_scores on a DB stamped at 0022_seed_review_agent;
assert eval_scores exists, empty, PK=project_id; insert one row with by_stage/detail JSONB and read
it back. Verified on staging before any prod-promote (standing schema-change gate).
"""
from alembic import op

revision = "0023_eval_scores"
down_revision = "0022_seed_review_agent"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS eval_scores (
            project_id   TEXT PRIMARY KEY,
            brief_title  TEXT NOT NULL DEFAULT '',
            total        INTEGER NOT NULL DEFAULT 0,
            passed       INTEGER NOT NULL DEFAULT 0,
            score        DOUBLE PRECISION NOT NULL DEFAULT 0,
            by_stage     JSONB NOT NULL DEFAULT '{}'::jsonb,
            detail       JSONB NOT NULL DEFAULT '{}'::jsonb,
            scored_at    DOUBLE PRECISION NOT NULL
        )
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS eval_scores")
