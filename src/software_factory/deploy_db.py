"""Factory-side provisioning of a run's DEPLOY DATABASE, plus direct Railway GraphQL operations
on a run's OWN app service (`set_app_variable` — post-deploy provider-key replacement, #107).

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
import logging
import os
from dataclasses import dataclass
from typing import Callable, Iterable

import urllib.error
import urllib.request

from . import env
from .deploy import RunResult, _real_runner

logger = logging.getLogger(__name__)

# ===========================================================================================
# RAILWAY GRAPHQL API — thin helpers for service-delete and variables-read.
#
# Using the GraphQL API instead of the CLI for these two ops eliminates link-drift: the CLI
# reads ~/.railway/config.json for project/environment context; another process running
# `railway link` can silently redirect subsequent CLI calls. GraphQL uses a bearer token
# directly — no ambient link state, no CLI env resolution.
#
# Auth: RAILWAY_TOKEN (Railway injects this into every service it runs). For teardown the
# token just needs access to the target service by ID (no project/env required in the
# GraphQL mutation). For variables the token plus explicit projectId + environmentId
# (SF_RUNAPP_RAILWAY_ENVIRONMENT_IDS) are required.
# ===========================================================================================

_RAILWAY_GRAPHQL_URL = "https://backboard.railway.app/graphql/v2"


def _graphql(query: str, variables: dict, token: str) -> dict:
    """POST a Railway GraphQL request. Returns the parsed JSON body. Raises on HTTP error.

    SOF-160: two things Railway's GraphQL requires that this call was missing —
    1. AUTH HEADER: RAILWAY_TOKEN here is always a Railway PROJECT token (env-scoped), authenticated
       via the `Project-Access-Token` header — NOT `Authorization: Bearer` (that's account/team
       tokens; a project token sent as Bearer → "Project Token not found").
    2. USER-AGENT: backboard is behind Cloudflare, which BANS urllib's default `Python-urllib/x.y`
       UA with HTTP 403 "error code: 1010" — BEFORE the request ever reaches Railway's auth. With no
       UA set, every serviceDelete/variables call 403'd regardless of the auth header (this is the
       actual "1010" the ticket saw). Any non-default UA passes; we send an honest descriptive one.
    Both are required: the header alone still 1010s at Cloudflare; the UA alone still fails auth."""
    payload = json.dumps({"query": query, "variables": variables}).encode()
    req = urllib.request.Request(
        _RAILWAY_GRAPHQL_URL,
        data=payload,
        headers={"Content-Type": "application/json", "Project-Access-Token": token,
                 "User-Agent": "software-factory-deploy-db/1.0"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


def _graphql_service_delete(service_id: str, token: str) -> dict:
    """Delete a Railway service via GraphQL. Needs only the service ID — no project/env linking.
    Returns {service_id, deleted, already_gone, ok, detail}. Never raises."""
    try:
        resp = _graphql(
            "mutation ServiceDelete($id: String!) { serviceDelete(id: $id) }",
            {"id": service_id},
            token,
        )
    except Exception as exc:
        return {"service_id": service_id, "deleted": False, "already_gone": False,
                "ok": False, "detail": f"graphql error: {exc}"[:200]}
    errors = resp.get("errors") or []
    err_text = " ".join(str(e) for e in errors).lower()
    if any(p in err_text for p in ("not found", "does not exist", "no service")):
        return {"service_id": service_id, "deleted": False, "already_gone": True,
                "ok": True, "detail": "already gone"}
    if errors:
        return {"service_id": service_id, "deleted": False, "already_gone": False,
                "ok": False, "detail": str(errors)[:200]}
    return {"service_id": service_id, "deleted": True, "already_gone": False,
            "ok": True, "detail": "deleted via graphql"}


def _graphql_get_database_url(service_id: str, project_id: str,
                              environment_id: str, token: str) -> str | None:
    """Fetch DATABASE_URL for a Railway service via GraphQL variables query.
    Returns the URL string or None on any error / missing variable."""
    try:
        resp = _graphql(
            """query Variables($projectId: String!, $serviceId: String!, $environmentId: String!) {
                 variables(projectId: $projectId, serviceId: $serviceId, environmentId: $environmentId)
               }""",
            {"projectId": project_id, "serviceId": service_id, "environmentId": environment_id},
            token,
        )
    except Exception:
        return None
    data = (resp.get("data") or {}).get("variables") or {}
    url = data.get("DATABASE_URL") or data.get("DATABASE_PUBLIC_URL")
    return url.rstrip("/") if url else None


def _graphql_find_service_by_name(project_id: str, service_name: str, token: str) -> str | None:
    """Resolve a run-app's Railway serviceId by an EXACT name match within a project — a live API
    lookup, never CLI-output text-parsing (the exact scar that made variables-read move to GraphQL
    above). Returns None on any error or no exact match; never partial-matches or guesses."""
    try:
        resp = _graphql(
            """query Services($projectId: String!) {
                 project(id: $projectId) { services { edges { node { id name } } } }
               }""",
            {"projectId": project_id},
            token,
        )
    except Exception:
        return None
    edges = (((resp.get("data") or {}).get("project") or {}).get("services") or {}).get("edges") or []
    for e in edges:
        node = e.get("node") or {}
        if node.get("name") == service_name:
            return node.get("id")
    return None


def _graphql_list_services(project_id: str, token: str) -> dict[str, dict]:
    """Snapshot a project's services as {serviceId: {"name", "createdAt"}} via GraphQL — the basis
    for resolving a just-added service by diffing against a pre-add snapshot (SOF-235), independent
    of `railway add`'s drifting --json stdout. Returns {} on any error (full traceback logged)."""
    try:
        resp = _graphql(
            """query Services($projectId: String!) {
                 project(id: $projectId) { services { edges { node { id name createdAt } } } }
               }""",
            {"projectId": project_id},
            token,
        )
    except Exception:
        logger.exception("deploy-db: GraphQL service-list query failed for project %s", project_id)
        return {}
    edges = (((resp.get("data") or {}).get("project") or {}).get("services") or {}).get("edges") or []
    out: dict[str, dict] = {}
    for e in edges:
        node = e.get("node") or {}
        sid = node.get("id")
        if sid:
            out[sid] = {"name": node.get("name"), "createdAt": node.get("createdAt")}
    return out


def _resolve_new_service(pre_add: dict, project_id: str, token: str) -> tuple[str | None, str | None]:
    """Resolve the (serviceId, serviceName) of the Postgres just created by `railway add`,
    independent of the CLI's stdout, by diffing the live GraphQL service list against a pre-add
    snapshot (SOF-235). A "new" service is one present now but absent from `pre_add`; we keep only
    `Postgres-*` services (what `railway add --database postgres` creates) and, if several appeared,
    pick the newest by `createdAt`. Returns (None, None) when no new Postgres service appeared."""
    post_add = _graphql_list_services(project_id, token)
    candidates = [(sid, node) for sid, node in post_add.items()
                  if sid not in pre_add and (node.get("name") or "").startswith("Postgres")]
    if not candidates:
        return None, None
    candidates.sort(key=lambda c: c[1].get("createdAt") or "", reverse=True)
    sid, node = candidates[0]
    return sid, node.get("name")


def set_app_variable(project_id: str, name: str, value: str, service_id: str | None = None) -> dict:
    """Set one environment variable on a run-app's OWN deployed Railway service (never the deploy
    -DB service) and trigger a redeploy so the live app picks it up — the #107 "provide your own
    key" flow: an operator revisiting a deployed project replaces a mocked provider dep (e.g.
    OPENROUTER_API_KEY) with their real value.

    Resolution order: an explicit `service_id` wins (once a caller has one on record — not
    populated by anything today, kept for when record-deployment reliably captures it); otherwise
    resolve by the deterministic exact name `sf-{project_id}` (the same convention stage-3's SKILL
    uses at `create_service`) via a live GraphQL exact-name lookup.

    FAILS LOUD: every failure returns {"ok": False, "detail": ...} — never a silent no-op. Never
    raises."""
    token = os.environ.get("RAILWAY_TOKEN")
    if not token:
        return {"ok": False, "detail": "RAILWAY_TOKEN not set on the console"}
    railway_project_id = env.runapp_railway_project_id()
    railway_env_id = env.runapp_railway_environment_id()
    if not railway_project_id or not railway_env_id:
        return {"ok": False, "detail": "run-app Railway project/environment not configured "
                                        "(SF_RUNAPP_RAILWAY_PROJECT_IDS / _ENVIRONMENT_IDS)"}
    sid = service_id or _graphql_find_service_by_name(railway_project_id, f"sf-{project_id}", token)
    if not sid:
        return {"ok": False, "detail": f"could not locate the deployed app's Railway service "
                                        f"('sf-{project_id}') — has it been deployed yet?"}
    try:
        resp = _graphql(
            "mutation VariableUpsert($input: VariableUpsertInput!) { variableUpsert(input: $input) }",
            {"input": {"projectId": railway_project_id, "environmentId": railway_env_id,
                       "serviceId": sid, "name": name, "value": value}},
            token,
        )
    except Exception as exc:
        return {"ok": False, "detail": f"graphql error: {exc}"[:200]}
    errors = resp.get("errors") or []
    if errors:
        return {"ok": False, "detail": str(errors)[:200]}
    return {"ok": True, "service_id": sid}

DEPLOY_DB_FILE = "deploy-db.json"


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


def _parse_volume_id(text: str, service_name: str) -> str:
    """Find the volumeId for the named service in `railway volume list --json` output.
    railway service delete does NOT cascade volumes — they must be deleted separately."""
    try:
        d = json.loads(text)
        for v in (d.get("volumes") or []):
            if v.get("serviceName") == service_name and not v.get("deletedAt"):
                return str(v.get("id", ""))
    except Exception:
        pass
    return ""


def _parse_database_url(text: str) -> str | None:
    try:
        d = json.loads(text)
        u = d.get("DATABASE_URL") or d.get("DATABASE_PUBLIC_URL")
        if u:
            return u.rstrip("/")
    except Exception:
        pass
    return _pg_url_from(text)


_PROVISION_URL_POLL_ATTEMPTS = int(os.environ.get("SF_PROVISION_URL_POLL_ATTEMPTS", "10") or 10)
_PROVISION_URL_POLL_SLEEP = float(os.environ.get("SF_PROVISION_URL_POLL_SLEEP", "3") or 3)


def provision(project_id: str, context_dir: str,
              run: Callable[[list[str]], RunResult] = _real_runner,
              sleep: Callable[[float], None] | None = None) -> dict:
    """Provision (or RESUME) this run's Railway Postgres and return + persist its connection info
    {DATABASE_URL, provider, service, service_id, project_id} to context_dir/deploy-db.json.

    Behavior verified against the live railway CLI (5.12.1); SOF-235 made serviceId resolution
    robust to `railway add --json` stdout drift on newer CLIs (5.27/5.28 stopped returning it):
      • `railway add --database postgres` is INTERACTIVE (prompts + hangs headless) — the bare form was
        the original stall. We use `--json`, which on 5.12.1 returned {serviceId, serviceName:"Postgres-XXXX"}.
      • Railway auto-names the service; we CAPTURE its serviceId and read DATABASE_URL from THAT id
        (`railway variables --service <serviceId> --json`) — reading by a guessed name was the bug.
      • serviceId resolution (SOF-235): first TRUST `railway add --json` stdout; if the CLI's --json
        shape drifted and returned no serviceId, RESOLVE it via a live GraphQL diff — snapshot the
        project's service IDs before `add`, then find the newly-appeared `Postgres-*` service after
        (newest by createdAt if several). This survives arbitrary stdout drift and, by adopting the
        just-created service, stops the orphan-Postgres leak that a raised provision used to cause.
      • Railway provisions the Postgres ASYNCHRONOUSLY: DATABASE_URL may be absent on the first
        variables read. We poll with backoff (~10× over ~30s) until it appears.
    IDEMPOTENT: the serviceId is persisted the MOMENT `add` succeeds (before the variables read), so a
    retry REUSES that service (no second `add` → no orphan); a fully-provisioned file is a no-op. Raises
    RuntimeError on failure (the caller records a blocker + counts the attempt against the retry cap)."""
    import time as _time
    _sleep = sleep if sleep is not None else _time.sleep

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
        add_token = os.environ.get("RAILWAY_TOKEN", "")
        # SOF-235: snapshot the project's existing service IDs BEFORE `railway add` so we can
        # resolve the newly-created Postgres by diffing the live GraphQL service list — a source
        # of truth that is INDEPENDENT of `railway add`'s --json stdout, whose shape drifted across
        # CLI versions (5.12.1 → 5.27/5.28) and silently stopped returning `serviceId`. Empty when
        # GraphQL is unavailable (no token / no project id) — we then rely on stdout parsing alone.
        pre_add = (_graphql_list_services(railway_project_id, add_token)
                   if (add_token and railway_project_id) else {})
        # In dev (no RAILWAY_TOKEN), link the CLI to the correct project before `railway add`
        # since `add` has no -p/--project flag. In prod, RAILWAY_TOKEN is project-scoped so
        # no link is needed. Guard on railway_project_id too: if unconfigured, skip silently.
        if not add_token and railway_project_id:
            run(["railway", "link", "-p", railway_project_id])
        add_out = run(["railway", "add", "--database", "postgres", "--json"]).stdout
        # First TRUST the CLI stdout (some versions still return serviceId); FALL BACK to a live
        # GraphQL diff when the --json shape drifted and yielded no id (SOF-235). If the diff finds
        # a just-created Postgres we couldn't otherwise track, we ADOPT it here — that is precisely
        # what stops the orphan leak (the service exists on Railway either way).
        svc_id, svc_name = _parse_added_service(add_out)
        if not svc_id and add_token and railway_project_id:
            svc_id, svc_name = _resolve_new_service(pre_add, railway_project_id, add_token)
        if not svc_id:
            # Genuine failure: neither stdout nor the GraphQL diff surfaced a provisioned service.
            raise RuntimeError(
                "railway add produced no resolvable serviceId (stdout parse and GraphQL diff both "
                f"failed): {(add_out or '')[:200]!r}")
        # Persist the handle BEFORE reading variables: if the read fails, the retry reuses this exact
        # service instead of adding another one. service_id is also the durable teardown handle.
        write_file(context_dir, {"service_id": svc_id, "service": svc_name,
                                 "provider": "railway-postgres", "project_id": project_id})

    # Railway provisions Postgres asynchronously: DATABASE_URL may not appear on the first
    # variables read. Poll until it does (up to ~30s) before giving up.
    # GraphQL path: when RAILWAY_TOKEN + SF_RUNAPP_RAILWAY_ENVIRONMENT_IDS are both set,
    # query via GraphQL (no link-drift). Otherwise fall back to the CLI.
    _token = os.environ.get("RAILWAY_TOKEN", "")
    _env_id = env.runapp_railway_environment_id()
    _use_graphql = bool(_token and railway_project_id and _env_id)
    url = None
    for attempt in range(_PROVISION_URL_POLL_ATTEMPTS):
        if _use_graphql:
            url = _graphql_get_database_url(svc_id, railway_project_id, _env_id, _token)
        else:
            var_out = run(["railway", "variables", "--service", svc_id, "--json"]).stdout
            url = _parse_database_url(var_out)
        if url:
            break
        if attempt < _PROVISION_URL_POLL_ATTEMPTS - 1:
            _sleep(_PROVISION_URL_POLL_SLEEP)
    if not url:
        raise RuntimeError(f"could not obtain a Postgres DATABASE_URL for service {svc_id} "
                           f"after {_PROVISION_URL_POLL_ATTEMPTS} attempts")
    info = {"DATABASE_URL": url, "provider": "railway-postgres",
            "service": svc_name, "service_id": svc_id, "project_id": project_id}
    # Capture the volume ID while the service is still attached (serviceName is set on the volume).
    # This MUST be done before service deletion — after deletion the volume becomes detached
    # (serviceName=null) and is indistinguishable from other orphaned volumes.
    # Best-effort: if the list fails we proceed without volume_id (teardown skips volume delete).
    try:
        vol_out = run(["railway", "volume", "list", "--json"]).stdout or "{}"
        volume_id = _parse_volume_id(vol_out, svc_name or "")
        if volume_id:
            info["volume_id"] = volume_id
    except Exception:
        pass
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
#   • Deleting the service does NOT cascade its volume (live-verified 2026-06-24 — 20 orphaned
#     volumes survived service deletion). Volumes MUST be deleted explicitly after the service.
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


def teardown(service_id: str, volume_id: str = "",
             run: Callable[[list[str]], RunResult] = _real_runner) -> dict:
    """Delete the EXACT captured Railway Postgres service AND its volume. Idempotent. Refuses a
    missing service_id. Returns {service_id, deleted, already_gone, ok, volume_deleted,
    volume_already_gone, detail} — never raises on CLI failure (caller logs).

    Service delete uses the GraphQL API when RAILWAY_TOKEN is set (no link-drift, no -e env
    resolution). Falls back to the CLI when no token is available (local dev without Railway)."""
    sid = (service_id or "").strip()
    if not sid:
        raise ValueError("teardown requires a captured service_id (never a name guess)")
    token = os.environ.get("RAILWAY_TOKEN", "")
    if token:
        # GraphQL path: bearer-token auth, no ambient link state, no -e environment resolution.
        result = _graphql_service_delete(sid, token)
    else:
        # CLI fallback for local dev (no RAILWAY_TOKEN injected outside Railway containers).
        args = ["railway", "service", "delete", "-s", sid]
        project = env.runapp_railway_project_id() or os.environ.get("RAILWAY_PROJECT_ID")
        if project:
            args += ["-p", project]
        args += ["-e", _railway_environment(), "-y"]
        res = run(args)
        out = res.stdout or ""
        combined = (out + "\n" + (getattr(res, "stderr", "") or ""))
        _gone = combined.lower()
        if any(p in _gone for p in ("not found", "no services found", "does not exist", "no service")):
            result = {"service_id": sid, "deleted": False, "already_gone": True, "ok": True,
                      "detail": "already gone"}
        elif res.returncode == 0:
            result = {"service_id": sid, "deleted": True, "already_gone": False, "ok": True,
                      "detail": out[:200]}
        else:
            return {"service_id": sid, "deleted": False, "already_gone": False, "ok": False,
                    "detail": (combined.strip()[:200]) or f"exit {res.returncode}",
                    "volume_deleted": False, "volume_already_gone": not bool(volume_id)}

    # Explicit volume delete: railway service delete does NOT cascade volumes.
    vid = (volume_id or "").strip()
    if not vid:
        result["volume_deleted"] = False
        result["volume_already_gone"] = True   # no volume to track — treat as clean
        return result
    vol_res = run(["railway", "volume", "delete", "--volume", vid, "--yes"])
    vol_out = (vol_res.stdout or "") + "\n" + (getattr(vol_res, "stderr", "") or "")
    _vgone = vol_out.lower()
    if any(p in _vgone for p in ("not found", "does not exist", "no volume")):
        result["volume_deleted"] = False
        result["volume_already_gone"] = True
    elif vol_res.returncode == 0:
        result["volume_deleted"] = True
        result["volume_already_gone"] = False
    else:
        # Volume delete failed — service is gone but volume leaked; log, don't fail
        result["volume_deleted"] = False
        result["volume_already_gone"] = False
        result["detail"] += f" | volume-delete-failed: {vol_out.strip()[:100]}"
    return result


@dataclass
class ReapRecord:
    """One run's deploy-DB teardown candidate. The console builds these from ProjectState
    (service_id = deploy_db_service_id, has_verified_deploy = bool(deploy_url))."""
    project_id: str
    service_id: str
    archived: bool = False
    phase: str = ""
    has_verified_deploy: bool = False
    volume_id: str = ""  # deploy_db_volume_id from ProjectState — must be deleted explicitly


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


def _parse_detached_volumes(text: str) -> list[str]:
    """Return volume IDs that are detached (no serviceName, not deleted) from `railway volume list --json`.
    These are orphans stranded by half-failed provisions — `service delete` skipped them."""
    try:
        d = json.loads(text)
        return [str(v["id"]) for v in (d.get("volumes") or [])
                if not v.get("serviceName") and not v.get("deletedAt") and v.get("id")]
    except Exception:
        return []


def sweep_detached_volumes(run: Callable[[list[str]], RunResult] = _real_runner,
                           log: Callable[[str], None] | None = None,
                           dry_run: bool = False) -> dict:
    """List volumes in the runapp project and delete any that have no attached service.
    These are orphans from half-failed provisions — `service delete` does not cascade them.
    Returns {swept, would_sweep, failed} volume ID lists."""
    log = log or (lambda m: None)
    report: dict = {"swept": [], "would_sweep": [], "failed": []}
    try:
        vol_out = run(["railway", "volume", "list", "--json"]).stdout or "{}"
    except Exception as e:
        log(f"[deploy-db reaper] detached-volume sweep: volume list failed: {e}")
        return report
    orphan_ids = _parse_detached_volumes(vol_out)
    for vid in orphan_ids:
        if dry_run:
            report["would_sweep"].append(vid)
            log(f"[deploy-db reaper] DRY-RUN would sweep detached volume {vid}")
            continue
        del_res = run(["railway", "volume", "delete", "--volume", vid, "--yes"])
        del_out = (del_res.stdout or "") + "\n" + (getattr(del_res, "stderr", "") or "")
        if del_res.returncode == 0 or any(p in del_out.lower()
                                          for p in ("not found", "does not exist", "no volume")):
            report["swept"].append(vid)
            log(f"[deploy-db reaper] swept detached volume {vid}")
        else:
            report["failed"].append({"volume_id": vid, "detail": del_out.strip()[:100]})
            log(f"[deploy-db reaper] FAILED to sweep detached volume {vid}: {del_out.strip()[:100]}")
    return report


def reap(records: Iterable[ReapRecord],
         run: Callable[[list[str]], RunResult] = _real_runner,
         log: Callable[[str], None] | None = None,
         dry_run: bool = False) -> dict:
    """Sweep: tear down the deploy-DB of every reap-eligible run under the configured policy, then
    sweep any detached (orphaned) volumes left by half-failed provisions. DISARMED
    (SF_DEPLOY_DB_TEARDOWN unset/off) or dry_run=True → log what WOULD be reaped, delete nothing.
    Records with no service_id (never provisioned a DB) are skipped. Returns a structured report
    {mode, armed, policy, reaped, would_reap, kept, failed, detached_volumes} — every persisted DB
    and orphaned volume is accounted for."""
    log = log or (lambda m: None)
    mode = teardown_mode()
    armed = mode != "off" and not dry_run
    policy = "ephemeral" if mode == "ephemeral" else "persistent"   # disarmed previews the recommended B
    report: dict = {"mode": mode, "armed": armed, "policy": policy,
                    "reaped": [], "would_reap": [], "kept": [], "failed": [],
                    "detached_volumes": {}}
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
        res = teardown(rec.service_id, volume_id=rec.volume_id, run=run)
        if res["ok"]:
            report["reaped"].append({**base, "reason": reason,
                                     "deleted": res["deleted"], "already_gone": res["already_gone"]})
            log(f"[deploy-db reaper] tore down {rec.service_id} (project {rec.project_id}, "
                f"reason={reason}, {'deleted' if res['deleted'] else 'already gone'})")
        else:
            report["failed"].append({**base, "reason": reason, "detail": res["detail"]})
            log(f"[deploy-db reaper] FAILED to tear down {rec.service_id} "
                f"(project {rec.project_id}): {res['detail']}")
    # Belt-and-suspenders: sweep any detached/orphaned volumes regardless of whether any services
    # were reaped this pass. Catches volumes stranded by half-failed provisions (#51 reduces new
    # stranding but can't eliminate it for provisions that die after volume creation).
    report["detached_volumes"] = sweep_detached_volumes(run=run, log=log, dry_run=not armed)
    return report
