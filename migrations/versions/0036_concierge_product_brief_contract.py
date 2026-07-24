"""Make the Concierge Product Brief contract authoritative (SOF-240).

Revision ID: 0036_concierge_product_brief_contract
Revises: 0035_directory_summary_error
Create Date: 2026-07-22

The live Concierge instructions come solely from ``system_agents.CONCIERGE.prompt``.  Append the
canonical Product Brief contract only when that row still contains the exact prompt seeded by
0032.  The explicit MD5 comparison is the identity check for that known 4,252-character seed; a
later operator edit is left untouched and reported in the migration log instead of being
overwritten.
"""
import logging

from alembic import op
from sqlalchemy import text

revision = "0036_concierge_product_brief_contract"
down_revision = "0035_directory_summary_error"
branch_labels = None
depends_on = None

logger = logging.getLogger("alembic.runtime.migration")

_SEEDED_PROMPT_MD5 = "b0686426cf6b59d7b7f46cecdcc423ce"

PRODUCT_BRIEF_CONTRACT = """
## Product Brief contract
Use your judgment—not a section count, checklist, completeness score, or readiness flag—to decide
when you understand the project well enough to draft its Product Brief.

Draft a detailed, readable brief from the onboarding conversation and processed source material.
It must communicate an unambiguous business problem, the intended users and their needs, the
desired outcome, and the first-release scope. Include constraints, assumptions, and unresolved
questions when they matter. Choose headings and depth that fit this project; never force the brief
into a fixed template or fixed number of parts.

Preserve important language the customer uses unless they ask you to rewrite it. Clearly
distinguish source-backed facts from unresolved questions—never turn an inference into a fact.

When the brief is ready, save it with **finalize_product_brief**, then call
**read_product_brief** and read the resulting brief back to the customer. Invite corrections and
revise the same canonical brief by calling **finalize_product_brief** again. Hand off only after
the customer has reviewed the brief and you both clearly agree it is ready; the finalized
`product_brief` artifact remains the only mechanical handoff prerequisite.
"""


def upgrade() -> None:
    result = op.get_bind().execute(
        text(
            "UPDATE system_agents "
            "SET prompt = prompt || :contract, "
            "    version = version + 1, "
            "    updated_at = now() "
            "WHERE callsign = 'CONCIERGE' "
            "  AND md5(prompt) = :seeded_prompt_md5"
        ),
        {
            "contract": PRODUCT_BRIEF_CONTRACT,
            "seeded_prompt_md5": _SEEDED_PROMPT_MD5,
        },
    )
    if result.rowcount == 0:
        logger.warning(
            "SOF-240 did not alter system_agents.CONCIERGE.prompt because it no longer matches "
            "the exact 0032 seed; preserve the operator edit and reconcile the Product Brief "
            "contract through the Agents screen"
        )


def downgrade() -> None:
    contract_length = len(PRODUCT_BRIEF_CONTRACT)
    op.get_bind().execute(
        text(
            "UPDATE system_agents "
            "SET prompt = LEFT(prompt, LENGTH(prompt) - :contract_length), "
            "    version = version + 1, "
            "    updated_at = now() "
            "WHERE callsign = 'CONCIERGE' "
            "  AND RIGHT(prompt, :contract_length) = :contract "
            "  AND md5(LEFT(prompt, LENGTH(prompt) - :contract_length)) = :seeded_prompt_md5"
        ),
        {
            "contract_length": contract_length,
            "contract": PRODUCT_BRIEF_CONTRACT,
            "seeded_prompt_md5": _SEEDED_PROMPT_MD5,
        },
    )
