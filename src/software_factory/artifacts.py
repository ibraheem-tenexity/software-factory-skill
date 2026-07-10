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


_LOCK_IN_VERDICTS = ("SHIP_AS_IS", "SHIP_WITH_EDITS", "SEND_BACK")


def prd_lock_in_verdict(text: str) -> str | None:
    """SOF-73: the PRD's closing lock-in line (SHIP_AS_IS / SHIP_WITH_EDITS / SEND_BACK, per
    stage-1-research/SKILL.md's product-phase contract). None if no verdict token is present —
    a missing verdict is treated as hollow by the caller, same as a missing acceptance-criteria
    section is today."""
    for verdict in _LOCK_IN_VERDICTS:
        if re.search(rf"\b{verdict}\b", text or ""):
            return verdict
    return None


def parse_screen_ids(text: str) -> list[str]:
    """Stable screen IDs from the PRD's screen-catalog table (stage-1-research/SKILL.md requires
    one). Reads markdown table rows inside a '## ... screen catalog' section and takes each row's
    first cell as the ID. Best-effort: an unparseable/absent catalog yields an empty list rather
    than raising — the caller decides what an empty list means for its gate."""
    in_section = False
    ids: list[str] = []
    for line in (text or "").splitlines():
        stripped = line.strip()
        if re.match(r"^#{1,3}\s+(\d+\.\s+)?.*screen\s+catalog", stripped, re.I):
            in_section = True
            continue
        if in_section:
            if re.match(r"^#{1,2}\s+\S", stripped):
                break
            if stripped.startswith("|"):
                cell = stripped.strip("|").split("|", 1)[0].strip()
                if cell and not re.match(r"^-+$", cell) and cell.lower() not in ("id", "screen id"):
                    ids.append(cell)
    return ids


def design_spec_is_complete(text: str, screen_ids: list[str]) -> tuple[bool, list[str]]:
    """SOF-73: design-spec.md must actually cover the PRD's screen catalog, not just exist.
    Returns (ok, reasons). No screen_ids parsed from the PRD (catalog missing/unparseable) is
    surfaced as a reason for visibility but does NOT fail this check on its own —
    `artifacts.verify()` already requires design-spec.md to exist and be non-empty; this only adds
    the per-screen coverage bar on top, and there's nothing to enforce when there's no catalog."""
    if not screen_ids:
        return (True, ["no screen IDs found in the PRD's screen catalog to check coverage against"])
    missing = [sid for sid in screen_ids if sid not in (text or "")]
    if missing:
        return (False, [f"design-spec.md never references screen ID(s): {', '.join(missing)}"])
    return (True, [])


def _find_section(text: str, heading_re: str) -> str | None:
    """Body of the first h1-h3 heading whose text matches `heading_re`, up to the next heading of
    the same or shallower level. None if no such heading exists. Numbered headings ('## 5. Foo')
    match fine since `heading_re` is searched anywhere in the heading text, not anchored."""
    lines = (text or "").splitlines()
    start = level = None
    for i, line in enumerate(lines):
        m = re.match(r"^(#{1,3})\s+(.*)$", line.strip())
        if m and re.search(heading_re, m.group(2), re.I):
            start, level = i + 1, len(m.group(1))
            break
    if start is None:
        return None
    body = []
    for line in lines[start:]:
        m = re.match(r"^(#{1,3})\s+\S", line.strip())
        if m and len(m.group(1)) <= level:
            break
        body.append(line)
    return "\n".join(body)


def _subsections(body: str) -> list[str]:
    """Split a section's body into its nested-heading (h2-h4) subsection chunks. The whole body as
    one chunk if it has no nested headings of its own."""
    lines = body.splitlines()
    starts = [i for i, l in enumerate(lines) if re.match(r"^#{2,4}\s+\S", l.strip())]
    if not starts:
        return [body] if body.strip() else []
    ends = starts[1:] + [len(lines)]
    return ["\n".join(lines[s:e]) for s, e in zip(starts, ends)]


def prd_required_sections_complete(text: str, genres: list[str] | None = None) -> tuple[bool, list[str]]:
    """SOF-96: the PRD must carry real product depth, not just the SOF-73 structural skeleton —
    personas, per-feature user stories + acceptance criteria, explicit non-goals, a phased
    roadmap, and one module per scope genre the user selected. Mechanical presence-check only
    (headings + key phrases): depth/quality of what's written under each heading stays the
    synthesizing agent's judgment (Minimum Machinery) — this only catches a PRD that skipped a
    required section outright. Returns (ok, reasons-it-failed)."""
    reasons = []

    personas = _find_section(text, r"personas?")
    if personas is None or not personas.strip():
        reasons.append("no Personas section (or it's empty)")

    features = _find_section(text, r"feature\s*specs?|\bfeatures\b")
    if features is None or not features.strip():
        reasons.append("no Feature Specs section")
    else:
        subs = _subsections(features)
        if not subs:
            reasons.append("Feature Specs section has no per-feature subsections")
        bad = []
        for sub in subs:
            sub_low = sub.lower()
            has_story = "user stor" in sub_low or re.search(r"\bas an?\b.+\bi want\b", sub_low, re.S)
            has_ac = "acceptance criteria" in sub_low
            if not (has_story and has_ac):
                heading = next((ln.lstrip("#").strip() for ln in sub.splitlines() if ln.strip()), "(unnamed feature)")
                bad.append(heading)
        if bad:
            reasons.append(f"feature(s) missing a user story and/or acceptance criteria: {', '.join(bad)}")

    non_goals = _find_section(text, r"non[-\s]?goals?|out\s+of\s+scope")
    if non_goals is None or not non_goals.strip():
        reasons.append("no Non-Goals / Out of Scope section")

    roadmap = _find_section(text, r"roadmap")
    if roadmap is None or not roadmap.strip():
        reasons.append("no phased Roadmap section")
    else:
        rlow = roadmap.lower()
        missing_phases = [p for p, present in (
            ("v1", "v1" in rlow), ("v1.1", "v1.1" in rlow),
            ("later/v2/future", bool(re.search(r"\b(later|v2|future)\b", rlow))),
        ) if not present]
        if missing_phases:
            reasons.append(f"Roadmap missing phase(s): {', '.join(missing_phases)}")

    headings_norm = [
        _normalize(m.group(1))
        for m in re.finditer(r"^#{1,3}\s+(.*)$", text or "", re.M)
    ]
    for genre in (genres or []):
        name = (genre or "").strip()
        if not name:
            continue
        norm = _normalize(name)
        if norm and not any(norm in h for h in headings_norm):
            reasons.append(f"no module/section covering selected scope genre: {name}")

    return (len(reasons) == 0, reasons)


def _normalize(s: str) -> str:
    """Case/whitespace/punctuation-insensitive form for genre-heading matching — 'AP/AR' and
    'AP / AR' (or '## AP & AR') must compare equal."""
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()


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
