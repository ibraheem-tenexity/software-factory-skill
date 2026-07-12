#!/usr/bin/env python3
"""SOF-159: read-only reconciliation reporter for orphaned deploy Postgres in the software-factory
projects Railway project.

The stage-3 deploy-DB provisioner can leak a Postgres whose serviceId handle was never captured
(SOF-159: `railway add` killed after resource creation) — a DB no project row or console reaper
knows about. This tool ENUMERATES the SFP Railway Postgres services, ATTRIBUTES each to a project
where it can, and FLAGS the ones it can't. It NEVER deletes anything — disposal of a data-carrying
unattributable DB is an operator decision (CLAUDE.md #3: gates check facts, humans decide).

Attribution (deterministic, no timing heuristics):
  1. app-service reference — a live `sf-project-<pid>` service whose DATABASE_URL host resolves to
     this Postgres → attributed to <pid>. If <pid> is in --live-pids the DB is PROTECTED.
  2. (future) deterministic name — once provisioning names DBs `sf-db-<pid>` (SOF-159 prevention),
     the name self-attributes; this reporter already matches that prefix if present.
  3. otherwise UNATTRIBUTABLE → orphan candidate (operator disposal only).

Exclusivity guard (the 2026-07-11 sweep lesson): a DB referenced by ANY live/preserved service is
PROTECTED even if another referrer is dead. Under-report before you over-delete.

Enumeration is BY SERVICE via `railway status --json` — deliberately NOT `railway volume list`,
which was observed to silently return a partial set (16/20) during the sweep.

Auth: uses the ambient `railway` CLI session (account token). The injected RAILWAY_TOKEN cannot be
used — it 403s on the Railway GraphQL API (SOF-160); this tool's future auto-delete sibling depends
on SOF-160's token fix landing.

Usage:
  python3 scripts/reconcile_orphan_dbs.py --project <SFP_ID> --env <ENV_ID> \
      --live-pids project-38c082661e5740da[,project-...]
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys


def _run(args: list[str]) -> str:
    """Run a railway CLI command, return stdout. Read-only calls only."""
    p = subprocess.run(args, capture_output=True, text=True, timeout=60)
    if p.returncode != 0:
        raise RuntimeError(f"{' '.join(args)} -> rc={p.returncode}: {p.stderr[:200]}")
    return p.stdout


def _services(project: str) -> dict[str, str]:
    """{service_id: name} for every service in the project (via status --json).

    `railway status` reports the LINKED project and silently ignores a project arg — so on a tool
    that emits DELETE candidates we do NOT trust the ambient link: assert the linked project id
    equals the caller's --project and hard-fail on any mismatch (the silent-wrong-target class that
    burned a session today). `_var`/`_volumes` operate on this same linked project, so this one
    assertion guards the whole enumeration."""
    d = json.loads(_run(["railway", "status", "--json"]))
    linked = d.get("id")
    if linked != project:
        raise SystemExit(f"REFUSING: railway is linked to project {linked!r}, not --project {project!r}. "
                         f"`railway link` to the intended project (or fix --project) and re-run.")
    return {e["node"]["id"]: e["node"]["name"] for e in d.get("services", {}).get("edges", [])}


def _var(project: str, env: str, sid: str, key: str) -> str:
    """One variable's value for a service (--kv), or '' if absent. Callers must only read
    NON-SECRET keys through this in logs; DATABASE_URL is read but only its host is ever kept."""
    out = _run(["railway", "variables", "-p", project, "-e", env, "--service", sid, "--kv"])
    for line in out.splitlines():
        if line.startswith(key + "="):
            return line[len(key) + 1:]
    return ""


def _host(url: str) -> str:
    """Strip credentials + path from a postgres URL, keep host:port only (never keep the password)."""
    return re.sub(r"/.*$", "", re.sub(r"^[a-z]+://[^@]*@", "", url)).strip()


def _volumes() -> dict[str, dict]:
    """{serviceName: {name,id,used_mb}} from volume list --json (best-effort; known to under-report,
    so a missing entry is reported as 'unknown', never treated as 'no volume')."""
    try:
        vols = json.loads(_run(["railway", "volume", "list", "--json"])).get("volumes", [])
    except Exception:
        return {}
    return {v["serviceName"]: {"name": v.get("name"), "id": v.get("id"),
                               "used_mb": round(v.get("currentSizeMB") or 0)}
            for v in vols if v.get("serviceName")}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", required=True, help="SFP Railway project id")
    ap.add_argument("--env", required=True, help="Railway environment id")
    ap.add_argument("--live-pids", default="", help="comma-sep console-active project ids (exclusivity guard)")
    a = ap.parse_args()
    live = {p.strip() for p in a.live_pids.split(",") if p.strip()}

    svcs = _services(a.project)
    by_name = {n: i for i, n in svcs.items()}
    pg = {n: i for n, i in by_name.items() if n.startswith("Postgres")}
    apps = {n: i for n, i in by_name.items() if n.startswith("sf-project-")}

    # Build Postgres lookup keys from non-secret fields: private domain + proxy domain:port.
    pg_by_priv, pg_by_proxy = {}, {}
    for name, sid in pg.items():
        priv = _var(a.project, a.env, sid, "RAILWAY_PRIVATE_DOMAIN")
        pdom = _var(a.project, a.env, sid, "RAILWAY_TCP_PROXY_DOMAIN")
        pport = _var(a.project, a.env, sid, "RAILWAY_TCP_PROXY_PORT")
        if priv:
            pg_by_priv[priv] = name
        if pdom and pport:
            pg_by_proxy[f"{pdom}:{pport}"] = name

    # Map each app service to the Postgres it references (via DATABASE_URL host, creds stripped).
    referrers: dict[str, list[tuple[str, bool]]] = {n: [] for n in pg}
    for aname, asid in apps.items():
        pid = aname[len("sf-project-"):]
        pid_full = "project-" + pid
        host = _host(_var(a.project, a.env, asid, "DATABASE_URL"))
        hostname = host.split(":")[0]
        target = pg_by_priv.get(hostname) or pg_by_proxy.get(host)
        if target:
            referrers[target].append((pid_full, pid_full in live))

    vols = _volumes()

    protect, left_attrib, orphans = [], [], []
    for name in sorted(pg):
        refs = referrers[name]
        v = vols.get(name, {"name": "unknown", "id": "unknown", "used_mb": "?"})
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

    print(f"SFP Postgres reconciliation — {len(pg)} DBs, {len(apps)} app services, live_pids={sorted(live)}\n")
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
