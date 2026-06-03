"""Dry-run integration: prove the orchestrator's deterministic SPINE composes into a run
that reaches DONE — and that the "no hollow done" guards block a fake one. No money, no
network; provider CLIs / agent / Playwright are faked. The live version is test_guestbook_slice.py.

This mirrors the exact call sequence SKILL.md tells the orchestrator to make, so it catches
spine regressions (a gate wired wrong, budget not tracked, resume broken) offline.
"""
from software_factory.budget import Budget, Usage, BudgetExceeded
from software_factory.runstate import RunState, JsonFileStore
from software_factory.tickets import TicketStore, HollowWorkError
from software_factory.repo import GitHub, RunResult
from software_factory.gate import happy_flow_passed, bugs_from
from software_factory import deploy as deploy_mod


def gh_runner(pr_url="https://github.com/acme/guestbook/pull/1", checks_rc=0):
    def run(args):
        if args[:2] == ["repo", "create"]:
            return RunResult("https://github.com/acme/guestbook\n", 0)
        if args[:2] == ["pr", "create"]:
            return RunResult(pr_url + "\n", 0)
        if args[:2] == ["pr", "checks"]:
            return RunResult("", checks_rc)
        return RunResult("", 0)
    return run


def deploy_runner(url):
    return lambda args: deploy_mod.RunResult(url + "\n", 0)


def test_happy_slice_reaches_done_under_budget(tmp_path):
    store = JsonFileStore(str(tmp_path))
    state = RunState.load("run-dry", store)
    budget = Budget(100.0)
    tickets = TicketStore(str(tmp_path / "tickets.db"))
    gh = GitHub(run=gh_runner())

    # provision
    state.repo_url = gh.create_repo("guestbook")
    budget.charge(Usage("claude-opus-4-8", input_tokens=2000, output_tokens=1000))
    state.phase = "tickets"; state.save()

    # tickets
    tid = tickets.create_ticket(
        "Guestbook happy flow", acceptance="submit name -> see it in list",
        dod="happy flow green in browser", wave=1,
    )
    state.phase = "build"; state.save()

    # build — the agent produced a real diff (120 lines) and a PR
    tickets.claim(tid, agent="build-agent-1")
    budget.charge(Usage("claude-opus-4-8", input_tokens=8000, output_tokens=4000))
    pr = gh.open_pr(branch="feat/guestbook", title="guestbook", body="impl")
    assert gh.merge_if_green(pr, diff_lines=120) is True
    tickets.mark_done(tid, pr=pr, diff_lines=120)
    assert tickets.open_tickets(wave=1) == []
    state.phase = "deploy"; state.save()

    # deploy + prove live
    url = deploy_mod.deploy("vercel", "web", run=deploy_runner("https://guestbook.vercel.app"))
    assert deploy_mod.healthy(url, get=lambda u: 200, sleep=lambda s: None) is True
    state.deploy_url = url
    state.phase = "test"; state.save()

    # test gate — happy flow green => DONE
    result = {"journey": "guestbook", "steps": [
        {"name": "load page", "ok": True},
        {"name": "submit name", "ok": True},
        {"name": "see name in list", "ok": True},
    ]}
    assert happy_flow_passed(result) is True
    state.phase = "done"; state.spent_usd = budget.spent(); state.save()

    # run is resumable: a fresh load sees DONE with real recorded spend
    resumed = RunState.load("run-dry", JsonFileStore(str(tmp_path)))
    assert resumed.phase == "done"
    assert resumed.deploy_url == "https://guestbook.vercel.app"
    assert 0 < resumed.spent_usd < 100


def test_empty_diff_build_cannot_reach_done(tmp_path):
    """A no-op build turn must not pass the build gate, at either guard."""
    tickets = TicketStore(str(tmp_path / "t.db"))
    gh = GitHub(run=gh_runner(checks_rc=0))
    tid = tickets.create_ticket("t", acceptance="a", dod="d", wave=1)
    pr = gh.open_pr(branch="feat", title="t", body="b")

    assert gh.merge_if_green(pr, diff_lines=0) is False   # VCS guard
    try:
        tickets.mark_done(tid, pr=pr, diff_lines=0)        # ticket guard
        assert False, "should have refused hollow done"
    except HollowWorkError:
        pass
    assert tickets.open_tickets(wave=1)  # still open -> orchestrator retries/escalates


def test_red_browser_run_is_not_done_and_yields_bugs(tmp_path):
    result = {"journey": "guestbook", "steps": [
        {"name": "load page", "ok": True},
        {"name": "submit name", "ok": True},
        {"name": "see name in list", "ok": False, "error": "500 from /api/entries"},
    ]}
    assert happy_flow_passed(result) is False
    bugs = bugs_from(result)
    assert len(bugs) == 1 and "500" in bugs[0]["error"]


def test_budget_cutoff_stops_the_run(tmp_path):
    budget = Budget(100.0, spent_usd=99.5)
    raised = False
    try:
        # a normal Opus turn pushes past $100
        budget.charge(Usage("claude-opus-4-8", input_tokens=10000, output_tokens=8000))
    except BudgetExceeded as e:
        raised = True
        assert e.spent >= 100.0
    assert raised, "run must stop at the $100 cutoff"
