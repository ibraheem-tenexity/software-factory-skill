"""Thin `gh` wrappers. The wrappers themselves are dumb; the one rule with teeth is
merge-on-green: never merge red checks, and never merge an empty diff (the second "no
hollow done" guard, at the VCS layer this time).

Tests inject a fake runner so no live `gh`/network is touched.
"""
from software_factory.repo import GitHub, RunResult


class FakeRunner:
    """Maps a command (matched by its leading args) to a canned RunResult."""

    def __init__(self, responses):
        self._responses = responses
        self.calls = []

    def __call__(self, args):
        self.calls.append(args)
        for prefix, result in self._responses.items():
            if args[: len(prefix)] == list(prefix):
                return result
        return RunResult(stdout="", returncode=0)

    def ran(self, *prefix):
        return any(c[: len(prefix)] == list(prefix) for c in self.calls)


def test_create_repo_returns_clone_url():
    runner = FakeRunner({("repo", "create"): RunResult("https://github.com/acme/guestbook\n", 0)})
    gh = GitHub(run=runner)
    assert gh.create_repo("guestbook") == "https://github.com/acme/guestbook"
    assert runner.ran("repo", "create")


def test_open_pr_parses_pr_number_from_url():
    runner = FakeRunner({("pr", "create"): RunResult("https://github.com/acme/guestbook/pull/42\n", 0)})
    gh = GitHub(run=runner)
    assert gh.open_pr(branch="feat", title="t", body="b") == 42


def test_checks_green_reflects_exit_code():
    green = GitHub(run=FakeRunner({("pr", "checks"): RunResult("", 0)}))
    red = GitHub(run=FakeRunner({("pr", "checks"): RunResult("", 8)}))
    assert green.checks_green(42) is True
    assert red.checks_green(42) is False


def test_merge_if_green_refuses_empty_diff_and_does_not_merge():
    runner = FakeRunner({("pr", "checks"): RunResult("", 0)})  # checks are green...
    gh = GitHub(run=runner)
    assert gh.merge_if_green(42, diff_lines=0) is False  # ...but the diff is empty
    assert not runner.ran("pr", "merge")


def test_merge_if_green_refuses_red_checks_and_does_not_merge():
    runner = FakeRunner({("pr", "checks"): RunResult("", 8)})
    gh = GitHub(run=runner)
    assert gh.merge_if_green(42, diff_lines=120) is False
    assert not runner.ran("pr", "merge")


def test_merge_if_green_merges_on_green_checks_and_a_real_diff():
    runner = FakeRunner({("pr", "checks"): RunResult("", 0)})
    gh = GitHub(run=runner)
    assert gh.merge_if_green(42, diff_lines=120) is True
    assert runner.ran("pr", "merge")
