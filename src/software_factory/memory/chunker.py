"""SOF-29: markdown -> ordered, section-aware chunks (T3.1's chunking layer).

Wraps Chonkie's RecursiveChunker for the actual text splitting (structure-aware: it recurses
through paragraph/sentence/word boundaries) and adds the one thing it doesn't track itself:
which markdown heading each chunk falls under (`section_path`), by mapping the chunk's
character offset back onto a heading scan of the source document.
"""
from __future__ import annotations

import re

from chonkie import RecursiveChunker

# ATX headings only ("# Title" .. "###### Title") — the markdown this pipeline ingests is
# produced by pdf_extract/docx_extract, which emit ATX headings, not setext ("Title\n===").
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$", re.MULTILINE)

# Default chunk_size chosen to land near the design's ~400-token target using Chonkie's
# built-in 'character' tokenizer (no downloaded model, no network) — roughly 4 chars/token
# for English prose, so ~1600 characters ~= ~400 tokens.
_DEFAULT_CHUNK_SIZE = 1600


def _heading_index(md: str) -> list[tuple[int, int, str]]:
    """[(char_offset, level, title), ...] for every ATX heading, in document order."""
    return [(m.start(), len(m.group(1)), m.group(2).strip()) for m in _HEADING_RE.finditer(md)]


def _section_path_at(headings: list[tuple[int, int, str]], offset: int) -> str | None:
    """The heading path active at `offset`: the most recent heading at each level (1..6) seen
    at or before `offset`, joined " / " in level order. None before any heading."""
    active: dict[int, str] = {}
    for h_offset, level, title in headings:
        if h_offset > offset:
            break
        active[level] = title
        # A heading at level N resets any previously-tracked deeper level (N+1..6) — the old
        # subsection no longer applies once a new same-or-shallower heading starts.
        for deeper in [lvl for lvl in active if lvl > level]:
            del active[deeper]
    if not active:
        return None
    return " / ".join(active[lvl] for lvl in sorted(active))


def chunk_markdown(md: str, chunk_size: int = _DEFAULT_CHUNK_SIZE) -> list[tuple[int, str | None, str]]:
    """(ordinal, section_path, text) for every chunk of `md`, in document order.

    `ordinal` is 0-based, matching the `chunk.ordinal` column. `section_path` is the markdown
    heading path the chunk falls under (e.g. "2 Architecture / 2.3 Auth"), or None if the chunk
    precedes the first heading.
    """
    if not md or not md.strip():
        return []
    headings = _heading_index(md)
    chunker = RecursiveChunker(chunk_size=chunk_size)
    chunks = chunker.chunk(md)
    return [
        (i, _section_path_at(headings, chunk.start_index), chunk.text)
        for i, chunk in enumerate(chunks)
    ]
