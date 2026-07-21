"""Prepare a structured workspace for each stage's claude -p invocation.

The workspace gets: the correct stage skill, .mcp.json, claude-settings.json,
phase files, and (for Stage 2+) the prior stage's artifacts. This ensures the
headless Claude has everything it needs — and that MCP is configured correctly
in the workspace, not just in the Docker image root.
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import tempfile

from . import workspace

logger = logging.getLogger(__name__)

SKILLS_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "skills")
PHASE_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "phases")
DESIGN_SKILL_NAMES = ("frontend-design", "ui-ux-pro-max", "tenexity-design")
# The brand canon ships to EVERY stage: S1 reads it for the PRD's design guidance, S2's
# design doc must speak in its tokens/archetypes, S3 vendors tokens.css into the app.
BUILD_SKILL_NAMES = ("tenexity-design",)

# SOF-81: BOOT-RESILIENCE FALLBACK ONLY. The `tools` table (tools.ToolStore) is the source of
# truth — mcp_config() below reads it. These hardcoded dicts fire only if that read fails (DB
# unreachable, table missing), so a console boot hiccup can't strand every stage launch. If you're
# changing a tool's config, edit its `tools` row (OS Tools tab), not this dict — a live edit here
# with no matching DB row is exactly the drift SOF-81 exists to kill.
#
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
# NO OpenRouter MCP (SOF-158, removed): no code ever called mcp__openrouter__* — the concierge's
# fusion_search/exa_search (concierge_tools.py) hit research.py's OpenRouter Fusion REST API
# directly via httpx (openrouter.ai/api/v1/chat/completions), a different endpoint entirely from
# this MCP server's (mcp.openrouter.ai/mcp). It was a real, always-present, never-called entry in
# every stage's .mcp.json.
# Project Memory — console-hosted (SOF-41/T4.2), not a third-party MCP. The URL/token are per-run,
# not console-static, so both are env-var'd (resolved from SF_MEMORY_MCP_URL/SF_MEMORY_TOKEN,
# injected by console.py::_launch_stage — see env._STAGE_ESSENTIAL's docstring for why a per-run
# value can't just live in the console's own static env like EXA_API_KEY does). Always offered
# (SOF-71 — memory is core, not opt-in); if SF_APP_URL was unset at launch the env vars never got
# injected, so the placeholders below are literally unresolved and the server call fails auth —
# memory/mcp_server.py enforces the token boundary regardless, this is belt+braces either way.
_MEMORY = {"type": "http", "url": "${SF_MEMORY_MCP_URL}",
          "headers": {"Authorization": "Bearer ${SF_MEMORY_TOKEN}"}}


def _hardcoded_mcp_config(stage: int) -> dict:
    servers = {"playwright": _PLAYWRIGHT, "exa": _EXA, "memory": _MEMORY}
    if stage >= 3:
        servers["railway"] = _RAILWAY
    return {"mcpServers": servers}


def _is_mcp_shaped(config: dict) -> bool:
    """A `tools` row is an MCP server block if it has a `command` (local) or `type` (remote, e.g.
    http) key. Rows shaped {"kind": "api", ...} (github, fusion) aren't MCP servers at all — they're
    env-key/config-only entries with no .mcp.json presence."""
    return "command" in config or "type" in config


def mcp_config(stage: int) -> dict:
    """The stage's .mcp.json, COMPOSED FROM THE `tools` TABLE (SOF-81) — the OS Tools tab IS what
    a stage build gets, by construction. `env_key` is SOF-81 registry metadata (which env var a
    vault-attached key overrides — see tool_env_overrides), never part of the real MCP server
    shape, so it's stripped before writing. Falls back to the hardcoded dicts above only if the
    table read itself fails."""
    callsign = f"STAGE-{stage}"
    try:
        from .tools import ToolStore
        rows = ToolStore().all()
        if not rows:
            raise RuntimeError("tools table is empty")
        servers = {
            row["name"]: {k: v for k, v in row["config"].items() if k != "env_key"}
            for row in rows
            if callsign in (row.get("attached_to") or []) and _is_mcp_shaped(row["config"])
        }
        return {"mcpServers": servers}
    except Exception:
        logger.warning("[mcp_config] tools-table read failed — falling back to hardcoded config",
                       exc_info=True)
        return _hardcoded_mcp_config(stage)


def tool_env_overrides(stage: int) -> dict:
    """Vault-backed env var overrides for this stage's tools (SOF-81) — an operator-attached key on
    a `tools` row whose attached_to includes this stage is injected as that row's config.env_key,
    superseding the console's own env passthrough for stage agents that use the tool. No key
    attached -> {} (current env passthrough behavior, unchanged). Best-effort: never blocks a
    launch on a registry/vault hiccup."""
    try:
        from .tools import ToolStore
        return ToolStore().env_overrides(f"STAGE-{stage}")
    except Exception:
        logger.debug("[tool_env_overrides] lookup failed — env passthrough used", exc_info=True)
        return {}


# Back-compat alias (stage-1 view, hardcoded fallback shape); prefer mcp_config(stage).
MCP_CONFIG = _hardcoded_mcp_config(1)

CLAUDE_SETTINGS = {"enableAllProjectMcpServers": True}

# Official Langfuse Claude Code hook script — vendored from
# https://langfuse.com/integrations/developer-tools/claude-code
_LANGFUSE_HOOK_SRC = os.path.join(
    os.path.dirname(__file__), "..", "..", "resources", "langfuse_hook.py"
)


def _write_langfuse_hook(ws: str) -> None:
    """Copy the official Langfuse Stop-hook into the workspace and register it.

    Places the script at .claude/hooks/langfuse_hook.py and writes
    .claude/settings.json with the Stop hook registration.  Also appends
    .claude/ to the workspace .gitignore so the hook (and any keys in the
    process env) never get committed to the customer's app repo that stage-3
    pushes to GitHub.

    Called whenever the Langfuse keys are configured — tracing is default behavior, not a toggle.
    The hook itself gates on that same env var at runtime (silently skips if
    absent), and reads LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY / LANGFUSE_BASE_URL
    from os.environ (forwarded via env._STAGE_ESSENTIAL).
    """
    hooks_dir = os.path.join(ws, ".claude", "hooks")
    os.makedirs(hooks_dir, exist_ok=True)

    dst_hook = os.path.join(hooks_dir, "langfuse_hook.py")
    shutil.copy2(_LANGFUSE_HOOK_SRC, dst_hook)

    settings = {
        "hooks": {
            "Stop": [
                {"hooks": [{"type": "command", "command": "python3 .claude/hooks/langfuse_hook.py"}]}
            ]
        }
    }
    with open(os.path.join(ws, ".claude", "settings.json"), "w") as f:
        json.dump(settings, f, indent=2)

    # Gitignore .claude/ so the hook + any env-injected secrets never reach the customer's repo.
    gitignore_path = os.path.join(ws, ".gitignore")
    entry = ".claude/\n"
    try:
        existing = open(gitignore_path).read() if os.path.isfile(gitignore_path) else ""
        if ".claude/" not in existing:
            with open(gitignore_path, "a") as f:
                if existing and not existing.endswith("\n"):
                    f.write("\n")
                f.write(entry)
    except OSError:
        pass


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


def opencode_config(stage: int) -> dict:
    """opencode.json for a stage workspace — same MCP set as the claude path, translated to
    OpenCode's shape, plus: permissions that can't 'ask' (headless never answers prompts), the
    stage contract injected ambiently via `instructions`. No steps cap — stages run to completion."""
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


def write_agent_file(ws: str, callsign: str, row: dict) -> None:
    """SOF-73: materialize a system_agents row (PRODUCT/DESIGN) as a native Claude Code subagent
    file at ws/.claude/agents/<callsign-lower>.md, so the orchestrator can dispatch
    Task(subagent_type=<callsign-lower>) using the operator-configured prompt. Claude-runtime
    only — opencode has no Task/subagent concept (see _launch_stage's opencode branch, which
    splices the same row's prompt into the SKILL.opencode.md override instead)."""
    agents_dir = os.path.join(ws, ".claude", "agents")
    os.makedirs(agents_dir, exist_ok=True)
    name = callsign.lower()
    frontmatter = (
        f"---\nname: {name}\n"
        f"description: {row.get('name') or name.title()} phase agent for the software factory pipeline.\n"
        f"tools: Read, Write, Edit, Bash, Grep, Glob, WebSearch, WebFetch\n"
        f"model: {row.get('model_id') or 'inherit'}\n---\n\n"
    )
    with open(os.path.join(agents_dir, f"{name}.md"), "w") as f:
        f.write(frontmatter + (row.get("prompt") or ""))


class RecipeSeedError(Exception):
    """Raised with the real git error when a recipe's seed repo can't be cloned at launch time."""


def _clone_recipe_seed(repo_url: str, dest: str) -> None:
    r = subprocess.run(["git", "clone", "--depth", "1", repo_url, dest],
                       capture_output=True, text=True, timeout=180)
    if r.returncode != 0:
        raise RecipeSeedError(
            f"could not clone recipe seed {repo_url}: {(r.stderr or r.stdout).strip()[-500:]}")


def prepare_workspace(
    projects_dir: str,
    project_id: str,
    stage: int,
    skills_dir: str | None = None,
    phase_dir: str | None = None,
    runtime: str = "claude",
    skill_override: str | None = None,
    recipe: dict | None = None,
) -> str:
    ws = workspace.create(projects_dir, project_id)

    # .mcp.json is written for BOTH runtimes: mcp_health.check_mcp reads exactly this shape
    # and _launch_stage hard-gates on it before any launch.
    with open(os.path.join(ws, ".mcp.json"), "w") as f:
        json.dump(mcp_config(stage), f, indent=2)
    if runtime == "opencode":
        with open(os.path.join(ws, "opencode.json"), "w") as f:
            json.dump(opencode_config(stage), f, indent=2)
    else:
        with open(os.path.join(ws, "claude-settings.json"), "w") as f:
            json.dump(CLAUDE_SETTINGS, f, indent=2)
        from software_factory import langfuse_tracing
        if langfuse_tracing.enabled():  # tracing is DEFAULT behavior when keys exist — no toggle var
            _write_langfuse_hook(ws)

    # Stage contract → ws/SKILL.md (both the prompt and opencode.json `instructions` reference that
    # one name). An operator's web edit (skill_override, resolved by the caller from the
    # SystemAgentStore) WINS — written verbatim; otherwise copy the on-disk default (the opencode variant's
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

    # CBT-9: fork-and-extend. Prompt-delivered judgment, deliberately unverified by code — there
    # is no "did it really fork" checker; the existing deploy/happy-flow/QA gates are the only
    # proof a recipe build worked. Never scaffold from scratch when a recipe is selected.
    if recipe and recipe.get("repo_url"):
        repo_url = recipe["repo_url"]
        if stage == 3:
            note = "Its working tree is already in this workspace."
        else:
            note = ("Its AGENTS.md is included as context (context/recipe-AGENTS.md) — read it "
                    "before framing the plan so tickets target real extension points.")
        block = (f"\n\n## RECIPE BUILD — {recipe['name']}\n"
                f"This app is FORKED from the recipe repository ({repo_url}). {note} "
                f"Read its AGENTS.md first; keep its architecture and conventions; implement the "
                f"tickets as extensions and modifications of this codebase. Never scaffold a new "
                f"app from scratch.\n")
        with open(os.path.join(ws, "SKILL.md"), "a") as f:
            f.write(block)

        if stage == 3:
            if not os.path.exists(os.path.join(ws, "AGENTS.md")):
                seed_dir = os.path.join(ws, "seed")
                _clone_recipe_seed(repo_url, seed_dir)
                for name in os.listdir(seed_dir):
                    if name == ".git":
                        continue
                    shutil.move(os.path.join(seed_dir, name), os.path.join(ws, name))
                shutil.rmtree(seed_dir, ignore_errors=True)  # drop seed history; the factory pushes its own repo
        else:
            with tempfile.TemporaryDirectory() as tmp:
                _clone_recipe_seed(repo_url, tmp)
                agents_src = os.path.join(tmp, "AGENTS.md")
                if os.path.isfile(agents_src):
                    ctx_dir = os.path.join(ws, "context")
                    os.makedirs(ctx_dir, exist_ok=True)
                    shutil.copy2(agents_src, os.path.join(ctx_dir, "recipe-AGENTS.md"))

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
        _copy_prior_artifacts(
            projects_dir, project_id, ws,
            ["architecture.md", "architecture.svg", "flow-map.md"])   # flow-map.md: SOF-100
        _copy_prior_dir(projects_dir, project_id, ws, "mockups")       # SOF-100

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


def _copy_prior_dir(projects_dir: str, project_id: str, ws: str, dirname: str) -> None:
    """SOF-100: same search as `_copy_prior_artifacts` but for a whole directory (e.g. the SOF-99
    `mockups/` directory) rather than a single file — `shutil.copy2` doesn't handle directories."""
    base = os.path.join(projects_dir, project_id)
    ctx_dir = os.path.join(ws, "context")
    ctx_real = os.path.realpath(ctx_dir)
    for root, dirs, _files in os.walk(base):
        if os.path.realpath(root) == ctx_real:
            continue
        if dirname in dirs:
            src = os.path.join(root, dirname)
            dst = os.path.join(ctx_dir, dirname)
            if os.path.realpath(src) != os.path.realpath(dst):
                os.makedirs(ctx_dir, exist_ok=True)
                shutil.copytree(src, dst, dirs_exist_ok=True)
            break
