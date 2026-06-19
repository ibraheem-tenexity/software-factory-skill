"""dbshim: the Postgres connection seam (Supabase transaction pooler on 6543). Postgres everywhere
— there is no sqlite backend. The pg path is tested against a FAKE psycopg connection (no live DB)."""
import os

import pytest

from software_factory import dbshim


# ---------- pg behaviour (fake connection; no live pg) ----------

class FakeCursor:
    def __init__(self, log):
        self.log = log
        self.rowcount = 1
        self._rows = []

    def execute(self, sql, params=None):
        self.log.append((sql.strip(), tuple(params or ())))
        if "RETURNING id" in sql:
            self._rows = [{"id": 7}]
        return self

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return self._rows

    def close(self):
        pass


class FakeTx:
    def __init__(self, conn): self.conn = conn
    def __enter__(self): self.conn.tx_count += 1; return self
    def __exit__(self, *a): return False


class FakePgConn:
    def __init__(self):
        self.statements = []
        self.tx_count = 0
        self.closed = False

    def cursor(self):
        return FakeCursor(self.statements)

    def transaction(self):
        return FakeTx(self)

    def commit(self):
        pass

    def close(self):
        self.closed = True


@pytest.fixture()
def pg(monkeypatch, tmp_path):
    monkeypatch.setenv("SF_ENVIRONMENT", "test")
    monkeypatch.setenv("SF_DB", "postgres")
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@pooler:6543/postgres")
    fake = FakePgConn()
    monkeypatch.setattr(dbshim, "_pg_connect", lambda url: fake)
    conn = dbshim.connect(str(tmp_path / "run-abc12345" / "run.db"))
    return conn, fake


def test_pg_runs_against_public_no_schema_per_run(pg):
    # Flat schema: there is no per-run schema and no search_path — statements run against public.
    conn, fake = pg
    conn.execute("SELECT * FROM phases WHERE name = ?", ("build",))
    sqls = [s for s, _ in fake.statements]
    assert not any("SET LOCAL search_path" in s for s in sqls)     # schema-per-run is gone
    assert not any("CREATE SCHEMA" in s for s in sqls)
    assert any("FROM phases WHERE name = %s" in s for s in sqls)    # ?->%s still translated
    assert fake.tx_count >= 1                                       # every stmt inside a tx


def test_pg_lastrowid_via_returning(pg):
    conn, fake = pg
    cur = conn.execute("INSERT INTO tickets (title) VALUES (?)", ("t",))
    assert cur.lastrowid == 7
    assert any("RETURNING id" in s for s, _ in fake.statements)


def test_pg_executescript_runs_each_statement(pg):
    conn, fake = pg
    conn.executescript("UPDATE tickets SET status='done' WHERE id=?; DELETE FROM phases WHERE id=?;")
    sqls = [s for s, _ in fake.statements]
    assert any(s.startswith("UPDATE tickets") for s in sqls)
    assert any(s.startswith("DELETE FROM phases") for s in sqls)


def test_pg_write_retries_then_raises(monkeypatch, tmp_path):
    monkeypatch.setenv("SF_ENVIRONMENT", "test")
    monkeypatch.setenv("SF_DB", "postgres")
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@pooler:6543/postgres")
    attempts = []

    class Boom(FakePgConn):
        def transaction(self):
            attempts.append(1)
            raise ConnectionError("pooler hiccup")

    monkeypatch.setattr(dbshim, "_pg_connect", lambda url: Boom())
    monkeypatch.setattr(dbshim, "_RETRY_SLEEP", 0)
    conn = dbshim.connect(str(tmp_path / "run-r" / "run.db"))
    with pytest.raises(ConnectionError):
        conn.execute("INSERT INTO phases (name) VALUES (?)", ("x",))
    assert len(attempts) == 3                                          # 3 tries, then surface


def test_pg_connect_creates_no_schema_or_registry(monkeypatch, tmp_path):
    # Flat schema: connecting performs NO side effects — no CREATE SCHEMA, no sf_runs registry
    # write (those were the schema-per-run machinery, now retired). The first statement is the
    # caller's own; nothing is injected ahead of it.
    monkeypatch.setenv("SF_ENVIRONMENT", "test")
    monkeypatch.setenv("SF_DB", "postgres")
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@x:6543/postgres")
    fake = FakePgConn()
    monkeypatch.setattr(dbshim, "_pg_connect", lambda url: fake)
    conn = dbshim.connect(str(tmp_path / "run-abc12345" / "run.db"))
    assert fake.statements == []                                    # connect() is side-effect free
    conn.execute("SELECT 1")
    sqls = [s for s, _ in fake.statements]
    assert not any("CREATE SCHEMA" in s for s in sqls)
    assert not any("sf_run" in s for s in sqls)


def test_registry_runs_reads_runstate(monkeypatch):
    # Run discovery in flat mode comes from public.runstate (the sf_runs registry is retired).
    monkeypatch.setenv("SF_ENVIRONMENT", "test")
    monkeypatch.setenv("SF_DB", "postgres")
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@x:6543/postgres")

    class RunstateCursor(FakeCursor):
        def execute(self, sql, params=None):
            self.log.append((sql.strip(), tuple(params or ())))
            if "FROM public.runstate" in sql:
                self._rows = [{"run_id": "run-aaaaaaaa"}, {"run_id": "run-bbbbbbbb"}]
            return self

    class RunstateConn(FakePgConn):
        def cursor(self):
            return RunstateCursor(self.statements)

    monkeypatch.setattr(dbshim, "_pg_connect", lambda url: RunstateConn())
    runs = dbshim.registry_runs()
    assert sorted(r["run_id"] for r in runs) == ["run-aaaaaaaa", "run-bbbbbbbb"]


