"""Ephemeral per-run workspace lifecycle: create -> build inside it -> publish -> destroy.

Each run builds in its own disposable directory at `<runs_dir>/<run_id>/workspace/`. After the
work is published to durable surfaces (GitHub + the live URL) and the run reaches a terminal
state, the workspace is deleted. Proof artifacts (agents.db, tickets.db, runstate) live at the
run BASE beside the workspace, so teardown never touches them.

`destroy` is the only destructive op in the skill, so it is gated: it refuses to remove anything
that lacks our sentinel (i.e. a dir we didn't create) or that sits outside the runs dir.
"""
from __future__ import annotations

import os
import shutil

SENTINEL = ".sf-workspace"


def create(runs_dir: str, run_id: str) -> str:
    path = os.path.join(runs_dir, run_id, "workspace")
    os.makedirs(path, exist_ok=True)
    open(os.path.join(path, SENTINEL), "w").close()
    return path


def is_ours(path: str) -> bool:
    return os.path.isfile(os.path.join(path, SENTINEL))


def destroy(path: str, runs_dir: str) -> None:
    path_abs = os.path.realpath(path)
    runs_abs = os.path.realpath(runs_dir)
    # Gate 1: must be inside the runs dir we were told to manage.
    if os.path.commonpath([path_abs, runs_abs]) != runs_abs or path_abs == runs_abs:
        raise ValueError(f"refusing to destroy {path!r}: not under runs dir {runs_dir!r}")
    # Gate 2: must carry our sentinel — never delete a dir we didn't create.
    if not is_ours(path_abs):
        raise ValueError(f"refusing to destroy {path!r}: no {SENTINEL} sentinel (not ours)")
    shutil.rmtree(path_abs)
