"""Tests for the running-build version helper (software_factory.version) and GET /api/version.

The endpoint exposes the deployed git SHA so a deploy can be verified against the expected
commit (TEN-151 / KNOWN_ISSUES #87). env/git are injected so these run offline.
"""
from software_factory.version import version_info

_SHA = "a1b2c3d4e5f60718293a4b5c6d7e8f9001122334"


def _no_git(_args):
    return None


def test_prefers_sf_git_sha():
    info = version_info(env={"SF_GIT_SHA": _SHA}, git=_no_git)
    assert info == {"sha": _SHA, "short": _SHA[:7], "dirty": False}


def test_falls_back_to_railway_commit_sha():
    info = version_info(env={"RAILWAY_GIT_COMMIT_SHA": _SHA}, git=_no_git)
    assert info["sha"] == _SHA
    assert info["short"] == _SHA[:7]
    assert info["dirty"] is False


def test_git_fallback_clean_tree():
    calls = []

    def git(args):
        calls.append(args)
        return _SHA if args[:1] == ["rev-parse"] else ""  # status --porcelain empty => clean

    info = version_info(env={}, git=git)
    assert info["sha"] == _SHA
    assert info["dirty"] is False
    assert ["rev-parse", "HEAD"] in calls and ["status", "--porcelain"] in calls


def test_git_fallback_dirty_tree():
    def git(args):
        return _SHA if args[:1] == ["rev-parse"] else " M console/foo.py"

    assert version_info(env={}, git=git)["dirty"] is True


def test_unknown_when_no_source():
    info = version_info(env={}, git=_no_git)
    assert info == {"sha": "unknown", "short": "unknown", "dirty": False}


def test_sf_git_dirty_env_overrides():
    info = version_info(env={"SF_GIT_SHA": _SHA, "SF_GIT_DIRTY": "1"}, git=_no_git)
    assert info["dirty"] is True


def test_baked_sha_never_probes_tree():
    # An env-baked SHA must not shell out to git status (the deployed container has no tree).
    def git(args):
        raise AssertionError(f"git should not be called when SHA is baked: {args}")

    info = version_info(env={"SF_GIT_SHA": _SHA}, git=git)
    assert info["sha"] == _SHA
