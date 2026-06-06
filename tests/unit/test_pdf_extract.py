"""Tests for pdf_extract — turn an uploaded document into Markdown via markitdown."""
import pytest

from software_factory.pdf_extract import extract_to_markdown


def test_returns_markdown_from_converter(tmp_path):
    doc = tmp_path / "proposal.pdf"
    doc.write_bytes(b"%PDF-1.4 fake")
    out = extract_to_markdown(str(doc), convert=lambda p: "# Title\n\nbody text")
    assert out == "# Title\n\nbody text"


def test_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        extract_to_markdown(str(tmp_path / "nope.pdf"), convert=lambda p: "x")


def test_empty_extraction_raises(tmp_path):
    """A silently empty extraction is a failure, not a valid result."""
    doc = tmp_path / "blank.pdf"
    doc.write_bytes(b"%PDF-1.4 fake")
    with pytest.raises(RuntimeError):
        extract_to_markdown(str(doc), convert=lambda p: "   \n  ")
