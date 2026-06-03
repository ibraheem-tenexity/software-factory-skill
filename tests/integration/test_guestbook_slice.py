"""Live smoke test of the factory's HANDS against real infra. Opt-in only.

This verifies the deterministic I/O layer works against real `gh`/providers — it is NOT the
full app build (that is driven by the skill/orchestrator, an LLM loop, not pytest). It
creates a throwaway private repo and deletes it.

Run explicitly:  SF_LIVE=1 make test-live
Skips silently unless SF_LIVE=1 and `gh` is authenticated.
"""
import os
import subprocess

import pytest

pytestmark = pytest.mark.live


def _gh_authed() -> bool:
    try:
        return subprocess.run(["gh", "auth", "status"], capture_output=True).returncode == 0
    except FileNotFoundError:
        return False


requires_live = pytest.mark.skipif(
    os.environ.get("SF_LIVE") != "1" or not _gh_authed(),
    reason="set SF_LIVE=1 and authenticate `gh` to run the live smoke test",
)


@requires_live
def test_create_repo_then_cleanup():
    from software_factory.repo import GitHub

    gh = GitHub()
    name = "sf-smoke-guestbook-DELETEME"
    try:
        url = gh.create_repo(name, private=True)
        assert "github.com" in url
        # confirm it really exists
        assert subprocess.run(["gh", "repo", "view", name], capture_output=True).returncode == 0
    finally:
        subprocess.run(["gh", "repo", "delete", name, "--yes"], capture_output=True)
