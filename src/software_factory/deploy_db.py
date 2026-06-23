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


def _parse_added_service(text: str) -> tuple[str | None, str | None]:
    """(serviceId, serviceName) from `railway add --database postgres --json`. Railway AUTO-NAMES the
    service "Postgres-XXXX" (NOT a name we pass) — so we capture the REAL id it returns, never a guess."""
    try:
        d = json.loads(text)
        return d.get("serviceId"), d.get("serviceName")
    except Exception:
        return None, None


def _parse_database_url(text: str) -> str | None:
    try:
        d = json.loads(text)
        u = d.get("DATABASE_URL") or d.get("DATABASE_PUBLIC_URL")
        if u:
            return u.rstrip("/")
    except Exception:
        pass
    return _pg_url_from(text)


def provision(project_id: str, context_dir: str,
              run: Callable[[list[str]], RunResult] = _real_runner) -> dict:
    """Provision (or RESUME) this run's Railway Postgres and return + persist its connection info
    {DATABASE_URL, provider, service, service_id, project_id} to context_dir/deploy-db.json.

    Behavior verified against the live railway CLI (5.12.1):
      • `railway add --database postgres` is INTERACTIVE (prompts + hangs headless) — the bare form was
        the original stall. We use `--json`, which returns {serviceId, serviceName:"Postgres-XXXX"}.
      • Railway auto-names the service; we CAPTURE the returned serviceId and read DATABASE_URL from THAT
        id (`railway variables --service <serviceId> --json`) — reading by a guessed name was the bug.
    IDEMPOTENT: the serviceId is persisted the MOMENT `add` succeeds (before the variables read), so a
    retry REUSES that service (no second `add` → no orphan); a fully-provisioned file is a no-op. Raises
    RuntimeError on failure (the caller records a blocker + counts the attempt against the retry cap)."""
    railway_project_id = os.environ.get("RAILWAY_PROJECT_ID")
    if not env.railway_project_allowed(railway_project_id):
        raise RuntimeError(
            f"RAILWAY_PROJECT_ID={railway_project_id!r} is not allowed for run-app DB provisioning")

    info_path = os.path.join(context_dir, DEPLOY_DB_FILE)
    info: dict = {}
    if os.path.exists(info_path):
        try:
            with open(info_path) as f:
                info = json.load(f)
        except Exception:
            info = {}
    if info.get("DATABASE_URL"):
        return info                              # already provisioned — idempotent no-op

    svc_id, svc_name = info.get("service_id"), info.get("service")
    if not svc_id:
        add_out = run(["railway", "add", "--database", "postgres", "--json"]).stdout
        svc_id, svc_name = _parse_added_service(add_out)
        if not svc_id:
            raise RuntimeError(f"railway add --json returned no serviceId: {(add_out or '')[:200]!r}")
        # Persist the handle BEFORE reading variables: if the read fails, the retry reuses this exact
        # service instead of adding another one. service_id is also the durable teardown handle.
        write_file(context_dir, {"service_id": svc_id, "service": svc_name,
                                 "provider": "railway-postgres", "project_id": project_id})

    var_out = run(["railway", "variables", "--service", svc_id, "--json"]).stdout
    url = _parse_database_url(var_out)
    if not url:
        raise RuntimeError(f"could not obtain a Postgres DATABASE_URL for service {svc_id}")
    info = {"DATABASE_URL": url, "provider": "railway-postgres",
            "service": svc_name, "service_id": svc_id, "project_id": project_id}
    write_file(context_dir, info)
    return info


def write_file(context_dir: str, info: dict) -> str:
    """Write the deploy-db file the stage-3 agent reads. Returns its path."""
    os.makedirs(context_dir, exist_ok=True)
    path = os.path.join(context_dir, DEPLOY_DB_FILE)
    with open(path, "w") as f:
        json.dump(info, f, indent=2)
    return path
