"""Unit tests for vault.py — Supabase Vault BYOK key storage helpers.

The SQL surface itself (exact statement text, ANY-array binding) is covered by
test_vault_repo_compile.py against the real VaultRepository/FakeExec pipeline. These tests only
check vault.py's own wrapper logic (uuid<->name mapping, empty-input short-circuits, null-decrypt
filtering) against a mocked `_repo` — vault.py composes `VaultRepository(GlobalExec())` as its
module-level `_repo`, not a raw connection, so there's nothing to open/patch a connection for.
"""
from unittest.mock import MagicMock, patch

from software_factory import vault


def test_vault_store_calls_create_secret_and_returns_uuid():
    # Storing a secret must call the repo's create_secret(value, name) and return the UUID.
    fake_repo = MagicMock()
    fake_repo.create_secret.return_value = {"create_secret": "uuid-aaa"}
    with patch.object(vault, "_repo", fake_repo):
        result = vault.vault_store("byok-proj-RAILWAY_TOKEN", "tok_secret")
    assert result == "uuid-aaa"
    fake_repo.create_secret.assert_called_once_with("tok_secret", "byok-proj-RAILWAY_TOKEN")


def test_vault_retrieve_many_returns_name_to_value_mapping():
    # Retrieval must query the repo's decrypted_secrets and map uuid->name->value.
    vault_ids = {"RAILWAY_TOKEN": "uuid-111", "OPENROUTER_API_KEY": "uuid-222"}
    fake_repo = MagicMock()
    fake_repo.decrypted_secrets.return_value = [
        {"id": "uuid-111", "decrypted_secret": "tok_prod"},
        {"id": "uuid-222", "decrypted_secret": "sk-or-prod"},
    ]
    with patch.object(vault, "_repo", fake_repo):
        result = vault.vault_retrieve_many(vault_ids)
    assert result == {"RAILWAY_TOKEN": "tok_prod", "OPENROUTER_API_KEY": "sk-or-prod"}
    fake_repo.decrypted_secrets.assert_called_once_with(["uuid-111", "uuid-222"])


def test_vault_retrieve_many_empty_input_makes_no_db_call():
    # Empty vault_ids must return {} immediately without touching the repo.
    fake_repo = MagicMock()
    with patch.object(vault, "_repo", fake_repo):
        result = vault.vault_retrieve_many({})
    assert result == {}
    fake_repo.decrypted_secrets.assert_not_called()


def test_vault_retrieve_many_skips_null_decrypted_values():
    # Rows with NULL decrypted_secret (Vault couldn't decrypt) must not appear in output.
    vault_ids = {"RAILWAY_TOKEN": "uuid-111", "OPENROUTER_API_KEY": "uuid-222"}
    fake_repo = MagicMock()
    fake_repo.decrypted_secrets.return_value = [
        {"id": "uuid-111", "decrypted_secret": "tok_prod"},
        {"id": "uuid-222", "decrypted_secret": None},
    ]
    with patch.object(vault, "_repo", fake_repo):
        result = vault.vault_retrieve_many(vault_ids)
    assert result == {"RAILWAY_TOKEN": "tok_prod"}
    assert "OPENROUTER_API_KEY" not in result


def test_vault_delete_many_uses_single_delete_call():
    # Our pgsodium/Vault setup does not expose vault.delete_secret(), so the repo does a single
    # DELETE FROM vault.secrets WHERE id = ANY(...) for all UUIDs at once.
    fake_repo = MagicMock()
    with patch.object(vault, "_repo", fake_repo):
        vault.vault_delete_many(["uuid-aaa", "uuid-bbb"])
    fake_repo.delete_secrets.assert_called_once_with(["uuid-aaa", "uuid-bbb"])


def test_vault_delete_many_empty_list_makes_no_db_call():
    # Empty UUID list must return without touching the repo.
    fake_repo = MagicMock()
    with patch.object(vault, "_repo", fake_repo):
        vault.vault_delete_many([])
    fake_repo.delete_secrets.assert_not_called()


def test_vault_delete_many_filters_empty_strings():
    # Falsy UUIDs must be silently skipped; the remaining UUIDs are passed in one call.
    fake_repo = MagicMock()
    with patch.object(vault, "_repo", fake_repo):
        vault.vault_delete_many(["", None, "uuid-real"])
    fake_repo.delete_secrets.assert_called_once_with(["uuid-real"])
