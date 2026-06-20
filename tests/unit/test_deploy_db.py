"""Factory-side deploy-database provisioning (the replacement for agent Supabase access)."""
import json

import pytest

from software_factory import deploy_db
from software_factory.deploy import RunResult


def _runner(outputs):
    seq = iter(outputs)
    calls = []

    def run(args):
        calls.append(args)
        return RunResult(stdout=next(seq), returncode=0)
    run.calls = calls
    return run


def test_needs_deploy_db():
    assert deploy_db.needs_deploy_db(["DATABASE_URL"])
    assert deploy_db.needs_deploy_db(["SUPABASE_URL", "FOO"])
    assert deploy_db.needs_deploy_db(["POSTGRES_PASSWORD"])
    assert not deploy_db.needs_deploy_db(["OPENROUTER_API_KEY", "NEXTAUTH_SECRET"])
    assert not deploy_db.needs_deploy_db([])
    assert not deploy_db.needs_deploy_db(None)


def test_provision_reads_url_from_variables_json(monkeypatch):
    monkeypatch.delenv("RAILWAY_PROJECT_ID", raising=False)
    run = _runner(["postgres added", json.dumps({"DATABASE_URL": "postgresql://u:p@h:5432/db"})])
    info = deploy_db.provision("project-abcd1234", run=run)
    assert info["DATABASE_URL"] == "postgresql://u:p@h:5432/db"
    assert info["provider"] == "railway-postgres"
    assert info["service"] == "sf-project-abcd1234-db"
    assert run.calls[0][:2] == ["railway", "add"]          # provisioned before reading


def test_provision_falls_back_to_url_in_plain_text(monkeypatch):
    monkeypatch.delenv("RAILWAY_PROJECT_ID", raising=False)
    run = _runner(["added", "DATABASE_URL=postgres://a:b@c:5432/d  (set)"])
    info = deploy_db.provision("project-xy", run=run)
    assert info["DATABASE_URL"] == "postgres://a:b@c:5432/d"


def test_provision_raises_when_no_url(monkeypatch):
    monkeypatch.delenv("RAILWAY_PROJECT_ID", raising=False)
    run = _runner(["added", "no connection string here"])
    with pytest.raises(RuntimeError):
        deploy_db.provision("project-z", run=run)


def test_provision_refuses_disallowed_railway_project(monkeypatch):
    # the console's own project must never host a run app's DB
    monkeypatch.setenv("SF_RUNAPP_RAILWAY_PROJECT_IDS", "allowed-proj")
    monkeypatch.setenv("RAILWAY_PROJECT_ID", "some-other-proj")
    with pytest.raises(RuntimeError):
        deploy_db.provision("project-q", run=_runner(["x", "y"]))


def test_write_file_roundtrip(tmp_path):
    p = deploy_db.write_file(str(tmp_path / "context"), {"DATABASE_URL": "x", "provider": "railway-postgres"})
    assert p.endswith("deploy-db.json")
    assert json.load(open(p))["DATABASE_URL"] == "x"
