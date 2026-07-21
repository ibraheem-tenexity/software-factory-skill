"""Remove the dead 'openrouter' MCP tool row (SOF-158)

Revision ID: 0026_remove_openrouter_tool
Revises: 0025_recovery_actions
Create Date: 2026-07-15

The 'openrouter' row (seeded by 0013, {"type": "http", "url": "https://mcp.openrouter.ai/mcp",
"env_key": "OPENROUTER_API_KEY"}, attached_to STAGE-1/2/3/CONCIERGE) is a real MCP server entry —
`workspace_setup.mcp_config()` reads this table as the source of truth and composes it into every
stage's live .mcp.json. Verified genuinely unreferenced: no code anywhere calls `mcp__openrouter__*`
or hits `https://mcp.openrouter.ai` (grepped the whole repo); no stage SKILL.md instructs an agent
to use an "openrouter" tool (their "use OpenRouter" sections are LLM-access guidance for the APP
BEING BUILT, via the plain REST API, unrelated to this MCP server); the concierge doesn't compose
MCP config at all (chat_agent.py's ConciergeAgent gets its tools as plain Python objects from
concierge_tools.py, which calls research.py's OpenRouter Fusion REST API directly via httpx —
`https://openrouter.ai/api/v1/chat/completions`, a completely different endpoint from the MCP
server url this row configures). Net effect today: every stage agent's tool belt carries one
never-called MCP server. Removing the row (not just workspace_setup.py's hardcoded DB-unreachable
fallback dict) is what actually stops it landing in a real .mcp.json.

`fusion`/`exa` rows are untouched — `fusion` is the declarative-only Fusion model-list config
`research.py` reads (real, live consumer), `exa` really is composed as an MCP server for stage
agents (unlike openrouter, nothing suggests it's dead) and is out of this ticket's scope.
"""
import json

from alembic import op

revision = "0026_remove_openrouter_tool"
down_revision = "0025_recovery_actions"
branch_labels = None
depends_on = None

_OPEN_ROUTER_CONFIG = {"type": "http", "url": "https://mcp.openrouter.ai/mcp", "env_key": "OPENROUTER_API_KEY"}
_OPEN_ROUTER_ATTACHED_TO = ["STAGE-1", "STAGE-2", "STAGE-3", "CONCIERGE"]


def upgrade() -> None:
    op.execute("DELETE FROM tools WHERE name = 'openrouter'")


def downgrade() -> None:
    conn = op.get_bind()
    conn.exec_driver_sql(
        "INSERT INTO tools (name, config, attached_to) VALUES (%s, %s, %s) "
        "ON CONFLICT (name) DO NOTHING",
        ("openrouter", json.dumps(_OPEN_ROUTER_CONFIG), json.dumps(_OPEN_ROUTER_ATTACHED_TO)),
    )
