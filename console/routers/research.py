"""In-stage Fusion research proxy (SOF-155).

The stage subprocess is scrubbed of factory secrets (env.py isolation) so a customer's built app
can never inherit `OPENROUTER_API_KEY`. But Stage-1 research legitimately needs Fusion (the
multi-model research council). Rather than re-inject the key into the build env, the key stays in
the CONSOLE and the stage reaches Fusion only through this endpoint, authed by a per-run,
research-scoped token — exactly mirroring the memory-MCP proxy (SOF-41, /mcp/memory).

`_launch_stage` injects `SF_RESEARCH_TOKEN = auth.sign_scope_token(pid, purpose="research")` +
`SF_RESEARCH_URL`; `research.fusion_research()` POSTs here when `SF_RESEARCH_URL` is set.
"""
import os
import re

from fastapi import APIRouter, Depends, HTTPException, Request

from software_factory import auth
from software_factory.research import research_company, fusion_research, ResearchError

from console.deps import require_authed
from console.schemas import CompanyEnrichIn

router = APIRouter()


def _domain_stem(website: str) -> str:
    """The bare domain name (no scheme/path/TLD) as a fallback company name — e.g.
    'https://acme-industrial.com/about' -> 'acme-industrial'."""
    host = re.sub(r"^https?://", "", website).split("/")[0]
    return host.split(".")[0]


@router.post("/api/research/fusion")
def research_fusion(body: dict, request: Request):
    """Run one Fusion research question server-side (the console holds OPENROUTER_API_KEY) and
    return {panels, consensus, contradictions, cost_usd}.

    Authed ONLY by a research-scoped bearer token (NOT a session/service token): `purpose="research"`
    means a memory token or a session cookie can't reach this endpoint, and this token can't reach
    /mcp/memory — least privilege, per-run, revocable via secret rotation.

    Synchronous ~3 min hold: Fusion is a real multi-model panel (~165-180s measured). We
    deliberately do NOT add a job queue — fusion runs only a handful of times per Stage-1, so one
    occupied worker for the duration is an acceptable tradeoff against that machinery (SOF-155).
    """
    raw = request.headers.get("authorization", "")
    token = raw[7:] if raw.lower().startswith("bearer ") else None
    if not token or not auth.verify_scope_token(token, purpose="research"):
        raise HTTPException(status_code=401, detail="unauthorized")
    question = (body or {}).get("question")
    if not question or not str(question).strip():
        raise HTTPException(status_code=400, detail="question is required")
    if not os.environ.get("OPENROUTER_API_KEY"):
        raise HTTPException(status_code=503, detail="OPENROUTER_API_KEY not configured on the console")
    try:
        # Pass the key explicitly so fusion_research takes its direct transport (never re-proxies).
        return fusion_research(str(question), api_key=os.environ["OPENROUTER_API_KEY"])
    except ResearchError as exc:
        raise HTTPException(status_code=502, detail=str(exc))


@router.post("/api/research/company")
def research_company_route(body: CompanyEnrichIn, depth: str = "quick",
                            v: tuple = Depends(require_authed)):
    """Company-enrich wow prefill (CBT-1): look up a company from a name/website/email domain.
    Read-only — no DB writes; accepting the result is a separate, explicit action (PATCH /api/org).

    `depth=quick` (default, Exa — the UI's only caller) or `depth=deep` (OpenRouter Fusion,
    ~165-180s, SOF-79 — concierge-only). ResearchError surfaces as the provider's own honest
    reason, never a guess (CLAUDE.md Principle 4)."""
    website = body.website or body.email_domain
    name = (body.name or "").strip() or (_domain_stem(website) if website else "")
    if not name and not website:
        raise HTTPException(status_code=422, detail="one of name, website, or email_domain is required")
    mode = depth if depth in ("quick", "deep") else "quick"
    try:
        profile = research_company(name or website, website=website, mode=mode)
    except ResearchError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    return profile.to_dict()
