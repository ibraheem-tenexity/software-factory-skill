"""Structured project brief + interview vocabulary.

Brings the legacy software-factory's richer context model into the new system: instead of a
single lazy prompt, onboarding accumulates a structured brief (the 7 sections below) through a
conversational interview. The brief is durable run state (see RunState.brief) and is injected
into the Stage-1 PRD prompt via `brief_to_prompt_block` (the `briefToPromptBlock` analogue).

Determinism note: this module is pure vocabulary + string helpers — no model, no I/O — so it is
safe to import everywhere and trivially testable.
"""
from __future__ import annotations

# Ordered canonical sections (snake_case; legacy used camelCase TS). Order = display + prompt order.
BRIEF_SECTIONS: list[str] = [
    "goals",
    "success_metrics",
    "constraints",
    "stakeholders",
    "existing_assets",
    "risks",
    "definition_of_done",
]

# Human labels for each section (UI + prompt headings).
SECTION_LABELS: dict[str, str] = {
    "goals": "Goals",
    "success_metrics": "Success Metrics",
    "constraints": "Constraints",
    "stakeholders": "Stakeholders",
    "existing_assets": "Existing Assets",
    "risks": "Risks & Unknowns",
    "definition_of_done": "Definition of Done",
}

# The conversational interview: one topic per turn. Ported from the legacy intake script.
# Each topic maps onto one brief section and carries a rubric of points a complete answer covers.
INTERVIEW_TOPICS: list[dict] = [
    {
        "key": "client_context",
        "section": "goals",
        "label": "Client & project context",
        "primary_question": "Tell me about the project — who is it for, what does your business do, "
                            "and what are you trying to accomplish?",
        "rubric": [
            "what the business/client does (industry, business model)",
            "the core problem this project solves and the value to users",
            "the primary objective or metric to optimize",
        ],
    },
    {
        "key": "success_metrics",
        "section": "success_metrics",
        "label": "Success metrics",
        "primary_question": "How will we know this is a success? What concrete outcomes or numbers matter?",
        "rubric": [
            "at least one quantifiable target or threshold",
            "the current baseline (if any)",
            "how/where success is measured",
        ],
    },
    {
        "key": "constraints",
        "section": "constraints",
        "label": "Tech stack & constraints",
        "primary_question": "Any constraints I should respect — timeline, budget, required/avoided "
                            "tech, hosting, or compliance?",
        "rubric": [
            "timeline or deadline",
            "budget or spend ceiling",
            "required or off-limits technology / platforms",
            "regulatory, security, or performance requirements",
        ],
    },
    {
        "key": "stakeholders",
        "section": "stakeholders",
        "label": "Stakeholders & users",
        "primary_question": "Who are the decision-makers and the end users? Who signs off?",
        "rubric": [
            "primary decision-maker / sponsor",
            "the end users or affected parties",
            "the approval / sign-off chain",
        ],
    },
    {
        "key": "existing_assets",
        "section": "existing_assets",
        "label": "Existing assets",
        "primary_question": "What already exists I should build on — code, designs, brand assets, "
                            "integrations, docs? (Attach files if you have them.)",
        "rubric": [
            "existing codebases or repositories",
            "designs, brand assets, or wireframes",
            "third-party services / integrations already in use",
            "documentation or domain knowledge to preserve",
        ],
    },
    {
        "key": "risks",
        "section": "risks",
        "label": "Risks & unknowns",
        "primary_question": "What are the biggest risks or open questions — technical, business, "
                            "or dependencies?",
        "rubric": [
            "technical risks or open technical questions",
            "business or market risks",
            "dependency / third-party risks",
        ],
    },
    {
        "key": "definition_of_done",
        "section": "definition_of_done",
        "label": "Definition of done",
        "primary_question": "What does 'done' look like for the first version?",
        "rubric": [
            "functional completion criteria",
            "quality / testing bar",
            "deployment or go-live state",
            "who accepts / signs off",
        ],
    },
]

# Sections that must be covered before the concierge offers to proceed. Kept deliberately small so
# the interview never traps the user — everything else is nice-to-have and the user can force-proceed.
REQUIRED_SECTIONS: list[str] = ["goals", "success_metrics", "definition_of_done"]

# A section counts as "covered" once its text is beyond this trivial length.
_MIN_COVERED_CHARS = 24


def coverage(brief: dict) -> dict[str, bool]:
    """Per-section covered flag: non-empty and beyond a trivial length threshold."""
    out: dict[str, bool] = {}
    for s in BRIEF_SECTIONS:
        val = (brief.get(s) or "").strip()
        out[s] = len(val) >= _MIN_COVERED_CHARS
    return out


def enough(brief: dict) -> tuple[bool, list[str]]:
    """(ready_to_proceed, missing_required_sections).

    Ready once every REQUIRED_SECTIONS is covered. `missing` lists the still-uncovered required
    sections so the concierge knows what to ask next.
    """
    cov = coverage(brief)
    missing = [s for s in REQUIRED_SECTIONS if not cov.get(s)]
    return (not missing, missing)


def brief_to_prompt_block(brief: dict) -> str:
    """Render the accumulated brief as a Markdown block for injection into the Stage-1 prompt.

    Returns "" when the brief is entirely empty so callers can skip injection cleanly.
    """
    filled = [(s, (brief.get(s) or "").strip()) for s in BRIEF_SECTIONS]
    filled = [(s, v) for s, v in filled if v]
    if not filled:
        return ""
    lines = ["PROJECT BRIEF", "---"]
    for section, value in filled:
        lines.append(f"## {SECTION_LABELS[section]}")
        lines.append(value)
        lines.append("")
    lines.append("---")
    return "\n".join(lines).strip() + "\n"
