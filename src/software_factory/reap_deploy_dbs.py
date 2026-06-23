"""CLI: the deploy-DB REAPER — sweep terminal/archived runs and tear down their leaked Railway
Postgres services (matching persisted captured serviceIds ↔ run state).

SAFE BY DEFAULT — two independent guards must both open before anything is deleted:
  1. --apply on the command line (omit it for a dry-run PREVIEW that only logs candidates), AND
  2. SF_DEPLOY_DB_TEARDOWN armed (=persistent [B, recommended] or =ephemeral [A]); unset/off = held.

    python -m software_factory.reap_deploy_dbs                          # dry-run preview
    SF_DEPLOY_DB_TEARDOWN=persistent python -m software_factory.reap_deploy_dbs --apply

The actual lifecycle FIRING stays held until the operator arms SF_DEPLOY_DB_TEARDOWN — this CLI just
lets the integrator preview/rehearse the sweep. Prints the structured report as JSON.
"""
from __future__ import annotations

import json
import os
import sys


def _projects_dir() -> str:
    # Matches console.state: the run base lives on SF_PROJECTS_DIR (a Railway volume in prod).
    return os.environ.get("SF_PROJECTS_DIR") or os.path.join(
        os.path.dirname(__file__), "..", "..", ".projects")


def _run_sweep(dry_run: bool) -> dict:
    from .console import Console
    return Console(_projects_dir()).reap_deploy_dbs(dry_run=dry_run)


def main(argv: list[str]) -> int:
    # Without --apply we force a dry-run preview even if the env is armed (belt-and-suspenders); with
    # --apply we defer to SF_DEPLOY_DB_TEARDOWN (so an unset/off env STILL only previews).
    report = _run_sweep(dry_run="--apply" not in argv)
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
