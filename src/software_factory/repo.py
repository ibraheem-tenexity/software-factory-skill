"""Thin `gh` wrappers for the repo I/O the factory must not hallucinate.

The runner is injectable: subprocess to real `gh` in production, a fake in tests. The only
logic worth its salt lives in `merge_if_green` — merge-on-green, and never an empty diff.
"""
from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass
from typing import Callable


@dataclass
class RunResult:
    stdout: str
    returncode: int


def _real_runner(args: list[str]) -> RunResult:
    proc = subprocess.run(["gh", *args], capture_output=True, text=True)
    return RunResult(stdout=proc.stdout, returncode=proc.returncode)


class GitHub:
    def __init__(self, run: Callable[[list[str]], RunResult] = _real_runner):
        self._run = run

    def create_repo(self, name: str, private: bool = True) -> str:
        """SOF-204: create under SF_GITHUB_ORG when set (e.g. `Tenexity-Factory`) — an org-prefixed
        `gh repo create org/name` — otherwise unprefixed, which `gh` resolves to the authenticated
        user (`ibraheem-tenexity`), the SAME real-world default `reap_github_repos.py`'s own
        `SF_GITHUB_ORG` fallback already points at. Existing personal-account repos are untouched;
        this only changes where NEW repos land."""
        org = os.environ.get("SF_GITHUB_ORG", "").strip()
        target = f"{org}/{name}" if org else name
        args = ["repo", "create", target, "--clone"]
        args.append("--private" if private else "--public")
        return self._run(args).stdout.strip()

    def clone_repo(self, url: str) -> None:
        """Clone an already-existing repo into the cwd (SOF-22: stage-3 reusing the repo stage-1
        already created via create_repo's own --clone doesn't get that clone for free)."""
        self._run(["repo", "clone", url])

    def add_collaborator(self, repo: str, username: str, permission: str = "pull") -> bool:
        """Invite `username` as a collaborator on `repo` ('owner/repo'). GitHub's collaborator
        API is username-only (no email-invite path exists for personal-account-owned repos,
        confirmed against the REST docs) — `username` must be a real GitHub handle. Returns
        True on success (invite created or already a collaborator); False on any failure
        (unknown username, no permission, etc.) — never raises, so a failed invite can be
        turned into a visible blocker instead of crashing the run."""
        result = self._run(
            ["api", "-X", "PUT", f"repos/{repo}/collaborators/{username}",
             "-f", f"permission={permission}"]
        )
        return result.returncode == 0

    def open_pr(self, branch: str, title: str, body: str) -> int:
        out = self._run(
            ["pr", "create", "--head", branch, "--title", title, "--body", body]
        ).stdout
        m = re.search(r"/pull/(\d+)", out)
        if not m:
            raise RuntimeError(f"could not parse PR number from: {out!r}")
        return int(m.group(1))

    def checks_green(self, pr: int) -> bool:
        # `gh pr checks` exits non-zero unless every required check has passed.
        return self._run(["pr", "checks", str(pr)]).returncode == 0

    def merge_if_green(self, pr: int, diff_lines: int) -> bool:
        if diff_lines <= 0:
            return False  # empty diff is a no-op turn; never merge it as work
        if not self.checks_green(pr):
            return False
        self._run(["pr", "merge", str(pr), "--squash", "--delete-branch"])
        return True
