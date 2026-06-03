"""Deploy a surface and then prove it is live.

`deploy` triggers a provider CLI and returns the deployed URL. `healthy` polls that URL
and returns True only on a 2xx — a timeout returns False, never an optimistic "probably up".
Runner / HTTP getter / sleeper are injectable so the logic is testable offline.
"""
from __future__ import annotations

import re
import subprocess
import time
import urllib.request
from dataclasses import dataclass
from typing import Callable


@dataclass
class RunResult:
    stdout: str
    returncode: int


def _real_runner(args: list[str]) -> RunResult:
    proc = subprocess.run(args, capture_output=True, text=True)
    return RunResult(stdout=proc.stdout, returncode=proc.returncode)


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
    if target == "vercel":
        # `vercel deploy --prod` prints the deployment URL on stdout.
        return _parse_url(run(["vercel", "deploy", "--cwd", dir, "--prod", "--yes"]).stdout)
    # railway: `up` ships the dir, then `domain` ensures + prints the public domain.
    run(["railway", "up", "--ci", dir])
    return _parse_url(run(["railway", "domain"]).stdout)


def _http_status(url: str) -> int:
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            return resp.status
    except urllib.error.HTTPError as e:
        return e.code
    except Exception:
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
