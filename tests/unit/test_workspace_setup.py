"""Workspace preparation: each stage's claude -p gets a correctly wired workspace."""
import json
import os
from software_factory.workspace_setup import prepare_workspace


def _make_skills_dir(tmp_path):
    """Create a skills dir mirroring the new directory structure."""
    d = tmp_path / "skills"
    d.mkdir()
    for name, content in {
        "stage-1-research": "# Stage 1 Research Skill",
        "stage-2-design": "# s2",
        "stage-3-build": "# s3",
    }.items():
        sd = d / name
        sd.mkdir()
        (sd / "SKILL.md").write_text(content)
    fd = d / "frontend-design"
    fd.mkdir()
    (fd / "SKILL.md").write_text("# frontend-design skill")
    ux = d / "ui-ux-pro-max"
    ux.mkdir()
    (ux / "SKILL.md").write_text("# ui-ux skill")
    return str(d)


def _make_phase_dir(tmp_path):
    d = tmp_path / "phases"
    d.mkdir()
    (d / "00-provision.md").write_text("# provision")
    return str(d)


def test_skill_override_replaces_the_on_disk_skill(tmp_path):
    # An operator's web-edited prompt (skill_override) drives the run: it lands as ws/SKILL.md verbatim
    # INSTEAD of the on-disk default. This is the seam that makes a dashboard edit take effect.
    runs = tmp_path / "runs"; runs.mkdir()
    skills_dir = _make_skills_dir(tmp_path)
    ws = prepare_workspace(str(runs), "project-ovr", 1, skills_dir=skills_dir,
                           phase_dir=_make_phase_dir(tmp_path), skill_override="# EDITED BY OPERATOR")
    assert open(os.path.join(ws, "SKILL.md")).read() == "# EDITED BY OPERATOR"


def test_no_override_uses_the_on_disk_default(tmp_path):
    runs = tmp_path / "runs"; runs.mkdir()
    skills_dir = _make_skills_dir(tmp_path)
    ws = prepare_workspace(str(runs), "project-def", 1, skills_dir=skills_dir,
                           phase_dir=_make_phase_dir(tmp_path))
    assert open(os.path.join(ws, "SKILL.md")).read() == "# Stage 1 Research Skill"   # copied default


def test_stage1_workspace_has_mcp_and_settings(tmp_path):
    runs = tmp_path / "runs"
    runs.mkdir()
    skills_dir = _make_skills_dir(tmp_path)
    phase_dir = _make_phase_dir(tmp_path)

    ws = prepare_workspace(str(runs), "project-test", 1,
                           skills_dir=skills_dir, phase_dir=phase_dir)

    mcp = json.loads(open(os.path.join(ws, ".mcp.json")).read())
    assert "playwright" in mcp["mcpServers"]
    assert "ruflo" not in mcp["mcpServers"]   # ruflo/claude-flow removed; playwright is the only MCP

    settings = json.loads(open(os.path.join(ws, "claude-settings.json")).read())
    assert settings["enableAllProjectMcpServers"] is True


def test_stage3_workspace_wires_railway_mcp_and_no_supabase(tmp_path):
    # Stage 3 deploys, so its workspace gets the Railway MCP + playwright — but NEVER Supabase
    # (agents have no Supabase access; the DB is factory-provided via context/deploy-db.json).
    runs = tmp_path / "runs"; runs.mkdir()
    ws = prepare_workspace(str(runs), "project-s3mcp", 3,
                           skills_dir=_make_skills_dir(tmp_path), phase_dir=_make_phase_dir(tmp_path))
    mcp = json.loads(open(os.path.join(ws, ".mcp.json")).read())["mcpServers"]
    assert {"playwright", "railway"}.issubset(set(mcp))
    assert "supabase" not in mcp
    assert mcp["railway"]["command"] == "railway" and mcp["railway"]["args"] == ["mcp"]


def test_stage1_and_2_workspace_has_playwright_and_exa_no_deploy_mcps(tmp_path):
    # Stages 1-2 get playwright + exa + openrouter (web search & LLM, all stages) but NOT the
    # deploy MCPs (railway).
    runs = tmp_path / "runs"; runs.mkdir()
    skills_dir = _make_skills_dir(tmp_path); phase_dir = _make_phase_dir(tmp_path)
    for stage in (1, 2):
        ws = prepare_workspace(str(runs), "project-s%d" % stage, stage,
                               skills_dir=skills_dir, phase_dir=phase_dir)
        mcp = json.loads(open(os.path.join(ws, ".mcp.json")).read())["mcpServers"]
        assert set(mcp) == {"playwright", "exa", "openrouter"}, \
            "stages 1-2 = playwright + exa + openrouter, no deploy MCPs"


def test_exa_web_search_mcp_in_every_stage_both_runtimes_env_var_key(tmp_path):
    """exa (the remote web-search MCP) is wired into EVERY stage for both runtimes, with its
    api-key sourced from an env var (never a literal), in the runtime-correct remote shape."""
    from software_factory.workspace_setup import mcp_config, opencode_config
    for stage in (1, 2, 3):
        # claude .mcp.json shape: remote http server, ${EXA_API_KEY} expansion.
        exa = mcp_config(stage)["mcpServers"]["exa"]
        assert exa == {"type": "http", "url": "https://mcp.exa.ai/mcp",
                       "headers": {"x-api-key": "${EXA_API_KEY}"}}
        # opencode shape: remote, {env:EXA_API_KEY} expansion; no `command` key.
        oc = opencode_config(stage)["mcp"]["exa"]
        assert oc["type"] == "remote" and oc["url"] == "https://mcp.exa.ai/mcp"
        assert oc["headers"] == {"x-api-key": "{env:EXA_API_KEY}"}
        assert "command" not in oc
        # The key is env-var'd in BOTH runtimes — never a literal value.
        assert "EXA_API_KEY" in json.dumps(exa) and "EXA_API_KEY" in json.dumps(oc)


def test_generated_workspace_configs_contain_exa_and_health_check_survives(tmp_path):
    """A generated stage workspace (claude .mcp.json + opencode opencode.json) contains exa with the
    env-var key, and mcp_health.check_mcp tolerates the url-only exa server (no KeyError, no fail)."""
    from software_factory.mcp_health import check_mcp
    runs = tmp_path / "runs"; runs.mkdir()
    skills_dir = _make_skills_dir(tmp_path); phase_dir = _make_phase_dir(tmp_path)
    for stage in (1, 2, 3):
        # claude runtime
        ws = prepare_workspace(str(runs), "project-clx%d" % stage, stage,
                               skills_dir=skills_dir, phase_dir=phase_dir)
        mcp = json.loads(open(os.path.join(ws, ".mcp.json")).read())["mcpServers"]
        assert mcp["exa"]["headers"]["x-api-key"] == "${EXA_API_KEY}"
        # check_mcp must not crash on the url-only exa server; remote is best-effort (ok=True).
        results = check_mcp(os.path.join(ws, ".mcp.json"),
                            run=lambda cmd, inp, t: (0, '{"jsonrpc":"2.0","id":1,"result":{}}', ""))
        by_name = {c.name: c for c in results}
        assert by_name["exa"].ok is True
        # opencode runtime
        wso = prepare_workspace(str(runs), "project-ocx%d" % stage, stage, runtime="opencode",
                                skills_dir=skills_dir, phase_dir=phase_dir)
        ocmcp = json.loads(open(os.path.join(wso, "opencode.json")).read())["mcp"]
        assert ocmcp["exa"]["headers"]["x-api-key"] == "{env:EXA_API_KEY}"


def test_stage1_includes_design_skills(tmp_path):
    runs = tmp_path / "runs"
    runs.mkdir()
    skills_dir = _make_skills_dir(tmp_path)

    ws = prepare_workspace(str(runs), "project-ds", 1,
                           skills_dir=skills_dir,
                           phase_dir=_make_phase_dir(tmp_path))

    assert os.path.isfile(os.path.join(ws, "skills", "frontend-design", "SKILL.md"))
    assert os.path.isfile(os.path.join(ws, "skills", "ui-ux-pro-max", "SKILL.md"))


def test_stage2_excludes_design_skills(tmp_path):
    runs = tmp_path / "runs"
    runs.mkdir()
    skills_dir = _make_skills_dir(tmp_path)

    ws = prepare_workspace(str(runs), "project-s2", 2,
                           skills_dir=skills_dir,
                           phase_dir=_make_phase_dir(tmp_path))

    assert not os.path.exists(os.path.join(ws, "skills", "frontend-design"))


def test_stage2_copies_stage1_artifacts(tmp_path):
    runs = tmp_path / "runs"
    runs.mkdir()
    project_dir = runs / "project-art"
    project_dir.mkdir()
    ws_old = project_dir / "workspace"
    ws_old.mkdir()
    (ws_old / ".sf-workspace").touch()
    (ws_old / "PRD.md").write_text("# PRD content")

    skills_dir = _make_skills_dir(tmp_path)
    ws = prepare_workspace(str(runs), "project-art", 2,
                           skills_dir=skills_dir, phase_dir=_make_phase_dir(tmp_path))

    assert os.path.isfile(os.path.join(ws, "context", "PRD.md"))


def test_prepare_workspace_is_idempotent_on_rerun(tmp_path):
    """Re-running a stage (retry) must not crash when context/ already holds the prior
    artifact — the walk must skip the destination, not copy a file onto itself.
    Reproduces the SameFileError that crashed the /retry handler on project-79e88589."""
    runs = tmp_path / "runs"
    runs.mkdir()
    project_dir = runs / "project-rt"
    project_dir.mkdir()
    ws_old = project_dir / "workspace"
    ws_old.mkdir()
    (ws_old / ".sf-workspace").touch()
    # Simulate the post-first-Stage-2 state: PRD.md already sits in the destination context/.
    ctx = ws_old / "context"
    ctx.mkdir()
    (ctx / "PRD.md").write_text("# PRD content")

    skills_dir = _make_skills_dir(tmp_path)
    phase_dir = _make_phase_dir(tmp_path)
    # Must not raise SameFileError; the prior artifact stays put.
    ws = prepare_workspace(str(runs), "project-rt", 2, skills_dir=skills_dir, phase_dir=phase_dir)
    assert os.path.isfile(os.path.join(ws, "context", "PRD.md"))


def test_stage3_copies_architecture_artifacts(tmp_path):
    runs = tmp_path / "runs"
    runs.mkdir()
    project_dir = runs / "project-s3"
    project_dir.mkdir()
    ws_old = project_dir / "workspace"
    ws_old.mkdir()
    (ws_old / ".sf-workspace").touch()
    (ws_old / "PRD.md").write_text("# PRD")
    (ws_old / "architecture.md").write_text("# Arch")
    (ws_old / "architecture.svg").write_text("<svg/>")

    skills_dir = _make_skills_dir(tmp_path)
    ws = prepare_workspace(str(runs), "project-s3", 3,
                           skills_dir=skills_dir, phase_dir=_make_phase_dir(tmp_path))

    assert os.path.isfile(os.path.join(ws, "context", "architecture.md"))
    assert os.path.isfile(os.path.join(ws, "context", "architecture.svg"))
    assert os.path.isfile(os.path.join(ws, "context", "PRD.md"))


def test_workspace_copies_skill_file(tmp_path):
    runs = tmp_path / "runs"
    runs.mkdir()
    skills_dir = _make_skills_dir(tmp_path)

    ws = prepare_workspace(str(runs), "project-sk", 1,
                           skills_dir=skills_dir, phase_dir=_make_phase_dir(tmp_path))

    content = open(os.path.join(ws, "SKILL.md")).read()
    assert "Stage 1 Research Skill" in content


def test_workspace_copies_phase_files(tmp_path):
    runs = tmp_path / "runs"
    runs.mkdir()
    skills_dir = _make_skills_dir(tmp_path)
    phase_dir = _make_phase_dir(tmp_path)

    ws = prepare_workspace(str(runs), "project-ph", 1,
                           skills_dir=skills_dir, phase_dir=phase_dir)

    assert os.path.isfile(os.path.join(ws, "phases", "00-provision.md"))


def test_tenexity_design_canon_ships_to_every_stage(tmp_path):
    # The REAL skills dir: the canon must exist (tokens + SKILL) and land in S1/S2/S3
    # workspaces — S3 vendors tokens.css into the app, so build especially needs it.
    runs = tmp_path / "runs"
    runs.mkdir()
    for stage in (1, 2, 3):
        ws = prepare_workspace(str(runs), "project-tnx%d" % stage, stage)
        canon = os.path.join(ws, "skills", "tenexity-design")
        assert os.path.isfile(os.path.join(canon, "SKILL.md")), f"stage {stage} missing canon"
        tokens = open(os.path.join(canon, "tokens.css")).read()
        assert "--brand: 214 100% 55%" in tokens   # the gate's literal brand marker
        assert os.path.isfile(os.path.join(canon, "tailwind.config.ts"))


def test_stage_contracts_reference_the_canon():
    base = os.path.join(os.path.dirname(__file__), "..", "..", "skills")
    for rel in ("stage-1-research/SKILL.md", "stage-1-research/SKILL.opencode.md",
                "stage-3-build/SKILL.md", "stage-3-build/SKILL.opencode.md"):
        text = open(os.path.join(base, rel)).read()
        assert "tenexity-design" in text, f"{rel} lost the canon wiring"
    for rel in ("stage-3-build/SKILL.md", "stage-3-build/SKILL.opencode.md"):
        text = open(os.path.join(base, rel)).read()
        assert "--brand: 214 100% 55%" in text     # gate brand-check instruction


def test_opencode_config_pins_provider_key_to_the_env_var():
    # project-d81f37da scar: SDK-spawned `opencode serve` fell back to the host's global
    # auth.json (spend-limited key) — the workspace config must pin the env key so every
    # opencode entrypoint (run AND serve) uses the run's credential.
    from software_factory.workspace_setup import opencode_config
    cfg = opencode_config(stage=3)
    assert cfg["provider"]["openrouter"]["options"]["apiKey"] == "{env:OPENROUTER_API_KEY}"


def test_no_supabase_mcp_at_any_stage():
    from software_factory.workspace_setup import mcp_config
    for s in (1, 2, 3):
        assert "supabase" not in mcp_config(s)["mcpServers"], s
    assert "railway" in mcp_config(3)["mcpServers"]      # railway stays (deploy)
    assert "railway" not in mcp_config(1)["mcpServers"]
    assert "playwright" in mcp_config(1)["mcpServers"]


def test_stage3_contracts_drop_supabase_and_use_deploy_db_file():
    import os
    base = os.path.join(os.path.dirname(__file__), "..", "..", "skills")
    for rel in ("stage-3-build/SKILL.md", "stage-3-build/SKILL.opencode.md"):
        t = open(os.path.join(base, rel)).read()
        assert "context/deploy-db.json" in t
        assert "create the Supabase project" not in t
        assert "supabase` MCP" not in t
