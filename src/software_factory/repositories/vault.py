"""Pure CRUD wrapper for the Supabase Vault extension (`vault.create_secret`, `vault.decrypted_secrets`,
`vault.secrets`) via SQLAlchemy Core `text()`. These are the Vault EXTENSION's own internal objects,
not app tables we own — there's no `Table` definition for them in `models.py` (and shouldn't be; we
don't control that schema). `text()` is the correct Core construct for vendor/extension SQL that
doesn't map to one of our tables, while still going through the same compile/exec lanes as everything
else (named bind params instead of positional, since `text()` doesn't support `%s` positionally)."""
from __future__ import annotations

from sqlalchemy import text


class VaultRepository:
    def __init__(self, exec_):
        self._x = exec_

    def create_secret(self, secret: str, name: str):
        return self._x.fetchone(text("SELECT vault.create_secret(:secret, :name)")
                                .bindparams(secret=secret, name=name))

    def decrypted_secrets(self, ids: list):
        return self._x.fetchall(
            text("SELECT id::text AS id, decrypted_secret FROM vault.decrypted_secrets "
                "WHERE id = ANY(:ids)").bindparams(ids=ids))

    def delete_secrets(self, uuids: list) -> None:
        self._x.execute(text("DELETE FROM vault.secrets WHERE id = ANY(:uuids)").bindparams(uuids=uuids))
