#!/usr/bin/env python3
"""SOF-93 interim runner: polls the deployed console's own API for benchmark-owned runs (owner ==
run_autopsy.BENCHMARK_OWNER) and autopsies any newly-terminal one it hasn't already processed.

Swaps to reading the SOF-92 harness's JSON reports directly once it lands — run_autopsy.classify_run
itself does not change; only this script's report-assembly step (build_report_from_console) gets
replaced by a file read.

Usage: python3 scripts/run_autopsy_scan.py <console_base_url> <service_token>
Requires DATABASE_URL/SF_STATE_DB_URL set (the dedup ledger lives in the same Postgres as the
console). LINEAR_API_KEY/SF_LINEAR_TEAM_ID are optional — absent, filing degrades honestly and the
signature is still recorded (see run_autopsy.py).
"""
from __future__ import annotations

import json
import sys
import urllib.request

sys.path.insert(0, "src")

from software_factory.run_autopsy import (  # noqa: E402
    BENCHMARK_OWNER, RunAutopsyStore, autopsy_and_file, build_report_from_console,
)


def _get(url: str, token: str) -> dict:
    req = urllib.request.Request(url, headers={"X-SF-Service-Token": token})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read())


def _is_terminal(list_entry: dict, status: dict) -> bool:
    return bool(
        status.get("done")
        or status.get("crashed_at_node")
        or status.get("held")
        or list_entry.get("budget_stopped")
    )


def main(base: str, token: str) -> None:
    store = RunAutopsyStore()
    projects = _get(f"{base}/api/projects", token)["projects"]
    benchmark = [p for p in projects if (p.get("owner") or "") == BENCHMARK_OWNER]
    print(f"[run-autopsy] {len(benchmark)} benchmark-owned project(s) found")
    for entry in benchmark:
        pid = entry["project_id"]
        if store.already_processed(pid):
            continue
        status = _get(f"{base}/api/projects/{pid}", token)
        if not _is_terminal(entry, status):
            continue  # still running; a later scan will pick it up once it lands terminal
        events = _get(f"{base}/api/projects/{pid}/events", token)["events"]
        report = build_report_from_console(entry, status, events)
        record = autopsy_and_file(report, store)
        print(f"[run-autopsy] {pid}: {record.classification} — {record.reason}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(1)
    main(sys.argv[1], sys.argv[2])
