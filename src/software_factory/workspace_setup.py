"""Prepare a structured workspace for each stage's claude -p invocation.

The workspace gets: the correct stage skill, .mcp.json, claude-settings.json,
phase files, and (for Stage 2+) the prior stage's artifacts. This ensures the
headless Claude has everything it needs — and that MCP is configured correctly
in the workspace, not just in the Docker image root.
"""
from __future__ import annotations

import json
import os
import shutil

from . import workspace

SKILL_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "skills")
PHASE_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "phases")
DESIGN_SKILLS_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "design-skills")

MCP_CONFIG = {
    "mcpServers": {
        "playwright": {
            "command": "npx",
            "args": ["-y", "@playwright/mcp@latest", "--headless", "--browser", "chromium"],
        },
        "ruflo": {
            "command": "claude-flow",
            "args": ["mcp", "start"],
        },
    },
}

CLAUDE_SETTINGS = {"enableAllProjectMcpServers": True}


def _skill_file(stage: int) -> str:
    names = {1: "stage-1-research.md", 2: "stage-2-design.md", 3: "stage-3-build.md"}
    return os.path.join(SKILL_DIR, names[stage])


def prepare_workspace(
    runs_dir: str,
    run_id: str,
    stage: int,
    design_skills_dir: str | None = None,
    skill_dir: str | None = None,
    phase_dir: str | None = None,
) -> str:
    ws = workspace.create(runs_dir, run_id)

    with open(os.path.join(ws, ".mcp.json"), "w") as f:
        json.dump(MCP_CONFIG, f, indent=2)
    with open(os.path.join(ws, "claude-settings.json"), "w") as f:
        json.dump(CLAUDE_SETTINGS, f, indent=2)

    src_skill = _skill_file(stage) if skill_dir is None else os.path.join(skill_dir, os.path.basename(_skill_file(stage)))
    if os.path.isfile(src_skill):
        shutil.copy2(src_skill, os.path.join(ws, "SKILL.md"))

    src_phases = phase_dir or PHASE_DIR
    if os.path.isdir(src_phases):
        dst_phases = os.path.join(ws, "phases")
        if not os.path.exists(dst_phases):
            shutil.copytree(src_phases, dst_phases)

    if stage == 1:
        ds = design_skills_dir or DESIGN_SKILLS_DIR
        if os.path.isdir(ds):
            for skill_name in os.listdir(ds):
                src = os.path.join(ds, skill_name)
                dst = os.path.join(ws, "skills", skill_name)
                if os.path.isdir(src):
                    shutil.copytree(src, dst, dirs_exist_ok=True)
                elif os.path.isfile(src):
                    os.makedirs(os.path.dirname(dst), exist_ok=True)
                    shutil.copy2(src, dst)

    if stage >= 2:
        _copy_prior_artifacts(runs_dir, run_id, ws, ["PRD.md", "design-spec.md"])
    if stage >= 3:
        _copy_prior_artifacts(runs_dir, run_id, ws, ["architecture.md", "architecture.svg"])

    return ws


def _copy_prior_artifacts(runs_dir: str, run_id: str, ws: str, names: list[str]) -> None:
    base = os.path.join(runs_dir, run_id)
    ctx_dir = os.path.join(ws, "context")
    for name in names:
        for root, _dirs, files in os.walk(base):
            if name in files:
                os.makedirs(ctx_dir, exist_ok=True)
                shutil.copy2(os.path.join(root, name), os.path.join(ctx_dir, name))
                break
