"""Review gates — the "sit idle until reviewed" mechanism for key phases.

`await_gate` emits `awaiting_review` and blocks (poll-sleeping) until the gate's `.ok` file
appears; the dashboard's Continue button calls `clear_gate` (via the server) to write it. Sleep
is injected so the block is testable. Cost stays bounded while waiting — it's just a sleep loop,
no model calls.
"""
from __future__ import annotations

import os
import time
from typing import Callable

from . import events


def _ok_path(runs_dir: str, run_id: str, gate: str) -> str:
    return os.path.join(runs_dir, run_id, "gates", f"{gate}.ok")


def clear_gate(runs_dir: str, run_id: str, gate: str) -> None:
    p = _ok_path(runs_dir, run_id, gate)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    open(p, "w").close()
    events.emit(runs_dir, run_id, "resumed", {"gate": gate})


def is_cleared(runs_dir: str, run_id: str, gate: str) -> bool:
    return os.path.exists(_ok_path(runs_dir, run_id, gate))


def pending_gate(runs_dir: str, run_id: str):
    """The most recent awaiting_review gate that hasn't been cleared, else None."""
    pending = None
    for e in events.read_events(runs_dir, run_id):
        if e.get("type") == "awaiting_review":
            g = (e.get("payload") or {}).get("gate")
            if g and not is_cleared(runs_dir, run_id, g):
                pending = g
            elif g and is_cleared(runs_dir, run_id, g):
                pending = None
    return pending


def await_gate(
    runs_dir: str,
    run_id: str,
    gate: str,
    interval: float = 3.0,
    max_wait: float = 3600.0,
    sleep: Callable[[float], None] = time.sleep,
) -> bool:
    """Pause for review: emit awaiting_review, block until cleared. True if cleared, False on timeout."""
    if is_cleared(runs_dir, run_id, gate):
        return True
    events.emit(runs_dir, run_id, "awaiting_review", {"gate": gate})
    waited = 0.0
    while waited < max_wait:
        sleep(interval)
        waited += interval
        if is_cleared(runs_dir, run_id, gate):
            events.emit(runs_dir, run_id, "resumed", {"gate": gate})
            return True
    return False
