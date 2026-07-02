"""Tools registry rebuild (SOF-81): mcp_tools (free-text display rows) -> tools (real config)

Revision ID: 0013_tools_registry
Revises: 0012_agent_tables
Create Date: 2026-07-02

`mcp_tools` was display-only — name/type/provider/scope/status/auth free-text rows with no
connection to what the factory actually runs. `tools` replaces it as the SOURCE OF TRUTH:
`config` is the literal shape workspace_setup.py composes into a stage's .mcp.json (or, for a
non-MCP tool, {"kind": "api", "env_key": ...}); `attached_to` names the system_agents callsigns /
pipeline nodes that actually use the tool today. `key_vault_id`/`key_last4` follow the org_secrets/
vault.py pattern exactly — plaintext keys are NEVER stored in this table.

Seed data is lifted VERBATIM from workspace_setup.py's mcp_config()/_PLAYWRIGHT/_RAILWAY/_EXA/
_OPEN_ROUTER/_MEMORY dicts as of this migration (behavior-preserving — diffed against the
hardcoded dicts in the PR). `attached_to` reflects real code paths as of merge time:
  - playwright/exa/openrouter/memory: every stage (mcp_config gives them unconditionally)
  - exa/openrouter: also CONCIERGE (concierge_tools.py's exa_search/fusion_search tools hit
    research.py's exa/OpenRouter Fusion APIs directly with the same env keys)
  - railway: STAGE-3 only (mcp_config's `if stage >= 3`)
  - github: STAGE-3 only (the build agent shells out to `gh`, reading GH_TOKEN/GITHUB_TOKEN —
    not MCP-shaped, so config is the {"kind": "api", ...} form)
memory has no env_key: SF_MEMORY_TOKEN is minted per-run by console.py, not an operator-attachable
static secret, so it deliberately has no vault-key affordance.

Also seeds `fusion` (operator directive 2026-07-02, on-ticket comment): the OpenRouter Fusion
research panel's model list, previously a hardcoded tuple in research.py — now DB-editable via
this row's `config.analysis_models` (OS Tools tab), with NO code-level default or fallback.
attached_to=["STAGE-1", "CONCIERGE"] — CONCIERGE is what's true today (concierge_tools.py's
fusion_search tool); STAGE-1 per operator sign-off on #293 (2026-07-02, SOF-73's research-phase
direction). fusion is {"kind": "api"} (no `command`/`type`) so it's declarative only — it never
enters the composed .mcp.json or tool_env_overrides regardless of attached_to.

REHEARSAL PROTOCOL:
  1. alembic upgrade 0013_tools_registry (on a test DB stamped at 0012_agent_tables)
  2. Assert: `mcp_tools` is gone, `tools` has exactly 7 rows (playwright, exa, openrouter, memory,
     railway, github, fusion) with the configs below and no key material set.
  3. Deploy to prod only after rehearsal passes.
"""
import json

from alembic import op

revision = "0013_tools_registry"
down_revision = "0012_agent_tables"
branch_labels = None
depends_on = None

_PLAYWRIGHT = {"command": "npx", "args": ["-y", "@playwright/mcp@latest", "--headless", "--browser", "chromium"]}
_RAILWAY = {"command": "railway", "args": ["mcp"], "env_key": "RAILWAY_TOKEN"}
_EXA = {"type": "http", "url": "https://mcp.exa.ai/mcp", "headers": {"x-api-key": "${EXA_API_KEY}"},
        "env_key": "EXA_API_KEY"}
_OPEN_ROUTER = {"type": "http", "url": "https://mcp.openrouter.ai/mcp", "env_key": "OPENROUTER_API_KEY"}
_MEMORY = {"type": "http", "url": "${SF_MEMORY_MCP_URL}",
           "headers": {"Authorization": "Bearer ${SF_MEMORY_TOKEN}"}}
_GITHUB = {"kind": "api", "env_key": "GH_TOKEN"}
# SOF-79's confirmed-working set (the original models 404'd on OpenRouter) — now the seed value,
# not a code default. Edit via the OS Tools tab from here on, not research.py.
_FUSION = {"kind": "api", "analysis_models": ["google/gemini-2.5-flash", "moonshotai/kimi-k2.6",
                                              "deepseek/deepseek-chat-v3-0324"]}

_SEED = (
    ("playwright", _PLAYWRIGHT, ["STAGE-1", "STAGE-2", "STAGE-3"]),
    ("exa", _EXA, ["STAGE-1", "STAGE-2", "STAGE-3", "CONCIERGE"]),
    ("openrouter", _OPEN_ROUTER, ["STAGE-1", "STAGE-2", "STAGE-3", "CONCIERGE"]),
    ("memory", _MEMORY, ["STAGE-1", "STAGE-2", "STAGE-3"]),
    ("railway", _RAILWAY, ["STAGE-3"]),
    ("github", _GITHUB, ["STAGE-3"]),
    ("fusion", _FUSION, ["STAGE-1", "CONCIERGE"]),
)


def upgrade() -> None:
    op.execute("DROP TABLE IF EXISTS mcp_tools")
    op.execute("""
        CREATE TABLE IF NOT EXISTS tools (
            name          TEXT PRIMARY KEY,
            config        JSONB NOT NULL,
            attached_to   JSONB NOT NULL DEFAULT '[]'::jsonb,
            key_vault_id  TEXT,
            key_last4     TEXT,
            updated_by    TEXT,
            updated_at    TIMESTAMPTZ DEFAULT now()
        )
    """)
    conn = op.get_bind()
    for name, config, attached_to in _SEED:
        conn.exec_driver_sql(
            "INSERT INTO tools (name, config, attached_to) VALUES (%s, %s, %s) "
            "ON CONFLICT (name) DO NOTHING",
            (name, json.dumps(config), json.dumps(attached_to)),
        )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS tools")
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
