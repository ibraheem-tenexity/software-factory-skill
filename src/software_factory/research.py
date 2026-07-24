"""Company research — enrich a company profile via Exa (quick) or OpenRouter Fusion (deep)."""
from __future__ import annotations

import json
import os
import re
import httpx
from dataclasses import dataclass, asdict

from .log import get_logger

logger = get_logger(__name__)

# SOF-79: real measured end-to-end latency for a Fusion call is ~165-181s (two live runs);
# the original 60s timeout killed every successful call before it could complete.
# SOF-185: the ONLY limit on a fusion call is TIME — output is unbounded (no max_tokens, ever), so
# a genuinely deep research pass is never truncated mid-response. 30 minutes purely bounds a
# never-ending call. This single constant feeds every hop of the chain (in-stage _fusion_via_proxy
# client → console route → outbound httpx to OpenRouter), so 30 min holds end-to-end.
_FUSION_TIMEOUT_S = 1800


def _fusion_analysis_models() -> list[str]:
    """The OpenRouter Fusion panel's model list — SOF-81: DB-editable via the `fusion` row in the
    `tools` registry (OS Tools tab), not a code default. No code fallback on purpose: a missing/
    empty config is a real operator setup gap, not something to paper over with a guessed list."""
    from .tools import ToolStore
    config = ToolStore().config_for("fusion")
    models = (config or {}).get("analysis_models")
    if not models:
        raise ResearchError("'fusion' tool has no analysis_models configured — set it in the OS Tools tab")
    return list(models)


def _fusion_judge_model() -> str | None:
    """The Fusion judge/aggregator model — the OpenRouter fusion plugin's `model` field (SOF-185),
    from the same DB-editable `fusion` row (OS Tools tab). OPTIONAL, unlike analysis_models: unset
    ⇒ the plugin uses its own default judge, so this never raises — a judge is a refinement, not a
    hard prerequisite like the panel."""
    from .tools import ToolStore
    try:
        return (ToolStore().config_for("fusion") or {}).get("judge_model") or None
    except Exception:
        logger.exception("[research] fusion judge_model config read failed — using the plugin's default judge")
        return None


def _fusion_plugin() -> dict:
    """The `fusion` plugin object for the OpenRouter request: panel (`analysis_models`) plus the
    optional judge (`model`), both from the DB-editable `fusion` tool row (SOF-81/SOF-185)."""
    plugin = {"id": "fusion", "analysis_models": _fusion_analysis_models()}
    judge = _fusion_judge_model()
    if judge:
        plugin["model"] = judge
    return plugin


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

    # Per-field attribution (CBT-1): deep mode only, and only for fields the synthesis could
    # attribute to a specific consulted URL — never fabricated, never present in quick mode.
    field_sources: dict[str, str] | None = None

    def to_dict(self) -> dict:
        return asdict(self)


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
        logger.exception("[research] exa search transport failed")
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
  "sources": ["<URL you consulted>"],
  "field_sources": {{"<field name above>": "<the specific URL you actually used for that field>"}}
}}

For "field_sources": for each profile field you fill in, also note the specific URL you used —
but OMIT any field you cannot attribute to one specific consulted URL. Never invent a URL just to
fill this in.

Return ONLY valid JSON. No markdown fences. No commentary."""


# ---------------------------------------------------------------------------------------------
# SOF-79: Fusion (openrouter/fusion) does NOT return JSON even with response_format=json_object
# — verified live 2026-07-02. It returns MARKDOWN:
#   ## Panel responses
#   ### <model-id>                (one per analysis model)
#   <that model's raw reply — usually a bare JSON object, sometimes fenced ```json ... ```>
#   ## Analysis
#   **Consensus**
#   <bullet text>
#   **Contradictions**
#   <bullet text>
#   [optionally: **Partial coverage** / **Unique insights** / **Blind spots** — free text]
#   [optionally: a final synthesized/merged JSON object, outside any ### header — undocumented,
#    observed live, not guaranteed; when present it's a real reconciliation across panels and a
#    better source than picking one panel arbitrarily]
# These three helpers are shared by the company-profile path (_fusion_research) and the general
# question-answering path (fusion_research) below — neither invents data the response didn't
# provide; a panel that doesn't parse as JSON is skipped, not guessed at.
# ---------------------------------------------------------------------------------------------

def _balanced_json_span_end(text: str, start: int) -> int | None:
    """Index one past the '}' that closes the '{' at `start`, or None if it never closes.
    STRING-AWARE (tracks quoted-string state + backslash escapes) so a literal '{'/'}' inside a
    JSON string VALUE — e.g. a company description that happens to mention a brace — can never
    desync the depth count. A naive char-counting scanner would either close too early or never
    close at all in that case; this one only counts braces that are actually structural."""
    depth = 0
    in_string = False
    escaped = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return i + 1
    return None


def _extract_json_block(text: str) -> dict | None:
    """The first fenced-or-bare JSON object in `text`, or None if none parses. Never raises —
    Fusion's panels are LLM prose with an embedded object, not guaranteed-clean JSON."""
    fence = re.search(r"```(?:json)?\s*\n?(.*?)```", text, re.DOTALL)
    candidate = fence.group(1) if fence else text
    start = candidate.find("{")
    if start == -1:
        return None
    end = _balanced_json_span_end(candidate, start)
    if end is None:
        return None
    try:
        return json.loads(candidate[start:end])
    except json.JSONDecodeError:
        return None


def _split_fusion_markdown(raw: str) -> tuple[dict[str, str], str]:
    """Structural split only (no JSON parsing): {model_id: raw_panel_text} and the '## Analysis'
    section's raw text (empty string if the response has no Analysis section at all)."""
    panel_section = re.search(r"## Panel responses\s*\n(.*?)(?=\n## |\Z)", raw, re.DOTALL)
    analysis_section = re.search(r"## Analysis\s*\n?(.*)", raw, re.DOTALL)
    panels: dict[str, str] = {}
    if panel_section:
        chunks = re.split(r"^### (.+)$", panel_section.group(1), flags=re.MULTILINE)
        # re.split with a capturing group yields [pre, header1, body1, header2, body2, ...].
        for model, body in zip(chunks[1::2], chunks[2::2]):
            panels[model.strip()] = body.strip()
    analysis_text = analysis_section.group(1).strip() if analysis_section else ""
    return panels, analysis_text


def _extract_bold_section(text: str, heading: str) -> str:
    """Text under a `**Heading**` marker, up to the next `**Bold**` marker or end of `text`."""
    m = re.search(rf"\*\*{re.escape(heading)}\*\*\s*(.*?)(?=\n\*\*|\Z)", text, re.DOTALL)
    return m.group(1).strip() if m else ""


def _top_level_json_objects(text: str) -> list[dict]:
    """Every top-level (non-nested) balanced {...} span in `text`, parsed as JSON, in order.
    Depth-tracks (string-aware, via _balanced_json_span_end) so a nested object (e.g. one
    competitor entry inside a profile's `competitors` list) is never mistaken for its own
    top-level object — jumps past the whole outer span once its matching close is found,
    rather than re-scanning inside it. A malformed span is skipped, not fatal."""
    objs: list[dict] = []
    i, n = 0, len(text)
    while i < n:
        if text[i] != "{":
            i += 1
            continue
        end = _balanced_json_span_end(text, i)
        if end is None:
            i += 1
            continue
        try:
            objs.append(json.loads(text[i:end]))
        except json.JSONDecodeError:
            pass
        i = end
    return objs


def _synthesized_profile(analysis_text: str) -> dict | None:
    """A final merged/reconciled JSON object Fusion sometimes appends after the analysis prose
    (observed live 2026-07-02; not documented anywhere) — preferred over any single panel's raw
    guess when present, since it reconciles the panels rather than picking one arbitrarily. Must
    be the LAST TOP-LEVEL object, not just the text's last '{' — a naive rfind("{") finds the
    opening brace of the last NESTED object instead (e.g. one `competitors` entry near the end
    of the real profile), silently returning a 3-field competitor stub instead of the profile;
    caught by testing against the real captured response, not assumed correct from source
    reading alone."""
    objs = _top_level_json_objects(analysis_text)
    return objs[-1] if objs else None


def _fusion_post(payload: dict, api_key: str, timeout: float) -> tuple[str, float | None]:
    """POST to Fusion and return (raw_markdown_content, cost_usd). Shared transport for both
    the company-profile path and the general question path.

    SOF-185: NEVER set max_tokens on the payload — fusion output must stay unbounded so a deep
    research pass isn't clipped; the only limit is `timeout` (30 min, _FUSION_TIMEOUT_S).
    SOF-183: the observed prod failure was resp.json() raising on a 200-OK whose HTTP body was cut
    off mid-object (an INCOMPLETE body, not a max_tokens length cap — a real length cap returns
    valid JSON with finish_reason="length"; live probe confirmed fusion returns a single COMPLETE
    JSON body when it returns at all). Body truncation on these long (~8-11 min) calls is
    intermittent, so we retry ONCE on an unparseable body, then degrade: a broken tool must
    degrade the answer (ResearchError → the console route's clean 502 → the in-stage proxy
    re-wraps it), never crash the stage with an unhandled JSONDecodeError/KeyError (CLAUDE.md).
    A transport error / timeout is NOT retried — a 30-min timeout must not silently become 60.
    Every parsed response logs its finish_reason + size, so a future clipped answer self-diagnoses
    as cap (finish_reason="length") vs body cutoff (unparseable JSON) from the logs alone."""
    last_err: ResearchError | None = None
    for _attempt in range(2):  # 1 try + 1 retry, parse-failure only
        try:
            resp = httpx.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json=payload,
                timeout=timeout,
            )
            resp.raise_for_status()
        except Exception as exc:
            logger.exception("[research] fusion transport failed")
            raise ResearchError(f"Fusion research failed: {exc}") from exc
        try:
            body = resp.json()
            raw = body["choices"][0]["message"]["content"]
            finish = (body.get("choices") or [{}])[0].get("finish_reason")
            logger.info("[research] fusion response: finish_reason=%s content_chars=%s cost=%s",
                        finish, len(raw or ""), (body.get("usage") or {}).get("cost"))
            if finish == "length":
                logger.warning("[research] fusion response CLIPPED by a token cap "
                               "(finish_reason=length) — SOF-185 says this must never happen; "
                               "no max_tokens is set, so the cap is the provider's")
            return raw, (body.get("usage") or {}).get("cost")
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            last_err = ResearchError(
                f"Fusion returned an incomplete/unparseable response "
                f"({type(exc).__name__}: {exc}); last 200 chars: {(resp.text or '')[-200:]!r}")
    raise last_err


def _fusion_research(
    name: str,
    website: str | None,
    extra: str | None,
    api_key: str,
) -> CompanyProfile:
    website_hint = f" (website: {website})" if website else ""
    extra_hint = f". Additional context: {extra}" if extra else ""
    prompt = _FUSION_PROMPT.format(name=name, website_hint=website_hint, extra_hint=extra_hint)

    raw, _cost_usd = _fusion_post(
        {
            "model": "openrouter/fusion",
            "messages": [{"role": "user", "content": prompt}],
            "plugins": [_fusion_plugin()],
            "response_format": {"type": "json_object"},
        },
        api_key, _FUSION_TIMEOUT_S,
    )

    panels_raw, analysis_text = _split_fusion_markdown(raw)
    panel_json = {m: j for m, t in panels_raw.items() if (j := _extract_json_block(t))}
    # Fallback to treating the WHOLE response as one bare JSON object if the markdown structure
    # isn't there at all (no "## Panel responses"/"## Analysis" found) — defensive, not the
    # normal path (every live call this session returned the full markdown wrapper), in case a
    # future single-model-panel or config variant ever skips the wrapper.
    data = (_synthesized_profile(analysis_text) or next(iter(panel_json.values()), None)
           or _extract_json_block(raw))
    if data is None:
        raise ResearchError(
            f"Fusion response had no parseable panel or synthesized JSON "
            f"({len(panels_raw)} panel(s) found, 0 parsed)")

    field_sources = data.get("field_sources")
    if not isinstance(field_sources, dict):
        field_sources = None  # never fabricate a mapping the model didn't actually emit
    else:
        # SOF-210: each value is meant to be a single source-URL string. Drop any non-string value
        # so a future deep-mode UI can't render "[object Object]" (the model occasionally emits a
        # nested object/list). Empty after filtering → None, consistent with "don't fabricate".
        field_sources = {k: v for k, v in field_sources.items() if isinstance(v, str)} or None

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
        field_sources=field_sources,
    )


def _fusion_via_proxy(url: str, token: str | None, question: str, timeout: float) -> dict:
    """SOF-155: POST the research question to the console's /api/research/fusion proxy with the
    research-scoped bearer token. The console holds OPENROUTER_API_KEY and returns the same
    {panels, consensus, contradictions, cost_usd} dict fusion_research produces directly."""
    try:
        resp = httpx.post(url, json={"question": question},
                          headers={"Authorization": f"Bearer {token or ''}"}, timeout=timeout)
        resp.raise_for_status()
        return resp.json()
    except httpx.HTTPError as exc:
        logger.exception("[research] fusion proxy call failed")
        raise ResearchError(f"Fusion research proxy failed: {exc}") from exc


def fusion_research(question: str, *, api_key: str | None = None,
                    timeout: float = _FUSION_TIMEOUT_S) -> dict:
    """General-purpose Fusion research (SOF-79/SOF-73): ask any question, get the per-model
    panel replies plus the cross-model consensus/contradiction synthesis and real cost. For
    company-profile enrichment specifically, use research_company(mode='deep') instead — this
    is the lower-level primitive the Stage-1 research phase (SOF-73) consumes directly.

    Returns {"panels": {model_id: raw_text}, "consensus": str, "contradictions": str,
    "cost_usd": float | None}. Panel text is kept RAW (not JSON-parsed) — a general research
    question has no reason to produce structured JSON per panel the way the company-profile
    prompt does. Raises ResearchError only on a transport failure, never on the response's shape
    (an empty consensus/contradictions string just means Fusion's markdown didn't include one)."""
    # SOF-155: in-stage, the OpenRouter key is scrubbed from the build env (env.py isolation), so
    # reach Fusion through the console proxy instead — the console holds the key and makes the real
    # call. _launch_stage injects SF_RESEARCH_URL + SF_RESEARCH_TOKEN per run. Console-side callers
    # (the concierge's research_company path) pass api_key explicitly / have no SF_RESEARCH_URL, so
    # they take the direct path below, unchanged.
    proxy_url = os.environ.get("SF_RESEARCH_URL")
    if proxy_url and api_key is None:
        return _fusion_via_proxy(proxy_url, os.environ.get("SF_RESEARCH_TOKEN"), question, timeout)

    api_key = api_key or os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        raise ResearchError("OPENROUTER_API_KEY is not set — required for Fusion research")

    raw, cost_usd = _fusion_post(
        {
            "model": "openrouter/fusion",
            "messages": [{"role": "user", "content": question}],
            "plugins": [_fusion_plugin()],
        },
        api_key, timeout,
    )
    panels_raw, analysis_text = _split_fusion_markdown(raw)
    return {
        "panels": panels_raw,
        "consensus": _extract_bold_section(analysis_text, "Consensus"),
        "contradictions": _extract_bold_section(analysis_text, "Contradictions"),
        "cost_usd": cost_usd,
    }


def research_company(
    name: str,
    *,
    website: str | None = None,
    extra: str | None = None,
    mode: str = "quick",
) -> CompanyProfile:
    """Enrich a company profile.

    mode="quick"  — Exa REST search, ~1-3s, requires EXA_API_KEY
    mode="deep"   — OpenRouter Fusion (built-in panel web search + LLM synthesis). SOF-79:
                    real measured latency is ~165-180s (NOT ~10-30s as originally assumed) —
                    callers must tolerate a multi-minute call, not a quick one. Requires
                    OPENROUTER_API_KEY.
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
