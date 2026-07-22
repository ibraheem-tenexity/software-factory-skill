"""Extract a Word document (.docx) to Markdown.

Primary: pandoc via pypandoc (`pypandoc_binary` bundles the pandoc binary — no system dep).
Chosen over markitdown/mammoth/docx2txt after benchmarking on a structured project brief: pandoc is
the only method that preserves headings + TABLES (milestone pricing) + lists with GFM output.
Fallback: mammoth (pure-Python; keeps headings/lists, flattens tables) if pandoc can't init.

Same contract as pdf_extract: converter injectable for tests; empty extraction raises.
"""
from __future__ import annotations

import os
import re
from typing import Callable

from .log import get_logger

logger = get_logger(__name__)


def extract_with_images(path: str, out_dir: str, img_subdir: str = "images") -> tuple[str, list[str]]:
    """Convert a .docx to Markdown, extracting EVERY embedded image — including images that
    live inside table cells, the common wireframe/screenshot layout that the pandoc text path
    silently drops. Ported from the proven gk9 `docx2md` flow:

      1. `mammoth.convert_to_html` with an `img_element` handler writes each image to
         `<out_dir>/<img_subdir>/image-NN.ext` (sequential, document-order ids) AND rewrites
         the <img src> in one pass.
      2. `markdownify(..., keep_inline_images_in=["td","th",...])` so table-cell screenshots
         survive into the Markdown instead of being dropped.

    Returns (markdown_text, [input-relative image paths written]). Raises FileNotFoundError if
    the path is missing, RuntimeError on empty extraction, and ImportError if mammoth/markdownify
    are unavailable (the caller falls back to the text-only pandoc path).
    """
    if not os.path.isfile(path):
        raise FileNotFoundError(path)
    import mammoth
    from markdownify import markdownify as _md

    img_dir = os.path.join(out_dir, img_subdir)
    os.makedirs(img_dir, exist_ok=True)
    counter = {"n": 0}
    images: list[str] = []

    def _img_handler(image):
        counter["n"] += 1
        ext = (image.content_type or "image/png").split("/")[-1]
        fname = f"image-{counter['n']:02d}.{ext}"
        with image.open() as fh:
            data = fh.read()
        with open(os.path.join(img_dir, fname), "wb") as out:
            out.write(data)
        rel = f"{img_subdir}/{fname}"
        images.append(rel)
        return {"src": rel}

    with open(path, "rb") as f:
        html = mammoth.convert_to_html(f, convert_image=mammoth.images.img_element(_img_handler)).value
    text = _md(html, heading_style="ATX", bullets="-",
               keep_inline_images_in=["td", "th", "li", "p", "a", "span"])
    text = re.sub(r"\n{3,}", "\n\n", text).strip() + "\n"
    if not text.strip():
        raise RuntimeError(f"no text extracted from {path!r}")
    return text, images


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
        logger.exception("[ingest] %s: pandoc conversion failed — degrading to mammoth (tables lost)", path)
        import mammoth
        with open(path, "rb") as f:
            return mammoth.convert_to_markdown(f).value
