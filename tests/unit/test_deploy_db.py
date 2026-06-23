"""Factory-side deploy-database provisioning (the replacement for agent Supabase access).

These tests assert the REAL railway-CLI flow (verified live, CLI 5.12.1): `railway add --database
postgres --json` returns {serviceId, serviceName:"Postgres-XXXX"} (auto-named — NOT a name we pass),
then `railway variables --service <serviceId> --json` yields DATABASE_URL. The old tests mocked a
read-back by a guessed name that never existed in prod — that blind spot shipped the orphan-leak bug.
"""
import json
import os

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


_ADD = json.dumps({"serviceId": "svc-123", "serviceName": "Postgres-RNK8", "templateName": "PostgreSQL"})
_VARS = json.dumps({"DATABASE_URL": "postgresql://u:p@h:5432/railway", "PGHOST": "h"})


def test_needs_deploy_db():
    assert deploy_db.needs_deploy_db(["DATABASE_URL"])
    assert deploy_db.needs_deploy_db(["SUPABASE_URL", "FOO"])
    assert deploy_db.needs_deploy_db(["POSTGRES_PASSWORD"])
    assert not deploy_db.needs_deploy_db(["OPENROUTER_API_KEY", "NEXTAUTH_SECRET"])
    assert not deploy_db.needs_deploy_db([])
    assert not deploy_db.needs_deploy_db(None)


def test_provision_captures_real_service_id_and_reads_url(tmp_path, monkeypatch):
    monkeypatch.delenv("RAILWAY_PROJECT_ID", raising=False)
    run = _runner([_ADD, _VARS])
    info = deploy_db.provision("project-abcd1234", str(tmp_path), run=run)
    assert info["DATABASE_URL"] == "postgresql://u:p@h:5432/railway"
    assert info["service_id"] == "svc-123" and info["service"] == "Postgres-RNK8"
    assert info["provider"] == "railway-postgres"
    # add uses --json (NON-interactive); variables reads by the CAPTURED serviceId (never a guessed name)
    assert run.calls[0] == ["railway", "add", "--database", "postgres", "--json"]
    assert run.calls[1] == ["railway", "variables", "--service", "svc-123", "--json"]
    assert json.load(open(os.path.join(str(tmp_path), deploy_db.DEPLOY_DB_FILE)))["service_id"] == "svc-123"


def test_provision_is_noop_when_already_provisioned(tmp_path):
    deploy_db.write_file(str(tmp_path), {"DATABASE_URL": "x", "service_id": "s", "service": "Postgres-Z"})
    run = _runner([])                                   # must call NOTHING
    info = deploy_db.provision("p", str(tmp_path), run=run)
    assert info["DATABASE_URL"] == "x" and run.calls == []


def test_provision_resumes_from_persisted_service_without_re_adding(tmp_path):
    # A partial handle (add succeeded, URL not yet read) → reuse the service: read variables, NO new add.
    deploy_db.write_file(str(tmp_path), {"service_id": "svc-9", "service": "Postgres-Old",
                                         "provider": "railway-postgres", "project_id": "p"})
    run = _runner([_VARS])
    info = deploy_db.provision("p", str(tmp_path), run=run)
    assert info["DATABASE_URL"] == "postgresql://u:p@h:5432/railway" and info["service_id"] == "svc-9"
    assert run.calls[0] == ["railway", "variables", "--service", "svc-9", "--json"]   # NO add


def test_handle_persisted_before_variables_so_retry_never_re_adds(tmp_path, monkeypatch):
    monkeypatch.delenv("RAILWAY_PROJECT_ID", raising=False)
    # Attempt 1: add succeeds but variables returns no URL → raises. The serviceId MUST be persisted.
    run1 = _runner([_ADD, json.dumps({"PGHOST": "h"})])   # vars without DATABASE_URL
    with pytest.raises(RuntimeError):
        deploy_db.provision("p", str(tmp_path), run=run1)
    saved = json.load(open(os.path.join(str(tmp_path), deploy_db.DEPLOY_DB_FILE)))
    assert saved["service_id"] == "svc-123" and "DATABASE_URL" not in saved
    # Attempt 2: reuse the persisted service — NO second add (no orphan), just re-read variables.
    run2 = _runner([_VARS])
    info = deploy_db.provision("p", str(tmp_path), run=run2)
    assert info["DATABASE_URL"] == "postgresql://u:p@h:5432/railway"
    assert run2.calls[0][:2] == ["railway", "variables"]      # reused; no "railway add"


def test_provision_raises_when_add_returns_no_service_id(tmp_path, monkeypatch):
    monkeypatch.delenv("RAILWAY_PROJECT_ID", raising=False)
    run = _runner([json.dumps({"error": "nope"}), _VARS])
    with pytest.raises(RuntimeError):
        deploy_db.provision("p", str(tmp_path), run=run)


def test_provision_refuses_disallowed_railway_project(tmp_path, monkeypatch):
    # the console's own project must never host a run app's DB — guard raises BEFORE any CLI call
    from software_factory import env
    monkeypatch.setattr(env, "railway_project_allowed", lambda pid: False)
    monkeypatch.setenv("RAILWAY_PROJECT_ID", "some-other-proj")
    run = _runner([])
    with pytest.raises(RuntimeError):
        deploy_db.provision("project-q", str(tmp_path), run=run)
    assert run.calls == []                              # refused before any railway call


def test_write_file_roundtrip(tmp_path):
    p = deploy_db.write_file(str(tmp_path / "context"), {"DATABASE_URL": "x", "provider": "railway-postgres"})
    assert p.endswith("deploy-db.json")
    assert json.load(open(p))["DATABASE_URL"] == "x"
