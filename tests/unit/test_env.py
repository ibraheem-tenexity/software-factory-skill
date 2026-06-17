"""Tests for the environment-tier / isolation module."""
import os

import pytest

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


def test_db_backend_defaults_to_sqlite_in_dev(monkeypatch):
    monkeypatch.delenv("SF_DB", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("SF_ENVIRONMENT", "dev")
    assert env.db_backend() == "sqlite"


def test_db_backend_defaults_to_postgres_in_prod_with_url(monkeypatch):
    monkeypatch.setenv("SF_ENVIRONMENT", "prod")
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@x:6543/postgres")
    assert env.db_backend() == "postgres"


def test_postgres_allowed_in_test(monkeypatch):
    monkeypatch.setenv("SF_ENVIRONMENT", "test")
    monkeypatch.setenv("SF_DB", "postgres")
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@x:6543/postgres")
    assert env.db_backend() == "postgres"


def test_postgres_refused_in_dev(monkeypatch):
    monkeypatch.setenv("SF_ENVIRONMENT", "dev")
    monkeypatch.setenv("SF_DB", "postgres")
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@x:6543/postgres")
    with pytest.raises(RuntimeError):
        env.db_backend()


def test_postgres_allowed_in_dev_with_override(monkeypatch):
    monkeypatch.setenv("SF_ENVIRONMENT", "dev")
    monkeypatch.setenv("SF_DB", "postgres")
    monkeypatch.setenv("SF_ALLOW_DEV_PG", "1")
    assert env.db_backend() == "postgres"


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
