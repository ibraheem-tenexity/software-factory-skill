"""Tests for the SF_STATE_DB_URL guardrail.

The factory stage_env_baseline scrubs DATABASE_URL/SF_DB from the stage child env to prevent
the factory DB from leaking to the customer's Railway service variables.  But the stage agent
calls `python3 -m software_factory.db ...` which needs a DB URL.

The fix: stage_env_baseline injects SF_STATE_DB_URL (the factory DB URL under a dedicated name),
and dbshim._db_url() reads SF_STATE_DB_URL first, falling back to DATABASE_URL.

These tests assert:
  (a) stage_env_baseline result contains SF_STATE_DB_URL and does NOT contain DATABASE_URL or SF_DB
  (b) dbshim._db_url() prefers SF_STATE_DB_URL over DATABASE_URL when both are set
  (c) dbshim._db_url() works when only SF_STATE_DB_URL is present (no DATABASE_URL in env)
  (d) dbshim._db_url() falls back to DATABASE_URL when SF_STATE_DB_URL is absent
  (e) dbshim._db_url() raises KeyError when neither is set (same as before)
"""
import os
import pytest

from software_factory import env as _env_mod
from software_factory import dbshim as _dbshim_mod


# ── (a) stage_env_baseline: SF_STATE_DB_URL present, DATABASE_URL/SF_DB absent ──────────

def test_stage_env_injects_sf_state_db_url(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://factory-db/prod")
    monkeypatch.delenv("SF_STATE_DB_URL", raising=False)
    result = _env_mod.stage_env_baseline()
    assert result.get("SF_STATE_DB_URL") == "postgresql://factory-db/prod"
    assert "DATABASE_URL" not in result


def test_stage_env_no_database_url_in_child(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://factory-db/prod")
    result = _env_mod.stage_env_baseline()
    assert "DATABASE_URL" not in result


def test_stage_env_no_sf_db_in_child(monkeypatch):
    monkeypatch.setenv("SF_DB", "postgresql://factory-db/prod")
    monkeypatch.setenv("DATABASE_URL", "postgresql://factory-db/prod")
    result = _env_mod.stage_env_baseline()
    assert "SF_DB" not in result


def test_stage_env_prefers_existing_sf_state_db_url(monkeypatch):
    # If SF_STATE_DB_URL is already set in the console env, it takes precedence over DATABASE_URL.
    monkeypatch.setenv("SF_STATE_DB_URL", "postgresql://dedicated-state-db/state")
    monkeypatch.setenv("DATABASE_URL", "postgresql://should-not-be-used/other")
    result = _env_mod.stage_env_baseline()
    assert result.get("SF_STATE_DB_URL") == "postgresql://dedicated-state-db/state"


def test_stage_env_no_sf_state_db_url_when_neither_set(monkeypatch):
    monkeypatch.delenv("SF_STATE_DB_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    result = _env_mod.stage_env_baseline()
    assert "SF_STATE_DB_URL" not in result
    assert "DATABASE_URL" not in result


def test_stage_env_provided_creds_preserved(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://factory-db/prod")
    result = _env_mod.stage_env_baseline(provided={"RAILWAY_TOKEN": "tok-123"})
    assert result["RAILWAY_TOKEN"] == "tok-123"
    assert "DATABASE_URL" not in result


# ── (b-e) dbshim._db_url() resolution order ──────────────────────────────────────────────

def test_dbshim_prefers_sf_state_db_url(monkeypatch):
    monkeypatch.setenv("SF_STATE_DB_URL", "postgresql://state-url/db")
    monkeypatch.setenv("DATABASE_URL", "postgresql://legacy-url/db")
    assert _dbshim_mod._db_url() == "postgresql://state-url/db"


def test_dbshim_falls_back_to_database_url(monkeypatch):
    monkeypatch.delenv("SF_STATE_DB_URL", raising=False)
    monkeypatch.setenv("DATABASE_URL", "postgresql://legacy-url/db")
    assert _dbshim_mod._db_url() == "postgresql://legacy-url/db"


def test_dbshim_works_with_only_sf_state_db_url(monkeypatch):
    monkeypatch.setenv("SF_STATE_DB_URL", "postgresql://state-only/db")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    # Should not raise — this is the stage subprocess scenario
    assert _dbshim_mod._db_url() == "postgresql://state-only/db"


def test_dbshim_raises_when_neither_set(monkeypatch):
    monkeypatch.delenv("SF_STATE_DB_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(KeyError):
        _dbshim_mod._db_url()


# ── round-trip: stage env → dbshim._db_url() reads SF_STATE_DB_URL ───────────────────────

def test_stage_env_url_is_readable_by_dbshim(monkeypatch):
    """The URL injected by stage_env_baseline is exactly what dbshim._db_url() will read
    in the stage subprocess (which has SF_STATE_DB_URL but no DATABASE_URL)."""
    monkeypatch.setenv("DATABASE_URL", "postgresql://factory/prod")
    monkeypatch.delenv("SF_STATE_DB_URL", raising=False)

    child_env = _env_mod.stage_env_baseline()
    # Simulate the stage subprocess's env: only has what stage_env_baseline gave it
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("SF_STATE_DB_URL", child_env["SF_STATE_DB_URL"])

    assert _dbshim_mod._db_url() == "postgresql://factory/prod"


# ── deployed-service boundary: SF_STATE_DB_URL NOT in customer/deploy context ────────────

def test_customer_provided_creds_cannot_contain_sf_state_db_url(monkeypatch):
    """SF_STATE_DB_URL is injected by stage_env_baseline at the base layer, NOT sourced from
    customer-declared creds (provided). The SKILL.md set_variables call uses only the
    provided creds + context/deploy-db.json vars — SF_STATE_DB_URL is in neither."""
    monkeypatch.setenv("DATABASE_URL", "postgresql://factory/prod")

    # Customer creds (vault-retrieved) never contain SF_STATE_DB_URL
    customer_creds = {"RAILWAY_TOKEN": "tok-abc", "NEXTAUTH_SECRET": "s3cr3t"}
    result = _env_mod.stage_env_baseline(provided=customer_creds)

    # Factory state-DB URL is present (factory-injected), but NOT in the customer cred set
    assert result.get("SF_STATE_DB_URL") == "postgresql://factory/prod"
    assert "SF_STATE_DB_URL" not in customer_creds  # sanity: not in the provided dict


def test_deploy_db_json_keys_have_no_sf_state_db_url():
    """deploy-db.json written by deploy_db.write_file contains only DATABASE_URL (customer
    app's Railway Postgres) and provider metadata — never SF_STATE_DB_URL.
    SKILL.md stage-3 reads this file for set_variables; SF_STATE_DB_URL never enters that path."""
    import json, os, tempfile
    from software_factory import deploy_db

    with tempfile.TemporaryDirectory() as ctx:
        info = {
            "DATABASE_URL": "postgresql://railway-postgres/customerdb",
            "provider": "railway-postgres",
            "service": "Postgres-1234",
            "service_id": "svc-abc",
            "project_id": "proj-xyz",
        }
        deploy_db.write_file(ctx, info)
        with open(os.path.join(ctx, deploy_db.DEPLOY_DB_FILE)) as f:
            written = json.load(f)

    assert "SF_STATE_DB_URL" not in written
    assert "DATABASE_URL" in written  # customer app's DB URL IS there
