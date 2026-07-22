"""Stage request contract and the variable context passed to each factory stage."""
from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass
class ProjectRequest:
    description: str
    context: str = ""
    budget: float = 25.0
    target: str = "railway"
    credentials: dict = field(default_factory=dict)
    context_files: list = field(default_factory=list)
    runtime: str = ""  # claude | opencode | codex; empty -> SF_RUNTIME env (default claude)
    planning_model: str = ""  # S1/S2 orchestrator model (claude runtime); empty -> stage default
    impl_model: str = ""      # S3 model (claude runtime); empty -> stage default
    model: str = ""           # opencode model alias: "kimi"|"glm"; empty -> _OPENCODE_DEFAULT_ALIAS
    name: str = ""            # operator-chosen project name (display label)
    owner: str = ""           # email of the creating user (multi-tenant: members see only their own)
    owner_github_username: str = ""  # SOF-3: owner's GitHub handle, if on file — invites them onto the repo


def _orchestration_preamble(stage_title: str, project_id: str, projects_dir: str, budget: float,
                            runtime: str = "claude") -> str:
    """The per-run VARIABLE context block. ALL instructions live in the stage's SKILL.md (the
    agent's contract, loaded from its cwd); this supplies ONLY the run-specific data SKILL.md
    references — no instructions. Kept per-runtime signature for callers; runtime doesn't change
    the variables (the claude/opencode work-model is stated in the SKILL.md variant)."""
    return (
        f"software-factory {stage_title}. Run this fully autonomously per SKILL.md (your cwd).\n"
        f"THIS RUN:\n"
        f"  project_id   = {project_id}\n"
        f"  projects_dir = {projects_dir}\n"
        f"  run base     = {os.path.join(projects_dir, project_id)}  (your cwd is its workspace/; prior-stage artifacts in context/)\n"
        f"  budget       = ${budget:.0f} (HARD cutoff)\n"
        f"  db-verb call = python3 -m software_factory.db <verb> {projects_dir} {project_id} ...\n"
    )


def make_prompt_stage1(req: ProjectRequest, project_id: str, projects_dir: str, runtime: str = "claude",
                       brief_block: str = "") -> str:
    ctx = f"\n\nContext / detailed input:\n{req.context}" if req.context else ""
    # The concierge-authored product brief is the richest context — inject it directly so the
    # council seats plan from it; the full markdown is also at input/brief.md and the transcript
    # at input/interview.md.
    brief = (f"\n\nThe user was interviewed; the product brief follows (also at input/brief.md; "
             f"full transcript at input/interview.md). Treat it as authoritative project context:\n"
             f"{brief_block.strip()}") if brief_block.strip() else ""
    return (
        _orchestration_preamble("Stage 1 — Research", project_id, projects_dir, req.budget, runtime)
        + f"  app          = {req.description}{ctx}{brief}"
    )


def make_prompt_stage2(req: ProjectRequest, project_id: str, projects_dir: str, runtime: str = "claude") -> str:
    return (
        _orchestration_preamble("Stage 2 — Design & Plan", project_id, projects_dir, req.budget, runtime)
        + f"  app          = {req.description}"
    )


def _disposition_guidance(dispositions: dict | None) -> str:
    """The per-run VARIABLE lists of which tokens fall in each disposition. What MOCK/DEPLOY-DB/MCP
    MEAN (and how to satisfy each) is instruction — it lives in SKILL.md Phase 1. This supplies only
    the token names for THIS run."""
    disp = dispositions or {}
    # Legacy 'env' (pre-removal runs) degrades to mock: a built app NEVER inherits the
    # runner's own keys (operator security rule).
    mock = sorted(name for name, disposition in disp.items() if disposition in ("mock", "env"))
    mcp = sorted(name for name, disposition in disp.items() if disposition == "mcp")
    dbtok = sorted(name for name, disposition in disp.items() if disposition == "deploy-db")
    if not disp:
        return ""
    return (
        f"  dispositions (see SKILL.md Phase 1 for what each means):\n"
        f"    MOCK     = {', '.join(mock) or 'none'}\n"
        f"    DEPLOY-DB= {', '.join(dbtok) or 'none'}\n"
        f"    SELF/MCP = {', '.join(mcp) or 'none'}\n"
    )


def make_prompt_stage3(req: ProjectRequest, project_id: str, projects_dir: str, dispositions: dict | None = None,
                       runtime: str = "claude") -> str:
    return (
        _orchestration_preamble("Stage 3 — Build & Ship", project_id, projects_dir, req.budget, runtime)
        + f"  deploy target= {req.target}  (own service sf-{project_id}[-<app>]; deploy per SKILL.md)\n"
        + _disposition_guidance(dispositions)
        + f"  app          = {req.description}"
    )
