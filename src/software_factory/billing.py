"""Org usage & billing rollup (PRD §2.3 "Usage & billing").

A pure summary over the runs that belong to an organization — kept here (not in `console`, which
knows nothing of orgs, nor in `users`, which knows nothing of runs) so the app layer can join the
two: gather the org's runs, hand them here with the org record, get back the dashboard payload.

"Spent" is the sum of each run's lifetime spend (the per-project figure the console already computes);
there is no reliable per-month boundary on run spend, so this is total-to-date, not month-windowed.
"""
from __future__ import annotations


def summarize(org: dict | None, runs: list[dict]) -> dict:
    """Roll the org's runs into the Usage & billing payload.

    `org` is the organization record (for `plan`/`monthly_budget_cap`), or None.
    `runs` are that org's runs (already owner-filtered to org members) as returned by
    `Console.list_projects`. A run is "active" (building now) when it is neither budget-stopped,
    held, nor already shipped (has a deploy_url)."""
    org = org or {}
    by_project = [
        {"project_id": r["project_id"],
         "name": r.get("name") or r["project_id"],
         "spent_usd": round(r.get("spent_usd") or 0.0, 2)}
        for r in runs
    ]
    by_project.sort(key=lambda p: p["spent_usd"], reverse=True)
    active = sum(1 for r in runs
                 if not r.get("budget_stopped") and not r.get("held") and not r.get("deploy_url"))
    return {
        "plan": org.get("plan"),
        "monthly_budget_cap": org.get("monthly_budget_cap"),
        "spent": round(sum(p["spent_usd"] for p in by_project), 2),
        "active_projects": active,
        "total_projects": len(runs),
        "by_project": by_project,
    }
