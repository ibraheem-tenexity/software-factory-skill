"""Deploy a surface and then prove it is live.

`deploy` triggers a provider CLI and returns the deployed URL. `healthy` polls that URL
and returns True only on a 2xx — a timeout returns False, never an optimistic "probably up".
Runner / HTTP getter / sleeper are injectable so the logic is testable offline.
"""
from __future__ import annotations

import logging
import os
import re
import subprocess
import time
import urllib.request
from dataclasses import dataclass
from typing import Callable

from . import env

logger = logging.getLogger(__name__)


@dataclass
class RunResult:
    stdout: str
    returncode: int
    stderr: str = ""   # captured so callers can read CLI errors that land on stderr (e.g. teardown's "not found")


def _real_runner(args: list[str]) -> RunResult:
    # Override RAILWAY_PROJECT_ID in the subprocess env when SF_RUNAPP_RAILWAY_PROJECT_IDS
    # is configured: Railway forcibly injects RAILWAY_PROJECT_ID as the console's own project
    # id into every service it runs, so the env var cannot be set via the dashboard and
    # must be overridden explicitly in the CLI subprocess.
    target = env.runapp_railway_project_id()
    run_env = {**os.environ, "RAILWAY_PROJECT_ID": target} if target else None
    proc = subprocess.run(args, capture_output=True, text=True, env=run_env)
    return RunResult(stdout=proc.stdout, returncode=proc.returncode, stderr=proc.stderr or "")


_TARGETS = ("vercel", "railway")


def _parse_url(text: str) -> str:
    """Pull a public URL from CLI output; accept a bare domain and add https://."""
    m = re.search(r"https?://[^\s]+", text)
    if m:
        return m.group(0).rstrip("/")
    m = re.search(r"[a-z0-9-]+(?:\.[a-z0-9-]+)*\.(?:railway\.app|vercel\.app|up\.railway\.app)", text)
    if m:
        return "https://" + m.group(0)
    raise RuntimeError(f"could not parse a deployed URL from: {text!r}")


def deploy(target: str, dir: str, run: Callable[[list[str]], RunResult] = _real_runner) -> str:
    """Ship `dir` to the target and return its public URL.

    The provider auth (e.g. RAILWAY_TOKEN) is read from the process environment by the CLI —
    the orchestrator/console injects it there; it is never passed on the command line.
    """
    if target not in _TARGETS:
        raise ValueError(f"unknown deploy target {target!r}; expected one of {list(_TARGETS)}")
    logger.info("[deploy] starting %s deploy of %s", target, dir)
    if target == "vercel":
        # `vercel deploy --prod` prints the deployment URL on stdout.
        url = _parse_url(run(["vercel", "deploy", "--cwd", dir, "--prod", "--yes"]).stdout)
        logger.info("[deploy] vercel deploy done: %s", url)
        return url
    # railway: `up` ships the dir, then `domain` ensures + prints the public domain.
    # Use SF_RUNAPP_RAILWAY_PROJECT_IDS as the authoritative target: RAILWAY_PROJECT_ID is
    # Railway-reserved and forced to the console's own project on prod, so it can't be
    # overridden via the dashboard and must not be used as the deployment target.
    project_id = env.runapp_railway_project_id() or os.environ.get("RAILWAY_PROJECT_ID")
    if not env.railway_project_allowed(project_id):
        raise RuntimeError(
            f"railway project {project_id!r} is not allowed for run-app deployment. "
            f"Set SF_RUNAPP_RAILWAY_PROJECT_IDS to the target project UUID."
        )
    run(["railway", "up", "--ci", dir])
    url = _parse_url(run(["railway", "domain"]).stdout)
    logger.info("[deploy] railway deploy done: %s", url)
    return url


def _http_status(url: str) -> int:
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            return resp.status
    except urllib.error.HTTPError as e:
        return e.code
    except Exception:
        # A connection error during a health poll is expected until the app boots (returns 0 =
        # not-yet-live). WARNING (not ERROR) so an expected pre-boot probe doesn't cry error, but
        # the traceback still emits — the software_factory logger is pinned at INFO, so debug would
        # be swallowed and a genuine failure (DNS/TLS/etc.) behind the False verdict would vanish.
        logger.warning("[deploy] health probe to %s failed (treating as not-live)", url, exc_info=True)
        return 0


def healthy(
    url: str,
    timeout_s: int = 120,
    interval_s: int = 3,
    get: Callable[[str], int] = _http_status,
    sleep: Callable[[float], None] = time.sleep,
) -> bool:
    attempts = max(1, timeout_s // interval_s)
    for i in range(attempts):
        if 200 <= get(url) < 300:
            return True
        if i < attempts - 1:
            sleep(interval_s)
    return False
