"""The Concierge's tool belt — every tool hits a real backend.

`build_project_tools(console, project_id)` binds the current project's Console + memory store into
the tools the agent may call:
  · project memory — write_to_project_memory / get_from_project_memory / create_project_summary
  · pipeline       — check_project_status (returns live state so the agent reasons about progress)
  · company research — exa_search (quick) / fusion_search (deep), from research.py; enrich_company
    (CBT-4) is the CBT-1 wow-prefill lookup specifically — same quick-mode call, name-or-website
    input, "sources only" result the concierge is instructed to present honestly (default_prompt.py)
  · document reading (SOF-62) — search_document_summaries (coarse, pick 2-3 relevant documents) /
    fetch_document_markdown (read one in full)
  · product brief (SOF-137, Minimum Machinery) — finalize_product_brief (writes the brief MD to
    storage, the single kind='product_brief' artifact Stage 1 builds from) / read_product_brief
    (read it back to self-check against the system prompt's criteria) / hand_off_to_factory (calls
    the SAME Console.promote_draft the UI button calls — no separate agent-side approval machinery;
    doubt is expressed in chat, the user (or the agent) can always hand off once a brief exists)
"""
from __future__ import annotations

import json
from dataclasses import asdict

from software_factory import storage
from software_factory.console import Console
from software_factory.db import ProjectStore
from software_factory.memory import search as memory_search
from software_factory.memory.ingest import _recompute_project_rollup, estimate_tokens
from software_factory.memory.store import MemoryStore
from software_factory.research import ResearchError, research_company
from software_factory.services.errors import ServiceError

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
        try:
            matches = memory_search.search("project", project_id, query)
            overview = store.overview("project", project_id)
            state = console._load_state(project_id)
            return json.dumps({
                "matches": matches,
                "overview": overview.get("rollup"),
                "notes": list(state.concierge_notes or []),
            }, default=str)
        except Exception as exc:  # a broken tool must degrade the answer, never kill the chat
            return f"memory search unavailable ({type(exc).__name__}: {exc}) — answer from the conversation and your context."

    @tool
    def create_project_summary() -> str:
        """Recompute and return the project's memory summary — the rollup over every ingested
        document. Call after documents finish ingesting, or when the user asks what you know."""
        try:
            _recompute_project_rollup(console, project_id, store)
            return store.overview("project", project_id).get("rollup") or "(no summary yet)"
        except Exception as exc:  # degrade, never kill the chat
            return f"summary unavailable ({type(exc).__name__}: {exc})"

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
        """Deep web research on a company via OpenRouter Fusion — multi-model panel + web
        synthesis, richer than exa_search. SOF-79: takes ~3 minutes (real measured latency
        ~165-180s), not a quick call — only reach for this when exa_search's fast pass genuinely
        isn't enough, and tell the user it'll take a few minutes before calling it."""
        try:
            return json.dumps(asdict(research_company(company_name, website=website, mode="deep")), default=str)
        except ResearchError as exc:
            return f"research unavailable: {exc}"

    @tool
    def enrich_company(name: str = "", website: str = "") -> str:
        """Look a company up on the web (quick mode, ~1-3s) — the CBT-1 wow-prefill lookup. Returns
        profile fields + the source URLs consulted (never a confidence score). Use when the user
        hasn't described their company yet and agrees to a lookup ("want me to look you up?");
        pass whichever of name/website you have — the other is optional."""
        try:
            p = research_company(name or website, website=website or None, mode="quick")
            return json.dumps(p.to_dict())
        except ResearchError as exc:
            return f"company lookup failed: {exc}"  # truth degrades the answer, never kills the chat

    @tool
    def search_document_summaries(query: str) -> str:
        """Find which 2-3 uploaded documents are relevant to `query` by searching document-level
        summaries (fast, coarse). Call this BEFORE fetch_document_markdown or chunk-level search
        once there are several documents — don't search everything by default."""
        try:
            hits = memory_search.search_documents("project", project_id, query)
        except Exception as exc:
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
    def finalize_product_brief(markdown: str) -> str:
        """Save your final, detailed product brief — the single source Stage 1 builds from
        (supersedes the raw intake composition). Call once you're genuinely confident in the
        scope, pain points, business problem, and audience (your own system-prompt criteria —
        use read_product_brief to check your latest save against them before hand-off). A later
        call supersedes an earlier one (read_product_brief/Console.product_brief always read the
        newest). Writes the MD to the project's durable storage, not just the database."""
        md = (markdown or "").strip()
        if not md:
            return "markdown is empty — nothing saved"
        url = storage.put(project_id, "product-brief.md", md.encode())
        paths = console._paths(project_id)
        ProjectStore(paths["db"]).record_artifact(
            "Product Brief", url, kind="product_brief", agent="concierge")
        return "saved"

    @tool
    def read_product_brief() -> str:
        """Read back your own finalized product brief in full, so you can check it against your
        system prompt's criteria (scope, pain points, business problem, audience) before hand-off.
        Returns a message saying none exists yet if finalize_product_brief hasn't been called."""
        brief = console.product_brief(project_id)
        return brief if brief else "no product brief exists yet — call finalize_product_brief first"

    @tool
    def hand_off_to_factory() -> str:
        """Promote this project into the factory and launch Stage 1 — the SAME action the user's
        "Hand off to the factory" button performs (calls the identical Console.promote_draft).
        Call this yourself once you and the user agree you're ready, instead of only ever offering
        the button. Refuses with the real reason (identical to what the button shows) if there is
        no finalized product brief yet — call finalize_product_brief first."""
        try:
            console.promote_draft(project_id)
        except ServiceError as exc:
            return str(exc.detail)
        return "handed off — Stage 1 is launching"

    return [write_to_project_memory, get_from_project_memory, create_project_summary,
            check_project_status, exa_search, fusion_search, enrich_company,
            search_document_summaries, fetch_document_markdown, finalize_product_brief,
            read_product_brief, hand_off_to_factory]
