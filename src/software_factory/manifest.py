"""The dependency/secret manifest the **architecture** phase emits — the contract that
drives provisioning. It declares the services the app needs (compute/storage/auth) and the
app's RUNTIME secrets (e.g. an LLM provider key) that must be obtained from the operator and
wired onto the deployed service — never inherited from the agent's own environment.

Persisted as `manifest.json` at the run base so provision, deploy, and the console/UI all read
one source of truth. This module is pure data + JSON I/O — no thinking, no subprocess.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field


@dataclass
class Service:
    name: str
    provider: str            # "railway" | "supabase" | "vercel"
    role: str = ""           # "compute" | "storage" | "auth" | "frontend"


@dataclass
class AppSecret:
    """A secret the BUILT APP needs at runtime — distinct from infra/deploy tokens.

    `name` is the env var the app reads (e.g. "OPENAI_API_KEY"). Values are NEVER stored here;
    the manifest only declares what's needed so provision can ask the operator for it.
    """

    name: str
    required: bool = True
    scope: str = "app-runtime"
    description: str = ""


@dataclass
class Manifest:
    services: list = field(default_factory=list)      # list[Service]
    app_secrets: list = field(default_factory=list)   # list[AppSecret]

    def to_dict(self) -> dict:
        return {
            "services": [vars(s) for s in self.services],
            "app_secrets": [vars(s) for s in self.app_secrets],
        }

    @staticmethod
    def from_dict(d: dict) -> "Manifest":
        return Manifest(
            services=[Service(**s) for s in d.get("services", [])],
            app_secrets=[AppSecret(**s) for s in d.get("app_secrets", [])],
        )

    def validate(self) -> None:
        """Raise on a malformed manifest — a declared secret with no name would silently
        never get provisioned, which is the exact failure mode we're closing."""
        for s in self.app_secrets:
            if not s.name or not s.name.strip():
                raise ValueError("app_secret with empty name")
            if s.scope != "app-runtime":
                raise ValueError(f"app_secret {s.name!r} has non-app-runtime scope {s.scope!r}")
        names = [s.name for s in self.app_secrets]
        if len(names) != len(set(names)):
            raise ValueError("duplicate app_secret names")


def manifest_path(runs_dir: str, run_id: str) -> str:
    return os.path.join(runs_dir, run_id, "manifest.json")


def write_manifest(runs_dir: str, run_id: str, manifest: Manifest) -> str:
    manifest.validate()
    base = os.path.join(runs_dir, run_id)
    os.makedirs(base, exist_ok=True)
    path = manifest_path(runs_dir, run_id)
    with open(path, "w") as f:
        json.dump(manifest.to_dict(), f, indent=2)
    return path


def load_manifest(runs_dir: str, run_id: str):
    """Return the Manifest, or None if the architecture phase hasn't emitted one yet."""
    path = manifest_path(runs_dir, run_id)
    if not os.path.exists(path):
        return None
    with open(path) as f:
        return Manifest.from_dict(json.load(f))


def required_secret_names(manifest: Manifest) -> list[str]:
    return [s.name for s in manifest.app_secrets if s.required]
