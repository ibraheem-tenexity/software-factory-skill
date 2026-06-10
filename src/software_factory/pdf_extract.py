"""Extract a document (PDF, docx, …) to Markdown.

The pipeline and the chat layer need one place to turn an uploaded document into
usable text. `extract_to_markdown` routes by type — .docx through pandoc (the only
converter that preserves headings + tables + lists on real SOW inputs; markitdown
is the fallback), everything else through markitdown. The converter is injectable
so the wrapper is testable without a real binary file. An empty extraction
raises — a silently blank result is a failure, not a valid output.
"""
from __future__ import annotations

import os
from typing import Callable


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
            pass  # pandoc missing/failed — markitdown[docx] still extracts, just flatter tables
    return _markitdown_convert(path)


def _pandoc_convert(path: str) -> str:
    import pypandoc

    return pypandoc.convert_file(path, "gfm")


def _markitdown_convert(path: str) -> str:
    from markitdown import MarkItDown

    return MarkItDown().convert(path).text_content
