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


def test_docx_is_extracted_to_markdown_and_composed(tmp_path):
    # Word docs follow the same contract as PDFs: persisted -> converted (pandoc) -> raw file
    # consumed -> markdown + composed context written. Singer-SOW is the canonical .docx input.
    import base64, os
    b64 = base64.b64encode(b"PK fake docx bytes").decode()
    written = persist_and_compose(
        str(tmp_path), "build the AutoBuilder",
        [{"name": "singer-sow.docx", "content_b64": b64}],
        extract_docx=lambda p: "# Singer SOW\n\nrecipes, quotes, P21",
    )
    assert "singer-sow.docx.md" in written and "context.txt" in written
    assert not os.path.exists(os.path.join(str(tmp_path), "singer-sow.docx"))  # consumed
    ctx = open(os.path.join(str(tmp_path), "context.txt")).read()
    assert "build the AutoBuilder" in ctx and "recipes, quotes, P21" in ctx


def test_docx_extractor_real_pandoc_on_singer_sow():
    # Real-binary integration check (skipped when pypandoc/mammoth aren't installed locally):
    # the actual Singer SOW must extract with structure intact.
    import pytest, os
    doc = "/home/ibraheem/sf-docx-input/singer-sow-autobuilder.docx"
    if not os.path.isfile(doc):
        pytest.skip("canonical Singer SOW not present")
    try:
        from software_factory.docx_extract import extract_to_markdown as dx
        md = dx(doc)
    except ImportError:
        pytest.skip("pypandoc/mammoth not installed locally")
    assert len(md) > 2000
    assert "82,500" in md or "82.5" in md or "$82" in md   # the milestone pricing survives
