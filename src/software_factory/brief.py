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
    "scale",
    "success_metrics",
    "constraints",
    "stakeholders",
    "existing_assets",
    "risks",
    "definition_of_done",
]

# Human labels for each section (UI + prompt headings).
SECTION_LABELS: dict[str, str] = {
    "goals": "Context & Goals",
    "scale": "Scale & Usage",
    "success_metrics": "Success Metrics",
    "constraints": "Constraints",
    "stakeholders": "Stakeholders",
    "existing_assets": "Existing Assets",
    "risks": "Risks & Unknowns",
    "definition_of_done": "Definition of Done",
}

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


def compose_description(goal: str, scope=None) -> str:
    """The CANONICAL project description = goal prose + an appended scope-of-work line.

    Single source of truth for the Option C onboarding format (the frontend used to do this as
    composeDescription; it now lives here so the form and the concierge agent produce identical
    strings). Scope is a list of work-area labels (e.g. ["Quoting / RFQ", "Pricing & approvals"]).
    Empty scope → just the goal; empty goal + scope → just the scope line.
    """
    goal = (goal or "").strip()
    items = [s.strip() for s in (scope or []) if s and s.strip()]
    if not items:
        return goal
    line = "Scope of work: " + ", ".join(items) + "."
    return f"{goal}\n\n{line}" if goal else line


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
