"""Thin `gh` wrappers for the repo I/O the factory must not hallucinate.

The runner is injectable: subprocess to real `gh` in production, a fake in tests. The only
logic worth its salt lives in `merge_if_green` — merge-on-green, and never an empty diff.
"""
from __future__ import annotations

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
        args = ["repo", "create", name, "--clone"]
        args.append("--private" if private else "--public")
        return self._run(args).stdout.strip()

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
