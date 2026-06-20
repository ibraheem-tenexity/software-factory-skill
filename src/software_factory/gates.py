"""Review gates — the "sit idle until reviewed" mechanism for key phases.

Backed by the per-project datastore (the `gates` table in project store), not files or events.
`await_gate` marks a gate `awaiting` and blocks (poll-sleeping) until it becomes `cleared`;
the dashboard's Continue button calls `clear_gate` (via the server) to clear it. Sleep is
injected so the block is testable. Cost stays bounded while waiting — just a sleep loop.
"""
from __future__ import annotations

import time
from typing import Callable

from . import db as _db


def _db_for(projects_dir: str, project_id: str) -> "_db.ProjectStore":
    return _db.ProjectStore(_db.db_path(projects_dir, project_id))


def clear_gate(projects_dir: str, project_id: str, gate: str) -> None:
    _db_for(projects_dir, project_id).set_gate(gate, "cleared")


def is_cleared(projects_dir: str, project_id: str, gate: str) -> bool:
    return _db_for(projects_dir, project_id).gate_status().get(gate) == "cleared"


def pending_gate(projects_dir: str, project_id: str):
    """The gate currently `awaiting` review (not yet cleared), else None."""
    for name, status in _db_for(projects_dir, project_id).gate_status().items():
        if status == "awaiting":
            return name
    return None


def await_gate(
    projects_dir: str,
    project_id: str,
    gate: str,
    interval: float = 3.0,
    max_wait: float = 3600.0,
    sleep: Callable[[float], None] = time.sleep,
) -> bool:
    """Pause for review: mark the gate `awaiting`, block until `cleared`. True if cleared, False on timeout."""
    if is_cleared(projects_dir, project_id, gate):
        return True
    _db_for(projects_dir, project_id).set_gate(gate, "awaiting")
    waited = 0.0
    while waited < max_wait:
        sleep(interval)
        waited += interval
        if is_cleared(projects_dir, project_id, gate):
            return True
    return False
