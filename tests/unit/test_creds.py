"""Provision-time credential checks: a bad or missing cred must HARD-BLOCK early, before any
build work — not blow up at deploy. Each check shells a lightweight verification (injected
runner) and reports ok + a human reason. `check_all` returns only the failures (the blocks).

Scar this defends: last run, env wasn't loaded and we discovered it mid-run. Verify up front.
"""
from software_factory.creds import check_railway, check_gh, check_all
from software_factory.deploy import RunResult


def runner(rc=0):
    return lambda args: RunResult(stdout="", returncode=rc)


def test_railway_ok_when_token_present_and_whoami_succeeds():
    c = check_railway(env={"RAILWAY_TOKEN": "rwt_x"}, run=runner(rc=0))
    assert c.ok is True


def test_railway_blocks_when_no_token_in_env():
    c = check_railway(env={}, run=runner(rc=0))
    assert c.ok is False
    assert "RAILWAY_TOKEN" in c.detail


def test_railway_blocks_when_token_is_rejected():
    c = check_railway(env={"RAILWAY_TOKEN": "bad"}, run=runner(rc=1))
    assert c.ok is False
    assert "reject" in c.detail.lower() or "invalid" in c.detail.lower()


def test_railway_accepts_account_token_var_too():
    c = check_railway(env={"RAILWAY_API_TOKEN": "acct"}, run=runner(rc=0))
    assert c.ok is True


def test_gh_ok_when_authed():
    assert check_gh(run=runner(rc=0)).ok is True


def test_gh_blocks_when_not_authed():
    c = check_gh(run=runner(rc=1))
    assert c.ok is False


def test_check_all_returns_only_failures_for_the_target():
    # gh authed, railway token missing -> exactly one block (railway)
    blocks = check_all("railway", env={}, run=runner(rc=0))
    names = [b.name for b in blocks]
    assert names == ["railway"]


def test_check_all_clean_when_everything_present():
    blocks = check_all("railway", env={"RAILWAY_TOKEN": "rwt_x"}, run=runner(rc=0))
    assert blocks == []
