"""Ephemeral per-project workspace lifecycle: create -> build inside it -> publish -> destroy.

Each run builds in its own disposable directory at `<projects_dir>/<project_id>/workspace/`. After the
work is published to durable surfaces (GitHub + the live URL) and the run reaches a terminal
state, the workspace is deleted. Proof artifacts (per-project Postgres rows: agents, tickets,
projectstate) are durable and unaffected by teardown.

`destroy` is the only destructive op in the skill, so it is gated: it refuses to remove anything
that lacks our sentinel (i.e. a dir we didn't create) or that sits outside the runs dir.
"""
from __future__ import annotations

import os
import shutil

SENTINEL = ".sf-workspace"


def create(projects_dir: str, project_id: str) -> str:
    path = os.path.join(projects_dir, project_id, "workspace")
    os.makedirs(path, exist_ok=True)
    open(os.path.join(path, SENTINEL), "w").close()
    return path


def is_ours(path: str) -> bool:
    return os.path.isfile(os.path.join(path, SENTINEL))


def destroy(path: str, projects_dir: str) -> None:
    path_abs = os.path.realpath(path)
    projects_abs = os.path.realpath(projects_dir)
    # Gate 1: must be inside the runs dir we were told to manage.
    if os.path.commonpath([path_abs, projects_abs]) != projects_abs or path_abs == projects_abs:
        raise ValueError(f"refusing to destroy {path!r}: not under runs dir {projects_dir!r}")
    # Gate 2: must carry our sentinel — never delete a dir we didn't create.
    if not is_ours(path_abs):
        raise ValueError(f"refusing to destroy {path!r}: no {SENTINEL} sentinel (not ours)")
    shutil.rmtree(path_abs)
