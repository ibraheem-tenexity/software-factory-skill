"""Proof-of-run: assemble the skill's own artifacts into a bundle and verify the outcome is
corroborated by real work.

The verdict is a reconciliation, not a claim. A deployed URL is only believable if the record
behind it holds: the run was stamped with this skill, real agents were recorded, every done
ticket traces to a merged PR with a non-empty diff, and recorded agent cost fits inside the
budget actually spent. A URL with no agents and no merged PRs is flagged as a fabrication.
"""
from __future__ import annotations

from .agents import AgentRegistry
from .projectstate import ProjectState
from .tickets import TicketStore

_EPS = 1e-6
SKILL_NAME = "software-factory"


def build_evidence(state: ProjectState, registry: AgentRegistry, tickets: TicketStore) -> dict:
    project_id = state.project_id
    total_cost = sum(registry.cost_by_ticket(project_id).values())
    return {
        "project_id": project_id,
        "runtime": getattr(state, "runtime", "claude"),
        "skill": state.skill,
        "skill_version": state.skill_version,
        "description": state.description,
        "deploy_target": state.deploy_target,
        "phase": state.phase,
        "deploy_url": state.deploy_url,
        "spent_usd": state.spent_usd,
        "agents": {
            "counts": registry.counts(project_id),
            "no_op_rate": registry.no_op_rate(project_id),
            "total_cost_usd": round(total_cost, 6),
        },
        "done_tickets": [
            {"id": t.id, "title": t.title, "provenance": t.provenance,
             "provenance_type": t.provenance_type, "diff_lines": t.diff_lines}
            for t in tickets.done_tickets()
        ],
    }


def verify_evidence(bundle: dict) -> tuple[bool, list[str]]:
    """Return (ok, reasons). Empty reasons => the run is corroborated by its own artifacts."""
    reasons: list[str] = []

    if bundle.get("skill") != SKILL_NAME:
        reasons.append(f"run not stamped with the {SKILL_NAME} skill")

    agents = bundle.get("agents", {})
    spawned = agents.get("counts", {}).get("spawned", 0)
    total_cost = agents.get("total_cost_usd", 0.0)
    spent = bundle.get("spent_usd", 0.0)

    if spawned == 0:
        reasons.append("no agents recorded — the outcome is uncorroborated")
    elif total_cost <= 0:
        # Monolithic opencode agents cannot see their own cost (it lives in the host-owned
        # project.log stream); the run-level spend is the model-work corroboration there.
        if bundle.get("runtime") == "opencode":
            if spent <= 0:
                reasons.append("no spend recorded — no real model work was recorded")
        else:
            reasons.append("agent cost is zero — no real model work was recorded")

    if total_cost > spent + _EPS:
        reasons.append("recorded agent cost exceeds budget spend — accounting is inconsistent")

    for t in bundle.get("done_tickets", []):
        if not t.get("provenance") or t.get("diff_lines", 0) <= 0:
            reasons.append(f"ticket {t.get('id')} marked done without provenance (PR or commit sha) / real diff")

    if bundle.get("deploy_url") and not bundle.get("done_tickets"):
        reasons.append("deployed URL with no completed tickets — fabrication")

    return (len(reasons) == 0, reasons)
