"""SOF-165 — the thin Recovery Action service (tier-2 recovery). Module-level functions over
`RecoveryActionRepository`, so every producer/resolver — mark_stage_crashed (console), the SOF-164
silence seam (poller), autopsy_and_file (run_autopsy), resume/archive — calls ONE primitive instead
of the two parallel ad hoc mechanisms we had (Recovery-bar phase vs benchmark-only Linear filing).

Minimum machinery: no new subsystem, just open/resolve/list over one table. The producers stay
ADDITIVE — they keep their existing external behavior (phase='crashed', Linear filing, the
Recovery-bar) unchanged; this only unifies the underlying RECORD. Best-effort by design: a recovery
bookkeeping hiccup must never break the lifecycle write that triggered it (mirrors _maybe_teardown
_deploy_db), so every call is wrapped and swallowed with a log — an unrecorded action is strictly
better than a crashed crash-handler.

Resolutions: restored | delegated | false_positive | blocked | escalated | cancelled.
"""
from __future__ import annotations

import time

from .log import get_logger
from .repositories._exec import GlobalExec
from .repositories.recovery_actions import RecoveryActionRepository

logger = get_logger(__name__)


def _repo(repo: RecoveryActionRepository | None) -> RecoveryActionRepository:
    return repo or RecoveryActionRepository(GlobalExec())


def open_recovery_action(project_id: str, kind: str, cause: str = "", evidence: dict | None = None,
                         owner: str = "auto", *, repo: RecoveryActionRepository | None = None) -> None:
    """Open (or idempotently refresh) the OPEN recovery action for (project_id, kind). Best-effort."""
    try:
        _repo(repo).open(project_id, kind, cause, evidence or {}, owner, time.time())
    except Exception:
        logger.exception("[recovery] open(%s, %s) failed — action not recorded (non-fatal)", project_id, kind)


def resolve_recovery_actions(project_id: str, resolution: str, kind: str | None = None,
                             *, repo: RecoveryActionRepository | None = None) -> None:
    """Resolve this run's open action(s). Idempotent no-op when none are open — callers fire it
    freely on done / resume / archive. Best-effort."""
    try:
        _repo(repo).resolve_open(project_id, resolution, time.time(), kind=kind)
    except Exception:
        logger.exception("[recovery] resolve(%s, %s) failed (non-fatal)", project_id, resolution)


def open_recovery_actions_for(project_id: str, *, repo: RecoveryActionRepository | None = None) -> list[dict]:
    try:
        return _repo(repo).open_for(project_id)
    except Exception:
        logger.exception("[recovery] open_for(%s) failed (non-fatal)", project_id)
        return []


def recovery_actions_for(project_id: str, limit: int = 50,
                         *, repo: RecoveryActionRepository | None = None) -> list[dict]:
    """SOF-165 PR2: full recovery-action history for a run (open + resolved), newest first — the
    read surface behind GET /api/projects/{pid}/recovery-actions. Best-effort → [] on any error."""
    try:
        return _repo(repo).by_project(project_id, limit)
    except Exception:
        logger.exception("[recovery] by_project(%s) failed (non-fatal)", project_id)
        return []


def open_recovery_action_count(project_id: str, *, repo: RecoveryActionRepository | None = None) -> int:
    """SOF-165 PR2: cheap open-action count for status(). Best-effort → 0 on any error (never breaks
    a status read)."""
    try:
        return _repo(repo).open_count(project_id)
    except Exception:
        logger.exception("[recovery] open_count(%s) failed (non-fatal)", project_id)
        return 0
