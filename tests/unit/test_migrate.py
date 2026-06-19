"""Migration framework: per-run version registry logic + the sqlite/dev no-op guard.
(The live Postgres path — alembic upgrade + fan-out — is exercised during the cutover, not in
hermetic unit tests.)"""
from software_factory import schema_ddl, migrate


def test_per_run_head_is_last_revision():
    assert schema_ddl.per_run_head() == schema_ddl.PER_RUN_REVISIONS[-1][0]
    assert schema_ddl.per_run_head() == "0001"


def test_pending_from_none_is_all_revisions():
    assert schema_ddl.pending_per_run(None) == schema_ddl.PER_RUN_REVISIONS


def test_pending_from_head_is_empty():
    assert schema_ddl.pending_per_run(schema_ddl.per_run_head()) == []


def test_pending_from_unknown_version_is_all():
    # a schema with a version we don't recognize → re-evaluate from the start (defensive)
    assert schema_ddl.pending_per_run("9999") == schema_ddl.PER_RUN_REVISIONS


def test_migrate_run_is_noop_without_postgres(monkeypatch, capsys):
    monkeypatch.delenv("SF_DB", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert migrate.run() == 0
    assert "skipping" in capsys.readouterr().out.lower()


def test_migrate_run_is_noop_when_db_unset_even_with_url(monkeypatch, capsys):
    # SF_DB not 'postgres' → no-op regardless of DATABASE_URL (dev safety)
    monkeypatch.setenv("SF_DB", "sqlite")
    monkeypatch.setenv("DATABASE_URL", "postgresql://x")
    assert migrate.run() == 0
    assert "skipping" in capsys.readouterr().out.lower()
