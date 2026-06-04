"""Append-only per-run event bus.

The orchestrator and its agents emit events — phase transitions, artifacts created, agents
spawned/finished, blockers raised, gates awaiting review — so the API server and the canvas can
render the run live without the orchestration doing anything more than a one-line shell `emit`.
Events live at `<runs_dir>/<run_id>/events.jsonl` (on the volume), so they survive redeploys.
"""
from __future__ import annotations

import json
import os
import sys
import time


def _path(runs_dir: str, run_id: str) -> str:
    return os.path.join(runs_dir, run_id, "events.jsonl")


def emit(runs_dir: str, run_id: str, type: str, payload: dict | None = None) -> None:
    base = os.path.join(runs_dir, run_id)
    os.makedirs(base, exist_ok=True)
    rec = {"ts": time.time(), "type": type, "payload": payload or {}}
    with open(_path(runs_dir, run_id), "a") as f:
        f.write(json.dumps(rec) + "\n")


def read_events(runs_dir: str, run_id: str) -> list[dict]:
    p = _path(runs_dir, run_id)
    if not os.path.exists(p):
        return []
    out = []
    with open(p) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except ValueError:
                continue  # torn / garbage line — skip, never break the reader
    return out


def main(argv: list[str]) -> int:
    # python -m software_factory.events emit <runs_dir> <run_id> <type> [json_payload]
    if len(argv) >= 5 and argv[0] == "emit":
        _, runs_dir, run_id, etype = argv[:4]
        payload = json.loads(argv[4]) if len(argv) > 4 else None
        emit(runs_dir, run_id, etype, payload)
        return 0
    if len(argv) == 4 and argv[0] == "emit":
        emit(argv[1], argv[2], argv[3])
        return 0
    print("usage: events emit <runs_dir> <run_id> <type> [json_payload]", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
