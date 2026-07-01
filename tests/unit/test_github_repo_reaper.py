"""Tests for github_repo_reaper — the GitHub repo cleanup service analogous to the deploy-DB reaper.

SAFETY CONTRACT (each test explicitly validates one guard):
  1. Pattern guard: only <name>-[0-9a-f]{8,16} repos are in scope.
  2. DB-match guard: hex-suffix repos with no project in the DB are LOG-ONLY, never deleted.
  3. Policy guard: archived | stopped-without-deploy → reap; everything else → keep.
  4. Arm guard: SF_GITHUB_REPO_REAPER=on required; off → dry-run.
"""
import json
import pytest

from software_factory import github_repo_reaper as _ghr
from software_factory.github_repo_reaper import (
    ReapRecord, RunResult, FACTORY_REPO_SUFFIX_RE,
    github_reaper_mode, _reap_reason, list_org_repos, delete_repo, reap,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _runner(responses):
    """Fake injectable runner — each call pops the next (stdout, returncode, stderr) triple."""
    seq = iter(responses)
    calls = []

    def run(args):
        calls.append(args)
        r = next(seq)
        if isinstance(r, RunResult):
            return r
        stdout, rc, *rest = r
        return RunResult(stdout=stdout, returncode=rc, stderr=rest[0] if rest else "")
    run.calls = calls
    return run


def _rec(**kw):
    base = dict(project_id="project-abcd1234", repo_full_name="org/my-app-abcd1234",
                archived=False, phase="", has_verified_deploy=False)
    base.update(kw)
    return ReapRecord(**base)


# ---------------------------------------------------------------------------
# Suffix pattern
# ---------------------------------------------------------------------------

def test_factory_repo_suffix_re_matches_8_hex():
    assert FACTORY_REPO_SUFFIX_RE.search("my-app-4849c0d8")
    assert FACTORY_REPO_SUFFIX_RE.search("task-tracker-order-entry-4849c0d8")

def test_factory_repo_suffix_re_matches_16_hex():
    assert FACTORY_REPO_SUFFIX_RE.search("my-app-4849c0d8d7a6b3c1")

def test_factory_repo_suffix_re_rejects_non_hex():
    assert not FACTORY_REPO_SUFFIX_RE.search("my-app-hello")
    assert not FACTORY_REPO_SUFFIX_RE.search("my-app")
    assert not FACTORY_REPO_SUFFIX_RE.search("my-app-12345678z")  # z is not hex

def test_factory_repo_suffix_re_rejects_suffix_not_at_end():
    assert not FACTORY_REPO_SUFFIX_RE.search("my-app-4849c0d8-extra")


# ---------------------------------------------------------------------------
# Mode gate
# ---------------------------------------------------------------------------

def test_github_reaper_mode_defaults_off(monkeypatch):
    monkeypatch.delenv("SF_GITHUB_REPO_REAPER", raising=False)
    assert github_reaper_mode() == "off"

def test_github_reaper_mode_on_when_set(monkeypatch):
    monkeypatch.setenv("SF_GITHUB_REPO_REAPER", "on")
    assert github_reaper_mode() == "on"

def test_github_reaper_mode_off_for_unknown_value(monkeypatch):
    monkeypatch.setenv("SF_GITHUB_REPO_REAPER", "yes")
    assert github_reaper_mode() == "off"


# ---------------------------------------------------------------------------
# Reap-reason policy (mirrors deploy_db persistent mode)
# ---------------------------------------------------------------------------

def test_reap_reason_archived_always_reaps():
    assert _reap_reason(_rec(archived=True)) == "archived"
    # Even with a live deploy — archived is archived.
    assert _reap_reason(_rec(archived=True, has_verified_deploy=True)) == "archived"

def test_reap_reason_stopped_without_deploy_reaps():
    assert _reap_reason(_rec(phase="stopped", has_verified_deploy=False)) == "stopped-without-deploy"

def test_reap_reason_stopped_with_deploy_keeps():
    assert _reap_reason(_rec(phase="stopped", has_verified_deploy=True)) is None

def test_reap_reason_done_always_keeps():
    # No auto-reap on done — aligns with deploy-DB persistent policy.
    assert _reap_reason(_rec(phase="done", has_verified_deploy=False)) is None
    assert _reap_reason(_rec(phase="done", has_verified_deploy=True)) is None

def test_reap_reason_active_phase_keeps():
    for phase in ("stage1", "stage2", "stage3", "provision", ""):
        assert _reap_reason(_rec(phase=phase)) is None


def test_reap_reason_owner_shared_keeps_even_when_archived():
    # SOF-3: an owner-shared repo must survive archival — the reaper's #1 guard, checked
    # before the archived check that would otherwise reap it unconditionally.
    assert _reap_reason(_rec(archived=True, owner_repo_shared=True)) is None

def test_reap_reason_owner_shared_keeps_even_when_stopped_without_deploy():
    assert _reap_reason(_rec(phase="stopped", has_verified_deploy=False, owner_repo_shared=True)) is None

def test_reap_reason_not_owner_shared_still_reaps_archived():
    # Guard against a vacuous test: without the flag, the same record still reaps as before.
    assert _reap_reason(_rec(archived=True, owner_repo_shared=False)) == "archived"


# ---------------------------------------------------------------------------
# list_org_repos
# ---------------------------------------------------------------------------

def test_list_org_repos_returns_parsed_list():
    repos = [{"name": "my-app-abcd1234", "isArchived": False},
             {"name": "tenexity-order-entry-ccc5a597", "isArchived": False}]
    run = _runner([(json.dumps(repos), 0)])
    result = list_org_repos("ibraheem-tenexity", run=run)
    assert result == repos
    assert run.calls[0] == ["repo", "list", "ibraheem-tenexity",
                             "--json", "name,isArchived", "--limit", "200"]

def test_list_org_repos_returns_empty_on_cli_error():
    run = _runner([("", 1)])
    assert list_org_repos("org", run=run) == []

def test_list_org_repos_returns_empty_on_empty_output():
    run = _runner([("", 0)])
    assert list_org_repos("org", run=run) == []


# ---------------------------------------------------------------------------
# delete_repo
# ---------------------------------------------------------------------------

def test_delete_repo_success():
    run = _runner([("Deleted repository ibraheem-tenexity/my-app-abcd1234", 0)])
    result = delete_repo("ibraheem-tenexity/my-app-abcd1234", run=run)
    assert result["ok"] and result["deleted"] and not result["already_gone"]
    assert run.calls[0] == ["repo", "delete", "ibraheem-tenexity/my-app-abcd1234", "--yes"]

def test_delete_repo_already_gone_stdout():
    run = _runner([("Could not resolve to a Repository", 1)])
    result = delete_repo("org/gone-repo-abcd1234", run=run)
    assert result["ok"] and result["already_gone"] and not result["deleted"]

def test_delete_repo_already_gone_stderr():
    run = _runner([RunResult(stdout="", returncode=1,
                             stderr="GraphQL: Could not resolve to a Repository")])
    result = delete_repo("org/gone-repo-abcd1234", run=run)
    assert result["ok"] and result["already_gone"]

def test_delete_repo_real_failure():
    run = _runner([("Unauthorized", 1)])
    result = delete_repo("org/repo-abcd1234", run=run)
    assert not result["ok"] and not result["deleted"] and not result["already_gone"]

def test_delete_repo_raises_on_invalid_name():
    with pytest.raises(ValueError):
        delete_repo("", run=_runner([]))
    with pytest.raises(ValueError):
        delete_repo("no-slash-here", run=_runner([]))


# ---------------------------------------------------------------------------
# reap() — policy gate + sweep
# ---------------------------------------------------------------------------

def test_reap_disarmed_is_dry_run_and_deletes_nothing(monkeypatch):
    monkeypatch.delenv("SF_GITHUB_REPO_REAPER", raising=False)
    run = _runner([])
    records = [
        _rec(project_id="project-abcd1234", repo_full_name="org/my-app-abcd1234", archived=True),
        _rec(project_id="project-bbbb5678", repo_full_name="org/other-bbbb5678",
             phase="done", has_verified_deploy=True),
    ]
    report = reap(records, run=run, log=lambda m: None)
    assert run.calls == []                              # no delete calls
    assert report["armed"] is False and report["mode"] == "off"
    assert {w["project_id"] for w in report["would_reap"]} == {"project-abcd1234"}
    assert {k["project_id"] for k in report["kept"]} == {"project-bbbb5678"}

def test_reap_armed_deletes_eligible_keeps_demo(monkeypatch):
    monkeypatch.setenv("SF_GITHUB_REPO_REAPER", "on")
    records = [
        _rec(project_id="project-aaaa0001", repo_full_name="org/app-aaaa0001", archived=True),
        _rec(project_id="project-bbbb0002", repo_full_name="org/app-bbbb0002",
             phase="stopped", has_verified_deploy=False),
        _rec(project_id="project-cccc0003", repo_full_name="org/app-cccc0003",
             phase="done", has_verified_deploy=True),   # KEEP — live demo
        _rec(project_id="project-dddd0004", repo_full_name="org/app-dddd0004",
             phase="stage3"),                           # KEEP — active
    ]
    run = _runner([
        ("Deleted", 0),   # archived → deleted
        ("Deleted", 0),   # stopped-without-deploy → deleted
    ])
    report = reap(records, run=run, log=lambda m: None)
    deleted_repos = [r["repo"] for r in report["reaped"]]
    assert sorted(deleted_repos) == sorted(["org/app-aaaa0001", "org/app-bbbb0002"])
    kept_repos = [k["repo"] for k in report["kept"]]
    assert sorted(kept_repos) == sorted(["org/app-cccc0003", "org/app-dddd0004"])
    assert report["would_reap"] == []

def test_reap_dry_run_override_forces_preview_even_when_armed(monkeypatch):
    monkeypatch.setenv("SF_GITHUB_REPO_REAPER", "on")
    run = _runner([])
    records = [_rec(archived=True)]
    report = reap(records, run=run, log=lambda m: None, dry_run=True)
    assert run.calls == []
    assert len(report["would_reap"]) == 1 and report["reaped"] == []

def test_reap_idempotent_when_repo_already_gone(monkeypatch):
    monkeypatch.setenv("SF_GITHUB_REPO_REAPER", "on")
    run = _runner([RunResult(stdout="", returncode=1, stderr="Could not resolve to a Repository")])
    records = [_rec(archived=True)]
    report = reap(records, run=run, log=lambda m: None)
    assert report["reaped"][0]["already_gone"] is True
    assert report["reaped"][0]["project_id"] == "project-abcd1234"
    assert report["failed"] == []

def test_reap_records_failure_without_raising(monkeypatch):
    monkeypatch.setenv("SF_GITHUB_REPO_REAPER", "on")
    run = _runner([("Unauthorized", 1)])
    records = [_rec(archived=True)]
    report = reap(records, run=run, log=lambda m: None)
    assert report["failed"][0]["project_id"] == "project-abcd1234"
    assert report["reaped"] == []


# ---------------------------------------------------------------------------
# #95/SOF-8: org_repo_from_url — the exact-match input, parsed from the CLEAN url Stage 3
# itself records via record-artifact("GitHub Repo", <url>, kind="repo").
# ---------------------------------------------------------------------------

def test_org_repo_from_url_parses_clean_github_url():
    assert _ghr.org_repo_from_url("https://github.com/acme/guestbook") == "acme/guestbook"


def test_org_repo_from_url_strips_trailing_slash_and_dot_git():
    assert _ghr.org_repo_from_url("https://github.com/acme/guestbook/") == "acme/guestbook"
    assert _ghr.org_repo_from_url("https://github.com/acme/guestbook.git") == "acme/guestbook"


def test_org_repo_from_url_rejects_non_github_urls():
    assert _ghr.org_repo_from_url("https://gitlab.com/acme/guestbook") is None
    assert _ghr.org_repo_from_url("https://github.com/acme/guestbook/pulls/3") is None


def test_org_repo_from_url_handles_none_and_blank():
    assert _ghr.org_repo_from_url(None) is None
    assert _ghr.org_repo_from_url("") is None
