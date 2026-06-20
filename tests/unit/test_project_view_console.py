"""Thin console read-accessors backing the Project View: agents(rid), artifacts(rid), project_created(rid)."""
from software_factory.console import Console, ProjectRequest
from software_factory.agents import AgentRegistry
from software_factory.db import ProjectStore


class FakeLauncher:
    def __call__(self, argv, env=None, log_path=None, cwd=None):
        return {"pid": 1}


def _console(tmp_path):
    return Console(str(tmp_path), launch=FakeLauncher(), new_id=lambda: "project-xyz")


def test_console_artifacts_lists_recorded(tmp_path):
    c = _console(tmp_path)
    rid = c.start_project(ProjectRequest(description="app", target="railway"))
    ProjectStore(c._paths(rid)["db"]).record_artifact("Architecture", "workspace/ARCHITECTURE.md",
                                               kind="plan", agent="architect")
    arts = c.artifacts(rid)
    a = next(x for x in arts if x["title"] == "Architecture")
    assert a["kind"] == "plan" and a["path"].endswith("ARCHITECTURE.md") and a["agent"] == "architect"


def test_console_agents_projects_role_ticket_cost(tmp_path):
    c = _console(tmp_path)
    rid = c.start_project(ProjectRequest(description="app", target="railway"))
    reg = AgentRegistry(c._paths(rid)["agents_db"])
    reg.spawn("a1", rid, 7, "opus", "claude-opus-4-8", "build")
    reg.record("a1", "real_diff", cost_usd=1.10)
    a = next(x for x in c.agents(rid) if x["agent_id"] == "a1")
    assert a["role"] == "opus" and a["model"] == "claude-opus-4-8"
    assert a["ticket_id"] == 7 and a["cost_usd"] == 1.10 and a["status"]


def test_console_run_created_from_first_phase(tmp_path):
    c = _console(tmp_path)
    rid = c.start_project(ProjectRequest(description="app", target="railway"))
    ProjectStore(c._paths(rid)["db"]).set_phase("provision", "active")
    assert (c.project_created(rid) or 0) > 0
