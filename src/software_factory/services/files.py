"""Filename → doc-kind classifier for uploaded materials / KB docs (shared by the org + projects
services). Lives in the service layer so both consumers — and console.state's `_doc_kind` re-export —
reference one definition."""
from __future__ import annotations

_DOC_KIND = {"pdf": "pdf", "xlsx": "xlsx", "xls": "xlsx", "csv": "csv", "doc": "doc", "docx": "doc",
             "mp4": "video", "mov": "video", "png": "img", "jpg": "img", "jpeg": "img"}


def doc_kind(name: str) -> str:
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    return _DOC_KIND.get(ext, "doc")
