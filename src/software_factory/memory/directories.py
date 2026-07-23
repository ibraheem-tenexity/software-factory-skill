"""SOF-254 (epic SOF-238): generated, read-only directory subtree summaries with ancestor
invalidation.

Directories (the Files-browser tree from SOF-251) carry a *generated* rollup summary so a person
can understand what a folder contains. The summary is **read-only** — there is no manual edit
endpoint or user-authored folder note anywhere; the only writer is this module. Each directory's
`summary_md` is rolled up from:

  * the per-document summaries of its DIRECT child files (`doc_summary`, produced by ingest.py)
  * the summaries of its DIRECT child directories (already regenerated, because we run bottom-up)
  * mechanically-computed coverage/failure metadata over its children

Truthful state lives in `directories.summary_status` (summarizing|ready|needs_refresh|failed),
`summary_source_hash` (the hash of the exact child inputs a `ready` summary was built from — the
staleness detector), `last_successful_summary_at`, and `summary_error` (the real failure reason,
retained alongside the last successful summary when a refresh fails).

Lifecycle (see the SOF-254 contract):
  * Any descendant mutation — a document added, deleted, moved, scope-changed, or re-ingested —
    mechanically marks EVERY ancestor directory `needs_refresh` (an older successful summary stays
    visible but is labelled stale). See `invalidate_ancestors_for_blob`.
  * Regeneration runs BOTTOM-UP (`refresh_scope`), so a parent only ever incorporates the latest
    available child results. A directory that is already `ready` with a matching source hash is
    skipped — unchanged subtrees make no model call.
  * A failed or still-processing child is never silently dropped to get a green parent: it stays
    visible in the parent's material and contributes an explicit incomplete-coverage statement.
  * An empty directory (no indexed material, no child directories) gets NO fabricated prose — it
    is `ready` with a NULL summary and the empty-subtree hash.

This module is CORE (like ingest.py): it must never import `console.*`. `console` is passed in by
the caller purely for cost attribution, exactly as ingest.py already does.
"""
from __future__ import annotations

import hashlib
import json
import threading

from .. import dbshim
from ..log import get_logger
from .cost import record_ingestion_cost

logger = get_logger(__name__)


# ---------------------------------------------------------------------------------------------
# Persistence — thin CRUD over dbshim (`?` placeholders, dict rows), mirroring MemoryStore.
# ---------------------------------------------------------------------------------------------
class DirectoryStore:
    def __init__(self, connect=None):
        self._connect = connect or (lambda: dbshim.connect("."))

    def list_for_scope(self, scope: str, scope_id: str) -> list[dict]:
        """Every directory row in one scope — enough to build the parent map for ancestor walks
        and to order a bottom-up refresh, without an N+1 per node."""
        conn = self._connect()
        try:
            return conn.execute(
                "SELECT id, parent_id, name, summary_md, summary_status, summary_source_hash "
                "FROM directories WHERE scope = ? AND scope_id = ?",
                (scope, scope_id),
            ).fetchall()
        finally:
            conn.close()

    def get(self, directory_id) -> dict | None:
        conn = self._connect()
        try:
            return conn.execute(
                "SELECT id, scope, scope_id, parent_id, name, summary_md, summary_status, "
                "summary_source_hash FROM directories WHERE id = ?",
                (directory_id,),
            ).fetchone()
        finally:
            conn.close()

    def child_directories(self, directory_id) -> list[dict]:
        """Direct child directories, with the summary state a parent rolls up from."""
        conn = self._connect()
        try:
            return conn.execute(
                "SELECT id, name, summary_md, summary_status, summary_source_hash "
                "FROM directories WHERE parent_id = ? ORDER BY name",
                (directory_id,),
            ).fetchall()
        finally:
            conn.close()

    def child_files(self, directory_id) -> list[dict]:
        """Direct child source documents filed in this directory, each joined to its per-document
        summary. Extracted-child assets (source_blob_id NOT NULL) never carry a directory_id, so
        they are excluded — only real top-level documents count toward a directory's summary."""
        conn = self._connect()
        try:
            return conn.execute(
                "SELECT b.id, b.name, ds.status AS doc_status, ds.summary_md, ds.content_sha256 "
                "FROM blobs b LEFT JOIN doc_summary ds ON ds.blob_id = b.id "
                "WHERE b.directory_id = ? AND b.source_blob_id IS NULL ORDER BY b.name",
                (directory_id,),
            ).fetchall()
        finally:
            conn.close()

    def mark_needs_refresh(self, directory_ids: list) -> None:
        """Flip the given directories to `needs_refresh` — but only the ones currently `ready` or
        `summarizing`. A `failed`/`needs_refresh` directory is left as-is: both already mean
        "not current, regenerate me", and overwriting `failed` would destroy its retained failure
        detail. The subsequent bottom-up refresh regenerates every non-ready directory anyway."""
        if not directory_ids:
            return
        conn = self._connect()
        try:
            for did in directory_ids:
                conn.execute(
                    "UPDATE directories SET summary_status = 'needs_refresh', updated_at = now() "
                    "WHERE id = ? AND summary_status IN ('ready', 'summarizing')",
                    (did,),
                )
        finally:
            conn.close()

    def set_summarizing(self, directory_id) -> None:
        conn = self._connect()
        try:
            conn.execute(
                "UPDATE directories SET summary_status = 'summarizing', updated_at = now() "
                "WHERE id = ?",
                (directory_id,),
            )
        finally:
            conn.close()

    def set_ready(self, directory_id, summary_md: str | None, source_hash: str) -> None:
        """A successful refresh: publish the new summary, record the source hash it was built from,
        stamp last-success, and clear any prior failure detail. `summary_md` is NULL only for an
        empty directory (no fabricated prose) — last-success is left untouched in that case."""
        conn = self._connect()
        try:
            if summary_md is None:
                conn.execute(
                    "UPDATE directories SET summary_status = 'ready', summary_md = NULL, "
                    "summary_source_hash = ?, summary_error = NULL, updated_at = now() "
                    "WHERE id = ?",
                    (source_hash, directory_id),
                )
            else:
                conn.execute(
                    "UPDATE directories SET summary_status = 'ready', summary_md = ?, "
                    "summary_source_hash = ?, summary_error = NULL, "
                    "last_successful_summary_at = now(), updated_at = now() WHERE id = ?",
                    (summary_md, source_hash, directory_id),
                )
        finally:
            conn.close()

    def set_failed(self, directory_id, error: str) -> None:
        """A failed refresh: record the real reason and RETAIN the last successful summary, its
        source hash, and last-success time. The stale hash (never advanced to the current subtree)
        guarantees the directory stays non-`ready` and is retried on the next refresh."""
        conn = self._connect()
        try:
            conn.execute(
                "UPDATE directories SET summary_status = 'failed', summary_error = ?, "
                "updated_at = now() WHERE id = ?",
                (error, directory_id),
            )
        finally:
            conn.close()


# ---------------------------------------------------------------------------------------------
# Ancestor invalidation — the mechanical "a descendant changed" signal.
# ---------------------------------------------------------------------------------------------
def _ancestor_chain(rows: list[dict], start_id) -> list:
    """Directory ids from `start_id` up to (and including) its scope root, using the parent map
    built from one scope's rows. `start_id` itself is included: a change to a directory's direct
    child file must refresh that directory's own summary too. Cycle-guarded (the schema forbids
    cycles, but never loop forever on a corrupt row)."""
    parent_of = {str(r["id"]): (str(r["parent_id"]) if r["parent_id"] is not None else None)
                 for r in rows}
    chain, seen, cur = [], set(), str(start_id) if start_id is not None else None
    while cur is not None and cur in parent_of and cur not in seen:
        seen.add(cur)
        chain.append(cur)
        cur = parent_of[cur]
    return chain


def invalidate_ancestors_for_blob(scope: str, scope_id: str, directory_id,
                                  store: DirectoryStore | None = None) -> list:
    """Mark the blob's directory and every ancestor up to the scope root `needs_refresh`.

    Synchronous and cheap — it runs at mutation time so the Files UI immediately shows the stale
    label. `directory_id` is None for an unfiled/virtual-top-level blob (a fresh upload not yet
    homed under the tree, or an extracted-child asset): there is no stored directory to invalidate,
    so this is a no-op. Returns the invalidated chain (for the caller's log / test reasoning)."""
    if directory_id is None:
        return []
    store = store or DirectoryStore()
    rows = store.list_for_scope(scope, scope_id)
    chain = _ancestor_chain(rows, directory_id)
    if not chain:
        logger.warning("[memory.directories] %s/%s: directory %s not found in scope — no ancestors "
                       "invalidated", scope, scope_id, directory_id)
        return []
    store.mark_needs_refresh(chain)
    logger.info("[memory.directories] %s/%s: marked %s director(y/ies) needs_refresh up from %s",
                scope, scope_id, len(chain), directory_id)
    return chain


# ---------------------------------------------------------------------------------------------
# Summary generation — bottom-up regeneration over one scope's tree.
# ---------------------------------------------------------------------------------------------
def _subtree_hash(child_files: list[dict], child_dirs: list[dict]) -> str:
    """A stable hash of the EXACT inputs a directory summary is built from: each child file's
    (name, content hash, doc status) and each child directory's (name, its own source hash, its
    status). Because a child directory's hash already reflects its whole subtree (we regenerate
    bottom-up), this transitively captures any descendant change. A `ready` directory whose current
    hash equals its stored `summary_source_hash` needs no model call."""
    payload = {
        "files": sorted([(f.get("name") or "", f.get("content_sha256") or "",
                          f.get("doc_status") or "") for f in child_files]),
        "dirs": sorted([(d.get("name") or "", d.get("summary_source_hash") or "",
                         d.get("summary_status") or "") for d in child_dirs]),
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()


def _coverage_statement(child_files: list[dict], child_dirs: list[dict]) -> str | None:
    """A truthful, code-computed note about incomplete coverage — NEVER left to the model, so a
    failed or still-processing child can never be silently omitted to obtain a green parent.
    Returns None when coverage is complete (every child ready)."""
    failed_files = [f.get("name") or "document" for f in child_files if f.get("doc_status") == "failed"]
    pending_files = [f.get("name") or "document" for f in child_files
                     if f.get("doc_status") in (None, "pending", "summarizing")]
    unready_dirs = [d.get("name") or "folder" for d in child_dirs
                    if d.get("summary_status") != "ready"]
    parts = []
    if failed_files:
        parts.append(f"{len(failed_files)} document(s) failed to summarize "
                     f"({', '.join(failed_files)})")
    if pending_files:
        parts.append(f"{len(pending_files)} document(s) not yet summarized "
                     f"({', '.join(pending_files)})")
    if unready_dirs:
        parts.append(f"{len(unready_dirs)} subfolder(s) with incomplete summaries "
                     f"({', '.join(unready_dirs)})")
    if not parts:
        return None
    return "**Incomplete coverage:** " + "; ".join(parts) + "."


def _ready_material(child_files: list[dict], child_dirs: list[dict]) -> list[tuple[str, str]]:
    """(label, summary_md) for every child that has summary text to roll up. A failed child
    directory keeps its last successful summary, so it still contributes here (and is additionally
    flagged by the coverage statement) rather than vanishing."""
    material = []
    for f in child_files:
        if (f.get("summary_md") or "").strip():
            material.append((f"File: {f.get('name') or 'document'}", f["summary_md"].strip()))
    for d in child_dirs:
        if (d.get("summary_md") or "").strip():
            material.append((f"Subfolder: {d.get('name') or 'folder'}", d["summary_md"].strip()))
    return material


def _summarize_directory(dir_name: str, material: list[tuple[str, str]]) -> tuple[str, dict]:
    """One OpenRouter chat call rolling child summaries up into a folder summary. Reuses ingest.py's
    chat client and model (the SAME summarization seam that produces per-document summaries).
    Returns (summary_md, usage)."""
    # Deferred import: ingest.py imports THIS module for its post-ingest trigger, so importing it at
    # module load would be circular. ingest owns the chat-client + pricing helpers; reuse them.
    from . import ingest

    body = "\n\n".join(f"[{label}]\n{summary}" for label, summary in material)
    prompt = (
        f"You are summarizing the folder \"{dir_name}\" of a project's source material, using the "
        f"summaries of the documents and subfolders it directly contains.\n\n{body}\n\n"
        "Write a concise markdown summary (2-4 short paragraphs or bullet groups) that tells a "
        "reader:\n"
        "1. what source material this folder contains;\n"
        "2. which questions it can help answer;\n"
        "3. notable files someone may need.\n"
        "Base every statement only on the summaries above. Do not invent files or facts, do not "
        "add confidence hedging, and do not mention this instruction."
    )
    client = ingest._default_chat_client()
    resp = client.chat.completions.create(
        model=ingest.SUMMARIZE_MODEL,
        messages=[{"role": "user", "content": prompt}],
    )
    usage = {"prompt_tokens": 0, "completion_tokens": 0}
    if getattr(resp, "usage", None) is not None:
        usage["prompt_tokens"] = resp.usage.prompt_tokens or 0
        usage["completion_tokens"] = resp.usage.completion_tokens or 0
    try:
        content = resp.choices[0].message.content or ""
    except (IndexError, AttributeError):
        logger.exception("[memory.directories] folder %r: malformed chat response shape", dir_name)
        content = ""
    return content.strip(), usage


def _record_cost(console, scope: str, scope_id: str, usage: dict) -> None:
    """Charge a directory-summary model call to the project's ingestion ledger (project scope only,
    mirroring ingest.py — org-scoped ingestion is not billed to a project). Uses live OpenRouter
    pricing; a missing price is logged and skipped, never billed as a fabricated $0."""
    if scope != "project" or not usage or console is None:
        return
    from . import ingest
    usd = ingest._estimate_cost_usd(
        ingest.SUMMARIZE_MODEL, "chat",
        prompt_tokens=usage.get("prompt_tokens", 0),
        completion_tokens=usage.get("completion_tokens", 0),
    )
    if usd is None:
        logger.warning("[memory.directories] %s: no live OpenRouter price for %s — directory "
                       "summary cost NOT recorded", scope_id, ingest.SUMMARIZE_MODEL)
        return
    record_ingestion_cost(console, scope_id, model=ingest.SUMMARIZE_MODEL, provider="openrouter",
                          input_tokens=usage.get("prompt_tokens", 0),
                          output_tokens=usage.get("completion_tokens", 0), usd=usd)


def refresh_directory(scope: str, scope_id: str, directory: dict, *, console=None,
                      store: DirectoryStore | None = None) -> dict:
    """Regenerate one directory's summary from its current direct children. Never raises — a model
    failure logs the full traceback and marks the directory `failed` (retaining its last successful
    summary), so a bottom-up sweep is never killed by one bad folder.

    Returns a small result dict describing what happened (for logs / reasoning)."""
    store = store or DirectoryStore()
    directory_id = directory["id"]
    dir_name = directory.get("name") or "folder"
    child_files = store.child_files(directory_id)
    child_dirs = store.child_directories(directory_id)
    current_hash = _subtree_hash(child_files, child_dirs)

    # Unchanged + already ready => no model call (the redundant-regeneration guard).
    if directory.get("summary_status") == "ready" \
            and directory.get("summary_source_hash") == current_hash:
        return {"directory_id": directory_id, "status": "ready", "skipped": "unchanged"}

    # Empty directory: no indexed material and no child directories => no fabricated prose.
    if not child_files and not child_dirs:
        store.set_ready(directory_id, None, current_hash)
        logger.info("[memory.directories] %s/%s: folder %r empty — ready with no summary",
                    scope, scope_id, dir_name)
        return {"directory_id": directory_id, "status": "ready", "empty": True}

    store.set_summarizing(directory_id)
    coverage = _coverage_statement(child_files, child_dirs)
    material = _ready_material(child_files, child_dirs)

    # Nothing summarizable yet (every child is failed/pending, none has retained text): don't call
    # the model — publish the honest coverage note as the summary so the state is truthful and
    # current. When the children finish, ingest re-invalidates this ancestor and it regenerates.
    if not material:
        summary_md = coverage or f"_{dir_name}_ contains material that has not been summarized yet."
        store.set_ready(directory_id, summary_md, current_hash)
        logger.info("[memory.directories] %s/%s: folder %r has no summarizable child material yet "
                    "— ready with coverage note only", scope, scope_id, dir_name)
        return {"directory_id": directory_id, "status": "ready", "coverage_only": True}

    try:
        summary_md, usage = _summarize_directory(dir_name, material)
    except Exception as exc:
        logger.exception("[memory.directories] %s/%s: folder %r summary generation FAILED — "
                         "marking failed, retaining last successful summary",
                         scope, scope_id, dir_name)
        store.set_failed(directory_id, str(exc) or exc.__class__.__name__)
        return {"directory_id": directory_id, "status": "failed", "error": str(exc)}

    if not summary_md:
        # A blank model reply is a real failure, not a green summary — never persist ready-but-empty
        # when material existed (that would be a fabricated/misleading "ready").
        logger.error("[memory.directories] %s/%s: folder %r summarization returned empty text — "
                     "marking failed", scope, scope_id, dir_name)
        store.set_failed(directory_id, "summarization returned empty text")
        return {"directory_id": directory_id, "status": "failed", "error": "empty summary"}

    if coverage:
        summary_md = f"{summary_md}\n\n{coverage}"
    _record_cost(console, scope, scope_id, usage)
    store.set_ready(directory_id, summary_md, current_hash)
    logger.info("[memory.directories] %s/%s: folder %r summary regenerated (status=ready)",
                scope, scope_id, dir_name)
    return {"directory_id": directory_id, "status": "ready"}


def _depth(rows_by_id: dict, node_id: str) -> int:
    depth, seen, cur = 0, set(), node_id
    while cur is not None and cur in rows_by_id and cur not in seen:
        seen.add(cur)
        parent = rows_by_id[cur]["parent_id"]
        cur = str(parent) if parent is not None else None
        depth += 1
    return depth


def refresh_scope(scope: str, scope_id: str, *, console=None,
                  store: DirectoryStore | None = None) -> list[dict]:
    """Regenerate every non-current directory in one scope, BOTTOM-UP (deepest first) so a parent
    always incorporates the latest available child results. `ready`+unchanged directories are
    skipped inside `refresh_directory` (no model call). Returns per-directory results."""
    store = store or DirectoryStore()
    rows = store.list_for_scope(scope, scope_id)
    if not rows:
        return []
    rows_by_id = {str(r["id"]): r for r in rows}
    ordered = sorted(rows, key=lambda r: _depth(rows_by_id, str(r["id"])), reverse=True)
    results = []
    for row in ordered:
        # Re-read the row's summary state per node: a child we just regenerated changed the parent's
        # inputs, and refresh_directory recomputes the hash from live children anyway.
        results.append(refresh_directory(scope, scope_id, dict(row), console=console, store=store))
    logger.info("[memory.directories] %s/%s: bottom-up refresh over %s director(y/ies) done",
                scope, scope_id, len(ordered))
    return results


def maybe_refresh_scope_async(scope: str, scope_id: str, console=None) -> None:
    """Fire-and-forget bottom-up refresh of one scope's directory tree, on a daemon thread — the
    same background seam ingest.py uses. Never blocks or fails the mutation that triggered it."""
    t = threading.Thread(target=_refresh_scope_safe, args=(scope, scope_id, console),
                         daemon=True, name=f"dir-summary-{scope}-{scope_id}")
    t.start()


def _refresh_scope_safe(scope: str, scope_id: str, console) -> None:
    try:
        refresh_scope(scope, scope_id, console=console)
    except Exception:
        logger.exception("[memory.directories] %s/%s: unhandled failure in background directory "
                         "refresh", scope, scope_id)


def invalidate_directories(directory_ids, store: DirectoryStore | None = None) -> set:
    """Mark each given directory's ancestor chain `needs_refresh` — invalidation ONLY, no
    regeneration. Returns the set of affected `(scope, scope_id)` pairs so a caller can decide
    whether to also sweep. `None` ids (an unfiled/virtual blob that belongs to no directory) are
    skipped: nothing rolls up from an unfiled blob, so there is nothing to invalidate.

    This is the seam for a mutation whose real rollup is produced elsewhere — e.g. `upload`, where
    the summary is regenerated at ingest-completion once the new document's own summary exists, so
    firing a sweep here would only burn a premature model call on a not-yet-summarized document."""
    store = store or DirectoryStore()
    affected: set = set()
    for directory_id in directory_ids:
        if directory_id is None:
            continue
        row = store.get(directory_id)
        if row is None:
            logger.warning("[memory.directories] directory %s not found — skipped in invalidation",
                           directory_id)
            continue
        scope, scope_id = row["scope"], row["scope_id"]
        try:
            invalidate_ancestors_for_blob(scope, scope_id, directory_id, store)
        except Exception:
            logger.exception("[memory.directories] %s/%s: ancestor invalidation failed for directory "
                             "%s", scope, scope_id, directory_id)
        affected.add((scope, scope_id))
    return affected


def on_directories_changed(directory_ids, console=None) -> None:
    """THE single entry point a mutation calls when it also owns the regeneration (ingest
    terminals, and SOF-253's Files-browser move/set_scope/delete) — one ancestor-aware
    invalidation mechanism, replacing SOF-253's directory-only `touch_directory`.

    Given the directories a mutation touched (a blob's directory, its OLD directory for a move, or
    both endpoints of a cross-scope move), it synchronously marks each one's ancestor chain
    `needs_refresh` (via `invalidate_directories`), then fires exactly ONE background bottom-up
    refresh per affected scope. Use `invalidate_directories` alone when ingest-completion will do
    the regeneration instead (see `upload`)."""
    for scope, scope_id in invalidate_directories(directory_ids):
        maybe_refresh_scope_async(scope, scope_id, console)
