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

SKILLS_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "skills")
PHASE_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "phases")
DESIGN_SKILL_NAMES = ("frontend-design", "ui-ux-pro-max")

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


def _skill_file(stage: int, skills_dir: str | None = None) -> str:
    names = {1: "stage-1-research", 2: "stage-2-design", 3: "stage-3-build"}
    base = skills_dir or SKILLS_DIR
    return os.path.join(base, names[stage], "SKILL.md")


def prepare_workspace(
    runs_dir: str,
    run_id: str,
    stage: int,
    skills_dir: str | None = None,
    phase_dir: str | None = None,
) -> str:
    ws = workspace.create(runs_dir, run_id)

    with open(os.path.join(ws, ".mcp.json"), "w") as f:
        json.dump(MCP_CONFIG, f, indent=2)
    with open(os.path.join(ws, "claude-settings.json"), "w") as f:
        json.dump(CLAUDE_SETTINGS, f, indent=2)

    src_skill = _skill_file(stage, skills_dir)
    if os.path.isfile(src_skill):
        shutil.copy2(src_skill, os.path.join(ws, "SKILL.md"))

    src_phases = phase_dir or PHASE_DIR
    if os.path.isdir(src_phases):
        dst_phases = os.path.join(ws, "phases")
        if not os.path.exists(dst_phases):
            shutil.copytree(src_phases, dst_phases)

    if stage == 1:
        base = skills_dir or SKILLS_DIR
        for name in DESIGN_SKILL_NAMES:
            src = os.path.join(base, name)
            if os.path.isdir(src):
                dst = os.path.join(ws, "skills", name)
                shutil.copytree(src, dst, dirs_exist_ok=True)

    if stage >= 2:
        _copy_prior_artifacts(runs_dir, run_id, ws, ["PRD.md", "design-spec.md"])
    if stage >= 3:
        _copy_prior_artifacts(runs_dir, run_id, ws, ["architecture.md", "architecture.svg"])

    return ws


def _copy_prior_artifacts(runs_dir: str, run_id: str, ws: str, names: list[str]) -> None:
    base = os.path.join(runs_dir, run_id)
    ctx_dir = os.path.join(ws, "context")
    ctx_real = os.path.realpath(ctx_dir)
    for name in names:
        for root, _dirs, files in os.walk(base):
            # Skip the destination itself — on a stage re-run (retry) the artifact already
            # lives in context/, and copying it onto itself raises SameFileError.
            if os.path.realpath(root) == ctx_real:
                continue
            if name in files:
                os.makedirs(ctx_dir, exist_ok=True)
                src = os.path.join(root, name)
                dst = os.path.join(ctx_dir, name)
                if os.path.realpath(src) != os.path.realpath(dst):
                    shutil.copy2(src, dst)
                break
