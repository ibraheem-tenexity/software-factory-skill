"""Turn raw run inputs (a user prompt + attached files) into Stage 1 input.

Pipeline: input → if a file is a PDF, convert it to Markdown (markitdown) → compose
the user prompt together with the extracted Markdown → write that as the Stage 1
input document. Only the *provision of input* lives here; the pipeline stages are
untouched — Stage 1 still just reads `input/`.

A malformed attachment or an empty extraction raises by default — a missing Stage-1 input is a
failure the operator needs to see (`start_project`/`promote_draft`'s call site, where the file
IS the input the run is about to build from). `tolerate_extract_failures=True` (SOF-56) opts a
DIFFERENT caller — `attach_to_draft`, materials attached mid-interview, any number of files at
any time — into the SOF-32 ingestion-pipeline pattern instead: one bad file is marked failed and
skipped, the rest of the request still succeeds. The original binary is still kept + returned
either way, so the caller can still blob-record it; only the `.md` extraction (and its inclusion
in the composed `context.md`) is skipped for a file that failed to convert.
"""
from __future__ import annotations

import base64
import os
from typing import Callable

from .log import get_logger
from .pdf_extract import extract_to_markdown

logger = get_logger(__name__)


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
    interview_md: str | None = None,
    tolerate_extract_failures: bool = False,
    product_brief_md: str | None = None,
) -> list[str]:
    """Write attached files into `input_dir`, converting PDFs (markitdown) and Word docs to
    Markdown, then write the composed Stage 1 input to `input_dir/context.md` (it's composed from
    the user's description plus `## Attached document: …` sections — genuinely Markdown, not
    plain text, per SOF-21). Word docs go
    through the image-aware path (`docx_extract.extract_with_images`) so embedded wireframe/
    screenshot images — including those inside table cells — are extracted to `input_dir/images/`
    and kept paired with their captions; falls back to the text-only converter if the image
    deps are unavailable. `product_brief_md` (the Concierge-finalized brief, SOF-63) SUPERSEDES
    the raw composition as context.md when present; `interview_md` is written verbatim as
    `interview.md` for Stage 1 to consume.

    PDF/DOCX originals are kept on disk alongside their `.md` extractions so callers can push
    them to object storage. Returned list includes both the original filename AND the `.md` name
    for each converted document; callers distinguish them by suffix.

    Returns the input-relative paths written (for artifact emission).
    """
    written: list[str] = []
    docs: list[tuple[str, str]] = []

    def _convert(raw: bytes, name: str, converter: Callable[[str], str]) -> None:
        src_path = os.path.join(input_dir, name)
        with open(src_path, "wb") as out:
            out.write(raw)
        try:
            md = converter(src_path)        # raises on empty/failed extraction
        except Exception:
            if not tolerate_extract_failures:
                raise
            logger.warning("[input_pipeline] %s: extraction failed, keeping the original "
                           "without a .md twin (tolerate_extract_failures=True)", name,
                           exc_info=True)
            written.append(name)            # original still retained/blob-recordable
            return
        # keep original alongside the extraction (caller records it as a blob)
        md_name = name + ".md"
        with open(os.path.join(input_dir, md_name), "w") as out:
            out.write(md)
        docs.append((name, md))
        written.append(name)                # original retained
        written.append(md_name)

    def _convert_docx_with_images(raw: bytes, name: str) -> None:
        src_path = os.path.join(input_dir, name)
        with open(src_path, "wb") as out:
            out.write(raw)
        from . import docx_extract
        try:
            md, images = docx_extract.extract_with_images(src_path, input_dir)
        except ImportError:
            # original already written; _convert will keep it too
            _convert(raw, name, extract_docx or docx_extract.extract_to_markdown)
            return
        # keep original alongside the extraction (caller records it as a blob)
        md_name = name + ".md"
        with open(os.path.join(input_dir, md_name), "w") as out:
            out.write(md)
        docs.append((name, md))
        written.append(name)                # original retained
        written.append(md_name)
        written.extend(images)              # input/images/image-NN.ext (wireframes survive)

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
            if extract_docx is not None:    # explicit injection (tests) keeps the text path
                _convert(raw, name, extract_docx)
            else:
                _convert_docx_with_images(raw, name)
        else:
            with open(os.path.join(input_dir, name), "wb") as out:
                out.write(raw)
            written.append(name)

    # SOF-63: a Concierge-finalized product brief IS the Stage-1 input — it was synthesized from
    # the description, the interview, and the documents, so context.md becomes the brief itself
    # rather than make_prompt's raw description+document concatenation. The per-document .md
    # extractions are still written above (and searchable via the memory MCP), so nothing is
    # lost — it just isn't dumped inline. No brief (API-created projects, no interview) → the
    # legacy composition, unchanged.
    composed = (product_brief_md or "").strip() or make_prompt(description, docs)
    if composed.strip():
        os.makedirs(input_dir, exist_ok=True)
        with open(os.path.join(input_dir, "context.md"), "w") as cf:
            cf.write(composed)
        written.append("context.md")

    if interview_md and interview_md.strip():
        os.makedirs(input_dir, exist_ok=True)
        with open(os.path.join(input_dir, "interview.md"), "w") as itf:
            itf.write(interview_md.strip() + "\n")
        written.append("interview.md")

    return written
