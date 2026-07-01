"""Expose the running build's git SHA so a deploy can be verified against an expected commit.

Sourced at runtime, in order: ``RAILWAY_GIT_COMMIT_SHA`` (injected fresh by Railway on every
git-connected deploy, auto or manual) → ``SF_GIT_SHA`` (a manual override; no longer baked
persistently by scripts/deploy.sh as of SOF-24) → ``git rev-parse HEAD`` fallback (local / dev
checkout) → ``"unknown"``. RAILWAY_GIT_COMMIT_SHA must win: it's the only source that's guaranteed
current on every deploy. SF_GIT_SHA is a persistent Railway service variable — once set, it
outlives the deploy that set it, so checking it first let a stale value from an old MANUAL deploy
silently shadow newer commits shipped by a native git-source AUTO-deploy (which never runs
deploy.sh and so never refreshes it) — SOF-24, follow-up to the SOF-16 auto-deploy rollout.
``dirty`` reflects an uncommitted working tree and is only meaningful in a dev checkout; an
env-provided deploy reports ``false``.

Used by GET /api/version (console/routers/open_routes.py). Knowing the deployed SHA lets the
verify step confirm it is exercising the commit it thinks it is — half of the TEN-151 /
KNOWN_ISSUES #87 fix for link-drift false-negative verifies (the other half is railway_link.py).
"""
from __future__ import annotations

import os
import subprocess
from typing import Callable, Mapping, Optional


def _git(args: list[str]) -> Optional[str]:
    """Run a git command and return trimmed stdout, or None if git is absent / the command fails
    (e.g. a deployed container with no .git directory)."""
    try:
        p = subprocess.run(["git", *args], capture_output=True, text=True)
    except OSError:
        return None
    return p.stdout.strip() if p.returncode == 0 else None


def version_info(
    env: Optional[Mapping[str, str]] = None,
    git: Callable[[list[str]], Optional[str]] = _git,
) -> dict:
    """Return ``{"sha", "short", "dirty"}`` for the running build. ``env``/``git`` are injectable
    for testing; in production both default to the live process environment and real git."""
    env = os.environ if env is None else env
    baked = (env.get("RAILWAY_GIT_COMMIT_SHA") or env.get("SF_GIT_SHA") or "").strip()

    sha = baked or (git(["rev-parse", "HEAD"]) or "").strip()

    dirty_env = env.get("SF_GIT_DIRTY")
    if dirty_env is not None:
        dirty = dirty_env.strip().lower() in ("1", "true", "yes")
    elif baked:
        # Env-baked SHA = an immutable build artifact; the running tree is not the source of truth.
        dirty = False
    else:
        # Local fallback: the working tree IS the build, so report whether it has uncommitted changes.
        status = git(["status", "--porcelain"])
        dirty = bool(status)

    sha = sha or "unknown"
    short = sha[:7] if sha != "unknown" else "unknown"
    return {"sha": sha, "short": short, "dirty": dirty}
