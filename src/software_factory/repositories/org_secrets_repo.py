"""Pure CRUD for `org_secrets` (SQLAlchemy Core). Global table, org-scoped — every method takes
org_id explicitly. Metadata only; the plaintext lives in Supabase Vault (see `vault.py`)."""
from __future__ import annotations

from sqlalchemy import select, insert, update, delete, func

from ..models import org_secrets

_ISO_FMT = 'YYYY-MM-DD"T"HH24:MI:SS"Z"'   # matches the old mock's time.strftime("%Y-%m-%dT%H:%M:%SZ", ...)
_COLS = (org_secrets.c.name, org_secrets.c.kind, org_secrets.c.last4, org_secrets.c.used_by,
          func.to_char(org_secrets.c.updated_at, _ISO_FMT).label("updated_at"))


class OrgSecretsRepository:
    def __init__(self, exec_):
        self._x = exec_

    def list_for(self, org_id) -> list:
        return self._x.fetchall(select(*_COLS)
                                .where(org_secrets.c.org_id == org_id)
                                .order_by(org_secrets.c.created_at))

    def by_name(self, org_id, name):
        return self._x.fetchone(select(org_secrets.c.name, org_secrets.c.kind,
                                       org_secrets.c.vault_id, org_secrets.c.last4,
                                       org_secrets.c.used_by)
                                .where(org_secrets.c.org_id == org_id, org_secrets.c.name == name))

    def insert(self, org_id, name, kind, vault_id, last4) -> None:
        self._x.execute(insert(org_secrets).values(org_id=org_id, name=name, kind=kind,
                                                    vault_id=vault_id, last4=last4))

    def update_vault(self, org_id, name, vault_id, last4) -> None:
        self._x.execute(update(org_secrets)
                        .where(org_secrets.c.org_id == org_id, org_secrets.c.name == name)
                        .values(vault_id=vault_id, last4=last4, updated_at=func.now()))

    def delete(self, org_id, name) -> None:
        self._x.execute(delete(org_secrets)
                        .where(org_secrets.c.org_id == org_id, org_secrets.c.name == name))
