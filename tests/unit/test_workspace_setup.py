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


def test_stage1_workspace_has_mcp_and_settings(tmp_path):
    runs = tmp_path / "runs"
    runs.mkdir()
    skills_dir = _make_skills_dir(tmp_path)
    phase_dir = _make_phase_dir(tmp_path)

    ws = prepare_workspace(str(runs), "run-test", 1,
                           skills_dir=skills_dir, phase_dir=phase_dir)

    mcp = json.loads(open(os.path.join(ws, ".mcp.json")).read())
    assert "ruflo" in mcp["mcpServers"]
    assert "playwright" in mcp["mcpServers"]

    settings = json.loads(open(os.path.join(ws, "claude-settings.json")).read())
    assert settings["enableAllProjectMcpServers"] is True


def test_stage1_includes_design_skills(tmp_path):
    runs = tmp_path / "runs"
    runs.mkdir()
    skills_dir = _make_skills_dir(tmp_path)

    ws = prepare_workspace(str(runs), "run-ds", 1,
                           skills_dir=skills_dir,
                           phase_dir=_make_phase_dir(tmp_path))

    assert os.path.isfile(os.path.join(ws, "skills", "frontend-design", "SKILL.md"))
    assert os.path.isfile(os.path.join(ws, "skills", "ui-ux-pro-max", "SKILL.md"))


def test_stage2_excludes_design_skills(tmp_path):
    runs = tmp_path / "runs"
    runs.mkdir()
    skills_dir = _make_skills_dir(tmp_path)

    ws = prepare_workspace(str(runs), "run-s2", 2,
                           skills_dir=skills_dir,
                           phase_dir=_make_phase_dir(tmp_path))

    assert not os.path.exists(os.path.join(ws, "skills", "frontend-design"))


def test_stage2_copies_stage1_artifacts(tmp_path):
    runs = tmp_path / "runs"
    runs.mkdir()
    run_dir = runs / "run-art"
    run_dir.mkdir()
    ws_old = run_dir / "workspace"
    ws_old.mkdir()
    (ws_old / ".sf-workspace").touch()
    (ws_old / "PRD.md").write_text("# PRD content")

    skills_dir = _make_skills_dir(tmp_path)
    ws = prepare_workspace(str(runs), "run-art", 2,
                           skills_dir=skills_dir, phase_dir=_make_phase_dir(tmp_path))

    assert os.path.isfile(os.path.join(ws, "context", "PRD.md"))


def test_prepare_workspace_is_idempotent_on_rerun(tmp_path):
    """Re-running a stage (retry) must not crash when context/ already holds the prior
    artifact — the walk must skip the destination, not copy a file onto itself.
    Reproduces the SameFileError that crashed the /retry handler on run-79e88589."""
    runs = tmp_path / "runs"
    runs.mkdir()
    run_dir = runs / "run-rt"
    run_dir.mkdir()
    ws_old = run_dir / "workspace"
    ws_old.mkdir()
    (ws_old / ".sf-workspace").touch()
    # Simulate the post-first-Stage-2 state: PRD.md already sits in the destination context/.
    ctx = ws_old / "context"
    ctx.mkdir()
    (ctx / "PRD.md").write_text("# PRD content")

    skills_dir = _make_skills_dir(tmp_path)
    phase_dir = _make_phase_dir(tmp_path)
    # Must not raise SameFileError; the prior artifact stays put.
    ws = prepare_workspace(str(runs), "run-rt", 2, skills_dir=skills_dir, phase_dir=phase_dir)
    assert os.path.isfile(os.path.join(ws, "context", "PRD.md"))


def test_stage3_copies_architecture_artifacts(tmp_path):
    runs = tmp_path / "runs"
    runs.mkdir()
    run_dir = runs / "run-s3"
    run_dir.mkdir()
    ws_old = run_dir / "workspace"
    ws_old.mkdir()
    (ws_old / ".sf-workspace").touch()
    (ws_old / "PRD.md").write_text("# PRD")
    (ws_old / "architecture.md").write_text("# Arch")
    (ws_old / "architecture.svg").write_text("<svg/>")

    skills_dir = _make_skills_dir(tmp_path)
    ws = prepare_workspace(str(runs), "run-s3", 3,
                           skills_dir=skills_dir, phase_dir=_make_phase_dir(tmp_path))

    assert os.path.isfile(os.path.join(ws, "context", "architecture.md"))
    assert os.path.isfile(os.path.join(ws, "context", "architecture.svg"))
    assert os.path.isfile(os.path.join(ws, "context", "PRD.md"))


def test_workspace_copies_skill_file(tmp_path):
    runs = tmp_path / "runs"
    runs.mkdir()
    skills_dir = _make_skills_dir(tmp_path)

    ws = prepare_workspace(str(runs), "run-sk", 1,
                           skills_dir=skills_dir, phase_dir=_make_phase_dir(tmp_path))

    content = open(os.path.join(ws, "SKILL.md")).read()
    assert "Stage 1 Research Skill" in content


def test_workspace_copies_phase_files(tmp_path):
    runs = tmp_path / "runs"
    runs.mkdir()
    skills_dir = _make_skills_dir(tmp_path)
    phase_dir = _make_phase_dir(tmp_path)

    ws = prepare_workspace(str(runs), "run-ph", 1,
                           skills_dir=skills_dir, phase_dir=phase_dir)

    assert os.path.isfile(os.path.join(ws, "phases", "00-provision.md"))
