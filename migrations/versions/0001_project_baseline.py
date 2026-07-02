"""project baseline — the entire flat project schema, from scratch.

Big-bang run->project rename (operator directive: drop ALL existing schema, no data, no migration,
no back-compat). This single revision REPLACES the pre-rename 0001-0004 chain. ``upgrade()`` wipes
the public schema and rebuilds every table directly from ``models.metadata`` — ``projectstate`` plus
the project_id-keyed canvas tables (phases/artifacts/blockers/gates/verifications/deployments/
tickets/agents/blob_uses) and the global directory tables (organizations/users/blobs). Irreversible.

Revision ID: 0001_project_baseline
Revises: (none — fresh baseline)

SOF-61: frozen to inline DDL (was ``models.metadata.create_all(op.get_bind())``) so a from-scratch
``alembic upgrade head`` no longer depends on the LIVE ``software_factory.models`` module — commit
c97c7eb dropped ``models.agent_prompts``/``agent_registry`` and broke exactly that dependency two
revisions later, at 0002. This DDL is the byte-for-byte schema ``models.metadata`` produced at
commit d9fa7b3e (the commit that added this migration) — every table below is IF NOT EXISTS /
idempotent, matching every other revision in this chain. `users` is intentionally still the OLD
shape here (email PRIMARY KEY, no uuid `id`) — 0003 drops and rebuilds it to the new shape, and a
from-scratch upgrade must replay that same transition, not skip straight to the new shape.
"""
from alembic import op

revision = "0001_project_baseline"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS projectstate (
            project_id  TEXT PRIMARY KEY,
            data        TEXT NOT NULL
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS phases (
            id          SERIAL PRIMARY KEY,
            project_id  TEXT NOT NULL,
            name        TEXT NOT NULL,
            status      TEXT NOT NULL DEFAULT 'active',
            stage       INTEGER,
            ts          FLOAT NOT NULL
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS artifacts (
            id          SERIAL PRIMARY KEY,
            project_id  TEXT NOT NULL,
            title       TEXT,
            path        TEXT,
            kind        TEXT,
            agent       TEXT,
            ts          FLOAT NOT NULL
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS blockers (
            id          SERIAL PRIMARY KEY,
            project_id  TEXT NOT NULL,
            what        TEXT,
            blocks      TEXT,
            cleared     INTEGER NOT NULL DEFAULT 0,
            ts          FLOAT NOT NULL
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS gates (
            project_id  TEXT NOT NULL,
            name        TEXT NOT NULL,
            status      TEXT NOT NULL,
            ts          FLOAT NOT NULL,
            PRIMARY KEY (project_id, name)
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS verifications (
            id          SERIAL PRIMARY KEY,
            project_id  TEXT NOT NULL,
            url         TEXT,
            passed      INTEGER NOT NULL,
            result      TEXT,
            ts          FLOAT NOT NULL
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS deployments (
            id            SERIAL PRIMARY KEY,
            project_id    TEXT NOT NULL,
            app           TEXT,
            service_name  TEXT,
            url           TEXT,
            status        TEXT NOT NULL DEFAULT 'deploying',
            verified      INTEGER NOT NULL DEFAULT 0,
            ts            FLOAT NOT NULL
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS tickets (
            id               SERIAL PRIMARY KEY,
            project_id       TEXT NOT NULL,
            title            TEXT NOT NULL,
            acceptance       TEXT NOT NULL,
            dod              TEXT NOT NULL,
            wave             INTEGER NOT NULL,
            status           TEXT NOT NULL DEFAULT 'open',
            agent            TEXT,
            provenance       TEXT,
            provenance_type  TEXT,
            diff_lines       INTEGER NOT NULL DEFAULT 0,
            app              TEXT,
            description      TEXT NOT NULL DEFAULT ''
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS agents (
            agent_id          TEXT NOT NULL,
            project_id        TEXT NOT NULL,
            ticket_id         INTEGER,
            role              TEXT NOT NULL,
            model             TEXT NOT NULL,
            phase             TEXT,
            status            TEXT NOT NULL DEFAULT 'running',
            outcome           TEXT,
            cost_usd          FLOAT NOT NULL DEFAULT 0,
            input_tokens      INTEGER NOT NULL DEFAULT 0,
            cached_tokens     INTEGER NOT NULL DEFAULT 0,
            output_tokens     INTEGER NOT NULL DEFAULT 0,
            reasoning_tokens  INTEGER NOT NULL DEFAULT 0,
            provenance        TEXT,
            provenance_type   TEXT,
            diff_lines        INTEGER NOT NULL DEFAULT 0,
            started_at        FLOAT NOT NULL,
            ended_at          FLOAT,
            PRIMARY KEY (agent_id, project_id)
        )
    """)

    # ---- global directory tables (one row-set, not per-project) ------------------------------
    op.execute("""
        CREATE TABLE IF NOT EXISTS organizations (
            id                  TEXT PRIMARY KEY,
            name                TEXT NOT NULL,
            industry            TEXT,
            sub_focus           TEXT,
            headcount           TEXT,
            revenue             TEXT,
            location            TEXT,
            website             TEXT,
            connected_systems   TEXT,
            plan                TEXT,
            monthly_budget_cap  FLOAT,
            created_at          TIMESTAMPTZ DEFAULT now(),
            created_by          TEXT
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS users (
            email             TEXT PRIMARY KEY,
            role              TEXT NOT NULL DEFAULT 'member',
            org_id            TEXT,
            designation       TEXT,
            role_description  TEXT,
            tenexity          INTEGER,
            created_at        TIMESTAMPTZ DEFAULT now(),
            created_by        TEXT
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS blobs (
            id            SERIAL PRIMARY KEY,
            scope         TEXT NOT NULL,
            scope_id      TEXT NOT NULL,
            kind          TEXT,
            name          TEXT,
            tag           TEXT,
            storage_key   TEXT NOT NULL,
            content_type  TEXT,
            size_bytes    INTEGER,
            sha256        TEXT,
            created_at    TIMESTAMPTZ DEFAULT now()
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS blob_uses (
            id          SERIAL PRIMARY KEY,
            blob_id     INTEGER NOT NULL,
            project_id  TEXT NOT NULL,
            created_at  TIMESTAMPTZ DEFAULT now()
        )
    """)


def downgrade() -> None:
    # Irreversible by design — the pre-rename schema is gone for good.
    pass
