"""Org usage & billing rollup (PRD §2.3) — pure summary over the org's runs."""
from software_factory import billing


def test_summarize_rolls_up_org_spend_and_activity():
    org = {"plan": "Team", "monthly_budget_cap": 120.0}
    runs = [
        {"run_id": "r1", "name": "AP matching", "spent_usd": 26.10,
         "budget_stopped": False, "held": False, "deploy_url": ""},
        {"run_id": "r2", "name": "Quote-to-Epicor", "spent_usd": 4.20,
         "budget_stopped": False, "held": False, "deploy_url": "http://x"},   # shipped
        {"run_id": "r3", "name": "Returns portal", "spent_usd": 2.05,
         "budget_stopped": True, "held": False, "deploy_url": ""},            # stopped
    ]
    u = billing.summarize(org, runs)
    assert u["plan"] == "Team"
    assert u["monthly_budget_cap"] == 120.0
    assert u["spent"] == 32.35
    assert u["total_projects"] == 3
    assert u["active_projects"] == 1                       # only r1 is building now
    assert [p["name"] for p in u["by_project"]] == ["AP matching", "Quote-to-Epicor",
                                                     "Returns portal"]  # highest spend first
    assert u["by_project"][0]["spent_usd"] == 26.10


def test_summarize_handles_no_org_and_no_runs():
    u = billing.summarize(None, [])
    assert u["plan"] is None
    assert u["monthly_budget_cap"] is None
    assert u["spent"] == 0
    assert u["total_projects"] == 0
    assert u["active_projects"] == 0
    assert u["by_project"] == []


def test_summarize_name_falls_back_to_run_id():
    u = billing.summarize({}, [{"run_id": "run-abc", "name": "", "spent_usd": 1.0}])
    assert u["by_project"][0]["name"] == "run-abc"
