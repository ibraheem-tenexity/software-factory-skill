"""Pure (no-DB) checks for OrgSecretsRepository — Core statements compile through the same
to_sql pipeline as VaultRepository's text() constructs (see test_vault_repo_compile.py)."""
from software_factory.repositories._compile import to_sql
from software_factory.repositories.org_secrets import OrgSecretsRepository


class FakeExec:
    def __init__(self):
        self.sql = None
        self.params = None

    def _cap(self, stmt):
        self.sql, self.params = to_sql(stmt)

    def fetchone(self, stmt):
        self._cap(stmt); return None

    def fetchall(self, stmt):
        self._cap(stmt); return []

    def execute(self, stmt):
        self._cap(stmt)


def test_list_for_scopes_by_org_and_formats_updated_at():
    fx = FakeExec()
    OrgSecretsRepository(fx).list_for("org-1")
    assert "WHERE org_secrets.org_id = %s" in fx.sql
    assert "to_char(org_secrets.updated_at" in fx.sql   # ISO string, not a raw timestamp/epoch
    assert fx.params[-1] == "org-1"


def test_by_name_scopes_by_org_and_name():
    fx = FakeExec()
    OrgSecretsRepository(fx).by_name("org-1", "MY_KEY")
    assert "org_secrets.org_id = %s AND org_secrets.name = %s" in fx.sql
    assert fx.params == ("org-1", "MY_KEY")
    assert "vault_id" in fx.sql   # by_name must expose vault_id — callers resolve/rotate/delete on it


def test_insert_writes_all_metadata_columns_never_the_plaintext():
    fx = FakeExec()
    OrgSecretsRepository(fx).insert("org-1", "MY_KEY", "api_key", "vault-uuid-1", "1234")
    assert fx.sql.startswith("INSERT INTO org_secrets")
    assert fx.params == ("org-1", "MY_KEY", "api_key", "vault-uuid-1", "1234")


def test_update_vault_scoped_by_org_and_name():
    fx = FakeExec()
    OrgSecretsRepository(fx).update_vault("org-1", "MY_KEY", "vault-uuid-2", "5678")
    assert fx.sql.startswith("UPDATE org_secrets")
    assert "org_secrets.org_id = %s AND org_secrets.name = %s" in fx.sql
    assert fx.params == ("vault-uuid-2", "5678", "org-1", "MY_KEY")


def test_delete_scoped_by_org_and_name():
    fx = FakeExec()
    OrgSecretsRepository(fx).delete("org-1", "MY_KEY")
    assert fx.sql == ("DELETE FROM org_secrets WHERE org_secrets.org_id = %s "
                      "AND org_secrets.name = %s")
    assert fx.params == ("org-1", "MY_KEY")
