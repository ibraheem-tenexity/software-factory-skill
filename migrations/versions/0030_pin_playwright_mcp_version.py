"""Pin the playwright MCP tools-row version, drop @latest (SOF-209, fast-follow to SOF-207)

Revision ID: 0030_pin_playwright_mcp_version
Revises: 0029_recipes_table
Create Date: 2026-07-21

`workspace_setup.mcp_config()` reads the `tools` table as the source of truth for every stage's
real `.mcp.json` (falls back to a hardcoded dict only if the table read itself fails — verified
directly against the live staging DB right now: the real `playwright` row's `config` is
`{"command": "npx", "args": ["-y", "@playwright/mcp@latest", ...]}`, exactly the un-pinned value
seeded by 0013). `@latest` floats (a future release could silently change stdio startup/protocol
under us, no code change) and isn't reliably cached, so every stage-launch may cold-hit the npm
registry (SOF-207's mcp_health fix makes a slow-starting server safe now, but doesn't stop the
registry hit itself).

Pin to `0.0.78` — the exact version SOF-207's Dockerfile change globally pre-installs (`npm install
-g ... @playwright/mcp@0.0.78 ...`), the same version SOF-207's own live verification (gyogcl1y's
K3 launch) just cleared the MCP gate with, i.e. known-good. `npx -y @playwright/mcp@0.0.78` then
resolves the pre-installed global copy instead of a registry round-trip.

0013 stays untouched (immutable history) — this is a forward data migration correcting the
already-seeded row, the standard pattern (mirrors 0026's tools-table UPDATE/DELETE style).
"""
import json
import logging

from alembic import op

revision = "0030_pin_playwright_mcp_version"
down_revision = "0029_recipes_table"
branch_labels = None
depends_on = None

logger = logging.getLogger(__name__)

_OLD_CONFIG = {"command": "npx", "args": ["-y", "@playwright/mcp@latest", "--headless", "--browser", "chromium"]}
_NEW_CONFIG = {"command": "npx", "args": ["-y", "@playwright/mcp@0.0.78", "--headless", "--browser", "chromium"]}


def upgrade() -> None:
    conn = op.get_bind()
    result = conn.exec_driver_sql(
        "UPDATE tools SET config = %s WHERE name = 'playwright'",
        (json.dumps(_NEW_CONFIG),),
    )
    # A zero-row UPDATE means the seeded 'playwright' row is missing on this DB (e.g. a fresh DB
    # that hasn't run 0013 yet, or an operator deleted it) — not this migration's job to fix that,
    # but silently doing nothing would leave the run un-pinned with no trace. Log, don't fail: a
    # missing tools row is a separate, real problem this migration can't solve by raising.
    if result.rowcount == 0:
        logger.warning(
            "0030_pin_playwright_mcp_version: UPDATE affected 0 rows — no 'playwright' row in "
            "`tools` on this DB (fresh DB not yet seeded by 0013, or the row was removed)")


def downgrade() -> None:
    conn = op.get_bind()
    result = conn.exec_driver_sql(
        "UPDATE tools SET config = %s WHERE name = 'playwright'",
        (json.dumps(_OLD_CONFIG),),
    )
    if result.rowcount == 0:
        logger.warning(
            "0030_pin_playwright_mcp_version downgrade: UPDATE affected 0 rows — no 'playwright' "
            "row in `tools` on this DB")
