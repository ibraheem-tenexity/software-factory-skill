"""Tests for input_pipeline — input → (pdf→markdown) → markdown+prompt → Stage 1 input."""
import base64
import os

import pytest

from software_factory.input_pipeline import make_prompt, persist_and_compose


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode()


# ---- make_prompt (pure composition) ----

def test_make_prompt_combines_description_and_docs():
    out = make_prompt("Build an HR app", [("brief.pdf", "# Brief\n\nHire faster")])
    assert "Build an HR app" in out
    assert "brief.pdf" in out           # the document is labeled
    assert "# Brief" in out             # its markdown body is included
    assert "Hire faster" in out


def test_make_prompt_with_no_docs_is_just_the_description():
    assert make_prompt("just a prompt", []) == "just a prompt"


def test_make_prompt_with_no_description_is_just_the_docs():
    out = make_prompt("", [("a.pdf", "# A")])
    assert "# A" in out
    assert "a.pdf" in out


# ---- persist_and_compose (I/O + conversion) ----

def test_pdf_is_converted_to_markdown_not_kept_raw(tmp_path):
    input_dir = str(tmp_path / "input")
    written = persist_and_compose(
        input_dir, "analyze this",
        [{"name": "brief.pdf", "content_b64": _b64(b"%PDF-1.4 ...")}],
        extract=lambda path: "# Extracted\n\nthe contract terms",
    )
    assert not os.path.exists(os.path.join(input_dir, "brief.pdf"))   # raw consumed
    md = open(os.path.join(input_dir, "brief.pdf.md")).read()
    assert "# Extracted" in md
    assert "brief.pdf.md" in written


def test_composed_context_contains_prompt_and_extracted_markdown(tmp_path):
    input_dir = str(tmp_path / "input")
    persist_and_compose(
        input_dir, "analyze this brief",
        [{"name": "brief.pdf", "content_b64": _b64(b"%PDF-1.4 ...")}],
        extract=lambda path: "# Extracted\n\nthe contract terms",
    )
    ctx = open(os.path.join(input_dir, "context.txt")).read()
    assert "analyze this brief" in ctx
    assert "the contract terms" in ctx


def test_non_pdf_file_is_written_as_is(tmp_path):
    input_dir = str(tmp_path / "input")
    persist_and_compose(
        input_dir, "", [{"name": "notes.txt", "content_b64": _b64(b"raw notes")}],
        extract=lambda path: (_ for _ in ()).throw(AssertionError("should not extract")),
    )
    assert open(os.path.join(input_dir, "notes.txt"), "rb").read() == b"raw notes"


def test_filename_traversal_is_stripped_to_basename(tmp_path):
    input_dir = str(tmp_path / "input")
    persist_and_compose(
        input_dir, "", [{"name": "../../evil.txt", "content_b64": _b64(b"x")}],
        extract=lambda p: "x",
    )
    assert os.path.exists(os.path.join(input_dir, "evil.txt"))
    assert not os.path.exists(os.path.join(str(tmp_path), "evil.txt"))


def test_file_missing_content_raises_rather_than_silently_skipping(tmp_path):
    """A malformed attachment is surfaced, not dropped."""
    input_dir = str(tmp_path / "input")
    with pytest.raises(ValueError):
        persist_and_compose(input_dir, "", [{"name": "brief.pdf"}], extract=lambda p: "x")
