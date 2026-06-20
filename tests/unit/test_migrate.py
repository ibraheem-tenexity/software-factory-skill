"""Migration entrypoint. With the flat schema Alembic owns every table directly (no per-project
fan-out); the live `alembic upgrade head` is exercised during the cutover, not in unit tests."""
from software_factory import migrate


def test_migrate_run_is_noop_without_a_database_url(monkeypatch, capsys):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert migrate.run() == 0
    assert "skipping" in capsys.readouterr().out.lower()
