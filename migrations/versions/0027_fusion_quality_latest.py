"""Fusion research: OpenRouter Model Fusion "Quality" set with latest aliases + judge (SOF-185)

Revision ID: 0027_fusion_quality_latest
Revises: 0026_remove_openrouter_tool
Create Date: 2026-07-15

Operator directive (2026-07-15): the Stage-1 / concierge Fusion research council uses the
OpenRouter Model Fusion **Quality** panel with **latest aliases** (so it tracks model releases
automatically instead of pinning dated ids):
  - panel (analysis_models): Claude Opus Latest + OpenAI GPT Latest + Google Gemini Pro Latest
  - judge / aggregator (the fusion plugin's `model` field, SOF-185): Claude Opus Latest

The model set stays DB-editable via the OS Tools tab (SOF-81) — this migration only moves the
SEEDED baseline off the SOF-79 set (`google/gemini-2.5-flash` / `moonshotai/kimi-k2.6` /
`deepseek/deepseek-chat-v3-0324`, no judge) onto the Quality-latest set so both envs pick it up on
deploy; an operator can still edit it afterward. `judge_model` is a NEW config key consumed by
research.py's `_fusion_plugin()` (optional — unset ⇒ the plugin's own default judge).

The `~`-prefixed slugs are OpenRouter's latest-alias form; verified accepted (HTTP 200, complete
JSON, finish_reason="stop") via a live probe 2026-07-15 — `~anthropic/claude-opus-latest` resolved
to `anthropic/claude-opus-4.8` (the current latest).

REHEARSAL PROTOCOL:
  1. alembic upgrade 0027_fusion_quality_latest (on a test DB stamped at 0026_remove_openrouter_tool)
  2. Assert: SELECT config FROM tools WHERE name='fusion' has analysis_models = the three latest
     aliases and judge_model = '~anthropic/claude-opus-latest'; `kind`/`attached_to` unchanged.
  3. Deploy to the target env only after rehearsal passes.
"""
import json

from alembic import op

revision = "0027_fusion_quality_latest"
down_revision = "0026_remove_openrouter_tool"
branch_labels = None
depends_on = None

_QUALITY_LATEST = {
    "kind": "api",
    "analysis_models": [
        "~anthropic/claude-opus-latest",
        "~openai/gpt-latest",
        "~google/gemini-pro-latest",
    ],
    "judge_model": "~anthropic/claude-opus-latest",
}

# The SOF-79/SOF-81 seed (0013) — restored on downgrade. No judge_model (plugin default judge).
_PRIOR_SEED = {
    "kind": "api",
    "analysis_models": ["google/gemini-2.5-flash", "moonshotai/kimi-k2.6",
                        "deepseek/deepseek-chat-v3-0324"],
}


def _set_fusion_config(config: dict) -> None:
    op.get_bind().exec_driver_sql(
        "UPDATE tools SET config = %s::jsonb, updated_at = now() WHERE name = 'fusion'",
        (json.dumps(config),),
    )


def upgrade() -> None:
    _set_fusion_config(_QUALITY_LATEST)


def downgrade() -> None:
    _set_fusion_config(_PRIOR_SEED)
