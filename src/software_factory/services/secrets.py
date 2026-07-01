"""Org secrets vault (SOF-45) — org-scoped secrets backed by Supabase Vault. Metadata (name, kind,
last4, vault_id pointer) lives in `org_secrets` via OrgSecretsRepository; the plaintext lives only
in Supabase Vault (pgsodium), resolved through vault.py's vault_store/vault_retrieve_many/
vault_delete_many. Replaces the earlier in-memory mock, which could list/create/rotate/delete but
never actually retrieve a stored value."""
import time

from software_factory.services.errors import Invalid, NotFound
from software_factory.vault import vault_store, vault_retrieve_many, vault_delete_many


class Secrets:
    def __init__(self, repo):
        self._repo = repo

    def list(self, org_id: str) -> list[dict]:
        return [dict(r) for r in self._repo.list_for(org_id)]

    def create(self, org_id: str, name: str, value: str, kind: str) -> dict:
        if self._repo.by_name(org_id, name):
            raise Invalid(f"secret '{name}' already exists")
        vault_id = vault_store(name, value)
        last4 = value[-4:]
        self._repo.insert(org_id, name, kind, vault_id, last4)
        return {"name": name, "kind": kind, "last4": last4, "used_by": 0, "updated_at": _now()}

    def rotate(self, org_id: str, name: str, value: str) -> dict:
        row = self._repo.by_name(org_id, name)
        if not row:
            raise NotFound(f"secret '{name}' not found")
        old_vault_id = row["vault_id"]
        new_vault_id = vault_store(name, value)
        last4 = value[-4:]
        self._repo.update_vault(org_id, name, new_vault_id, last4)
        vault_delete_many([old_vault_id])  # best-effort cleanup of the superseded ciphertext
        return {"name": name, "kind": row["kind"], "last4": last4, "used_by": row["used_by"],
                "updated_at": _now()}

    def delete(self, org_id: str, name: str) -> None:
        row = self._repo.by_name(org_id, name)
        if not row:
            raise NotFound(f"secret '{name}' not found")
        self._repo.delete(org_id, name)
        vault_delete_many([row["vault_id"]])

    def get_ref(self, org_id: str, name: str) -> dict:
        row = self._repo.by_name(org_id, name)
        if not row:
            raise NotFound(f"secret '{name}' not found")
        return {"name": name, "kind": row["kind"]}

    def get_value(self, org_id: str, name: str) -> str:
        """Real retrieval — the mock never had this. For a consumer that needs the actual secret
        value (e.g. a build stage using an org-level API key), not just its display ref."""
        row = self._repo.by_name(org_id, name)
        if not row:
            raise NotFound(f"secret '{name}' not found")
        values = vault_retrieve_many({name: row["vault_id"]})
        if name not in values:
            raise NotFound(f"secret '{name}' could not be decrypted")
        return values[name]


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
