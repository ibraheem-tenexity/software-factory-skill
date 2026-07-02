"""The Concierge's tool belt (concierge-agent-spec.md §5) — every tool hits a real backend.

`build_project_tools(console, project_id)` binds the current project's Console + memory store into
the tools the agent may call:
  · project memory — write_to_project_memory / get_from_project_memory / create_project_summary
  · pipeline       — check_project_status (returns live state so the agent reasons about progress)
  · company research — exa_search (quick) / fusion_search (deep), from research.py
  · document reading (SOF-62) — search_document_summaries (coarse, pick 2-3 relevant documents) /
    fetch_document_markdown (read one in full) / flag_for_verification (raise a question for the
    user, replacing SOF-37's automatic per-document escalation) / finalize_product_brief (the
    Concierge's final brief — the single kind='product_brief' artifact Stage 1 builds from)
"""
from __future__ import annotations

import hashlib
import json
import time
from dataclasses import asdict

from software_factory.console import Console
from software_factory.db import ProjectStore
from software_factory.memory import search as memory_search
from software_factory.memory.ingest import _recompute_project_rollup, estimate_tokens
from software_factory.memory.store import MemoryStore
from software_factory.research import ResearchError, research_company

# Above this estimated-token size, fetch_document_markdown refuses to dump the whole document into
# context and points the agent at search/summary tools instead (concierge-memory plan §7).
_MAX_FULL_DOCUMENT_TOKENS = 500_000

# Deferred at module level intentionally: langchain_core is a heavy import and this module is
# imported by console-side code paths that don't always need the agent. Kept local to the factory.
from langchain_core.tools import tool


def build_project_tools(console: Console, project_id: str) -> list:
    """Return the Concierge tools bound to this project."""
    store = MemoryStore()

    @tool
    def write_to_project_memory(note: str) -> str:
        """Save a durable fact about THIS project (a goal, constraint, decision, or success
        metric) so the build remembers it. Use it as soon as you learn something worth keeping."""
        state = console._load_state(project_id)
        state.concierge_notes = list(state.concierge_notes or []) + [note]
        state.save()
        return "saved"

    @tool
    def get_from_project_memory(query: str) -> str:
        """Search everything known about THIS project — ingested documents, the rolled-up
        overview, and notes you've saved — and return the most relevant results for `query`."""
        matches = memory_search.search("project", project_id, query)
        overview = store.overview("project", project_id)
        state = console._load_state(project_id)
        return json.dumps({
            "matches": matches,
            "overview": overview.get("rollup"),
            "notes": list(state.concierge_notes or []),
        }, default=str)

    @tool
    def create_project_summary() -> str:
        """Recompute and return the project's memory summary — the rollup over every ingested
        document. Call after documents finish ingesting, or when the user asks what you know."""
        _recompute_project_rollup(console, project_id, store)
        return store.overview("project", project_id).get("rollup") or "(no summary yet)"

    @tool
    def check_project_status() -> str:
        """Return the live build-pipeline state for THIS project (phase, stage, deploy URL, spend,
        outstanding dependencies) so you can answer 'where is my build' accurately."""
        return json.dumps(console.status(project_id), default=str)

    @tool
    def exa_search(company_name: str, website: str | None = None) -> str:
        """Quick web research on a company via Exa (~1-3s). Use to enrich the user's company
        profile — industry, what they do, size — from their name and (optional) website."""
        try:
            return json.dumps(asdict(research_company(company_name, website=website, mode="quick")), default=str)
        except ResearchError as exc:
            return f"research unavailable: {exc}"

    @tool
    def fusion_search(company_name: str, website: str | None = None) -> str:
        """Deep web research on a company via OpenRouter Fusion (~10-30s; richer than exa_search,
        web synthesis). Use when you need a thorough company profile."""
        try:
            return json.dumps(asdict(research_company(company_name, website=website, mode="deep")), default=str)
        except ResearchError as exc:
            return f"research unavailable: {exc}"

    @tool
    def search_document_summaries(query: str) -> str:
        """Find which 2-3 uploaded documents are relevant to `query` by searching document-level
        summaries (fast, coarse). Call this BEFORE fetch_document_markdown or chunk-level search
        once there are several documents — don't search everything by default."""
        try:
            hits = memory_search.search_documents("project", project_id, query)
        except ValueError as exc:
            return f"search failed: {exc}"
        return json.dumps(hits, default=str)

    @tool
    def fetch_document_markdown(blob_id: int) -> str:
        """Read one uploaded document in full, in its original order (chunk search loses
        whole-document structure). Use when a summary isn't enough to answer a specific question.
        Tells you to use search_document_summaries or get_from_project_memory instead if the
        document is too large to read whole."""
        content = store.get_document_markdown(blob_id)
        if content is None:
            return f"document {blob_id} has no readable markdown (not ingested, or not a document)"
        tokens = estimate_tokens(content)
        if tokens > _MAX_FULL_DOCUMENT_TOKENS:
            return (f"document {blob_id} is too large to read whole (~{tokens} estimated tokens) "
                    "— use search_document_summaries to confirm it's relevant, or "
                    "get_from_project_memory for exact passages, instead.")
        return content

    @tool
    def flag_for_verification(question: str, related_document_blob_id: int | None = None) -> str:
        """Raise something you're not confident about for the user to confirm or correct — an
        inference, a gap, or a contradiction across documents. Appears as an open question the
        user must answer or dismiss before hand-off. This is now the ONLY way reflection
        questions are created (ingest no longer auto-generates them) — use it whenever you're
        unsure, not just when explicitly asked."""
        text = (question or "").strip()
        if not text:
            return "question is empty — nothing flagged"
        state = console._load_state(project_id)
        questions = list(state.reflection_questions or [])
        # Same id convention ingest used to use: sha256(document_blob_id-or-'concierge' : question),
        # first 12 hex chars — keeps re-raising the identical question idempotent.
        seed = f"{related_document_blob_id if related_document_blob_id is not None else 'concierge'}:{text}"
        qid = hashlib.sha256(seed.encode()).hexdigest()[:12]
        if any(q["id"] == qid for q in questions):
            return "already flagged"
        questions.append({
            "id": qid, "fact": text, "document_blob_id": related_document_blob_id,
            "section_path_claimed": None, "status": "open", "answer": None,
            "created_at": time.time(),
        })
        state.reflection_questions = questions
        state.save()
        return "flagged"

    @tool
    def finalize_product_brief(markdown: str) -> str:
        """Save your final, detailed product brief — the single source Stage 1 builds from
        (supersedes the raw intake composition). Call once you're genuinely confident in the
        scope, pain points, business problem, and audience; a later call supersedes an earlier
        one (Console.product_brief always reads the newest)."""
        md = (markdown or "").strip()
        if not md:
            return "markdown is empty — nothing saved"
        paths = console._paths(project_id)
        ProjectStore(paths["db"]).record_artifact(
            "Product Brief", "", kind="product_brief", agent="concierge", content=md)
        return "saved"

    return [write_to_project_memory, get_from_project_memory, create_project_summary,
            check_project_status, exa_search, fusion_search, search_document_summaries,
            fetch_document_markdown, flag_for_verification, finalize_product_brief]
