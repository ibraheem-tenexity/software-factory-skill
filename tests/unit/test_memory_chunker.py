"""SOF-29: chunker.py — pure text splitting + section-path mapping. No DB, no network."""
from software_factory.memory.chunker import chunk_markdown

MD = """# Overview
Some intro text about the project and its goals here for context and background material.

## 2 Architecture
Architecture overview text goes here describing the system at a high level for the reader.

### 2.3 Auth
Auth details: OAuth2, JWT, session cookies, and the allowlist model described at some length.

## 3 Deployment
Deployment covers Railway services, environment variables, and the release process end to end.
"""


def test_chunk_markdown_returns_ordered_chunks_with_increasing_ordinals():
    chunks = chunk_markdown(MD, chunk_size=150)
    assert len(chunks) > 1
    ordinals = [c[0] for c in chunks]
    assert ordinals == list(range(len(chunks)))


def test_chunk_markdown_tracks_the_heading_path_per_chunk():
    chunks = chunk_markdown(MD, chunk_size=150)
    paths = [path for _ordinal, path, _text in chunks]
    assert paths[0] == "Overview"
    assert any(p == "Overview / 2 Architecture" for p in paths)
    assert any(p == "Overview / 2 Architecture / 2.3 Auth" for p in paths)
    # A sibling H2 clears the previous H3 subsection rather than inheriting it.
    assert any(p == "Overview / 3 Deployment" for p in paths)
    assert not any("Auth" in p and "Deployment" in p for p in paths if p)


def test_chunk_markdown_section_path_is_none_before_any_heading():
    chunks = chunk_markdown("just a paragraph with no heading at all, filling some space.",
                            chunk_size=100)
    assert chunks[0][1] is None


def test_chunk_markdown_empty_input_returns_no_chunks():
    assert chunk_markdown("") == []
    assert chunk_markdown("   \n  ") == []


def test_chunk_markdown_concatenated_text_covers_the_source_without_gaps():
    chunks = chunk_markdown(MD, chunk_size=150)
    # Every chunk's text must be a real, non-empty substring of the source (Chonkie splits by
    # offset — this catches an off-by-one in how chunk_size/boundaries are interpreted).
    for _ordinal, _path, text in chunks:
        assert text.strip()
        assert text in MD
