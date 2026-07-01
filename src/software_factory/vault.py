"""Supabase Vault helpers for BYOK key storage.

Stores customer-supplied API keys encrypted at rest in Supabase pgsodium Vault.
Our tables hold only vault UUIDs (references), never plaintext values.

vault_store   — encrypt and store a secret, returns UUID
vault_retrieve_many — decrypt a set of secrets by UUID, returns {name: value}
vault_delete_many   — delete stored secrets by UUID (called on archive/teardown)

DATA ACCESS: the SQL lives in `repositories.vault.VaultRepository` (SQLAlchemy Core `text()` —
the Vault extension's own internal objects have no `Table` definition in models.py; we don't own
that schema).
"""
from __future__ import annotations

from .repositories._exec import GlobalExec
from .repositories.vault import VaultRepository

_repo = VaultRepository(GlobalExec())


def vault_store(name: str, secret: str) -> str:
    """Store `secret` in Supabase Vault under `name`. Returns the vault UUID."""
    row = _repo.create_secret(secret, name)
    return str(list(row.values())[0]) if row else ""


def vault_retrieve_many(vault_ids: dict) -> dict:
    """Decrypt all secrets in `vault_ids` ({key_name: uuid}).
    Returns {key_name: plaintext_value} for found/decryptable entries."""
    if not vault_ids:
        return {}
    ids = list(vault_ids.values())
    rows = _repo.decrypted_secrets(ids)
    uuid_to_name = {v: k for k, v in vault_ids.items()}
    return {
        uuid_to_name[str(r["id"])]: r["decrypted_secret"]
        for r in rows
        if r["decrypted_secret"] is not None and str(r["id"]) in uuid_to_name
    }


def vault_delete_many(uuids) -> None:
    """Delete stored secrets by UUID. Best-effort — ignores missing entries."""
    uuids = [u for u in uuids if u]
    if not uuids:
        return
    _repo.delete_secrets(uuids)
