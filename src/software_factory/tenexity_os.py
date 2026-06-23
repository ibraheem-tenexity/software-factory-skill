"""Tenexity OS admin portal (PRD §3) — cross-tenant aggregates + pure assemblers.

Three layers, kept apart for testability:
  • CONSTANTS — the curated agent ROSTER (the 12 callsigns) + the real TOOLS registry.
  • cross-run SQL — direct reads over the flat Postgres tables (`public.agents`, `public.tickets`)
    that no per-run accessor exposes (today's burn, per-role rollups, in-flight ticket counts).
  • pure assemblers — shape already-fetched data into the §3 section payloads (unit-testable, no DB).
"""
from __future__ import annotations

import os

from . import dbshim

# Rollup-matching aliases (by callsign) — the pipeline's functional role names (architect/designer/…)
# that map onto a roster callsign. Identity itself lives in the agent_registry table (registries.py).
_ROLE_ALIASES = {
    "ATLAS": ["atlas"], "HORIZON": ["pm", "product"], "CHROMA": ["designer", "design"],
    "SIREN": ["marketing"], "TENDER": ["proposal"], "FORGE": ["devops", "deploy"],
    "GARRISON": ["ops"], "MATRIX": ["data"], "LEDGER": ["edi"], "CONDUIT": ["erp"],
    "CARGO": ["wms", "warehouse"], "PROFIT": ["pricing"],
}


# ── stage skills (PRD §3.4, Part 1) ───────────────────────────────────────────────────────────────
# The 3 stage-orchestrator prompts ARE the on-disk SKILL.md files the live pipeline reads per stage
# (one per runtime: SKILL.md = claude, SKILL.opencode.md = opencode). We surface them as READ-ONLY
# agent cards (kind:'stage_skill', prompt_applied:true) so the Agents dashboard shows the REAL live
# orchestrator prompts — distinct from the editable-but-disconnected PromptStore. The skills/ dir ships
# to the container at /app/skills (Dockerfile `COPY . /app`); resolved here relative to this module.
# Edits→pipeline + managed subagent prompts are Part 2 (deferred).
_SKILLS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "skills")

STAGE_SKILLS = [
    {"callsign": "STAGE-1", "stage": 1, "slug": "stage-1-research",
     "name": "Stage 1 · Research", "model": "claude-opus-4-8"},
    {"callsign": "STAGE-2", "stage": 2, "slug": "stage-2-design",
     "name": "Stage 2 · Design", "model": "claude-opus-4-8"},
    {"callsign": "STAGE-3", "stage": 3, "slug": "stage-3-build",
     "name": "Stage 3 · Build", "model": "claude-sonnet-4-6"},
]
_STAGE_BY_CALLSIGN = {s["callsign"]: s for s in STAGE_SKILLS}


def _skill_filename(runtime: str) -> str:
    return "SKILL.opencode.md" if runtime == "opencode" else "SKILL.md"


def _skill_variants(slug: str) -> dict:
    return {"claude": f"skills/{slug}/SKILL.md", "opencode": f"skills/{slug}/SKILL.opencode.md"}


def _frontmatter_description(text: str) -> str | None:
    """Pull `description:` from the SKILL.md YAML frontmatter (name/description block), else None."""
    if not text.startswith("---"):
        return None
    end = text.find("\n---", 3)
    if end == -1:
        return None
    for line in text[3:end].splitlines():
        if line.strip().lower().startswith("description:"):
            return line.split(":", 1)[1].strip()
    return None


def _read_skill(slug: str, runtime: str) -> tuple[str, str | None]:
    """(markdown_body, frontmatter_description). GRACEFUL: a missing file degrades to a clear
    placeholder body + None description rather than raising — the dashboard shows "not found",
    never a 500 (e.g. if the container ever ships without skills/)."""
    path = os.path.join(_SKILLS_DIR, slug, _skill_filename(runtime))
    try:
        with open(path, encoding="utf-8") as f:
            text = f.read()
    except OSError:
        return (f"(skill file not found: skills/{slug}/{_skill_filename(runtime)})", None)
    return (text, _frontmatter_description(text))


def stage_skill_cards() -> list:
    """The 3 stage-orchestrator cards for the Agents list — file-backed, kind:'stage_skill'."""
    cards = []
    for s in STAGE_SKILLS:
        _, desc = _read_skill(s["slug"], "claude")
        cards.append({
            "callsign": s["callsign"], "sign": s["callsign"], "name": s["name"],
            "role": "stage-orchestrator", "kind": "stage_skill", "stage": s["stage"],
            "desc": desc, "model": s["model"], "cost_tier": 3,
            "success": None, "runs": 0, "on": False, "runtimes": ["claude", "opencode"],
        })
    return cards


def stage_skill_detail(callsign: str, runtime: str = "claude") -> dict | None:
    """Full card + the REAL SKILL.md markdown for one stage orchestrator; None if not a stage skill."""
    s = _STAGE_BY_CALLSIGN.get((callsign or "").upper())
    if not s:
        return None
    runtime = "opencode" if runtime == "opencode" else "claude"
    body, desc = _read_skill(s["slug"], runtime)
    card = next(c for c in stage_skill_cards() if c["callsign"] == s["callsign"])
    return {
        **card, "desc": desc if desc is not None else card["desc"],
        "prompt": body, "prompt_source": "skill_file", "prompt_applied": True, "editable": True,
        "skill": s["slug"], "skill_path": f"skills/{s['slug']}/{_skill_filename(runtime)}",
        "runtime": runtime, "variants": _skill_variants(s["slug"]),
    }


# ── concierge (§3.4): a 4th live card, CODE-backed (not a SKILL.md) ───────────────────────────────
# The Factory Concierge's live instructions ARE the CONCIERGE_INSTRUCTIONS module constant used as the
# Agent's prompt (chat_agent.py). Surfaced read-only like the stage skills (prompt_applied:true) but
# kind:'concierge' + prompt_source:'code'. Lazy-imported so the OS module never pulls the agents/openai
# SDK unless this card is requested, and degrades gracefully if it can't load.
CONCIERGE_CALLSIGN = "CONCIERGE"


def _concierge() -> tuple[str, str]:
    """(live instructions, model label). Graceful: a placeholder + default model if chat_agent can't
    import (keeps the dashboard from 500ing)."""
    try:
        from .chat_agent import CONCIERGE_INSTRUCTIONS, chat_model_label
        return CONCIERGE_INSTRUCTIONS, chat_model_label()
    except Exception:
        return "(concierge instructions unavailable)", "gpt-5.4"


def concierge_card() -> dict:
    _, model = _concierge()
    return {
        "callsign": CONCIERGE_CALLSIGN, "sign": CONCIERGE_CALLSIGN, "name": "Factory Concierge",
        "role": "concierge", "kind": "concierge", "stage": 0,
        "desc": "Onboarding concierge — gathers requirements and drives the pipeline.",
        "model": model, "cost_tier": 2, "success": None, "runs": 0, "on": False, "runtimes": [],
    }


def concierge_detail(callsign: str) -> dict | None:
    if (callsign or "").upper() != CONCIERGE_CALLSIGN:
        return None
    prompt, model = _concierge()
    return {
        **concierge_card(), "model": model, "prompt": prompt, "prompt_source": "code",
        "prompt_applied": True, "editable": True,
        "source_ref": "src/software_factory/chat_agent.py:CONCIERGE_INSTRUCTIONS",
    }


def live_agent_cards() -> list:
    """The non-store, real-prompt cards: 3 stage skills (file-backed) + the concierge (code-backed)."""
    return stage_skill_cards() + [concierge_card()]


def live_agent_detail(callsign: str, runtime: str = "claude") -> dict | None:
    """Detail for a stage skill or the concierge; None if `callsign` is neither."""
    return stage_skill_detail(callsign, runtime) or concierge_detail(callsign)


def is_editable_orchestrator(callsign: str) -> bool:
    """True for the 4 MAIN cards whose web edits DRIVE runs (3 stage skills + concierge). The 12 role
    cards are NOT here — their prompt edits stay stored-not-applied (subagent prompts = later part-2b)."""
    cs = (callsign or "").upper()
    return cs in _STAGE_BY_CALLSIGN or cs == CONCIERGE_CALLSIGN


# ── cross-run SQL (flat Postgres tables; no per-run accessor exposes these) ───────────────────────
def _query(sql: str, params: tuple = ()) -> list:
    conn = dbshim._pg_connect(os.environ["DATABASE_URL"])
    try:
        with conn.transaction():
            cur = conn.cursor()
            cur.execute(sql, params)
            return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


def agent_rollups() -> list[dict]:
    """Per-role aggregates across ALL runs: distinct runs, total spend, success rate, active count."""
    return _query(
        "SELECT role, count(DISTINCT project_id) AS runs, coalesce(sum(cost_usd),0) AS cost_usd, "
        "count(*) AS total, count(*) FILTER (WHERE status='running') AS active, "
        "count(*) FILTER (WHERE outcome IN ('real_diff','success')) AS successes, "
        "max(model) AS model FROM public.agents GROUP BY role")


def agents_active_count() -> int:
    rows = _query("SELECT count(*) AS n FROM public.agents WHERE status='running'")
    return int(rows[0]["n"]) if rows else 0


def today_burn(since_epoch: float) -> float:
    rows = _query("SELECT coalesce(sum(cost_usd),0) AS burn FROM public.agents "
                  "WHERE started_at >= %s", (since_epoch,))
    return float(rows[0]["burn"]) if rows else 0.0


def open_tickets_by_project() -> dict:
    rows = _query("SELECT project_id, count(*) AS n FROM public.tickets "
                  "WHERE status IN ('open','in_progress') GROUP BY project_id")
    return {r["project_id"]: int(r["n"]) for r in rows}


def ticket_counts_by_project() -> dict:
    """{project_id: {"done": d, "total": t}} across all projects (delivered = done/deployed/approved)."""
    rows = _query(
        "SELECT project_id, count(*) AS total, "
        "count(*) FILTER (WHERE status IN ('done','deployed','approved')) AS done "
        "FROM public.tickets GROUP BY project_id")
    return {r["project_id"]: {"done": int(r["done"]), "total": int(r["total"])} for r in rows}


# ── pure assemblers (no DB; take already-fetched data) ───────────────────────────────────────────
def _success_rate(r: dict) -> int | None:
    total = r.get("total") or 0
    return round((r.get("successes") or 0) / total * 100) if total else None


def _initials(name: str) -> str:
    parts = [p for p in (name or "").split() if p]
    return ((parts[0][0] + (parts[1][0] if len(parts) > 1 else parts[0][1:2])).upper()
            if parts else "??")


def owner_to_org(orgs: list, members_by_org: dict) -> dict:
    """{email: org_name} from orgs + their member lists."""
    out = {}
    for o in orgs:
        for m in members_by_org.get(o["id"], []):
            out[(m["email"] or "").lower()] = o["name"]
    return out


def agent_roster(registry: list, rollups: list, prompts: dict) -> list:
    """Merge the agent_registry identity rows with live per-role rollups + stored prompt versions;
    append any live role not in the registry as its own card (honest: a live agent not yet named)."""
    by_role = {(r.get("role") or "").lower(): r for r in rollups}
    used = set()
    out = []

    def card(name, callsign, role, model, cost_tier, desc, roll):
        pv = prompts.get(callsign)
        return {"name": name, "callsign": callsign, "sign": callsign, "role": role,
                "desc": desc, "model": (roll.get("model") if roll else None) or model,
                "cost_tier": cost_tier, "success": _success_rate(roll) if roll else None,
                "runs": int(roll.get("runs") or 0) if roll else 0,
                "on": bool(roll.get("active")) if roll else False,
                "prompt_version": pv["version"] if pv else 0}

    for e in registry:
        cs = e["callsign"]
        roll = None
        for key in [(e.get("role") or "").lower(), *(_ROLE_ALIASES.get(cs, []))]:
            if key in by_role and key not in used:
                roll, _ = by_role[key], used.add(key)
                break
        out.append(card(e["name"], cs, e.get("role"), e.get("model"), e.get("cost_tier"),
                        e.get("descr"), roll))
    # live roles not claimed by any roster entry → their own cards
    for role, roll in by_role.items():
        if role and role not in used:
            out.append(card(role.title(), role.upper(), role, None, None,
                            "Live pipeline agent (not in the curated roster).", roll))
    return out


def overview(orgs, runs, rollups, agents_active, burn, roster, o2o):
    """§3.1 platform pulse + most-active projects + agent snapshot."""
    recent = sorted(runs, key=lambda r: r.get("updated") or 0, reverse=True)[:6]
    return {
        "pulse": {
            "tenants": len(orgs),
            "projects": len(runs),
            # Runs genuinely executing now: not finished (phase ∉ done/stopped), not budget-frozen,
            # not gated-pre-launch (held). A frozen/gated run isn't "running" — counting it would
            # inflate the operator's pulse. Computed over the runs already in hand (no extra query).
            "projects_active": sum(1 for r in runs
                                   if r.get("phase") not in ("done", "stopped")
                                   and not r.get("budget_stopped") and not r.get("held")),
            "agents_active": agents_active,
            "agents_total": sum(int(r.get("total") or 0) for r in rollups),
            "today_burn": round(burn, 2),
            "avg_friction": None,   # not tracked — FE renders "—", never a fake number
        },
        "active_projects": [
            {"project_id": r["project_id"], "name": r.get("name") or r["project_id"],
             "client": o2o.get((r.get("owner") or "").lower()), "phase": r.get("phase"),
             "spent_usd": round(r.get("spent_usd") or 0.0, 2), "updated": r.get("updated")}
            for r in recent
        ],
        "agents": [{"callsign": a["callsign"], "sign": a["sign"], "role": a["role"],
                    "success": a["success"], "on": a["on"]} for a in roster[:6]],
    }


def client_rows(orgs, runs, members_by_org, open_tickets):
    """§3.2 tenant table: per-org active projects, in-flight tickets, total spend, last activity."""
    rows = []
    for o in orgs:
        emails = {(m["email"] or "").lower() for m in members_by_org.get(o["id"], [])}
        org_runs = [r for r in runs if (r.get("owner") or "").lower() in emails]
        tickets = sum(open_tickets.get(r["project_id"], 0) for r in org_runs)
        spend = sum(r.get("spent_usd") or 0.0 for r in org_runs)
        last = max((r.get("updated") or 0 for r in org_runs), default=None)
        rows.append({"org_id": o["id"], "name": o["name"], "initials": _initials(o["name"]),
                     "projects": len(org_runs), "tickets": tickets, "spend": round(spend, 2),
                     "last_activity": last or None})
    return rows


def project_rows(runs, o2o, ticket_counts, mode="all"):
    """§3.3 all-projects (cross-tenant), optionally filtered by REAL/DEMO."""
    out = []
    for r in runs:
        demo = bool(r.get("is_demo"))
        if mode == "real" and demo:
            continue
        if mode == "demo" and not demo:
            continue
        tc = ticket_counts.get(r["project_id"], {})
        out.append({
            "project_id": r["project_id"], "name": r.get("name") or r["project_id"],
            "client": o2o.get((r.get("owner") or "").lower()), "factory": r.get("runtime") or "—",
            "phase": r.get("phase"), "stage": r.get("stage"),
            "tasks_done": tc.get("done", 0), "tasks_total": tc.get("total", 0),
            "spent_usd": round(r.get("spent_usd") or 0.0, 2), "updated": r.get("updated"),
            "is_demo": demo, "owner": r.get("owner") or "",
        })
    return out
