"""Deploy a surface and then prove it is live.

`deploy` triggers a provider CLI and returns the deployed URL. `healthy` polls that URL
and returns True only on a 2xx — a timeout returns False, never an optimistic "probably up".
Runner / HTTP getter / sleeper are injectable so the logic is testable offline.
"""
from __future__ import annotations

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


# Each target maps a source dir to the provider command that ships it.
_COMMANDS: dict[str, Callable[[str], list[str]]] = {
    "vercel": lambda dir: ["vercel", "deploy", "--cwd", dir, "--prod", "--yes"],
    "railway": lambda dir: ["railway", "up", "--ci", "--service", dir],
}


def deploy(target: str, dir: str, run: Callable[[list[str]], RunResult] = _real_runner) -> str:
    if target not in _COMMANDS:
        raise ValueError(f"unknown deploy target {target!r}; expected one of {sorted(_COMMANDS)}")
    return run(_COMMANDS[target](dir)).stdout.strip()


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
