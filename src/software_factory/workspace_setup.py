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
DESIGN_SKILL_NAMES = ("frontend-design", "ui-ux-pro-max", "tenexity-design")
# The brand canon ships to EVERY stage: S1 reads it for the PRD's design guidance, S2's
# design doc must speak in its tokens/archetypes, S3 vendors tokens.css into the app.
BUILD_SKILL_NAMES = ("tenexity-design",)

# Playwright everywhere (the happy-flow gate drives the live app with it). Stage 3 ALSO gets the
# Railway + Supabase MCP for deploy/provisioning. Both auth from env tokens already in the workspace
# (RAILWAY_TOKEN, SUPABASE_ACCESS_TOKEN) — verified headless: `railway mcp` exposes project-scoped
# tools (create_service/deploy/generate_domain/get_logs/set_variables) with a project token, and the
# supabase server reads SUPABASE_ACCESS_TOKEN from env. ruflo/claude-flow is gone.
_PLAYWRIGHT = {"command": "npx", "args": ["-y", "@playwright/mcp@latest", "--headless", "--browser", "chromium"]}
_RAILWAY = {"command": "railway", "args": ["mcp"]}
# Exa web-search — a REMOTE (HTTP) MCP, not a local command server. Wired into EVERY stage so any
# stage agent can search the web when useful. The key is env-var'd (${EXA_API_KEY}, resolved at MCP
# load from EXA_API_KEY in the stage env — see env._STAGE_ESSENTIAL) and never literal. Because it's
# url-only it has no `command`: the server-translation/health loops below branch on `url`.
_EXA = {"type": "http", "url": "https://mcp.exa.ai/mcp", "headers": {"x-api-key": "${EXA_API_KEY}"}}
# NO Supabase MCP — stage agents must never have Supabase access. The Supabase access token is
# an account-wide PAT (can create/DELETE any project, incl. production); an autonomous
# --dangerously-skip-permissions agent must not hold it. The app's database is provisioned BY
# THE STAGE-3 AGENT (the `provision-db` verb wrapping deploy_db.py) and written to
# context/deploy-db.json. Railway stays — the agent needs it to deploy the app
# (create_service/deploy/generate_domain), not to make a DB.
_OPEN_ROUTER = { "type":"http", "url": "https://mcp.openrouter.ai/mcp" }


def mcp_config(stage: int) -> dict:
    servers = {"playwright": _PLAYWRIGHT, "exa": _EXA, "openrouter": _OPEN_ROUTER}
    if stage >= 3:
        servers["railway"] = _RAILWAY
    return {"mcpServers": servers}


# Back-compat alias (stage-1 view); prefer mcp_config(stage).
MCP_CONFIG = mcp_config(1)

CLAUDE_SETTINGS = {"enableAllProjectMcpServers": True}


def _to_opencode_envref(value: str) -> str:
    """Rewrite a claude `.mcp.json` env-ref (`${VAR}`) to OpenCode's (`{env:VAR}`)."""
    import re
    return re.sub(r"\$\{(\w+)\}", r"{env:\1}", value) if isinstance(value, str) else value


def _opencode_server(srv: dict) -> dict:
    """Translate one .mcp.json server-dict to OpenCode's mcp shape. A url-only server (e.g. exa,
    the remote web-search MCP) becomes OpenCode's remote form with its headers carried over; a
    command server stays local. Header env-refs use OpenCode's `{env:VAR}` syntax, not `${VAR}`."""
    if srv.get("url"):
        headers = {k: _to_opencode_envref(v) for k, v in (srv.get("headers") or {}).items()}
        return {"type": "remote", "url": srv["url"], "headers": headers, "enabled": True}
    return {"type": "local", "command": [srv["command"], *srv["args"]], "enabled": True}


def opencode_config(stage: int, steps: int) -> dict:
    """opencode.json for a stage workspace — same MCP set as the claude path, translated to
    OpenCode's shape, plus: permissions that can't 'ask' (headless never answers prompts), the
    stage contract injected ambiently via `instructions`, and the steps-capped primary agent
    (OpenCode has no --max-turns; the cap lives here)."""
    servers = {name: _opencode_server(srv) for name, srv in mcp_config(stage)["mcpServers"].items()}
    cfg = {
        "$schema": "https://opencode.ai/config.json",
        "mcp": servers,
        # The env key is the run's ONLY OpenRouter credential — pinned explicitly because
        # auth resolution differs by entrypoint: `opencode run` honors the env key under
        # XDG_DATA_HOME isolation, but SDK-spawned `opencode serve` (the swarm path) fell
        # back to the host's global auth.json, whose spend-limited key credit-refused every
        # swarm agent on run-d81f37da while the env key had headroom.
        "provider": {"openrouter": {"options": {"apiKey": "{env:OPENROUTER_API_KEY}"}}},
        "permission": {"doom_loop": "allow", "external_directory": {"*": "allow"}},
        "instructions": ["SKILL.md"],
        "agent": {
            "factory": {
                "mode": "primary",
                "description": "Software factory stage agent",
                "steps": steps,
            },
        },
    }
    if stage == 1:
        # The design sub-skills (frontend-design, ui-ux-pro-max) are copied into ws/skills/;
        # nothing auto-loads them in OpenCode, so register the dir with the skill scanner.
        cfg["skills"] = {"paths": ["skills"]}
    return cfg


def _skill_file(stage: int, skills_dir: str | None = None) -> str:
    names = {1: "stage-1-research", 2: "stage-2-design", 3: "stage-3-build"}
    base = skills_dir or SKILLS_DIR
    return os.path.join(base, names[stage], "SKILL.md")


def prepare_workspace(
    projects_dir: str,
    project_id: str,
    stage: int,
    skills_dir: str | None = None,
    phase_dir: str | None = None,
    runtime: str = "claude",
    skill_override: str | None = None,
    steps: int | None = None,
) -> str:
    ws = workspace.create(projects_dir, project_id)

    # .mcp.json is written for BOTH runtimes: mcp_health.check_mcp reads exactly this shape
    # and _launch_stage hard-gates on it before any launch.
    with open(os.path.join(ws, ".mcp.json"), "w") as f:
        json.dump(mcp_config(stage), f, indent=2)
    if runtime == "opencode":
        # Per-project cap when the console threads one through; else the SF_MAX_TURNS env default.
        cap = steps if steps is not None else int(os.environ.get("SF_MAX_TURNS", "200") or 200)
        with open(os.path.join(ws, "opencode.json"), "w") as f:
            json.dump(opencode_config(stage, cap), f, indent=2)
    else:
        with open(os.path.join(ws, "claude-settings.json"), "w") as f:
            json.dump(CLAUDE_SETTINGS, f, indent=2)

    # Stage contract → ws/SKILL.md (both the prompt and opencode.json `instructions` reference that
    # one name). An operator's web edit (skill_override, resolved per-runtime by the caller from the
    # PromptStore) WINS — written verbatim; otherwise copy the on-disk default (the opencode variant's
    # monolithic framing when it exists and the runtime asks for it, else the claude SKILL.md).
    if skill_override is not None:
        with open(os.path.join(ws, "SKILL.md"), "w") as f:
            f.write(skill_override)
    else:
        src_skill = _skill_file(stage, skills_dir)
        if runtime == "opencode":
            oc_skill = src_skill.replace("SKILL.md", "SKILL.opencode.md")
            if os.path.isfile(oc_skill):
                src_skill = oc_skill
        if os.path.isfile(src_skill):
            shutil.copy2(src_skill, os.path.join(ws, "SKILL.md"))

    src_phases = phase_dir or PHASE_DIR
    if os.path.isdir(src_phases):
        dst_phases = os.path.join(ws, "phases")
        if not os.path.exists(dst_phases):
            shutil.copytree(src_phases, dst_phases)

    base = skills_dir or SKILLS_DIR
    for name in (DESIGN_SKILL_NAMES if stage == 1 else BUILD_SKILL_NAMES):
        src = os.path.join(base, name)
        if os.path.isdir(src):
            dst = os.path.join(ws, "skills", name)
            shutil.copytree(src, dst, dirs_exist_ok=True)

    if stage >= 2:
        _copy_prior_artifacts(projects_dir, project_id, ws, ["PRD.md", "design-spec.md"])
    if stage >= 3:
        _copy_prior_artifacts(projects_dir, project_id, ws, ["architecture.md", "architecture.svg"])

    return ws


def _copy_prior_artifacts(projects_dir: str, project_id: str, ws: str, names: list[str]) -> None:
    base = os.path.join(projects_dir, project_id)
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
