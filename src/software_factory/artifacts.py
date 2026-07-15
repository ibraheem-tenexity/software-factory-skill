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


def parse_v1_screen_ids(text: str) -> list[str]:
    """SOF-99: the PRD screen catalog's V1-only screen IDs (excludes Future). Column ORDER varies
    between PRDs (the V1?/ID columns aren't always in the same position), so this reads the
    header row to find both columns by name rather than assuming a fixed layout. Falls back to
    column 0 for ID and the last column for V1? if a header can't be matched — best-effort,
    same spirit as parse_screen_ids. A row counts as V1 when its V1? cell starts with "yes"
    (case-insensitive) — "Future"/"No"/blank do not."""
    in_section = False
    header_seen = False
    id_idx = 0
    v1_idx = -1
    ids: list[str] = []
    for line in (text or "").splitlines():
        stripped = line.strip()
        if re.match(r"^#{1,3}\s+(\d+\.\s+)?.*screen\s+catalog", stripped, re.I):
            in_section, header_seen, id_idx, v1_idx = True, False, 0, -1
            continue
        if not in_section:
            continue
        if re.match(r"^#{1,2}\s+\S", stripped):
            break
        if not stripped.startswith("|"):
            continue
        cells = [c.strip() for c in stripped.strip("|").split("|")]
        if re.match(r"^-+$", cells[0]):
            continue   # markdown table separator row
        if not header_seen:
            header_seen = True
            lowered = [c.lower() for c in cells]
            for i, c in enumerate(lowered):
                if c in ("id", "screen id"):
                    id_idx = i
            for i, c in enumerate(lowered):
                if "v1" in c:
                    v1_idx = i
            continue
        if id_idx >= len(cells):
            continue
        screen_id = cells[id_idx]
        if not screen_id:
            continue
        v1_cell = cells[v1_idx] if 0 <= v1_idx < len(cells) else cells[-1]
        if v1_cell.strip().lower().startswith("yes"):
            ids.append(screen_id)
    return ids


def mockups_cover_v1_screens(base_dir: str, screen_ids: list[str]) -> tuple[bool, list[str]]:
    """SOF-99: every V1 screen must have a real, non-husk mockup file at
    `mockups/<SCREEN_ID>.html` under base_dir — a FILE-existence check, not the text-substring
    coverage `design_spec_is_complete` does for design-spec.md's prose. "Non-husk" is still a
    mechanical fact, not a quality judgment: non-empty AND contains an `<html`/`<style` token, so
    a 0-byte or placeholder file doesn't pass. No screen_ids (PRD catalog missing/unparseable) is
    surfaced as a reason but does not fail this check on its own — nothing to enforce against."""
    if not screen_ids:
        return (True, ["no V1 screen IDs found in the PRD's screen catalog to check mockup coverage against"])
    reasons = []
    for sid in screen_ids:
        path = os.path.join(base_dir, "mockups", f"{sid}.html")
        if not os.path.isfile(path) or os.path.getsize(path) == 0:
            reasons.append(f"missing or empty mockup for screen {sid} (expected mockups/{sid}.html)")
            continue
        with open(path, "r", errors="replace") as f:
            content = f.read()
        low = content.lower()
        if "<html" not in low and "<style" not in low:
            reasons.append(f"mockups/{sid}.html doesn't look like real HTML (no <html or <style tag)")
    return (len(reasons) == 0, reasons)


def flow_map_is_complete(text: str, screen_ids: list[str]) -> tuple[bool, list[str]]:
    """SOF-99: flow-map.md must exist (verify() already checks that) AND actually reference every
    V1 screen ID — same text-substring coverage style as design_spec_is_complete, applied to the
    design stage's own screen-flow artifact instead of the PRD's prose nav map."""
    if not screen_ids:
        return (True, ["no V1 screen IDs found in the PRD's screen catalog to check flow-map coverage against"])
    missing = [sid for sid in screen_ids if sid not in (text or "")]
    if missing:
        return (False, [f"flow-map.md never references screen ID(s): {', '.join(missing)}"])
    return (True, [])


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


_DECISION_LOG_SENTINEL_RE = re.compile(
    r"\b(nothing to declare|none declared|no (assumptions|shortcuts|known gaps)[^.\n]{0,40}to declare)\b",
    re.I)
_DECISION_LOG_TYPE_RE = re.compile(r"^(assumption|shortcut|known[-\s]?gap)\b", re.I)


def decision_log_is_complete(text: str) -> tuple[bool, list[str]]:
    """SOF-118: decision-log.md must actually disclose real content, not just exist as a blank
    file — `verify()` already checks existence/non-emptiness; this checks the CONTENT is a real
    disclosure. Passes if EITHER (a) the file has ≥1 real `## <Type>: ...` entry (type is
    assumption/shortcut/known-gap, case-insensitive), each carrying a `Reason` and an
    `Affected surface`, OR (b) an explicit "nothing to declare" sentinel — a stage that genuinely
    made no notable shortcuts is allowed to say so, but silence/a placeholder heading is not the
    same as an honest, stated 'none'. Mechanical presence-check only: whether the disclosed reason
    is a GOOD reason is the writing agent's judgment, never the gate's."""
    if _DECISION_LOG_SENTINEL_RE.search(text or ""):
        return (True, [])
    lines = (text or "").splitlines()
    starts = [i for i, ln in enumerate(lines) if re.match(r"^#{1,3}\s+\S", ln.strip())]
    if not starts:
        return (False, ["no '## <Type>: ...' entries found, and no explicit "
                        "'nothing to declare' statement"])
    ends = starts[1:] + [len(lines)]
    reasons = []
    found_entry = False
    for s, e in zip(starts, ends):
        heading = re.sub(r"^#{1,3}\s+", "", lines[s].strip())
        if not _DECISION_LOG_TYPE_RE.match(heading):
            continue   # not a decision-log entry heading (e.g. a doc title) — ignore, not a failure
        found_entry = True
        body_low = "\n".join(lines[s + 1:e]).lower()
        missing = [label for label, needle in (("Reason", "reason"), ("Affected surface", "affected surface"))
                  if needle not in body_low]
        if missing:
            reasons.append(f"entry {heading!r} missing: {', '.join(missing)}")
    if not found_entry:
        reasons.append("no entry heading starts with Assumption/Shortcut/Known Gap, and no "
                       "explicit 'nothing to declare' statement")
    return (len(reasons) == 0, reasons)


def parse_feature_names(text: str) -> list[str]:
    """SOF-101: the PRD's '## Feature Specs' subsection names (SOF-96 requires one '### <Feature
    Name>' subsection per feature). Same parsing the section-presence check in
    `prd_required_sections_complete` already uses (`_find_section` + `_subsections`); this just
    returns the heading names instead of validating their content. Best-effort: an unparseable/
    absent Feature Specs section yields an empty list rather than raising."""
    features = _find_section(text, r"feature\s*specs?|\bfeatures\b")
    if not features:
        return []
    names = []
    for sub in _subsections(features):
        heading = next((ln.lstrip("#").strip() for ln in sub.splitlines() if ln.strip()), None)
        if heading:
            names.append(heading)
    return names


def decision_log_covers_features(text: str, feature_names: list[str]) -> tuple[bool, list[str]]:
    """SOF-101 (B4): Stage 3's build-decision-log.md must explicitly account for every PRD feature
    — built, or honestly deferred as a Known Gap — not silently drop features the PRD named. This
    is the same text-substring coverage style `flow_map_is_complete`/`design_spec_is_complete` use
    for screen IDs, applied to feature names: it only checks the name is MENTIONED somewhere (built
    how, or why deferred, is the build agent's judgment and disclosure, never the gate's). No
    feature_names (PRD Feature Specs section missing/unparseable) is not a failure — nothing to
    enforce against."""
    if not feature_names:
        return (True, ["no Feature Specs found in the PRD to check build coverage against"])
    body = _normalize(text or "")
    missing = [name for name in feature_names if _normalize(name) not in body]
    if missing:
        return (False, [f"build-decision-log.md never accounts for PRD feature(s) (not built, "
                        f"and no Known Gap entry naming them): {', '.join(missing)}"])
    return (True, [])


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
