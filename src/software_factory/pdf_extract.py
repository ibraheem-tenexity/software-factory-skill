"""Extract a document (PDF, docx, …) to Markdown.

The pipeline and the chat layer need one place to turn an uploaded document into
usable text. `extract_to_markdown` routes by type — .docx through pandoc (the only
converter that preserves headings + tables + lists on structured project inputs; markitdown
is the fallback), everything else through markitdown. The converter is injectable
so the wrapper is testable without a real binary file. An empty extraction
raises — a silently blank result is a failure, not a valid output.
"""
from __future__ import annotations

import os
from typing import Callable

from .log import get_logger

logger = get_logger(__name__)


def extract_to_markdown(path: str, convert: Callable[[str], str] | None = None) -> str:
    """Return the Markdown text of the document at `path`.

    Raises FileNotFoundError if the path is missing, and RuntimeError if the
    converter yields no text.
    """
    if not os.path.isfile(path):
        raise FileNotFoundError(path)
    text = (convert or _default_convert)(path)
    if not text or not text.strip():
        raise RuntimeError(f"no text extracted from {path!r}")
    return text


def _default_convert(path: str) -> str:
    if path.lower().endswith(".docx"):
        try:
            return _pandoc_convert(path)
        except Exception:
            # pandoc missing/failed — markitdown[docx] still extracts, just flatter tables.
            logger.exception("[ingest] %s: pandoc docx conversion failed — falling back to markitdown", path)
    return _markitdown_convert(path)


def _pandoc_convert(path: str) -> str:
    import pypandoc

    return pypandoc.convert_file(path, "gfm")


def _import_markitdown():
    """Import markitdown WITHOUT letting its transitive python-dotenv autoload mutate os.environ.

    Importing markitdown triggers python-dotenv, whose `find_dotenv` walks UP from the current
    working directory and loads the nearest `.env`. In a dev worktree that nearest file is the
    repo's LIVE `.env`, so the import silently injects real secrets (SF_GOOGLE_CLIENT_ID,
    SF_SESSION_SECRET, …) into `os.environ` — flipping a local auth-off console to authed the
    moment the first document is parsed (SOF-228). Snapshot `os.environ` before the import and
    restore it after, so the autoload's side effect cannot leak. No-op in deployed containers
    (no parent `.env` to find) and a one-time cost (markitdown is module-cached after first import).
    """
    snapshot = dict(os.environ)
    try:
        from markitdown import MarkItDown
        return MarkItDown
    finally:
        for k in set(os.environ) - set(snapshot):
            del os.environ[k]                       # drop keys the autoload ADDED
        for k, v in snapshot.items():
            if os.environ.get(k) != v:
                os.environ[k] = v                   # revert CHANGED / restore any REMOVED


def _markitdown_convert(path: str) -> str:
    MarkItDown = _import_markitdown()

    return MarkItDown().convert(path).text_content
