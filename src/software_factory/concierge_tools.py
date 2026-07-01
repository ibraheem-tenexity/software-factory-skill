"""The Concierge's tool belt (concierge-agent-spec.md §5) — every tool hits a real backend.

`build_project_tools(console, project_id)` binds the current project's Console + memory store into
the six tools the agent may call:
  · project memory — write_to_project_memory / get_from_project_memory / create_project_summary
  · pipeline       — check_project_status (returns live state so the agent reasons about progress)
  · company research — exa_search (quick) / fusion_search (deep), from research.py
"""
from __future__ import annotations

import json
from dataclasses import asdict

from software_factory.console import Console
from software_factory.memory import search as memory_search
from software_factory.memory.ingest import _recompute_project_rollup
from software_factory.memory.store import MemoryStore
from software_factory.research import ResearchError, research_company

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

    return [write_to_project_memory, get_from_project_memory, create_project_summary,
            check_project_status, exa_search, fusion_search]
