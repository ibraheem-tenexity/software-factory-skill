"""Pipeline-1 completeness gate — the mechanical teeth behind "the orchestrator must not consider
part 1 done before a validated PRD + architecture."

No human approval (the run stays fully autonomous). These are code checks the orchestrator cannot
fake past — the same spirit as `repo.merge_if_green` for tickets, applied to the product-definition
artifacts (PRD + architecture). `console.graph` uses the same existence notion to paint missing
artifacts red.
"""
from __future__ import annotations

import os
import re


def verify(project_dir: str, paths: list[str]) -> tuple[bool, list[str]]:
    """True only if every path exists under project_dir AND is non-empty. Returns the missing/empty ones."""
    missing = []
    for p in paths:
        full = os.path.join(project_dir, p)
        if not os.path.isfile(full) or os.path.getsize(full) == 0:
            missing.append(p)
    return (len(missing) == 0, missing)


def prd_is_complete(text: str) -> tuple[bool, list[str]]:
    """The PRD must actually drive the build: cite real research, and carry acceptance criteria +
    ticket seeds (HORIZON's contract). Returns (ok, reasons-it-failed)."""
    reasons = []
    urls = re.findall(r"https?://[^\s)>\]]+", text or "")
    if len(set(urls)) < 3:
        reasons.append("fewer than 3 real product/source URLs (research not grounded)")
    low = (text or "").lower()
    has_acceptance = ("acceptance criteria" in low) or re.search(r"given\b.*\bwhen\b.*\bthen\b", low, re.S)
    if not has_acceptance:
        reasons.append("no acceptance criteria (given/when/then) section")
    if "ticket seed" not in low:   # the phrase, not just the word "ticket" (e.g. "no tickets")
        reasons.append("no ticket seeds")
    return (len(reasons) == 0, reasons)


def parse_required_tokens(text: str) -> list[dict]:
    """Extract required tokens/keys/URLs from architecture.md's dependency section.

    Looks for a '## Required Tokens' or '## Dependencies' section and pulls out
    env-var-shaped names (UPPER_SNAKE_CASE ending in _TOKEN, _KEY, _URL, _SECRET,
    _ID, or _PASSWORD). Returns [{"name": "RAILWAY_TOKEN", "provider": "Railway"}, ...].
    """
    section = ""
    in_section = False
    for line in (text or "").splitlines():
        stripped = line.strip()
        if re.match(r"^#{1,3}\s+(\d+\.\s+)?(required\s+tokens|dependencies)", stripped, re.I):
            in_section = True
            continue
        if in_section:
            # End the section only at the next h1/h2 — h3+ subheadings (e.g.
            # '### Operator must supply') are subsections that BELONG to it.
            if re.match(r"^#{1,2}\s+\S", stripped):
                break
            section += line + "\n"
    names = re.findall(r"\b([A-Z][A-Z0-9_]*(?:_TOKEN|_KEY|_URL|_SECRET|_ID|_PASSWORD))\b", section)
    seen = set()
    result = []
    for name in names:
        if name in seen:
            continue
        seen.add(name)
        provider = name.split("_")[0].capitalize()
        result.append({"name": name, "provider": provider})
    return result
