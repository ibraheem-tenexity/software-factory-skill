"""Pure (no-DB) checks for VaultRepository — text() constructs compile through the same to_sql
pipeline as Table-based Core statements, with the ANY(list) array-bind semantics preserved (a single
bound param, not IN-expansion)."""
from software_factory.repositories._compile import to_sql
from software_factory.repositories.vault import VaultRepository


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


def test_create_secret_positional_params():
    fx = FakeExec()
    VaultRepository(fx).create_secret("s3cr3t", "MY_KEY")
    assert fx.sql == "SELECT vault.create_secret(%s, %s)"
    assert fx.params == ("s3cr3t", "MY_KEY")


def test_decrypted_secrets_any_array_not_expanded():
    fx = FakeExec()
    VaultRepository(fx).decrypted_secrets(["id-1", "id-2"])
    assert "ANY(%s)" in fx.sql
    assert fx.params == (["id-1", "id-2"],)   # ONE param: a list, not two expanded %s


def test_delete_secrets_any_array():
    fx = FakeExec()
    VaultRepository(fx).delete_secrets(["id-1"])
    assert fx.sql == "DELETE FROM vault.secrets WHERE id = ANY(%s)"
    assert fx.params == (["id-1"],)
