"""Factory-side provisioning of a run's DEPLOY DATABASE.

Stage-3 agents have NO Supabase access and must never provision a database themselves. Instead
the FACTORY provisions a per-project Railway Postgres and writes its connection details into the
stage-3 workspace as `context/deploy-db.json`; the agent reads that file and wires the built app
to it (and sets it on the app's own service at deploy).

Railway auth (RAILWAY_TOKEN / RAILWAY_PROJECT_ID) is read from the environment by the CLI — never
passed on the command line — exactly like deploy.py. The runner is injectable so the parse logic
is unit-tested offline; the exact `railway` incantation is the one place that needs a live smoke
check.
"""
from __future__ import annotations

import json
import os
from typing import Callable

from . import env
from .deploy import RunResult, _real_runner

DEPLOY_DB_FILE = "deploy-db.json"

# DB-ish required tokens that mean "this app needs a database" — used to decide whether to
# provision at all (a static app needs no Postgres).
_DB_TOKEN_HINTS = ("DATABASE_URL", "POSTGRES", "PG_", "SUPABASE_URL", "SUPABASE_DB", "DB_URL")


def needs_deploy_db(required: list | None) -> bool:
    up = [str(t).upper() for t in (required or [])]
    return any(any(h in t for h in _DB_TOKEN_HINTS) for t in up)


def _pg_url_from(text: str) -> str | None:
    """Pull a postgres connection URL out of CLI / JSON output, trimming shell/quote trailers."""
    import re
    m = re.search(r"postgres(?:ql)?://[^\s\"'`]+", text or "")
    return m.group(0).rstrip("/") if m else None


def provision(project_id: str, run: Callable[[list[str]], RunResult] = _real_runner) -> dict:
    """Create a Railway Postgres for this run and return its connection info:
    {DATABASE_URL, provider, service, project_id}. Raises RuntimeError if no URL can be obtained —
    the caller turns that into a deps blocker rather than letting the run proceed DB-less."""
    railway_project_id = os.environ.get("RAILWAY_PROJECT_ID")
    if not env.railway_project_allowed(railway_project_id):
        raise RuntimeError(
            f"RAILWAY_PROJECT_ID={railway_project_id!r} is not allowed for run-app DB provisioning")
    svc = f"sf-{project_id}-db"
    # Add a managed Postgres to the run-app project. Re-runs are tolerated: an "already exists"
    # is not fatal — we still read the connection string below.
    run(["railway", "add", "--database", "postgres", "--service", svc])
    out = run(["railway", "variables", "--service", svc, "--json"]).stdout
    url = None
    try:
        data = json.loads(out)
        url = data.get("DATABASE_URL") or data.get("DATABASE_PUBLIC_URL")
    except Exception:
        url = None
    url = url or _pg_url_from(out)
    if not url:
        raise RuntimeError(f"could not obtain a Postgres DATABASE_URL for {svc}")
    return {"DATABASE_URL": url, "provider": "railway-postgres", "service": svc, "project_id": project_id}


def write_file(context_dir: str, info: dict) -> str:
    """Write the deploy-db file the stage-3 agent reads. Returns its path."""
    os.makedirs(context_dir, exist_ok=True)
    path = os.path.join(context_dir, DEPLOY_DB_FILE)
    with open(path, "w") as f:
        json.dump(info, f, indent=2)
    return path
