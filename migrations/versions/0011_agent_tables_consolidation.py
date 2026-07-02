"""Agent tables consolidation: agents→runtime_agents · new system_agents · drop the old pair

Revision ID: 0011_agent_tables
Revises: 0010_org_secrets
Create Date: 2026-07-01

The agent mess collapses to TWO tables:
  · `runtime_agents` (renamed from `agents`) — runtime telemetry of build-spawned sub-agents.
  · `system_agents` (new) — the OS-configurable agents (CONCIERGE + STAGE-1/2/3), each carrying
    its editable prompt AND the LLM it runs on (model_id). Merges the dropped `agent_registry`
    (identity) + `agent_prompts` (prompt). NOTHING is seeded from code — these 4 rows are created
    here, carrying over any existing operator edits.
Also drops `conversation.referenced_artifact` — one prompt can reference SEVERAL artifacts, so a
single FK column was wrong; references ride as blocks inside `json_blob`.

CARRY-OVER: prompt from old `agent_prompts` (CONCIERGE as-is; STAGE-n takes the `STAGE-n::claude`
variant — the per-runtime override key is collapsed, `::opencode` override text is dropped);
model_id from old `agent_registry.model`. Each carry-over is independently guarded on its source
table existing, so a fresh DB (create_all already made the new schema) just gets the 4 bare rows.

REHEARSAL PROTOCOL:
  1. alembic upgrade 0011_agent_tables  (on a test DB stamped at 0010_org_secrets)
  2. Assert: `runtime_agents` exists (with the old `agents` rows), `system_agents` has exactly the
     4 rows (prompts/models carried over where the old tables had them), `agent_prompts` and
     `agent_registry` are gone, and `conversation` has no `referenced_artifact` column.
  3. Deploy to prod only after rehearsal passes.
"""
from alembic import op

revision = "0011_agent_tables"
down_revision = "0010_org_secrets"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1) The runtime-telemetry table: agents → runtime_agents (indexes keep their old names —
    #    harmless; they are addressed by table, not name, everywhere in this codebase).
    op.execute("ALTER TABLE IF EXISTS agents RENAME TO runtime_agents")

    # 2) The OS-configurable system agents.
    op.execute("""
        CREATE TABLE IF NOT EXISTS system_agents (
            callsign    TEXT PRIMARY KEY,
            name        TEXT NOT NULL,
            prompt      TEXT NOT NULL DEFAULT '',
            model_id    TEXT,
            version     INTEGER NOT NULL DEFAULT 1,
            updated_by  TEXT,
            updated_at  TIMESTAMPTZ DEFAULT now()
        )
    """)

    # 3) The 4 rows (idempotent), then carry over prompt/model from the old tables where present.
    op.execute("""
        INSERT INTO system_agents (callsign, name) VALUES
            ('CONCIERGE', 'Factory Concierge'),
            ('STAGE-1', 'Stage 1 · Research'),
            ('STAGE-2', 'Stage 2 · Design'),
            ('STAGE-3', 'Stage 3 · Build')
        ON CONFLICT (callsign) DO NOTHING
    """)
    op.execute("""
        DO $$
        BEGIN
            IF to_regclass('public.agent_prompts') IS NOT NULL THEN
                UPDATE system_agents sa SET prompt = p.prompt
                FROM agent_prompts p
                WHERE p.callsign = CASE sa.callsign WHEN 'CONCIERGE' THEN 'CONCIERGE'
                                                    ELSE sa.callsign || '::claude' END
                  AND COALESCE(p.prompt, '') <> '' AND sa.prompt = '';
            END IF;
        END $$
    """)
    op.execute("""
        DO $$
        BEGIN
            IF to_regclass('public.agent_registry') IS NOT NULL THEN
                UPDATE system_agents sa SET model_id = r.model
                FROM agent_registry r
                WHERE r.callsign = sa.callsign
                  AND COALESCE(r.model, '') <> '' AND sa.model_id IS NULL;
            END IF;
        END $$
    """)

    # 4) Drop the merged-away tables.
    op.execute("DROP TABLE IF EXISTS agent_prompts")
    op.execute("DROP TABLE IF EXISTS agent_registry")

    # 5) One artifact-FK column was wrong (a turn may reference several artifacts — they ride as
    #    blocks in json_blob).
    op.execute("ALTER TABLE conversation DROP COLUMN IF EXISTS referenced_artifact")


def downgrade() -> None:
    # Best-effort reverse: structures come back, carried-over data does not round-trip.
    op.execute("ALTER TABLE conversation ADD COLUMN IF NOT EXISTS referenced_artifact INTEGER REFERENCES blobs (id)")
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
    op.execute("DROP TABLE IF EXISTS system_agents")
    op.execute("ALTER TABLE IF EXISTS runtime_agents RENAME TO agents")
