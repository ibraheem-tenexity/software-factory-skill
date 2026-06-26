"""Company research — enrich a company profile via Exa (quick) or OpenRouter Fusion (deep)."""
from __future__ import annotations

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
