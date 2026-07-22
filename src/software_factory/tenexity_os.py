"""Tenexity OS admin portal (PRD §3) — cross-tenant aggregates + pure assemblers.

Three layers, kept apart for testability:
  • CONSTANTS — the stage-skill roster (STAGE-1/2/3 + CONCIERGE) + the real TOOLS registry.
  • cross-run SQL — direct reads over the flat Postgres tables (`public.runtime_agents`, `public.tickets`)
    that no per-run accessor exposes (today's burn, per-role rollups, in-flight ticket counts).
  • pure assemblers — shape already-fetched data into the §3 section payloads (unit-testable, no DB).
"""
from __future__ import annotations

import logging
import os

from .repositories._exec import GlobalExec
from .repositories.aggregates import AggregatesRepository

logger = logging.getLogger(__name__)

_aggregates = AggregatesRepository(GlobalExec())


# ── stage skills (PRD §3.4, Part 1) ───────────────────────────────────────────────────────────────
# The 3 stage-orchestrator prompts ARE the on-disk SKILL.md files the live pipeline reads per stage
# (one per runtime: SKILL.md = claude, SKILL.opencode.md = opencode). We surface them as READ-ONLY
# agent cards (kind:'stage_skill', prompt_applied:true) so the Agents dashboard shows the REAL live
# orchestrator prompts — distinct from the editable SystemAgentStore rows. The skills/ dir ships
# to the container at /app/skills (Dockerfile `COPY . /app`); resolved here relative to this module.
# Edits→pipeline + managed subagent prompts are Part 2 (deferred).
_SKILLS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "skills")

STAGE_SKILLS = [
    {"callsign": "STAGE-1", "stage": 1, "slug": "stage-1-research", "name": "Stage 1 · Research"},
    {"callsign": "STAGE-2", "stage": 2, "slug": "stage-2-design", "name": "Stage 2 · Design"},
    {"callsign": "STAGE-3", "stage": 3, "slug": "stage-3-build", "name": "Stage 3 · Build"},
]
_STAGE_BY_CALLSIGN = {s["callsign"]: s for s in STAGE_SKILLS}


def _stage_model(stage: int) -> str:
    """The model a stage ACTUALLY runs on, from live config (SF_MODEL override else console._STAGE_MODEL
    default) — data provenance, not a hardcoded literal. Lazy import avoids a tenexity_os↔console cycle;
    empty string if no real source."""
    try:
        from .constants import STAGE_MODEL
        return os.environ.get("SF_MODEL") or STAGE_MODEL.get(stage, "") or ""
    except Exception:
        return ""


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
            "desc": desc, "model": _stage_model(s["stage"]), "cost_tier": 3,
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


# ── concierge (§3.4): a 4th live card, DB-backed (not a SKILL.md) ─────────────────────────────────
# The Factory Concierge's live instructions ARE the DB `system_agents` CONCIERGE.prompt (the SOLE
# source — there is no code default). Surfaced read-only like the stage skills but kind:'concierge'
# + prompt_source:'db' (or 'unset' when no row/blank prompt exists — an honest unconfigured state,
# never a code constant). Lazy-imported so the OS module never pulls the DB/model layer unless this
# card is requested, and degrades gracefully (empty prompt) rather than 500ing if it can't load.
CONCIERGE_CALLSIGN = "CONCIERGE"


def _concierge() -> tuple[str, str]:
    """(live prompt, model label) sourced from the DB `system_agents` CONCIERGE row. Empty prompt +
    the default model label when no row/blank prompt exists — an honest unconfigured state, never a
    code default. Graceful: logs and returns the unconfigured state rather than raising out of the
    OS card render."""
    prompt, model = "", "gpt-5.4"
    try:
        from .system_agents import SystemAgentStore
        from .chat_agent import chat_model_label
        model = chat_model_label()
        row = SystemAgentStore().get(CONCIERGE_CALLSIGN)
        if row and (row.get("prompt") or "").strip():
            prompt = row["prompt"]
    except Exception:
        logger.exception("[tenexity_os] failed to load CONCIERGE prompt/model from system_agents")
    return prompt, model


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
    configured = bool(prompt.strip())
    return {
        **concierge_card(), "model": model, "prompt": prompt,
        "prompt_source": "db" if configured else "unset",
        "prompt_applied": configured, "editable": True,
        "source_ref": "system_agents.CONCIERGE.prompt",
    }


def live_agent_cards() -> list:
    """The real-prompt cards: 3 stage skills (file-backed) + the concierge (DB-backed)."""
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
def agent_rollups() -> list[dict]:
    """Per-role aggregates across ALL runs: distinct runs, total spend, success rate, active count."""
    return [dict(r) for r in _aggregates.agent_rollups()]


def agents_active_count() -> int:
    return _aggregates.agents_active_count()


def today_burn(since_epoch: float) -> float:
    return _aggregates.today_burn(since_epoch)


def open_tickets_by_project() -> dict:
    return {r["project_id"]: int(r["n"]) for r in _aggregates.open_tickets_by_project()}


def ticket_counts_by_project() -> dict:
    """{project_id: {"done": d, "total": t}} across all projects (delivered = done/deployed/approved)."""
    rows = _aggregates.ticket_counts_by_project()
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


def agent_roster(system_agents: list, rollups: list) -> list:
    """Merge the system_agents identity rows (callsign/name/prompt/model_id/version) with live
    per-role rollups from the runtime_agents table; append any live role not in system_agents as its
    own card (honest: a live agent not yet named). Roles are matched to rollups by callsign, since
    the old per-role registry `role` column no longer exists on system_agents."""
    by_role = {(r.get("role") or "").lower(): r for r in rollups}
    used = set()
    out = []

    def card(name, callsign, role, model, version, desc, roll):
        return {"name": name, "callsign": callsign, "sign": callsign, "role": role,
                "desc": desc, "model": (roll.get("model") if roll else None) or model,
                "cost_tier": None, "success": _success_rate(roll) if roll else None,
                "runs": int(roll.get("runs") or 0) if roll else 0,
                "on": bool(roll.get("active")) if roll else False,
                "prompt_version": version}

    for e in system_agents:
        roll = None
        # system_agents has no `role` column; match a rollup by the callsign lowercased.
        key = (e.get("callsign") or "").lower()
        if key and key in by_role and key not in used:
            roll = by_role[key]
            used.add(key)
        out.append(card(e["name"], e["callsign"], e.get("callsign"), e.get("model_id"),
                        e.get("version") or 0, e.get("prompt"), roll))
    # live roles not claimed by any roster entry → their own cards
    for role, roll in by_role.items():
        if role and role not in used:
            out.append(card(role.title(), role.upper(), role, None, 0,
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
            "created_by": r.get("created_by") or r.get("owner") or "",
            "created_at": r.get("created_at"),
        })
    return out
