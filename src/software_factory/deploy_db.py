"""Factory-side provisioning of a run's DEPLOY DATABASE.

Stage-3 agents have NO Supabase access and must never provision a database themselves. Instead
the FACTORY provisions a per-project Railway Postgres and writes its connection details into the
stage-3 workspace as `context/deploy-db.json`; the agent reads that file and wires the built app
to it (and sets it on the app's own service at deploy).

Railway auth (RAILWAY_TOKEN) is read from the environment by the CLI — never passed on the command
line. The target project is derived from SF_RUNAPP_RAILWAY_PROJECT_IDS (not RAILWAY_PROJECT_ID,
which Railway forces to the console's own project on prod). The runner is injectable so the parse logic
is unit-tested offline; the exact `railway` incantation is the one place that needs a live smoke
check.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Callable, Iterable

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
    # Use SF_RUNAPP_RAILWAY_PROJECT_IDS as the authoritative target: RAILWAY_PROJECT_ID is
    # Railway-reserved and forced to the console's own project on prod, so it can't be
    # overridden via the dashboard and must not be used as the DB provision target.
    railway_project_id = env.runapp_railway_project_id() or os.environ.get("RAILWAY_PROJECT_ID")
    if not env.railway_project_allowed(railway_project_id):
        raise RuntimeError(
            f"railway project {railway_project_id!r} is not allowed for run-app DB provisioning")

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


# ===========================================================================================
# TEARDOWN + REAPER — the second half of the orphan-leak fix.
#
# provision() captures the per-run Postgres serviceId (the durable handle). This deletes it when
# the run reaches a terminal/archive state so dead runs don't leak Postgres services. We delete the
# EXACT captured id — never a name guess, never the console — so a mistake can't take out
# factory-console (env.railway_project_allowed also rejects the console project as a second net).
#
# Live-verified incantation (operator l2a7ngax, CLI 5.12.1):
#   railway service delete -s <serviceId> -p <projectId> -e <ENV> -y
#   • `service delete` (NOT `railway delete`, which removes the whole PROJECT).
#   • -e MUST be the service's real environment or the CLI silently "not found"s — so we read it
#     from RAILWAY_ENVIRONMENT (factory DBs live in the console's own env), never hardcode it.
#   • Deleting the service CASCADES its volume — no separate volume delete needed.
#   • A re-attempt of an already-gone service returns "not found" → we treat that as success.
#
# POLICY GATE (single env SF_DEPLOY_DB_TEARDOWN): unset/off (default) = DISARMED — teardown and the
# reaper run as a DRY-RUN that logs what they WOULD delete but delete nothing (the "held" state until
# the operator makes the A/B lifecycle call). "persistent" (B, recommended) reaps discarded
# (archived) + stopped-without-a-live-deploy and KEEPS done runs / any run with a live URL (the
# demo). "ephemeral" (A) reaps on any terminal state.
# ===========================================================================================

_TEARDOWN_ENV = "SF_DEPLOY_DB_TEARDOWN"


def teardown_mode() -> str:
    """'off' (default, disarmed/dry-run), 'persistent' (B), or 'ephemeral' (A) from SF_DEPLOY_DB_TEARDOWN."""
    v = (os.environ.get(_TEARDOWN_ENV) or "").strip().lower()
    if v in ("ephemeral", "a"):
        return "ephemeral"
    if v in ("persistent", "b"):
        return "persistent"
    return "off"


def _railway_environment() -> str:
    """The -e value for a service delete. MUST match the service's project environment, else the CLI
    silently reports 'not found'. Factory-provisioned DBs live in the console's own Railway env."""
    return (os.environ.get("RAILWAY_ENVIRONMENT")
            or os.environ.get("RAILWAY_ENVIRONMENT_ID")
            or "production")


def teardown(service_id: str, run: Callable[[list[str]], RunResult] = _real_runner) -> dict:
    """Delete the EXACT captured Railway Postgres service (its volume cascades). Idempotent: a
    'not found' result means the service is already gone → success. Refuses a missing service_id so
    we never guess a name or fall back to the linked (console) service. Returns
    {service_id, deleted, already_gone, ok, detail} — never raises on a CLI failure (the caller logs)."""
    sid = (service_id or "").strip()
    if not sid:
        raise ValueError("teardown requires a captured service_id (never a name guess)")
    args = ["railway", "service", "delete", "-s", sid]
    # Prefer SF_RUNAPP_RAILWAY_PROJECT_IDS (the authoritative run-app target) over
    # RAILWAY_PROJECT_ID (Railway-reserved, forced to the console's own project on prod).
    project = env.runapp_railway_project_id() or os.environ.get("RAILWAY_PROJECT_ID")
    if project:
        args += ["-p", project]
    args += ["-e", _railway_environment(), "-y"]
    res = run(args)
    out = res.stdout or ""
    combined = (out + "\n" + (getattr(res, "stderr", "") or ""))   # railway may put 'not found' on stderr
    if "not found" in combined.lower():
        return {"service_id": sid, "deleted": False, "already_gone": True, "ok": True,
                "detail": "not found (already gone)"}
    if res.returncode == 0:
        return {"service_id": sid, "deleted": True, "already_gone": False, "ok": True,
                "detail": out[:200]}
    return {"service_id": sid, "deleted": False, "already_gone": False, "ok": False,
            "detail": (combined.strip()[:200]) or f"exit {res.returncode}"}


@dataclass
class ReapRecord:
    """One run's deploy-DB teardown candidate. The console builds these from ProjectState
    (service_id = deploy_db_service_id, has_verified_deploy = bool(deploy_url))."""
    project_id: str
    service_id: str
    archived: bool = False
    phase: str = ""
    has_verified_deploy: bool = False


def _reap_reason(rec: ReapRecord, policy: str) -> str | None:
    """Why rec's deploy-DB is eligible for teardown under `policy`, or None to KEEP it.
    persistent (B): reap discarded (archived) or stopped-without-a-live-deploy; keep done + live demos.
    ephemeral (A): reap on any terminal state (done/stopped/archived)."""
    if rec.archived:
        return "archived"                                  # explicit discard reaps under both policies
    if policy == "ephemeral":
        return rec.phase if rec.phase in ("done", "stopped") else None
    # persistent (B)
    if rec.phase == "stopped" and not rec.has_verified_deploy:
        return "stopped-without-deploy"
    return None                                            # done / live demo / still-active → keep


def reap(records: Iterable[ReapRecord],
         run: Callable[[list[str]], RunResult] = _real_runner,
         log: Callable[[str], None] | None = None,
         dry_run: bool = False) -> dict:
    """Sweep: tear down the deploy-DB of every reap-eligible run under the configured policy.
    DISARMED (SF_DEPLOY_DB_TEARDOWN unset/off) or dry_run=True → log what WOULD be reaped, delete
    nothing. Records with no service_id (never provisioned a DB) are skipped. Returns a structured
    report {mode, armed, policy, reaped, would_reap, kept, failed} — every persisted DB is accounted
    for in exactly one bucket (no silent drops)."""
    log = log or (lambda m: None)
    mode = teardown_mode()
    armed = mode != "off" and not dry_run
    policy = "ephemeral" if mode == "ephemeral" else "persistent"   # disarmed previews the recommended B
    report: dict = {"mode": mode, "armed": armed, "policy": policy,
                    "reaped": [], "would_reap": [], "kept": [], "failed": []}
    for rec in records:
        if not (rec.service_id or "").strip():
            continue                                       # never provisioned a DB — nothing to reap
        reason = _reap_reason(rec, policy)
        base = {"project_id": rec.project_id, "service_id": rec.service_id}
        if not reason:
            report["kept"].append({**base, "phase": rec.phase,
                                   "has_verified_deploy": rec.has_verified_deploy})
            continue
        if not armed:
            report["would_reap"].append({**base, "reason": reason})
            log(f"[deploy-db reaper] DRY-RUN would tear down {rec.service_id} "
                f"(project {rec.project_id}, reason={reason}) — set {_TEARDOWN_ENV}=persistent|ephemeral to arm")
            continue
        res = teardown(rec.service_id, run=run)
        if res["ok"]:
            report["reaped"].append({**base, "reason": reason,
                                     "deleted": res["deleted"], "already_gone": res["already_gone"]})
            log(f"[deploy-db reaper] tore down {rec.service_id} (project {rec.project_id}, "
                f"reason={reason}, {'deleted' if res['deleted'] else 'already gone'})")
        else:
            report["failed"].append({**base, "reason": reason, "detail": res["detail"]})
            log(f"[deploy-db reaper] FAILED to tear down {rec.service_id} "
                f"(project {rec.project_id}): {res['detail']}")
    return report
