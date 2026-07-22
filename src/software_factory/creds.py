"""Provision-time credential checks.

A missing or rejected credential is a HARD BLOCK that must surface at provision, before any
build work — never a guess, never a mid-run surprise. Each check shells a lightweight
verification through an injected runner so it is testable offline. `check_all` returns only
the failing checks (the blocks) for the chosen deploy target.

SOF-194: a check failure is NOT automatically a dead credential. The provider CLIs (`gh`,
`railway`) collapse a transient backend 5xx or a network blip on their auth health-check into
the same "token invalid" exit code as a genuinely-revoked token. Treating that transient as a
permanently-dead `credential` blocker hard-wedges a run for good (SOF-148 disarms auto-resume for
that category), even though the token is valid and the provider recovers seconds later. So each
check now (a) retries a non-definitive failure a few times so a fast blip clears on its own, and
(b) when a failure survives the retries, classifies it: a real auth rejection is `terminal` (the
non-resumable `credential` category, SOF-148 preserved); a recognizable 5xx/network signal is
transient (`.blocks == "transient"`), a category auto-resume CAN relaunch once the provider heals.
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Callable, Optional

from .deploy import RunResult


def _real_runner(args: list[str]) -> RunResult:
    import subprocess

    proc = subprocess.run(args, capture_output=True, text=True)
    # Capture stderr too — `gh auth status` / `railway status` write their real error text
    # (HTTP status, network message) to stderr, and classification needs to read it.
    return RunResult(stdout=proc.stdout, returncode=proc.returncode, stderr=proc.stderr or "")


# How many times a non-definitive failure is retried before we give up, and the backoff (seconds)
# slept between attempts. A real transient provider blip clears within this window; a truly revoked
# token stays failing across all attempts. Kept short — this runs once at provision.
_MAX_ATTEMPTS = 3
_BACKOFF = (1.0, 2.0)

# Substrings that PROVE a terminal auth rejection — safe to fail fast (retrying can't fix it) and
# to mark non-resumable. Deliberately specific: the CLIs' generic "invalid"/"not authenticated"
# summaries are NOT here, because a transient 5xx collapses into exactly those (SOF-194) and must
# be retried rather than declared dead.
_AUTH_REJECT = (
    "bad credentials", "401", "403", "requires authentication", "must have push access",
    "token has expired", "token expired", "must re-authorize", "re-authenticate",
)
# Substrings that mark a TRANSIENT backend/network failure — resumable, not a dead credential.
_TRANSIENT = (
    "500", "502", "503", "504", "http 5", "server error", "service unavailable", "bad gateway",
    "gateway timeout", "unicorn", "something went wrong", "timeout", "timed out", "temporarily",
    "try again", "connection refused", "connection reset", "eof", "dial tcp", "no such host",
    "tls handshake", "i/o timeout", "network is unreachable",
)


def _looks(text: str, needles: tuple[str, ...]) -> bool:
    low = text.lower()
    return any(n in low for n in needles)


def _probe(
    run: Callable[[list[str]], RunResult],
    args: list[str],
    sleep: Callable[[float], None],
) -> tuple[bool, bool]:
    """Run `args`, retrying a non-definitive failure so a transient provider 5xx/network blip
    clears instead of being mistaken for a dead credential (SOF-194).

    Returns (ok, terminal):
      ok       — the command finally exited 0 (credential is good).
      terminal — meaningful only when not ok: True = a real auth rejection (non-resumable
                 `credential`, SOF-148); False = a transient blip that survived retries (resumable).
    """
    output = ""
    for attempt in range(_MAX_ATTEMPTS):
        r = run(args)
        if r.returncode == 0:
            return True, False
        output = f"{r.stdout}\n{r.stderr}".strip()
        if _looks(output, _AUTH_REJECT):
            return False, True          # definitive rejection — retrying can't fix it
        if attempt < _MAX_ATTEMPTS - 1:
            sleep(_BACKOFF[attempt])
    # Exhausted retries with no clean success and no definitive rejection: a recognizable transient
    # signal ⇒ resumable; anything else stays terminal (SOF-148's conservative default — an unknown
    # persistent failure is treated as a dead credential the operator must resolve).
    return False, not _looks(output, _TRANSIENT)


@dataclass
class CredCheck:
    name: str
    ok: bool
    detail: str
    terminal: bool = True   # only meaningful when ok is False (see `blocks`)

    @property
    def blocks(self) -> str:
        """The blocker category to record for a failing check: `credential` (non-resumable,
        SOF-148) for a real rejection/missing cred, `transient` (resumable) for a 5xx/network blip
        that survived the check's own retries (SOF-194)."""
        return "credential" if self.terminal else "transient"


def check_gh(
    run: Callable[[list[str]], RunResult] = _real_runner,
    sleep: Callable[[float], None] = time.sleep,
) -> CredCheck:
    ok, terminal = _probe(run, ["gh", "auth", "status"], sleep)
    if ok:
        return CredCheck("gh", True, "authenticated")
    detail = (
        "`gh` is not authenticated"
        if terminal
        else "GitHub auth check hit a transient error (5xx/network) that survived retries"
    )
    return CredCheck("gh", False, detail, terminal=terminal)


def check_railway(
    env: Optional[dict] = None,
    run: Callable[[list[str]], RunResult] = _real_runner,
    sleep: Callable[[float], None] = time.sleep,
) -> CredCheck:
    env = os.environ if env is None else env
    if not (env.get("RAILWAY_TOKEN") or env.get("RAILWAY_API_TOKEN")):
        # A missing token is a real config block, not a transient — terminal by default.
        return CredCheck("railway", False, "no RAILWAY_TOKEN / RAILWAY_API_TOKEN in environment")
    # `railway status` works for project-scoped tokens; `whoami` only works for account tokens.
    ok, terminal = _probe(run, ["railway", "status"], sleep)
    if ok:
        return CredCheck("railway", True, "token accepted")
    detail = (
        "Railway token rejected (railway status failed)"
        if terminal
        else "Railway status check hit a transient error (5xx/network) that survived retries"
    )
    return CredCheck("railway", False, detail, terminal=terminal)


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
