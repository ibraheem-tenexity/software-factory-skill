"""Tests for the environment-tier / isolation module."""
import os

from software_factory import env


def test_sf_environment_defaults_to_dev(monkeypatch):
    monkeypatch.delenv("SF_ENVIRONMENT", raising=False)
    monkeypatch.delenv("RAILWAY_ENVIRONMENT", raising=False)
    assert env.sf_environment() == "dev"


def test_railway_production_infers_prod(monkeypatch):
    monkeypatch.delenv("SF_ENVIRONMENT", raising=False)
    monkeypatch.setenv("RAILWAY_ENVIRONMENT", "production")
    assert env.sf_environment() == "prod"


def test_explicit_sf_environment_overrides_railway(monkeypatch):
    monkeypatch.setenv("SF_ENVIRONMENT", "staging")
    monkeypatch.setenv("RAILWAY_ENVIRONMENT", "production")
    assert env.sf_environment() == "staging"


def _reload_env(monkeypatch):
    """Force env.py to re-evaluate module-level sets after monkeypatching env vars."""
    import importlib
    from software_factory import env as _env_mod
    importlib.reload(_env_mod)
    # also re-import so callers see the fresh module
    from software_factory import env as fresh
    return fresh


def test_runapp_railway_project_id_returns_single_configured_id(monkeypatch):
    monkeypatch.setenv("SF_RUNAPP_RAILWAY_PROJECT_IDS", "8ecbd1b2-2722-4968-91c9-4a242f8120f3")
    fresh = _reload_env(monkeypatch)
    assert fresh.runapp_railway_project_id() == "8ecbd1b2-2722-4968-91c9-4a242f8120f3"


def test_runapp_railway_project_id_returns_none_when_unset(monkeypatch):
    monkeypatch.delenv("SF_RUNAPP_RAILWAY_PROJECT_IDS", raising=False)
    fresh = _reload_env(monkeypatch)
    assert fresh.runapp_railway_project_id() is None


def test_runapp_railway_project_id_returns_none_for_multiple_ids(monkeypatch):
    monkeypatch.setenv("SF_RUNAPP_RAILWAY_PROJECT_IDS", "id-a,id-b")
    fresh = _reload_env(monkeypatch)
    assert fresh.runapp_railway_project_id() is None


def test_deploy_guard_uses_runapp_project_id_not_reserved_var(monkeypatch, tmp_path):
    """Guard check reads SF_RUNAPP_RAILWAY_PROJECT_IDS, ignores RAILWAY_PROJECT_ID."""
    from software_factory import deploy_db
    monkeypatch.setenv("SF_RUNAPP_RAILWAY_PROJECT_IDS", "allowed-uuid")
    monkeypatch.setenv("RAILWAY_PROJECT_ID", "console-uuid-forced-by-railway")
    fresh = _reload_env(monkeypatch)
    # Patch deploy_db's env reference to the reloaded module
    monkeypatch.setattr(deploy_db, "env", fresh)
    calls = []
    def fake_run(args):
        calls.append(args)
        from software_factory.deploy import RunResult
        import json
        if "add" in args:
            return RunResult(stdout=json.dumps({"serviceId": "s1", "serviceName": "Postgres-X"}), returncode=0)
        return RunResult(stdout=json.dumps({"DATABASE_URL": "postgresql://u:p@h/db"}), returncode=0)
    info = deploy_db.provision("pid", str(tmp_path), run=fake_run)
    assert info["DATABASE_URL"] == "postgresql://u:p@h/db"


def test_stage_env_baseline_drops_console_secrets(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://secret")
    monkeypatch.setenv("SF_DB", "postgres")
    monkeypatch.setenv("RAILWAY_TOKEN", "super-secret")
    monkeypatch.setenv("PATH", "/usr/bin")
    scrubbed = env.stage_env_baseline({"RAILWAY_TOKEN": "provided-token"})
    assert scrubbed["RAILWAY_TOKEN"] == "provided-token"
    assert scrubbed["PATH"] == "/usr/bin"
    assert "DATABASE_URL" not in scrubbed
    assert "SF_DB" not in scrubbed


def test_stage_env_baseline_forwards_github_token(monkeypatch):
    # #102: the stage-3 build agent's `gh` calls (repo create / push / PR) need GH_TOKEN to
    # survive the scrub, exactly like EXA_API_KEY — else `gh` is unauthenticated and repo
    # creation fails. GITHUB_TOKEN is carried as the alias `gh` also honours.
    monkeypatch.setenv("GH_TOKEN", "ghp_factory")
    monkeypatch.setenv("GITHUB_TOKEN", "ght_alias")
    monkeypatch.setenv("EXA_API_KEY", "exa_factory")
    scrubbed = env.stage_env_baseline()
    assert scrubbed["GH_TOKEN"] == "ghp_factory"
    assert scrubbed["GITHUB_TOKEN"] == "ght_alias"
    assert scrubbed["EXA_API_KEY"] == "exa_factory"


def test_stage_env_baseline_forwards_railway_token_and_runapp_project_id(monkeypatch):
    # #112: the stage-3 build agent deploys via the Railway MCP/CLI, which authenticate from
    # RAILWAY_TOKEN — it must survive the scrub or the MCP can't start and Railway returns
    # "Not Authorized". RAILWAY_PROJECT_ID is overridden to the RUN-APP project, NOT the console's
    # force-injected own project, so the agent targets software-factory-projects.
    monkeypatch.setenv("RAILWAY_TOKEN", "rwtok-factory")
    monkeypatch.setenv("RAILWAY_PROJECT_ID", "console-own-project")     # the wrong target
    monkeypatch.setattr(env, "_RUNAPP_RAILWAY_PROJECT_IDS", {"runapp-project-id"})
    scrubbed = env.stage_env_baseline()
    assert scrubbed["RAILWAY_TOKEN"] == "rwtok-factory"                 # token forwarded
    assert scrubbed["RAILWAY_PROJECT_ID"] == "runapp-project-id"        # run-app, NOT the console's
