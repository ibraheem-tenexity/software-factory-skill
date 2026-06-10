"""Extract a Word document (.docx) to Markdown.

Primary: pandoc via pypandoc (`pypandoc_binary` bundles the pandoc binary — no system dep).
Chosen over markitdown/mammoth/docx2txt after benchmarking on the real Singer SOW: pandoc is
the only method that preserves headings + TABLES (milestone pricing) + lists with GFM output.
Fallback: mammoth (pure-Python; keeps headings/lists, flattens tables) if pandoc can't init.

Same contract as pdf_extract: converter injectable for tests; empty extraction raises.
"""
from __future__ import annotations

import os
from typing import Callable


def extract_to_markdown(path: str, convert: Callable[[str], str] | None = None) -> str:
    """Return the Markdown text of the .docx at `path`.

    Raises FileNotFoundError if the path is missing, and RuntimeError if the
    converter yields no text.
    """
    if not os.path.isfile(path):
        raise FileNotFoundError(path)
    text = (convert or _pandoc_convert)(path)
    if not text or not text.strip():
        raise RuntimeError(f"no text extracted from {path!r}")
    return text


def _pandoc_convert(path: str) -> str:
    try:
        import pypandoc
        return pypandoc.convert_file(path, "gfm")
    except Exception:
        # pandoc binary unavailable/failed — degrade to mammoth (no tables, but real text).
        import mammoth
        with open(path, "rb") as f:
            return mammoth.convert_to_markdown(f).value
