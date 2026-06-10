"""Turn raw run inputs (a user prompt + attached files) into Stage 1 input.

Pipeline: input → if a file is a PDF, convert it to Markdown (markitdown) → compose
the user prompt together with the extracted Markdown → write that as the Stage 1
input document. Only the *provision of input* lives here; the pipeline stages are
untouched — Stage 1 still just reads `input/`.

A malformed attachment or an empty extraction raises rather than being silently
dropped — a missing input is a failure the operator needs to see.
"""
from __future__ import annotations

import base64
import os
from typing import Callable

from .pdf_extract import extract_to_markdown


def make_prompt(description: str, docs: list[tuple[str, str]]) -> str:
    """Compose the Stage 1 input text from the user prompt and the extracted
    Markdown of each attached document (labeled by filename)."""
    parts: list[str] = []
    if (description or "").strip():
        parts.append(description.strip())
    for name, md in docs:
        parts.append(f"## Attached document: {name}\n\n{md.strip()}")
    return "\n\n".join(parts)


def persist_and_compose(
    input_dir: str,
    description: str,
    files: list[dict],
    extract: Callable[[str], str] = extract_to_markdown,
    extract_docx: Callable[[str], str] | None = None,
) -> list[str]:
    """Write attached files into `input_dir`, converting PDFs (markitdown) and Word docs
    (pandoc) to Markdown, then write the composed Stage 1 input to `input_dir/context.txt`.

    Returns the input-relative paths written (for artifact emission).
    """
    written: list[str] = []
    docs: list[tuple[str, str]] = []

    def _convert(raw: bytes, name: str, converter: Callable[[str], str]) -> None:
        src_path = os.path.join(input_dir, name)
        with open(src_path, "wb") as out:
            out.write(raw)
        md = converter(src_path)            # raises on empty/failed extraction
        os.remove(src_path)                 # consumed by the conversion
        md_name = name + ".md"
        with open(os.path.join(input_dir, md_name), "w") as out:
            out.write(md)
        docs.append((name, md))
        written.append(md_name)

    for f in (files or []):
        name = os.path.basename(f.get("name") or "")
        b64 = f.get("content_b64")
        if not name or not b64:
            raise ValueError(f"attached file missing name or content: {f.get('name')!r}")
        os.makedirs(input_dir, exist_ok=True)
        raw = base64.b64decode(b64)

        if name.lower().endswith(".pdf"):
            _convert(raw, name, extract)
        elif name.lower().endswith(".docx"):
            from .docx_extract import extract_to_markdown as _docx_default
            _convert(raw, name, extract_docx or _docx_default)
        else:
            with open(os.path.join(input_dir, name), "wb") as out:
                out.write(raw)
            written.append(name)

    composed = make_prompt(description, docs)
    if composed.strip():
        os.makedirs(input_dir, exist_ok=True)
        with open(os.path.join(input_dir, "context.txt"), "w") as cf:
            cf.write(composed)
        written.append("context.txt")

    return written
