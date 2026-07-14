#!/usr/bin/env python3
"""SOF-159/167: read-only reconciliation reporter for orphaned deploy Postgres in the software-factory
projects Railway project.

The stage-3 deploy-DB provisioner can leak a Postgres whose serviceId handle was never captured
(SOF-159: `railway add` killed after resource creation) — a DB no project row or console reaper
knows about. This tool ENUMERATES the SFP Railway Postgres services IN ONE ENVIRONMENT, ATTRIBUTES
each to a project where it can, and FLAGS the ones it can't. It NEVER deletes anything — disposal of
a data-carrying unattributable DB is an operator decision (CLAUDE.md #3: gates check facts, humans decide).

Attribution (deterministic, no timing heuristics):
  1. app-service reference — a live `sf-project-<pid>` service whose DATABASE_URL host resolves to
     this Postgres → attributed to <pid>. If <pid> is in --live-pids the DB is PROTECTED.
  2. otherwise UNATTRIBUTABLE → orphan candidate (operator disposal only).

Exclusivity guard (the 2026-07-11 sweep lesson): a DB referenced by ANY live/preserved service is
PROTECTED even if another referrer is dead. Under-report before you over-delete.

ENV-SCOPED (SOF-167): enumeration is via the GraphQL `environment(id:)` service list — NOT
project-wide `railway status --json`, which on a multi-env project (software-factory-projects has
prod 3c8117be AND staging 92e3ec6c) mixes in the OTHER env's live services and would mis-flag them
(e.g. Nick's prod Postgres) as orphans. Every service the reporter sees provably belongs to
--environment. Uses deploy_db._graphql (post-SOF-160: Project-Access-Token header + non-default UA).

Auth: requires RAILWAY_TOKEN = a Railway PROJECT token scoped to --environment (the same token the
console/harness holds for that env). The reporter self-checks the token identifies exactly
--project/--environment and hard-fails (REFUSING) on any mismatch — never a guess.

Usage:
  RAILWAY_TOKEN=<project token for the env> python3 scripts/reconcile_orphan_dbs.py \
      --project <SFP_ID> --environment <ENV_ID> --live-pids project-...[,project-...]
"""
from __future__ import annotations

import argparse
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from software_factory import deploy_db  # noqa: E402  — _graphql (Project-Access-Token + UA, SOF-160)


def _gql(query: str, variables: dict) -> dict:
    """One env-scoped GraphQL call via deploy_db._graphql. REFUSES (SystemExit) with no RAILWAY_TOKEN
    or on any GraphQL error — this is a pre-delete gate; a partial/ambiguous read must hard-fail,
    never silently under-report."""
    token = os.environ.get("RAILWAY_TOKEN")
    if not token:
        raise SystemExit("REFUSING: RAILWAY_TOKEN (a Railway PROJECT token scoped to --environment) "
                         "is required for env-scoped enumeration.")
    resp = deploy_db._graphql(query, variables, token)
    if resp.get("errors"):
        raise SystemExit(f"REFUSING: Railway GraphQL error: {str(resp['errors'])[:200]}")
    return resp.get("data") or {}


def _assert_token_scope(project: str, environment: str) -> None:
    """The REFUSING guard (replaces the old linked-project assert): the RAILWAY_TOKEN must identify
    EXACTLY --project/--environment, else the whole enumeration is against the wrong scope. Strictly
    stronger than the ambient-link assert — the token itself defines what's visible."""
    pt = _gql("query { projectToken { projectId environmentId } }", {}).get("projectToken") or {}
    if pt.get("projectId") != project or pt.get("environmentId") != environment:
        raise SystemExit(
            f"REFUSING: RAILWAY_TOKEN identifies project={pt.get('projectId')!r}/env={pt.get('environmentId')!r}, "
            f"not --project {project!r} / --environment {environment!r}. Set the token for the intended env.")


def _services(environment: str) -> dict[str, str]:
    """{service_id: name} for every service IN this environment (env-scoped — the SOF-167 fix)."""
    d = _gql("query($e:String!){ environment(id:$e){ serviceInstances{ edges{ node{ serviceId serviceName } } } } }",
             {"e": environment})
    edges = ((d.get("environment") or {}).get("serviceInstances") or {}).get("edges", [])
    return {e["node"]["serviceId"]: e["node"]["serviceName"] for e in edges}


def _svc_vars(project: str, environment: str, sid: str) -> dict:
    """All resolved variables for one service in this env (env-scoped). DATABASE_URL carries a
    password — callers keep ONLY its host; the rest read here are non-secret domain/proxy fields."""
    d = _gql("""query($p:String!,$s:String!,$e:String!){
                  variables(projectId:$p, serviceId:$s, environmentId:$e) }""",
             {"p": project, "s": sid, "e": environment})
    return d.get("variables") or {}


def _host(url: str) -> str:
    """Strip credentials + path from a postgres URL, keep host:port only (never keep the password)."""
    return re.sub(r"/.*$", "", re.sub(r"^[a-z]+://[^@]*@", "", url or "")).strip()


def _volumes(environment: str) -> dict[str, dict]:
    """{service_id: {name,id,used_mb}} for volumes IN this env (env-scoped). Best-effort: any read
    error yields {} so a missing entry is reported 'unknown', never treated as 'no volume'."""
    try:
        token = os.environ["RAILWAY_TOKEN"]
        resp = deploy_db._graphql(
            "query($e:String!){ environment(id:$e){ volumeInstances{ edges{ node{ serviceId currentSizeMB volume{ id name } } } } } }",
            {"e": environment}, token)
        edges = (((resp.get("data") or {}).get("environment") or {}).get("volumeInstances") or {}).get("edges", [])
        out = {}
        for e in edges:
            n = e["node"]; v = n.get("volume") or {}
            out[n.get("serviceId")] = {"name": v.get("name"), "id": v.get("id"),
                                       "used_mb": round(n.get("currentSizeMB") or 0)}
        return out
    except Exception:
        return {}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", required=True, help="SFP Railway project id")
    ap.add_argument("--environment", required=True, help="Railway environment id to scope to (REQUIRED)")
    ap.add_argument("--live-pids", default="", help="comma-sep console-active project ids (exclusivity guard)")
    a = ap.parse_args()
    live = {p.strip() for p in a.live_pids.split(",") if p.strip()}

    _assert_token_scope(a.project, a.environment)          # REFUSING guard: token ⇔ --project/--environment
    svcs = _services(a.environment)                        # env-scoped enumeration
    by_name = {n: i for i, n in svcs.items()}
    pg = {n: i for n, i in by_name.items() if n.startswith("Postgres")}
    apps = {n: i for n, i in by_name.items() if n.startswith("sf-project-")}

    # Build Postgres lookup keys from non-secret fields: private domain + proxy domain:port.
    pg_by_priv, pg_by_proxy = {}, {}
    for name, sid in pg.items():
        v = _svc_vars(a.project, a.environment, sid)
        priv = v.get("RAILWAY_PRIVATE_DOMAIN", "")
        pdom, pport = v.get("RAILWAY_TCP_PROXY_DOMAIN", ""), v.get("RAILWAY_TCP_PROXY_PORT", "")
        if priv:
            pg_by_priv[priv] = name
        if pdom and pport:
            pg_by_proxy[f"{pdom}:{pport}"] = name

    # Map each app service to the Postgres it references (via DATABASE_URL host, creds stripped).
    referrers: dict[str, list[tuple[str, bool]]] = {n: [] for n in pg}
    for aname, asid in apps.items():
        pid_full = "project-" + aname[len("sf-project-"):]
        host = _host(_svc_vars(a.project, a.environment, asid).get("DATABASE_URL", ""))
        target = pg_by_priv.get(host.split(":")[0]) or pg_by_proxy.get(host)
        if target:
            referrers[target].append((pid_full, pid_full in live))

    vols = _volumes(a.environment)

    protect, left_attrib, orphans = [], [], []
    for name in sorted(pg):
        refs = referrers[name]
        v = vols.get(pg[name], {"name": "unknown", "id": "unknown", "used_mb": "?"})
        row = {"pg": name, "id": pg[name], "vol": v["name"], "vol_id": v["id"], "used_mb": v["used_mb"],
               "refs": refs}
        if any(is_live for _, is_live in refs):
            protect.append(row)
        elif refs:
            left_attrib.append(row)
        else:
            orphans.append(row)

    def _fmt(rows):
        for r in rows:
            rr = ",".join(f"{p}{'(LIVE)' if l else ''}" for p, l in r["refs"]) or "—"
            print(f"  {r['pg']:20} svc={r['id']:38} vol={str(r['vol']):22} used={str(r['used_mb']):>6}MB  refs={rr}")

    print(f"SFP Postgres reconciliation — env {a.environment} — {len(pg)} DBs, {len(apps)} app services, "
          f"live_pids={sorted(live)}\n")
    print(f"PROTECT — referenced by a LIVE project ({len(protect)}):")
    _fmt(protect)
    print(f"\nLEFT — attributed to a non-live/preserved service, not an orphan ({len(left_attrib)}):")
    _fmt(left_attrib)
    print(f"\nORPHAN CANDIDATES — no referring service, unattributable ({len(orphans)}):")
    _fmt(orphans)
    total = sum(r["used_mb"] for r in orphans if isinstance(r["used_mb"], int))
    print(f"\n{len(orphans)} orphan candidates, ~{total}MB written data. Disposal is an operator decision.")
    # Machine-readable candidate list for a subsequent (separately-authorized) delete step.
    print("\nORPHAN_CANDIDATE_IDS=" + ",".join(f"{r['id']}|{r['vol_id']}" for r in orphans))
    return 0


if __name__ == "__main__":
    sys.exit(main())
