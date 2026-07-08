"""SOF-32: the ingestion pipeline — blob -> parse -> chunk -> embed -> fts -> summarize ->
reference-backed assumptions -> project overview rollup -> cost. Console-side (never in a stage
agent). Always on (SOF-71) — memory is core product, not an opt-in rollout guard; a document
that fails to ingest (missing key, model error) is marked `failed` and surfaced in the UI, never
silently skipped.

Layering: this module is classified CORE (tests/unit/test_boundary.py) and must never import
`console.*`, even transitively. `console`/`push_progress` are passed in by the caller (the
upload route / org-doc-use hook), exactly like memory/cost.py already takes `console` as a
parameter rather than importing a global singleton.
"""
from __future__ import annotations

import json
import os
import tempfile
import threading
from typing import Callable

from .. import docx_extract, pdf_extract, storage
from ..blobs import BlobStore
from ..log import get_logger
from . import chunker, embed, pricing
from .cost import record_ingestion_cost
from .store import MemoryStore

logger = get_logger(__name__)

SUMMARIZE_MODEL = "anthropic/claude-haiku-4.5"
_OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
_ESTIMATED_CHARS_PER_TOKEN = 4  # standard rough heuristic for pre-call cost estimation


def estimate_tokens(text: str) -> int:
    """Rough token estimate (chars/4) for gating decisions like "is this document small enough
    to read whole" — same heuristic _estimate_cost_usd already uses. Not for billing."""
    return len(text or "") // _ESTIMATED_CHARS_PER_TOKEN


def maybe_ingest_async(blob_id: int, console, push_progress: Callable[[str | None, dict], None] | None = None) -> None:
    """Fire-and-forget: spawn ingest_blob on a daemon thread. Never blocks the caller (an upload
    HTTP handler) and never lets an ingest failure propagate into it — a genuine failure (missing
    key, model error) is caught inside ingest_blob and marked `failed`, not swallowed here."""
    t = threading.Thread(target=_ingest_blob_safe, args=(blob_id, console, push_progress),
                        daemon=True, name=f"ingest-blob-{blob_id}")
    t.start()


def _ingest_blob_safe(blob_id: int, console, push_progress) -> None:
    try:
        ingest_blob(blob_id, console=console, push_progress=push_progress)
    except Exception:
        logger.exception("[memory.ingest] blob %s: unhandled failure in background ingest", blob_id)


def _noop_progress(_project_id, _event) -> None:
    pass


def _fetch_blob_bytes(blob: dict) -> bytes:
    """blobs.storage_key is already the full bucket-relative path (see storage.put) — fetch it
    with storage.get_by_path, not the two-arg storage.get(scope_id, key), which would
    re-prefix an already-full path and 404 (SOF-50)."""
    return storage.get_by_path(blob["storage_key"])


def _extract(path: str, tmp_dir: str) -> tuple[str, list[str]]:
    """(markdown_text, [absolute image paths]). Only .docx gets image extraction (T3.2's own
    scope note: docx_extract already extracts images from Word tables; PDF image extraction
    doesn't exist in this codebase yet — text-only for everything else, including PDF)."""
    if path.lower().endswith(".docx"):
        try:
            text, rel_images = docx_extract.extract_with_images(path, tmp_dir)
            return text, [os.path.join(tmp_dir, rel) for rel in rel_images]
        except ImportError:
            return docx_extract.extract_to_markdown(path), []
    return pdf_extract.extract_to_markdown(path), []


def _record_extracted_images(blob: dict, image_paths: list[str], blobs_store: BlobStore) -> None:
    """Upload each image docx_extract wrote to disk as its own blobs row, with provenance
    linking back to the parent document. source_page is None — a .docx has no fixed page
    concept (Word reflows); only set when/if PDF image extraction exists (it doesn't yet)."""
    for i, img_path in enumerate(image_paths, start=1):
        ext = os.path.splitext(img_path)[1] or ".png"
        key = f"materials/extracted/{blob['id']}/image-{i:02d}{ext}" if blob["scope"] == "project" \
            else f"kb/extracted/{blob['id']}/image-{i:02d}{ext}"
        storage_scope_id = blob["scope_id"] if blob["scope"] == "project" else f"org/{blob['scope_id']}"
        storage.put(storage_scope_id, key, img_path)
        with open(img_path, "rb") as f:
            data = f.read()
        blobs_store.record(
            blob["scope"], blob["scope_id"], f"{storage_scope_id}/{key}",
            kind="image", name=os.path.basename(img_path), content_type=None,
            size_bytes=len(data), sha256=storage.sha256(data),
            source_blob_id=blob["id"], source_page=None,
            provenance={"extractor": "docx_extract"},
        )


def _summarize_and_extract_facts(chunks: list[tuple[int, str | None, str]], doc_name: str,
                                 client=None) -> tuple[str, list[dict], list[dict], dict]:
    """One OpenRouter chat-completions call -> (summary_md, outline, assumptions, usage).
    The assumptions returned here are UNFILTERED — the caller (ingest_blob) is responsible for
    dropping any entry whose section_path doesn't match a real chunk section_path and for
    attaching document_blob_id itself; this function never trusts the model for provenance,
    only for the claim text + which section it claims to come from. (The model-facing JSON key
    stays `key_facts` — it's a good extraction framing for the LLM; the product-facing name for
    what these become is "assumptions", confirmed or corrected by the customer.)"""
    if not chunks:
        return "", [], [], {}
    client = client or _default_chat_client()
    body = "\n\n".join(f"[section: {path or '(no heading)'}]\n{text}" for _o, path, text in chunks)
    prompt = (
        f"Document: {doc_name}\n\n{body}\n\n"
        "Return ONLY JSON (no prose, no markdown fences) with this exact shape:\n"
        '{"summary_md": "1-2 paragraph summary in markdown", '
        '"outline": [{"title": "section title", "gist": "one-line gist"}], '
        '"key_facts": [{"fact": "a specific, checkable fact", "section_path": "the exact '
        '[section: ...] value it came from"}]}\n'
        "Every key_fact MUST cite a section_path that appears verbatim above in a [section: ...] "
        "marker. Do not include a fact you cannot attribute to one of those exact section_path "
        "values. Do not include confidence levels or hedging language — state facts plainly or "
        "omit them."
    )
    usage = {"prompt_tokens": 0, "completion_tokens": 0}
    parsed = None
    # response_format=json_object is not reliably honored through OpenRouter for every provider —
    # the model can come back with fenced/prose-wrapped JSON. Rescue-parse, and retry once before
    # giving up (an empty summary silently marked 'ready' downstream is worse than a second call).
    for attempt in range(2):
        resp = client.chat.completions.create(
            model=SUMMARIZE_MODEL,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
        )
        if getattr(resp, "usage", None) is not None:
            usage["prompt_tokens"] += resp.usage.prompt_tokens or 0
            usage["completion_tokens"] += resp.usage.completion_tokens or 0
        try:
            content = resp.choices[0].message.content or ""
        except (IndexError, AttributeError):
            content = ""
        parsed = _rescue_parse_json(content)
        if parsed is not None:
            break
        logger.warning("[memory.ingest] summarization response wasn't valid JSON for %s (attempt %s)",
                       doc_name, attempt + 1)
    if parsed is None:
        return "", [], [], usage
    return (parsed.get("summary_md") or "", parsed.get("outline") or [],
           parsed.get("key_facts") or [], usage)


def _rescue_parse_json(content: str):
    """json.loads with a rescue pass for fenced/prose-wrapped replies: strip ``` fences, then
    fall back to the outermost {...} span. Returns None when nothing parses to a dict."""
    for candidate in (content, content.strip().strip("`").removeprefix("json")):
        try:
            out = json.loads(candidate)
            return out if isinstance(out, dict) else None
        except ValueError:
            pass
    i, j = content.find("{"), content.rfind("}")
    if 0 <= i < j:
        try:
            out = json.loads(content[i:j + 1])
            return out if isinstance(out, dict) else None
        except ValueError:
            return None
    return None


def _default_chat_client():
    from openai import OpenAI
    return OpenAI(base_url=_OPENROUTER_BASE_URL, api_key=os.environ["OPENROUTER_API_KEY"])


def _filter_assumptions(raw_facts: list[dict], blob_id: int,
                        valid_section_paths: set[str]) -> tuple[list[dict], list[dict]]:
    """The trust boundary (product spec: no confidence scores, no unreferenced claims). A claim
    whose section_path isn't a real section_path from THIS document's own chunks is never
    stored as an assumption — it comes back as an unreferenced candidate. SOF-60: ingest no
    longer auto-escalates those into blocking reflection questions (that was SOF-37's blind
    per-document pass); the Concierge raises reflection questions itself, from its own analysis,
    via its tool belt — same reflection_questions state, gate, and Interview UI, better source.
    document_blob_id is attached here, by code, never asked of the model, for both lists.

    Returns (referenced_assumptions, unreferenced_candidates)."""
    referenced, unreferenced = [], []
    for f in raw_facts:
        fact = (f.get("fact") or "").strip()
        section_path = f.get("section_path")
        if not fact:
            continue
        entry = {"fact": fact, "document_blob_id": blob_id, "section_path": section_path}
        if section_path in valid_section_paths:
            referenced.append(entry)
        else:
            unreferenced.append(entry)
    return referenced, unreferenced


def _estimate_cost_usd(model: str, kind: str, *, input_chars: int = 0,
                       prompt_tokens: int = 0, completion_tokens: int = 0) -> float | None:
    """Real live OpenRouter price x real-or-estimated tokens. Returns None (never a fabricated
    number) if live pricing can't be fetched — the caller must log loudly and skip recording,
    per the operator's explicit call: never silently record $0 for a call that really happened."""
    price = pricing.openrouter_price(model, kind=kind)
    if price is None:
        return None
    if kind == "embedding":
        # Estimated — the embeddings API path doesn't thread real usage back through
        # embed.embed_texts (T3.1's existing, unchanged contract). Real price, estimated tokens.
        tokens = input_chars / _ESTIMATED_CHARS_PER_TOKEN
        return tokens * price["input"]
    return prompt_tokens * price["input"] + completion_tokens * price["output"]


def _build_rollup(doc_summaries: list[dict]) -> str:
    """Non-LLM reduce over doc_summary rows — a bullet list of doc name + first line of its
    summary. The design doc allows a plain reduce here; no second LLM call needed."""
    lines = []
    for d in doc_summaries:
        if d.get("status") != "ready" or not d.get("summary_md"):
            continue
        first_line = d["summary_md"].strip().splitlines()[0] if d["summary_md"].strip() else ""
        lines.append(f"- {d.get('name') or 'document'}: {first_line}")
    return "\n".join(lines)


def ingest_blob(blob_id: int, *, console, push_progress: Callable[[str | None, dict], None] | None = None,
                force: bool = False) -> dict:
    """The pipeline for one document. Never raises — a parse/summarize/embed failure marks
    this doc `failed` and returns a clean dict, so a caller looping over N blobs is never
    killed by one bad file (SOF-32 AC).

    `force=True` (SOF-36's Regenerate button) bypasses the unchanged-content dedup skip below —
    a user who explicitly asks for a fresh summary wants one even if the file hasn't changed."""
    push_progress = push_progress or _noop_progress
    blobs_store = BlobStore()
    memory_store = MemoryStore()
    blob = blobs_store.get_blob(blob_id)
    if blob is None:
        return {"blob_id": blob_id, "status": "failed", "error": "blob not found"}

    scope, scope_id = blob["scope"], blob["scope_id"]
    project_id = scope_id if scope == "project" else None
    doc_name = blob.get("name") or f"blob-{blob_id}"

    existing = memory_store.get_doc_summary(blob_id)
    if (not force and existing and existing.get("status") == "ready"
            and existing.get("content_sha256") == blob.get("sha256")):
        return {"blob_id": blob_id, "status": "ready", "skipped": "unchanged (content_sha256 dedup)"}

    push_progress(project_id, {"blob_id": blob_id, "doc_name": doc_name, "stage": "parsing", "pct": 5, "status": "running"})
    try:
        with tempfile.TemporaryDirectory() as tmp_dir:
            src_path = os.path.join(tmp_dir, doc_name)
            with open(src_path, "wb") as f:
                f.write(_fetch_blob_bytes(blob))
            md_text, image_paths = _extract(src_path, tmp_dir)
            if image_paths:
                _record_extracted_images(blob, image_paths, blobs_store)
    except Exception as exc:
        logger.warning("[memory.ingest] blob %s (%s) parse failed: %s", blob_id, doc_name, exc)
        memory_store.upsert_doc_summary(blob_id, scope, scope_id, status="failed")
        push_progress(project_id, {"blob_id": blob_id, "doc_name": doc_name, "stage": "parsing", "pct": 100, "status": "failed"})
        return {"blob_id": blob_id, "status": "failed", "error": str(exc)}

    # SOF-60: persist the full converted markdown (chunking loses whole-document order) as an
    # origin='user' artifact so agents can read the document exactly as written.
    if project_id:
        memory_store.record_document_markdown(project_id, blob_id, doc_name, md_text)

    push_progress(project_id, {"blob_id": blob_id, "doc_name": doc_name, "stage": "chunking", "pct": 20, "status": "running"})
    chunks = chunker.chunk_markdown(md_text)
    valid_section_paths = {path for _o, path, _t in chunks if path}

    push_progress(project_id, {"blob_id": blob_id, "doc_name": doc_name, "stage": "embedding", "pct": 40, "status": "running"})
    try:
        vectors = embed.embed_texts([text for _o, _p, text in chunks]) if chunks else []
    except Exception as exc:
        logger.warning("[memory.ingest] blob %s (%s) embedding failed: %s", blob_id, doc_name, exc)
        memory_store.upsert_doc_summary(blob_id, scope, scope_id, status="failed")
        push_progress(project_id, {"blob_id": blob_id, "doc_name": doc_name, "stage": "embedding", "pct": 100, "status": "failed"})
        return {"blob_id": blob_id, "status": "failed", "error": str(exc)}
    memory_store.replace_chunks(blob_id, chunks, scope=scope, scope_id=scope_id, dense=vectors)

    embed_chars = sum(len(text) for _o, _p, text in chunks)
    embed_cost = _estimate_cost_usd(embed.DEFAULT_MODEL, "embedding", input_chars=embed_chars)
    if embed_cost is None:
        logger.warning("[memory.ingest] blob %s: could not fetch live OpenRouter pricing for %s "
                       "— embedding cost NOT recorded (never recording a fabricated $0)",
                       blob_id, embed.DEFAULT_MODEL)
    elif project_id:
        record_ingestion_cost(console, project_id, model=embed.DEFAULT_MODEL, provider="openrouter", usd=embed_cost)

    push_progress(project_id, {"blob_id": blob_id, "doc_name": doc_name, "stage": "summarizing", "pct": 65, "status": "running"})
    try:
        summary_md, outline, raw_facts, usage = _summarize_and_extract_facts(chunks, doc_name)
    except Exception as exc:
        logger.warning("[memory.ingest] blob %s (%s) summarization failed: %s", blob_id, doc_name, exc)
        memory_store.upsert_doc_summary(blob_id, scope, scope_id, status="failed")
        push_progress(project_id, {"blob_id": blob_id, "doc_name": doc_name, "stage": "summarizing", "pct": 100, "status": "failed"})
        return {"blob_id": blob_id, "status": "failed", "error": str(exc)}

    assumptions, _unreferenced = _filter_assumptions(raw_facts, blob_id, valid_section_paths)

    if usage:
        summarize_cost = _estimate_cost_usd(SUMMARIZE_MODEL, "chat", prompt_tokens=usage.get("prompt_tokens", 0),
                                            completion_tokens=usage.get("completion_tokens", 0))
        if summarize_cost is None:
            logger.warning("[memory.ingest] blob %s: could not fetch live OpenRouter pricing for %s "
                           "— summarization cost NOT recorded", blob_id, SUMMARIZE_MODEL)
        elif project_id:
            record_ingestion_cost(console, project_id, model=SUMMARIZE_MODEL, provider="openrouter",
                                  input_tokens=usage.get("prompt_tokens", 0),
                                  output_tokens=usage.get("completion_tokens", 0), usd=summarize_cost)

    memory_store.upsert_doc_summary(
        blob_id, scope, scope_id, summary_md=summary_md, assumptions=assumptions, outline=outline,
        content_sha256=blob.get("sha256"), status="ready",
    )

    if scope == "project":
        _recompute_project_rollup(console, scope_id, memory_store)

    push_progress(project_id, {"blob_id": blob_id, "doc_name": doc_name, "stage": "done", "pct": 100, "status": "ready"})
    return {"blob_id": blob_id, "status": "ready", "chunks": len(chunks), "assumptions": len(assumptions)}


def _recompute_project_rollup(console, project_id: str, memory_store: MemoryStore) -> None:
    """Read every ready doc_summary for this project, reduce to a short rollup, cache it in
    ProjectState.memory_overview — the locked "no third table" decision (T0.1/build-plan §7 #4).
    T3.1's MemoryStore.overview() reads the same key straight off the raw projectstate.data
    JSON blob; ProjectState.save() writes this field into that exact blob, so both agree."""
    conn = memory_store._connect()
    try:
        rows = conn.execute(
            "SELECT ds.summary_md, ds.status, b.name FROM doc_summary ds "
            "JOIN blobs b ON b.id = ds.blob_id WHERE ds.scope = ? AND ds.scope_id = ?",
            ("project", project_id),
        ).fetchall()
    finally:
        conn.close()
    rollup = _build_rollup([{"summary_md": r["summary_md"], "status": r["status"], "name": r["name"]} for r in rows])
    state = console._load_state(project_id)
    state.memory_overview = rollup
    state.save()
