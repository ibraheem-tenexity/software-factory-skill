"""Extract a document (PDF, docx, …) to Markdown via markitdown.

The pipeline and the chat layer need one place to turn an uploaded document into
usable text. `extract_to_markdown` wraps markitdown's converter; the converter is
injectable so the wrapper is testable without a real binary file. An empty
extraction raises — a silently blank result is a failure, not a valid output.
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
    text = (convert or _markitdown_convert)(path)
    if not text or not text.strip():
        raise RuntimeError(f"no text extracted from {path!r}")
    return text


def _markitdown_convert(path: str) -> str:
    from markitdown import MarkItDown

    return MarkItDown().convert(path).text_content
