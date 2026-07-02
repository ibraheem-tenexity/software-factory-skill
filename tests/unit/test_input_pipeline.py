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

def test_pdf_original_and_markdown_both_retained(tmp_path):
    input_dir = str(tmp_path / "input")
    written = persist_and_compose(
        input_dir, "analyze this",
        [{"name": "brief.pdf", "content_b64": _b64(b"%PDF-1.4 ...")}],
        extract=lambda path: "# Extracted\n\nthe contract terms",
    )
    # original kept on disk so caller can push it to blob storage
    assert os.path.exists(os.path.join(input_dir, "brief.pdf"))
    assert open(os.path.join(input_dir, "brief.pdf"), "rb").read() == b"%PDF-1.4 ..."
    md = open(os.path.join(input_dir, "brief.pdf.md")).read()
    assert "# Extracted" in md
    assert "brief.pdf" in written
    assert "brief.pdf.md" in written


def test_composed_context_contains_prompt_and_extracted_markdown(tmp_path):
    input_dir = str(tmp_path / "input")
    persist_and_compose(
        input_dir, "analyze this brief",
        [{"name": "brief.pdf", "content_b64": _b64(b"%PDF-1.4 ...")}],
        extract=lambda path: "# Extracted\n\nthe contract terms",
    )
    ctx = open(os.path.join(input_dir, "context.md")).read()
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
    assert "singer-sow.docx.md" in written and "context.md" in written
    # original kept on disk so caller can push it to blob storage
    assert "singer-sow.docx" in written
    assert os.path.exists(os.path.join(str(tmp_path), "singer-sow.docx"))
    ctx = open(os.path.join(str(tmp_path), "context.md")).read()
    assert "build the AutoBuilder" in ctx and "recipes, quotes, P21" in ctx


def test_docx_default_path_extracts_embedded_images(tmp_path, monkeypatch):
    # With NO injected converter, a .docx goes through the image-aware path so wireframe
    # screenshots (incl. those inside Word tables) are extracted and kept paired with the md.
    import base64, os
    from software_factory import docx_extract

    def fake_with_images(path, out_dir, img_subdir="images"):
        img_rel = os.path.join(img_subdir, "image-01.png")
        os.makedirs(os.path.join(out_dir, img_subdir), exist_ok=True)
        open(os.path.join(out_dir, img_rel), "wb").write(b"\x89PNG")
        return ("# Spec\n\n![](images/image-01.png)\n", [img_rel])

    monkeypatch.setattr(docx_extract, "extract_with_images", fake_with_images)
    written = persist_and_compose(
        str(tmp_path), "build it",
        [{"name": "spec.docx", "content_b64": base64.b64encode(b"docx").decode()}],
    )
    assert "spec.docx" in written          # original retained alongside extraction
    assert "spec.docx.md" in written
    assert os.path.isfile(os.path.join(str(tmp_path), "spec.docx"))
    assert os.path.join("images", "image-01.png") in written
    assert os.path.isfile(os.path.join(str(tmp_path), "images", "image-01.png"))


def test_docx_falls_back_to_text_when_image_deps_missing(tmp_path, monkeypatch):
    import base64, os
    from software_factory import docx_extract

    def raise_import(path, out_dir, img_subdir="images"):
        raise ImportError("markdownify not installed")

    monkeypatch.setattr(docx_extract, "extract_with_images", raise_import)
    monkeypatch.setattr(docx_extract, "extract_to_markdown", lambda p: "# Fallback text")
    written = persist_and_compose(
        str(tmp_path), "build it",
        [{"name": "spec.docx", "content_b64": base64.b64encode(b"docx").decode()}],
    )
    assert "spec.docx" in written          # original retained even via fallback path
    assert "spec.docx.md" in written
    assert os.path.isfile(os.path.join(str(tmp_path), "spec.docx"))
    assert "# Fallback text" in open(os.path.join(str(tmp_path), "spec.docx.md")).read()


def test_brief_and_interview_are_written_when_supplied(tmp_path):
    import os
    written = persist_and_compose(
        str(tmp_path), "build it", [],
        brief={"goals": "A cargo screening prototype for ground handlers."},
        interview_md="USER: build cargo screening\nAI: on it",
    )
    assert "brief.md" in written and "interview.md" in written
    assert "PROJECT BRIEF" in open(os.path.join(str(tmp_path), "brief.md")).read()
    assert "cargo screening" in open(os.path.join(str(tmp_path), "interview.md")).read()


def test_plain_text_upload_unchanged(tmp_path):
    """Non-PDF/DOCX files (images, txt, csv) are unchanged — no regression."""
    input_dir = str(tmp_path / "input")
    written = persist_and_compose(
        input_dir, "",
        [{"name": "spec.txt", "content_b64": _b64(b"raw spec text")},
         {"name": "logo.png", "content_b64": _b64(b"\x89PNG")}],
        extract=lambda p: (_ for _ in ()).throw(AssertionError("should not extract")),
    )
    assert open(os.path.join(input_dir, "spec.txt"), "rb").read() == b"raw spec text"
    assert open(os.path.join(input_dir, "logo.png"), "rb").read() == b"\x89PNG"
    assert "spec.txt" in written
    assert "logo.png" in written
    # no spurious .md extractions for plain files
    assert not any(n.endswith(".md") for n in written)


def test_pdf_original_bytes_match_what_was_uploaded(tmp_path):
    """The retained original must be bit-for-bit identical to what was uploaded."""
    input_dir = str(tmp_path / "input")
    raw_pdf = b"%PDF-1.4 fake content for test"
    persist_and_compose(
        input_dir, "test",
        [{"name": "doc.pdf", "content_b64": _b64(raw_pdf)}],
        extract=lambda path: "# Extracted",
    )
    assert open(os.path.join(input_dir, "doc.pdf"), "rb").read() == raw_pdf


# ---- tolerate_extract_failures (SOF-56 — attach_to_draft's mid-interview attach path) ----

def test_default_still_raises_on_a_malformed_pdf():
    """Regression guard: the DEFAULT behavior (start_project/_provision_and_launch's call site)
    is unchanged — a missing Stage-1 input must still surface loudly."""
    import tempfile
    input_dir = tempfile.mkdtemp()
    with pytest.raises(RuntimeError):
        persist_and_compose(
            input_dir, "", [{"name": "blank.pdf", "content_b64": _b64(b"%PDF-1.4 blank")}],
            extract=lambda path: (_ for _ in ()).throw(RuntimeError("no text extracted")),
        )


def test_tolerate_extract_failures_keeps_the_original_without_a_md_twin():
    import tempfile
    input_dir = tempfile.mkdtemp()
    written = persist_and_compose(
        input_dir, "", [{"name": "blank.pdf", "content_b64": _b64(b"%PDF-1.4 blank")}],
        extract=lambda path: (_ for _ in ()).throw(RuntimeError("no text extracted")),
        tolerate_extract_failures=True,
    )
    assert "blank.pdf" in written
    assert "blank.pdf.md" not in written
    assert os.path.exists(os.path.join(input_dir, "blank.pdf"))
    assert not os.path.exists(os.path.join(input_dir, "blank.pdf.md"))


def test_tolerate_extract_failures_does_not_raise_and_other_files_still_succeed():
    import tempfile
    input_dir = tempfile.mkdtemp()

    def flaky_extract(path):
        if "blank" in path:
            raise RuntimeError("no text extracted")
        return "# Good doc\n\nreal content"

    written = persist_and_compose(
        input_dir, "combine these",
        [{"name": "blank.pdf", "content_b64": _b64(b"%PDF-1.4 blank")},
         {"name": "good.pdf", "content_b64": _b64(b"%PDF-1.4 good")}],
        extract=flaky_extract, tolerate_extract_failures=True,
    )
    assert "blank.pdf" in written and "blank.pdf.md" not in written
    assert "good.pdf" in written and "good.pdf.md" in written
    assert os.path.exists(os.path.join(input_dir, "good.pdf"))


def test_tolerate_extract_failures_excludes_the_failed_doc_from_composed_context():
    import tempfile
    input_dir = tempfile.mkdtemp()

    def flaky_extract(path):
        if "blank" in path:
            raise RuntimeError("no text extracted")
        return "# Good doc\n\nreal content"

    persist_and_compose(
        input_dir, "combine these",
        [{"name": "blank.pdf", "content_b64": _b64(b"%PDF-1.4 blank")},
         {"name": "good.pdf", "content_b64": _b64(b"%PDF-1.4 good")}],
        extract=flaky_extract, tolerate_extract_failures=True,
    )
    ctx = open(os.path.join(input_dir, "context.md")).read()
    assert "real content" in ctx
    assert "blank.pdf" not in ctx    # a failed doc never gets an "## Attached document:" section


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


def test_product_brief_supersedes_raw_composition_as_context(tmp_path):
    """SOF-63: a Concierge-finalized product brief IS the Stage-1 input — context.md is the
    brief itself, not make_prompt's description+raw-doc concatenation. The per-document .md
    extraction is still written to disk (nothing lost), just not dumped inline."""
    input_dir = str(tmp_path / "input")
    written = persist_and_compose(
        input_dir, "analyze this brief",
        [{"name": "brief.pdf", "content_b64": _b64(b"%PDF-1.4 ...")}],
        extract=lambda path: "# Extracted\n\nthe contract terms",
        product_brief_md="# Product Brief\n\nQuote follow-up automation for Singer.",
    )
    ctx = open(os.path.join(input_dir, "context.md")).read()
    assert ctx == "# Product Brief\n\nQuote follow-up automation for Singer."
    assert "the contract terms" not in ctx          # raw doc text NOT inlined
    assert "analyze this brief" not in ctx          # raw description NOT inlined
    assert os.path.exists(os.path.join(input_dir, "brief.pdf.md"))   # extraction still on disk
    assert "context.md" in written


def test_blank_product_brief_falls_back_to_legacy_composition(tmp_path):
    """No/blank brief (API-created projects, no interview) -> the legacy composition, unchanged."""
    input_dir = str(tmp_path / "input")
    persist_and_compose(
        input_dir, "analyze this brief",
        [{"name": "brief.pdf", "content_b64": _b64(b"%PDF-1.4 ...")}],
        extract=lambda path: "# Extracted\n\nthe contract terms",
        product_brief_md="   ",
    )
    ctx = open(os.path.join(input_dir, "context.md")).read()
    assert "analyze this brief" in ctx
    assert "the contract terms" in ctx
