"""GitHub repo reaper — sweep factory-created repos whose project is confirmed dead and delete them.

SAFETY MODEL — four independent guards before any delete fires:
  1. Repo name matches the factory suffix pattern: <name>-[0-9a-f]{8,16}
  2. Suffix maps to a CONFIRMED project row in the DB; no-match repos are LOG-ONLY
     (never auto-deleted — a real repo could end in hex, and we can't prove provenance).
  3. Project is confirmed dead: archived | stopped-without-deploy (same states the deploy-DB
     reaper kills under its persistent policy — one coherent "project dead → clean everything").
  4. SF_GITHUB_REPO_REAPER=on (default off — ships disarmed, never deletes until armed).

Identification convention (#89): factory Stage 3 names repos as "<slug>-<project_id_prefix>"
where the prefix is the first 8 hex chars of the project_id hex part (e.g. project-4849c0d8…
→ suffix "4849c0d8"). Regex accepts 8–16 chars to cover both old and widened IDs.

Reap policy mirrors deploy_db.py persistent mode:
  owner_repo_shared=True → KEEP  (SOF-3: the project owner has real GitHub access to this repo —
                                   never destroy it out from under them, regardless of archived/stopped)
  archived=True          → REAP  (even with a live deploy — discarded is discarded)
  stopped + no_deploy    → REAP  (stopped run that never shipped → no reason to keep repo)
  stopped + has_deploy   → KEEP  (live demo; relaunch makes a fresh repo anyway)
  done (any)             → KEEP  (completed run; demo may still be linked)
  active phase           → KEEP  (run in progress)
  no DB match            → LOG-ONLY (unknown_repos in report, never auto-deleted)
"""
from __future__ import annotations

import json
import os
import re
import subprocess
from dataclasses import dataclass
from typing import Callable

# First 8–16 lowercase hex chars after a hyphen, at the end of the name.
# Anchored with $ so "my-repo-abcd1234" matches but "my-repo-abcd1234-extra" doesn't.
FACTORY_REPO_SUFFIX_RE = re.compile(r"-([0-9a-f]{8,16})$")

# Canonical suffix length written by the factory Stage 3 provision node.
FACTORY_REPO_SUFFIX_LENGTH = 8


@dataclass
class RunResult:
    stdout: str
    returncode: int
    stderr: str = ""


@dataclass
class ReapRecord:
    project_id: str           # confirmed project_id that matched the suffix
    repo_full_name: str       # "org/repo-name"
    archived: bool
    phase: str
    has_verified_deploy: bool
    owner_repo_shared: bool = False  # SOF-3: owner holds a real GitHub collaborator invite on this repo


def github_reaper_mode() -> str:
    """'on' when SF_GITHUB_REPO_REAPER=on; 'off' for everything else (disarmed by default)."""
    v = (os.environ.get("SF_GITHUB_REPO_REAPER") or "").strip().lower()
    return "on" if v == "on" else "off"


def _reap_reason(rec: ReapRecord) -> str | None:
    """Return a reap-reason string when the repo should be deleted; None to keep.

    Policy mirrors deploy_db._reap_reason (persistent mode) so the two reapers move in lockstep:
    a project whose DB service is reaped will also have its repo reaped on the same sweep."""
    if rec.owner_repo_shared:
        return None  # SOF-3: never reap a repo the owner has real access to, archived or not
    if rec.archived:
        return "archived"
    if rec.phase == "stopped" and not rec.has_verified_deploy:
        return "stopped-without-deploy"
    return None


def _real_runner(args: list[str]) -> RunResult:
    proc = subprocess.run(["gh", *args], capture_output=True, text=True)
    return RunResult(stdout=proc.stdout, returncode=proc.returncode, stderr=proc.stderr or "")


def list_org_repos(org: str, run: Callable[[list[str]], RunResult] = _real_runner) -> list[dict]:
    """Return repos in org as [{"name": str, "isArchived": bool}].
    Capped at 200 — well above expected factory scale for ibraheem-tenexity."""
    result = run(["repo", "list", org, "--json", "name,isArchived", "--limit", "200"])
    if result.returncode != 0 or not result.stdout.strip():
        return []
    try:
        return json.loads(result.stdout) or []
    except Exception:
        return []


def delete_repo(repo_full_name: str, run: Callable[[list[str]], RunResult] = _real_runner) -> dict:
    """Delete a single GitHub repo. Returns {ok, deleted, already_gone}. Idempotent."""
    if not repo_full_name or "/" not in repo_full_name:
        raise ValueError(f"invalid repo_full_name: {repo_full_name!r}")
    result = run(["repo", "delete", repo_full_name, "--yes"])
    combined = (result.stdout + " " + result.stderr).strip().lower()
    if result.returncode == 0:
        return {"ok": True, "deleted": True, "already_gone": False}
    if "not found" in combined or "could not resolve" in combined:
        return {"ok": True, "deleted": False, "already_gone": True}
    return {"ok": False, "deleted": False, "already_gone": False,
            "error": (result.stdout + result.stderr).strip()[:200]}


def reap(records: list[ReapRecord], run: Callable[[list[str]], RunResult] = _real_runner,
         log: Callable = print, dry_run: bool = False) -> dict:
    """Apply the policy gate to records and optionally delete repos.

    Returns a structured report: {armed, mode, reaped, kept, would_reap, failed}.
    dry_run=True forces preview regardless of SF_GITHUB_REPO_REAPER."""
    mode = github_reaper_mode()
    armed = mode == "on" and not dry_run
    reaped, kept, would_reap, failed = [], [], [], []
    for rec in records:
        reason = _reap_reason(rec)
        summary = {"project_id": rec.project_id, "repo": rec.repo_full_name,
                   "phase": rec.phase, "archived": rec.archived,
                   "has_verified_deploy": rec.has_verified_deploy}
        if reason is None:
            kept.append(summary)
            continue
        if armed:
            result = delete_repo(rec.repo_full_name, run=run)
            if result["ok"]:
                log(f"[github-reaper] reaped {rec.repo_full_name} "
                    f"(project {rec.project_id}, reason={reason})")
                reaped.append({**summary, "reason": reason, "already_gone": result["already_gone"]})
            else:
                log(f"[github-reaper] FAILED to reap {rec.repo_full_name}: "
                    f"{result.get('error', '')}")
                failed.append({**summary, "reason": reason})
        else:
            log(f"[github-reaper] DRY-RUN would reap {rec.repo_full_name} "
                f"(project {rec.project_id}, reason={reason})")
            would_reap.append({**summary, "reason": reason})
    return {"armed": armed, "mode": mode, "reaped": reaped, "kept": kept,
            "would_reap": would_reap, "failed": failed}
