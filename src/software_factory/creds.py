"""Provision-time credential checks.

A missing or rejected credential is a HARD BLOCK that must surface at provision, before any
build work — never a guess, never a mid-run surprise. Each check shells a lightweight
verification through an injected runner so it is testable offline. `check_all` returns only
the failing checks (the blocks) for the chosen deploy target.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Callable, Optional

from .deploy import RunResult


def _real_runner(args: list[str]) -> RunResult:
    import subprocess

    proc = subprocess.run(args, capture_output=True, text=True)
    return RunResult(stdout=proc.stdout, returncode=proc.returncode)


@dataclass
class CredCheck:
    name: str
    ok: bool
    detail: str


def check_gh(run: Callable[[list[str]], RunResult] = _real_runner) -> CredCheck:
    rc = run(["gh", "auth", "status"]).returncode
    return CredCheck("gh", rc == 0, "authenticated" if rc == 0 else "`gh` is not authenticated")


def check_railway(
    env: Optional[dict] = None,
    run: Callable[[list[str]], RunResult] = _real_runner,
) -> CredCheck:
    env = os.environ if env is None else env
    if not (env.get("RAILWAY_TOKEN") or env.get("RAILWAY_API_TOKEN")):
        return CredCheck("railway", False, "no RAILWAY_TOKEN / RAILWAY_API_TOKEN in environment")
    rc = run(["railway", "whoami"]).returncode
    if rc != 0:
        return CredCheck("railway", False, "Railway token rejected (railway whoami failed)")
    return CredCheck("railway", True, "token accepted")


# Which creds each deploy target needs. gh is always required (repo + PRs).
_REQUIRED = {
    "railway": ("gh", "railway"),
    "vercel": ("gh",),
}


def check_all(
    target: str,
    env: Optional[dict] = None,
    run: Callable[[list[str]], RunResult] = _real_runner,
) -> list[CredCheck]:
    """Run the checks required for `target`; return only the failures (the hard blocks)."""
    checks = []
    for name in _REQUIRED.get(target, ("gh",)):
        if name == "gh":
            checks.append(check_gh(run=run))
        elif name == "railway":
            checks.append(check_railway(env=env, run=run))
    return [c for c in checks if not c.ok]
