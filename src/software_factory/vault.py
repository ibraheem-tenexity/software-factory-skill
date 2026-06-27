"""Supabase Vault helpers for BYOK key storage.

Stores customer-supplied API keys encrypted at rest in Supabase pgsodium Vault.
Our tables hold only vault UUIDs (references), never plaintext values.

vault_store   — encrypt and store a secret, returns UUID
vault_retrieve_many — decrypt a set of secrets by UUID, returns {name: value}
vault_delete_many   — delete stored secrets by UUID (called on archive/teardown)
"""
from __future__ import annotations

import os
from . import dbshim


def _conn():
    return dbshim._pg_connect(os.environ["DATABASE_URL"])


def vault_store(name: str, secret: str) -> str:
    """Store `secret` in Supabase Vault under `name`. Returns the vault UUID."""
    conn = _conn()
    try:
        with conn.transaction():
            cur = conn.cursor()
            cur.execute("SELECT vault.create_secret(%s, %s)", (secret, name))
            row = cur.fetchone()
            return str(list(row.values())[0]) if row else ""
    finally:
        conn.close()


def vault_retrieve_many(vault_ids: dict) -> dict:
    """Decrypt all secrets in `vault_ids` ({key_name: uuid}).
    Returns {key_name: plaintext_value} for found/decryptable entries."""
    if not vault_ids:
        return {}
    ids = list(vault_ids.values())
    conn = _conn()
    try:
        with conn.transaction():
            cur = conn.cursor()
            cur.execute(
                "SELECT id::text, decrypted_secret"
                " FROM vault.decrypted_secrets WHERE id = ANY(%s)",
                (ids,),
            )
            rows = cur.fetchall()
        uuid_to_name = {v: k for k, v in vault_ids.items()}
        return {
            uuid_to_name[str(r["id"])]: r["decrypted_secret"]
            for r in rows
            if r["decrypted_secret"] is not None and str(r["id"]) in uuid_to_name
        }
    finally:
        conn.close()


def vault_delete_many(uuids) -> None:
    """Delete stored secrets by UUID. Best-effort — ignores missing entries."""
    uuids = [u for u in uuids if u]
    if not uuids:
        return
    conn = _conn()
    try:
        with conn.transaction():
            cur = conn.cursor()
            cur.execute("DELETE FROM vault.secrets WHERE id = ANY(%s)", (uuids,))
    finally:
        conn.close()
