"""Proof-of-run: assemble the skill's own artifacts into a bundle, then VERIFY the outcome
is corroborated. This is the answer to "convince me the skill was actually used" — not a
claim, but a reconciliation: skill stamped, agents recorded, every done ticket traced to a
merged PR with a real diff, agent cost reconciled against budget, and a deploy URL only if
real completed work backs it.
"""
from software_factory.runstate import RunState, JsonFileStore
from software_factory.agents import AgentRegistry
from software_factory.tickets import TicketStore
from software_factory.budget import Usage
from software_factory.evidence import build_evidence, verify_evidence


def real_run(tmp_path):
    """A run that genuinely used the skill: stamped, one agent did real work, one ticket done."""
    state = RunState.load("run-1", JsonFileStore(str(tmp_path)))
    state.skill = "software-factory"
    state.skill_version = "0.0.1"
    state.description = "guestbook web app"
    state.deploy_target = "railway"
    state.phase = "done"
    state.deploy_url = "https://guestbook.up.railway.app"
    state.spent_usd = 0.42
    state.save()

    reg = AgentRegistry(str(tmp_path / "agents.db"), clock=lambda: 1)
    reg.spawn("a1", "run-1", 1, "build", "claude-opus-4-8")
    reg.record("a1", outcome="real_diff", usage=Usage("claude-opus-4-8", output_tokens=4000),
               cost_usd=0.42, pr=7, diff_lines=120)

    tickets = TicketStore(str(tmp_path / "tickets.db"))
    tid = tickets.create_ticket("guestbook", acceptance="submit->see", dod="green", wave=1)
    tickets.mark_done(tid, pr=7, diff_lines=120)
    return state, reg, tickets


def test_build_evidence_captures_skill_marker_agents_and_tickets(tmp_path):
    state, reg, tickets = real_run(tmp_path)
    b = build_evidence(state, reg, tickets)
    assert b["skill"] == "software-factory"
    assert b["agents"]["counts"]["spawned"] == 1
    assert b["agents"]["total_cost_usd"] == 0.42
    assert b["done_tickets"][0]["pr"] == 7
    assert b["deploy_url"] == "https://guestbook.up.railway.app"


def test_verify_passes_for_a_genuinely_corroborated_run(tmp_path):
    state, reg, tickets = real_run(tmp_path)
    ok, reasons = verify_evidence(build_evidence(state, reg, tickets))
    assert ok is True, reasons
    assert reasons == []


def test_verify_flags_a_run_not_stamped_with_the_skill():
    bundle = {"skill": None, "deploy_url": None, "spent_usd": 0.0,
              "agents": {"counts": {"spawned": 0}, "total_cost_usd": 0.0}, "done_tickets": []}
    ok, reasons = verify_evidence(bundle)
    assert ok is False
    assert any("skill" in r.lower() for r in reasons)


def test_verify_flags_a_deploy_url_with_no_agents_as_fabrication():
    # The worst case: a URL appears, but nothing in the record produced it.
    bundle = {"skill": "software-factory", "deploy_url": "https://x.up.railway.app",
              "spent_usd": 0.0, "agents": {"counts": {"spawned": 0}, "total_cost_usd": 0.0},
              "done_tickets": []}
    ok, reasons = verify_evidence(bundle)
    assert ok is False
    assert any("agent" in r.lower() for r in reasons)
    assert any("fabricat" in r.lower() or "no completed" in r.lower() for r in reasons)


def test_verify_flags_a_hollow_done_ticket():
    bundle = {"skill": "software-factory", "deploy_url": None, "spent_usd": 0.42,
              "agents": {"counts": {"spawned": 1}, "total_cost_usd": 0.42},
              "done_tickets": [{"id": 1, "pr": None, "diff_lines": 0, "title": "t"}]}
    ok, reasons = verify_evidence(bundle)
    assert ok is False
    assert any("ticket 1" in r for r in reasons)


def test_verify_flags_cost_exceeding_budget_spend():
    bundle = {"skill": "software-factory", "deploy_url": None, "spent_usd": 0.10,
              "agents": {"counts": {"spawned": 1}, "total_cost_usd": 5.00},
              "done_tickets": []}
    ok, reasons = verify_evidence(bundle)
    assert ok is False
    assert any("exceed" in r.lower() for r in reasons)
