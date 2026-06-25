"""CLI: the GitHub repo REAPER — sweep factory-created repos whose project is confirmed dead.

SAFE BY DEFAULT — two independent guards must both open before anything is deleted:
  1. --apply on the command line (omit for a dry-run PREVIEW that only logs candidates), AND
  2. SF_GITHUB_REPO_REAPER=on (unset/off → held / dry-run only).

    python -m software_factory.reap_github_repos                          # dry-run preview
    SF_GITHUB_REPO_REAPER=on python -m software_factory.reap_github_repos --apply

Requires: gh CLI authed in the runtime environment with repo delete permissions.
GitHub org defaults to SF_GITHUB_ORG (default: ibraheem-tenexity).
"""
from __future__ import annotations

import json
import os
import sys


_DEFAULT_ORG = "ibraheem-tenexity"


def _projects_dir() -> str:
    return os.environ.get("SF_PROJECTS_DIR") or os.path.join(
        os.path.dirname(__file__), "..", "..", ".projects")


def _run_sweep(org: str, dry_run: bool) -> dict:
    from .console import Console
    return Console(_projects_dir()).reap_github_repos(org, dry_run=dry_run)


def main(argv: list[str]) -> int:
    org = os.environ.get("SF_GITHUB_ORG", _DEFAULT_ORG)
    report = _run_sweep(org, dry_run="--apply" not in argv)
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
