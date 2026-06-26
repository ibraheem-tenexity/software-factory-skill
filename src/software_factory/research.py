"""Company research — enrich a company profile via Exa (quick) or OpenRouter Fusion (deep)."""
from __future__ import annotations

import json
import os
import httpx
from dataclasses import dataclass, asdict


@dataclass
class CompanyProfile:
    # Core UI fields
    name: str
    website: str | None
    industry: str | None
    size_hint: str | None           # "startup" | "mid-market" | "enterprise"
    sub_focus: str | None           # e.g. "HR / Learning Management"
    connected_systems: list[str]    # e.g. ["Salesforce", "Slack"]

    # Description + rich context
    description: str
    products: list[str]
    competitors: list[dict]         # [{name, url, description}]
    recent_news: list[str]
    sources: list[str]              # URLs consulted

    # Metadata
    mode: str                       # "quick" | "deep"

    def to_dict(self) -> dict:
        return asdict(self)

    def to_prompt_block(self) -> str:
        lines = ["## Company Context", f"**Company:** {self.name}"]
        if self.website:
            lines.append(f"**Website:** {self.website}")
        if self.industry:
            lines.append(f"**Industry:** {self.industry}")
        if self.size_hint:
            lines.append(f"**Scale:** {self.size_hint}")
        if self.sub_focus:
            lines.append(f"**Sub-focus:** {self.sub_focus}")
        if self.connected_systems:
            lines.append(f"**Connected systems:** {', '.join(self.connected_systems)}")
        if self.description:
            lines.append(f"\n{self.description}")
        if self.products:
            lines.append("\n**Products/Services:**")
            lines.extend(f"- {p}" for p in self.products)
        if self.competitors:
            lines.append("\n**Competitors:**")
            for c in self.competitors:
                lines.append(f"- {c['name']} ({c.get('url', '')}) — {c.get('description', '')}")
        if self.recent_news:
            lines.append("\n**Recent news:**")
            lines.extend(f"- {n}" for n in self.recent_news)
        return "\n".join(lines)


class ResearchError(Exception):
    pass


def _exa_search(
    name: str,
    website: str | None,
    extra: str | None,
    api_key: str,
) -> CompanyProfile:
    query_parts = [name, "company overview products industry"]
    if website:
        query_parts.append(website)
    if extra:
        query_parts.append(extra)
    query = " ".join(query_parts)

    try:
        resp = httpx.post(
            "https://api.exa.ai/search",
            headers={"x-api-key": api_key, "Content-Type": "application/json"},
            json={"query": query, "numResults": 5, "contents": {"text": {"maxCharacters": 1500}}},
            timeout=15,
        )
        resp.raise_for_status()
    except Exception as exc:
        raise ResearchError(f"Exa search failed: {exc}") from exc

    results = resp.json().get("results", [])
    sources = [r["url"] for r in results if r.get("url")]
    if website and website not in sources:
        sources.insert(0, website)

    description = results[0].get("text", "")[:300].strip() if results else ""

    # Best-effort quick-mode heuristic: secondary result titles are often news,
    # but may include other pages (LinkedIn, about pages). Deep mode is richer.
    recent_news = [r["title"] for r in results[1:] if r.get("title")]

    return CompanyProfile(
        name=name,
        website=website,
        industry=None,
        size_hint=None,
        sub_focus=None,
        connected_systems=[],
        description=description,
        products=[],
        competitors=[],
        recent_news=recent_news,
        sources=sources,
        mode="quick",
    )


_FUSION_PROMPT = """\
Research the company "{name}"{website_hint}{extra_hint} and return a JSON object with EXACTLY these fields:

{{
  "name": "<company name>",
  "website": "<official website URL or null>",
  "industry": "<primary industry or null>",
  "size_hint": "<one of: startup | mid-market | enterprise | null>",
  "sub_focus": "<specific sub-area within their industry, e.g. 'HR / Learning Management' or null>",
  "connected_systems": ["<tool or system they use, e.g. Salesforce>"],
  "description": "<2-3 sentence company description>",
  "products": ["<product or service name>"],
  "competitors": [{{"name": "<competitor>", "url": "<url>", "description": "<one line>"}}],
  "recent_news": ["<recent headline or signal>"],
  "sources": ["<URL you consulted>"]
}}

Return ONLY valid JSON. No markdown fences. No commentary."""


def _fusion_research(
    name: str,
    website: str | None,
    extra: str | None,
    api_key: str,
) -> CompanyProfile:
    website_hint = f" (website: {website})" if website else ""
    extra_hint = f". Additional context: {extra}" if extra else ""
    prompt = _FUSION_PROMPT.format(name=name, website_hint=website_hint, extra_hint=extra_hint)

    try:
        resp = httpx.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": "openrouter/fusion",
                "messages": [{"role": "user", "content": prompt}],
                "plugins": [{
                    "id": "fusion",
                    "analysis_models": [
                        "google/gemini-flash-2.5",
                        "moonshotai/kimi-k2.6",
                        "deepseek/deepseek-v4-0324",
                    ],
                }],
                "response_format": {"type": "json_object"},
            },
            timeout=60,
        )
        resp.raise_for_status()
    except Exception as exc:
        raise ResearchError(f"Fusion research failed: {exc}") from exc

    raw = resp.json()["choices"][0]["message"]["content"]
    try:
        data = json.loads(raw)
    except Exception as exc:
        raise ResearchError(f"Failed to parse Fusion JSON response: {exc}") from exc

    return CompanyProfile(
        name=data.get("name") or name,
        website=data.get("website"),
        industry=data.get("industry"),
        size_hint=data.get("size_hint"),
        sub_focus=data.get("sub_focus"),
        connected_systems=data.get("connected_systems") or [],
        description=data.get("description") or "",
        products=data.get("products") or [],
        competitors=data.get("competitors") or [],
        recent_news=data.get("recent_news") or [],
        sources=data.get("sources") or [],
        mode="deep",
    )


def research_company(
    name: str,
    *,
    website: str | None = None,
    extra: str | None = None,
    mode: str = "quick",
) -> CompanyProfile:
    """Enrich a company profile.

    mode="quick"  — Exa REST search, ~1-3s, requires EXA_API_KEY
    mode="deep"   — OpenRouter Fusion (built-in panel web search + LLM synthesis), ~10-30s,
                    requires OPENROUTER_API_KEY
    """
    if mode == "quick":
        api_key = os.environ.get("EXA_API_KEY")
        if not api_key:
            raise ResearchError("EXA_API_KEY is not set — required for mode='quick'")
        return _exa_search(name, website, extra, api_key)
    elif mode == "deep":
        api_key = os.environ.get("OPENROUTER_API_KEY")
        if not api_key:
            raise ResearchError("OPENROUTER_API_KEY is not set — required for mode='deep'")
        return _fusion_research(name, website, extra, api_key)
    else:
        raise ResearchError(f"Unknown mode '{mode}': must be 'quick' or 'deep'")
