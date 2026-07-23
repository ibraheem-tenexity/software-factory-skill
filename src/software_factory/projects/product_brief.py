"""Versioned Product Brief application boundary (SOF-244).

The canonical Product Brief is the newest `kind='product_brief'` artifact for a project. Artifact
rows are append-only and immutable, so **each finalize / direct save is a version**, newest-wins,
and history is simply the filtered set newest-first. Direct edits and the Concierge's
`finalize_product_brief` converge on the SAME artifact stream — distinguished by the existing
`origin` provenance convention (SOF-60): a direct human edit is `origin='user'`, the Concierge
(an agent) is `origin='agent'` with `agent='concierge'`.

Immutability of history depends on each version's content living in the row's inline `content`
column (not only the fixed-key storage blob, which every write overwrites). Both write paths inline
`content` for exactly that reason — an older version's markdown is read back from its own row.

This owns brief READ/LIST/VERSION/SAVE only; it never launches stages or mutates lifecycle. The
handoff gate keeps reading the same newest canonical artifact via `ProjectIntake.product_brief`.
"""
from __future__ import annotations

from .. import storage
from ..db import ProjectStore
from ..log import get_logger
from ..services.errors import Conflict, Invalid, NotFound
from .intake import project_paths

logger = get_logger(__name__)

_KIND = "product_brief"
_STORAGE_KEY = "product-brief.md"


class ProductBrief:
    """Versioned read/write over a project's `product_brief` artifacts."""

    def __init__(self, projects_dir: str):
        self._projects_dir = projects_dir

    def _store(self, project_id: str) -> ProjectStore:
        return ProjectStore(project_paths(self._projects_dir, project_id)["db"])

    def _rows_newest_first(self, project_id: str) -> list[dict]:
        # artifacts() is ordered by id asc (append-only, monotonic PK) — reverse for newest-first.
        rows = [a for a in self._store(project_id).artifacts() if (a.get("kind") or "") == _KIND]
        rows.reverse()
        return rows

    @staticmethod
    def _content(row: dict, *, allow_storage_fallback: bool) -> str | None:
        """The version's markdown. Prefer the immutable inline `content` column (every write inlines
        it now). The storage-blob fallback is honest ONLY for the newest version: the brief's storage
        key is fixed and each finalize overwrote it, so an OLDER content-less (pre-inline) row's blob
        now holds a DIFFERENT, newer body — returning it would silently fake history. So older
        content-less rows return None and the reader surfaces "content not preserved for this
        version"; those old bodies are genuinely unrecoverable."""
        content = row.get("content")
        if content:
            return content
        if not allow_storage_fallback:
            return None
        url = row.get("path") or ""
        if not url:
            return None
        try:
            return storage.get_by_url(url).decode()
        except Exception:
            logger.exception("[brief] failed to read product-brief content from storage (%s)", url)
            return None

    @staticmethod
    def _meta(row: dict) -> dict:
        return {
            "artifact_id": row["id"],
            "ts": row.get("ts"),
            "origin": row.get("origin") or "agent",
            "agent": row.get("agent"),
            "title": row.get("title") or "Product Brief",
        }

    def _full(self, row: dict, *, is_latest: bool) -> dict:
        return {**self._meta(row), "markdown": self._content(row, allow_storage_fallback=is_latest)}

    # ---- reads -------------------------------------------------------------------------
    def latest(self, project_id: str) -> dict | None:
        """Newest canonical brief (metadata + markdown), or None if the project has none yet."""
        rows = self._rows_newest_first(project_id)
        return self._full(rows[0], is_latest=True) if rows else None

    def versions(self, project_id: str) -> list[dict]:
        """Every version newest-first — stable artifact ids + timestamps, no bodies."""
        return [self._meta(row) for row in self._rows_newest_first(project_id)]

    def version(self, project_id: str, artifact_id: int) -> dict:
        """One historical version by artifact id, scoped to THIS project. Read-only. The lookup
        is within the project's own product_brief rows, so an id from another project (or a
        non-brief artifact) is simply absent here — cross-project access is refused, not leaked,
        without an unscoped global fetch. Raises NotFound if the id is unknown."""
        rows = self._rows_newest_first(project_id)
        for index, row in enumerate(rows):
            if row["id"] == artifact_id:
                return self._full(row, is_latest=(index == 0))
        raise NotFound("product brief version not found")

    # ---- write -------------------------------------------------------------------------
    def save(self, project_id: str, markdown: str, base_artifact_id: int | None, *, agent: str) -> dict:
        """Create a NEW immutable version from complete markdown (never mutates a prior row).

        Optimistic concurrency: `base_artifact_id` is the version the editor loaded. If it is not
        the current newest, raise Conflict carrying the current latest so the editor can reconcile
        — two editors can't silently overwrite each other. Durable content is written first; only
        then is the artifact recorded, so a storage failure never yields a phantom 'saved'.

        The check-then-insert is not transactionally atomic: two writers that both pass the check on
        the same base can both append. That is benign here — the stream is append-only and immutable
        (neither clobbers the other; both survive in history and newest still wins), the window is
        tiny, and a real editor almost never has a concurrent co-writer on one project. A row lock
        would be machinery out of proportion to the risk.
        """
        md = (markdown or "").strip()
        if not md:
            raise Invalid("product brief markdown is empty")
        rows = self._rows_newest_first(project_id)
        current_id = rows[0]["id"] if rows else None
        if base_artifact_id != current_id:
            raise Conflict({
                "message": "product brief changed since you loaded it — reload the latest version",
                "latest": self._full(rows[0], is_latest=True) if rows else None,
            })
        # durable content first (raises on storage failure → no artifact row recorded), then record
        # the canonical artifact the same way Concierge finalization does, with the content inlined
        # so this exact version is immutable regardless of later same-key storage overwrites.
        url = storage.put(project_id, _STORAGE_KEY, md.encode())
        self._store(project_id).record_artifact(
            "Product Brief", url, kind=_KIND, agent=agent, content=md, origin="user")
        new_rows = self._rows_newest_first(project_id)
        return self._full(new_rows[0], is_latest=True)
