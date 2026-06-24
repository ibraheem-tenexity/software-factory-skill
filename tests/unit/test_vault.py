"""Unit tests for vault.py — Supabase Vault BYOK key storage helpers.

All tests use an injected mock connection so no real Supabase Vault is required.
We assert the exact SQL surface called (vault.create_secret / vault.decrypted_secrets /
vault.delete_secret) and the correct UUID-to-name mapping.
"""
from unittest.mock import MagicMock, patch


def _mock_conn(rows=None, scalar=None):
    """Build a minimal psycopg3-like mock connection."""
    cur = MagicMock()
    cur.fetchone.return_value = rows[0] if rows else None
    cur.fetchall.return_value = rows or []
    conn = MagicMock()
    conn.cursor.return_value = cur
    conn.transaction.return_value.__enter__ = lambda s: s
    conn.transaction.return_value.__exit__ = MagicMock(return_value=False)
    return conn, cur


def test_vault_store_calls_create_secret_and_returns_uuid(monkeypatch):
    # Storing a secret must call vault.create_secret(value, name) and return the UUID.
    conn, cur = _mock_conn()
    cur.fetchone.return_value = {"create_secret": "uuid-aaa"}
    monkeypatch.setenv("DATABASE_URL", "postgresql://x:x@localhost/x")
    with patch("software_factory.vault._conn", return_value=conn):
        from software_factory import vault
        result = vault.vault_store("byok-proj-RAILWAY_TOKEN", "tok_secret")
    assert result == "uuid-aaa"
    call_sql = cur.execute.call_args[0][0]
    assert "vault.create_secret" in call_sql
    call_args = cur.execute.call_args[0][1]
    assert call_args == ("tok_secret", "byok-proj-RAILWAY_TOKEN")


def test_vault_retrieve_many_returns_name_to_value_mapping(monkeypatch):
    # Retrieval must query vault.decrypted_secrets and map uuid→name→value.
    vault_ids = {"RAILWAY_TOKEN": "uuid-111", "OPENROUTER_API_KEY": "uuid-222"}
    rows = [
        {"id": "uuid-111", "decrypted_secret": "tok_prod"},
        {"id": "uuid-222", "decrypted_secret": "sk-or-prod"},
    ]
    conn, cur = _mock_conn(rows=rows)
    monkeypatch.setenv("DATABASE_URL", "postgresql://x:x@localhost/x")
    with patch("software_factory.vault._conn", return_value=conn):
        from software_factory import vault
        result = vault.vault_retrieve_many(vault_ids)
    assert result == {"RAILWAY_TOKEN": "tok_prod", "OPENROUTER_API_KEY": "sk-or-prod"}
    call_sql = cur.execute.call_args[0][0]
    assert "vault.decrypted_secrets" in call_sql


def test_vault_retrieve_many_empty_input_makes_no_db_call(monkeypatch):
    # Empty vault_ids must return {} immediately without touching the DB.
    monkeypatch.setenv("DATABASE_URL", "postgresql://x:x@localhost/x")
    with patch("software_factory.vault._conn") as mock_conn_fn:
        from software_factory import vault
        result = vault.vault_retrieve_many({})
    assert result == {}
    mock_conn_fn.assert_not_called()


def test_vault_retrieve_many_skips_null_decrypted_values(monkeypatch):
    # Rows with NULL decrypted_secret (Vault couldn't decrypt) must not appear in output.
    vault_ids = {"RAILWAY_TOKEN": "uuid-111", "OPENROUTER_API_KEY": "uuid-222"}
    rows = [
        {"id": "uuid-111", "decrypted_secret": "tok_prod"},
        {"id": "uuid-222", "decrypted_secret": None},
    ]
    conn, cur = _mock_conn(rows=rows)
    monkeypatch.setenv("DATABASE_URL", "postgresql://x:x@localhost/x")
    with patch("software_factory.vault._conn", return_value=conn):
        from software_factory import vault
        result = vault.vault_retrieve_many(vault_ids)
    assert result == {"RAILWAY_TOKEN": "tok_prod"}
    assert "OPENROUTER_API_KEY" not in result


def test_vault_delete_many_calls_delete_for_each_uuid(monkeypatch):
    # Each UUID must get its own vault.delete_secret call.
    conn, cur = _mock_conn()
    monkeypatch.setenv("DATABASE_URL", "postgresql://x:x@localhost/x")
    with patch("software_factory.vault._conn", return_value=conn):
        from software_factory import vault
        vault.vault_delete_many(["uuid-aaa", "uuid-bbb"])
    calls = [c[0][0] for c in cur.execute.call_args_list]
    assert all("vault.delete_secret" in sql for sql in calls)
    assert len(calls) == 2


def test_vault_delete_many_empty_list_makes_no_db_call(monkeypatch):
    # Empty UUID list must return without opening a connection.
    monkeypatch.setenv("DATABASE_URL", "postgresql://x:x@localhost/x")
    with patch("software_factory.vault._conn") as mock_conn_fn:
        from software_factory import vault
        vault.vault_delete_many([])
    mock_conn_fn.assert_not_called()


def test_vault_delete_many_filters_empty_strings(monkeypatch):
    # Falsy UUIDs must be silently skipped.
    conn, cur = _mock_conn()
    monkeypatch.setenv("DATABASE_URL", "postgresql://x:x@localhost/x")
    with patch("software_factory.vault._conn", return_value=conn):
        from software_factory import vault
        vault.vault_delete_many(["", None, "uuid-real"])
    calls = [c[0][0] for c in cur.execute.call_args_list]
    assert len(calls) == 1
