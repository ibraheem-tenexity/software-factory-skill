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


def test_db_backend_is_always_postgres(monkeypatch):
    # Postgres everywhere — there is no sqlite backend.
    monkeypatch.delenv("SF_DB", raising=False)
    monkeypatch.setenv("SF_ENVIRONMENT", "dev")
    assert env.db_backend() == "postgres"
    monkeypatch.setenv("SF_ENVIRONMENT", "prod")
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
