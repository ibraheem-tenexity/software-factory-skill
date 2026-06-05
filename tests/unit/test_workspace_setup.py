"""Workspace preparation: each stage's claude -p gets a correctly wired workspace."""
import json
import os
from software_factory.workspace_setup import prepare_workspace


def _make_skill_dir(tmp_path, stage_files):
    d = tmp_path / "skills"
    d.mkdir()
    for name, content in stage_files.items():
        (d / name).write_text(content)
    return str(d)


def _make_phase_dir(tmp_path):
    d = tmp_path / "phases"
    d.mkdir()
    (d / "00-provision.md").write_text("# provision")
    return str(d)


def _make_design_dir(tmp_path):
    d = tmp_path / "design-skills"
    fd = d / "frontend-design"
    fd.mkdir(parents=True)
    (fd / "SKILL.md").write_text("# frontend-design skill")
    ux = d / "ui-ux-pro-max"
    ux.mkdir(parents=True)
    (ux / "SKILL.md").write_text("# ui-ux skill")
    return str(d)


def test_stage1_workspace_has_mcp_and_settings(tmp_path):
    runs = tmp_path / "runs"
    runs.mkdir()
    skill_dir = _make_skill_dir(tmp_path, {"stage-1-research.md": "# stage 1"})
    phase_dir = _make_phase_dir(tmp_path)
    design_dir = _make_design_dir(tmp_path)

    ws = prepare_workspace(str(runs), "run-test", 1,
                           design_skills_dir=design_dir, skill_dir=skill_dir, phase_dir=phase_dir)

    mcp = json.loads(open(os.path.join(ws, ".mcp.json")).read())
    assert "ruflo" in mcp["mcpServers"]
    assert "playwright" in mcp["mcpServers"]

    settings = json.loads(open(os.path.join(ws, "claude-settings.json")).read())
    assert settings["enableAllProjectMcpServers"] is True


def test_stage1_includes_design_skills(tmp_path):
    runs = tmp_path / "runs"
    runs.mkdir()
    skill_dir = _make_skill_dir(tmp_path, {"stage-1-research.md": "# s1"})
    design_dir = _make_design_dir(tmp_path)

    ws = prepare_workspace(str(runs), "run-ds", 1,
                           design_skills_dir=design_dir, skill_dir=skill_dir,
                           phase_dir=_make_phase_dir(tmp_path))

    assert os.path.isfile(os.path.join(ws, "skills", "frontend-design", "SKILL.md"))
    assert os.path.isfile(os.path.join(ws, "skills", "ui-ux-pro-max", "SKILL.md"))


def test_stage2_excludes_design_skills(tmp_path):
    runs = tmp_path / "runs"
    runs.mkdir()
    skill_dir = _make_skill_dir(tmp_path, {"stage-2-design.md": "# s2"})
    design_dir = _make_design_dir(tmp_path)

    ws = prepare_workspace(str(runs), "run-s2", 2,
                           design_skills_dir=design_dir, skill_dir=skill_dir,
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

    skill_dir = _make_skill_dir(tmp_path, {"stage-2-design.md": "# s2"})
    ws = prepare_workspace(str(runs), "run-art", 2,
                           skill_dir=skill_dir, phase_dir=_make_phase_dir(tmp_path))

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

    skill_dir = _make_skill_dir(tmp_path, {"stage-3-build.md": "# s3"})
    ws = prepare_workspace(str(runs), "run-s3", 3,
                           skill_dir=skill_dir, phase_dir=_make_phase_dir(tmp_path))

    assert os.path.isfile(os.path.join(ws, "context", "architecture.md"))
    assert os.path.isfile(os.path.join(ws, "context", "architecture.svg"))
    assert os.path.isfile(os.path.join(ws, "context", "PRD.md"))


def test_workspace_copies_skill_file(tmp_path):
    runs = tmp_path / "runs"
    runs.mkdir()
    skill_dir = _make_skill_dir(tmp_path, {"stage-1-research.md": "# Stage 1 Research Skill"})

    ws = prepare_workspace(str(runs), "run-sk", 1,
                           skill_dir=skill_dir, phase_dir=_make_phase_dir(tmp_path))

    content = open(os.path.join(ws, "SKILL.md")).read()
    assert "Stage 1 Research Skill" in content


def test_workspace_copies_phase_files(tmp_path):
    runs = tmp_path / "runs"
    runs.mkdir()
    skill_dir = _make_skill_dir(tmp_path, {"stage-1-research.md": "# s1"})
    phase_dir = _make_phase_dir(tmp_path)

    ws = prepare_workspace(str(runs), "run-ph", 1,
                           skill_dir=skill_dir, phase_dir=phase_dir)

    assert os.path.isfile(os.path.join(ws, "phases", "00-provision.md"))
