"""Resumable run state.

The orchestrator is a `/loop` session: each re-entry loads state, does a slice of work,
and saves. A crash or loop tick therefore resumes instead of restarting. The store is a
small pluggable interface — JSON on disk for tests, ruflo memory (over MCP) in real runs.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, fields
from typing import Optional, Protocol


class Store(Protocol):
    def read(self, run_id: str) -> Optional[dict]: ...
    def write(self, run_id: str, data: dict) -> None: ...


class JsonFileStore:
    """One JSON file per run, under `dir`."""

    def __init__(self, dir: str):
        self._dir = dir
        os.makedirs(dir, exist_ok=True)

    def _path(self, run_id: str) -> str:
        return os.path.join(self._dir, f"{run_id}.json")

    def read(self, run_id: str) -> Optional[dict]:
        try:
            with open(self._path(run_id)) as f:
                return json.load(f)
        except FileNotFoundError:
            return None

    def write(self, run_id: str, data: dict) -> None:
        with open(self._path(run_id), "w") as f:
            json.dump(data, f, indent=2)


_PERSISTED = {"run_id", "phase", "spent_usd", "repo_url", "deploy_url"}


@dataclass
class RunState:
    run_id: str
    phase: str = "provision"
    spent_usd: float = 0.0
    repo_url: Optional[str] = None
    deploy_url: Optional[str] = None
    _store: Optional[Store] = field(default=None, repr=False, compare=False)

    @classmethod
    def load(cls, run_id: str, store: Store) -> "RunState":
        data = store.read(run_id) or {}
        known = {k: v for k, v in data.items() if k in _PERSISTED}
        known["run_id"] = run_id  # the id is authoritative from the caller, not the file
        return cls(_store=store, **known)

    def save(self) -> None:
        if self._store is None:
            raise RuntimeError("RunState has no store to save to")
        payload = {f.name: getattr(self, f.name) for f in fields(self) if f.name in _PERSISTED}
        self._store.write(self.run_id, payload)
