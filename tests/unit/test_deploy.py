"""Deploy triggers a provider and then PROVES the surface is live with a health check.
`healthy` returns True only on positive evidence (a 2xx), never on a timeout — the same
"earn done with evidence" rule the happy-flow gate uses, one layer down.

Runner and HTTP getter are injected; no real CLI or network in tests.
"""
import pytest

from software_factory.deploy import deploy, healthy, RunResult


def runner_for(url):
    def run(args):
        return RunResult(stdout=url + "\n", returncode=0)
    return run


def test_deploy_vercel_returns_deployed_url():
    url = deploy("vercel", "web", run=runner_for("https://guestbook.vercel.app"))
    assert url == "https://guestbook.vercel.app"


def test_deploy_railway_runs_up_then_domain_and_returns_the_public_url():
    calls = []

    def run(args):
        calls.append(args)
        if args[:2] == ["railway", "domain"]:
            # `railway domain` prints the generated public domain
            return RunResult(stdout="https://api.up.railway.app\n", returncode=0)
        return RunResult(stdout="Indexed\nUploaded\nBuild started\n", returncode=0)

    url = deploy("railway", "api", run=run)
    assert url == "https://api.up.railway.app"
    assert calls[0][:2] == ["railway", "up"]      # deploy first
    assert ["railway", "domain"] in [c[:2] for c in calls]  # then get the URL


def test_railway_domain_url_parsed_even_without_scheme():
    def run(args):
        if args[:2] == ["railway", "domain"]:
            return RunResult(stdout="Your service is live at api.up.railway.app\n", returncode=0)
        return RunResult(stdout="", returncode=0)

    assert deploy("railway", "api", run=run) == "https://api.up.railway.app"


def test_unknown_target_is_rejected():
    with pytest.raises(ValueError):
        deploy("heroku", "web", run=runner_for("x"))


def test_healthy_true_on_2xx():
    assert healthy("http://x", get=lambda u: 200, sleep=lambda s: None) is True


def test_healthy_polls_until_ready():
    codes = iter([503, 502, 200])
    calls = {"sleeps": 0}
    ok = healthy(
        "http://x",
        timeout_s=30,
        interval_s=3,
        get=lambda u: next(codes),
        sleep=lambda s: calls.__setitem__("sleeps", calls["sleeps"] + 1),
    )
    assert ok is True
    assert calls["sleeps"] == 2  # slept between the three attempts, not after success


def test_healthy_false_on_timeout_never_assumes_up():
    ok = healthy("http://x", timeout_s=9, interval_s=3, get=lambda u: 500, sleep=lambda s: None)
    assert ok is False
