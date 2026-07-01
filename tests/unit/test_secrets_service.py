"""Unit tests for services/secrets.py's Secrets — pure, against a fake repo + mocked vault.py
helpers (no DB, no real Supabase Vault). Route-level behavior (auth, status codes) is covered by
test_org_secrets_routes.py; these tests cover the service's own create/rotate/delete/get_value
logic and its vault_store/vault_retrieve_many/vault_delete_many call shape."""
from unittest.mock import MagicMock, patch

import pytest

from software_factory.services.errors import Invalid, NotFound
from software_factory.services.secrets import Secrets


class FakeRepo:
    def __init__(self):
        self._rows = {}  # (org_id, name) -> {kind, vault_id, last4, used_by}

    def list_for(self, org_id):
        return [{"name": name, "kind": row["kind"], "last4": row["last4"], "used_by": row["used_by"]}
                for (oid, name), row in self._rows.items() if oid == org_id]

    def by_name(self, org_id, name):
        row = self._rows.get((org_id, name))
        return {"name": name, **row} if row else None

    def insert(self, org_id, name, kind, vault_id, last4):
        self._rows[(org_id, name)] = {"kind": kind, "vault_id": vault_id, "last4": last4,
                                       "used_by": 0}

    def update_vault(self, org_id, name, vault_id, last4):
        self._rows[(org_id, name)]["vault_id"] = vault_id
        self._rows[(org_id, name)]["last4"] = last4

    def delete(self, org_id, name):
        del self._rows[(org_id, name)]


@pytest.fixture()
def secrets():
    return Secrets(FakeRepo())


def test_create_stores_via_vault_and_never_keeps_plaintext(secrets):
    with patch("software_factory.services.secrets.vault_store", return_value="vault-uuid-1") as vs:
        result = secrets.create("org-1", "MY_KEY", "supersecret1234", "api_key")
    vs.assert_called_once_with("MY_KEY", "supersecret1234")
    assert result["last4"] == "1234"
    assert "supersecret" not in str(result)
    assert "vault_id" not in result   # never surfaced to callers


def test_create_duplicate_raises_invalid(secrets):
    with patch("software_factory.services.secrets.vault_store", return_value="vault-uuid-1"):
        secrets.create("org-1", "DUPE", "val1", "api_key")
        with pytest.raises(Invalid):
            secrets.create("org-1", "DUPE", "val2", "api_key")


def test_rotate_stores_new_value_and_deletes_old_vault_entry(secrets):
    with patch("software_factory.services.secrets.vault_store", return_value="vault-uuid-1"):
        secrets.create("org-1", "MY_KEY", "oldvalue0000", "api_key")
    with patch("software_factory.services.secrets.vault_store",
              return_value="vault-uuid-2") as vs, \
         patch("software_factory.services.secrets.vault_delete_many") as vd:
        result = secrets.rotate("org-1", "MY_KEY", "newvalueABCD")
    vs.assert_called_once_with("MY_KEY", "newvalueABCD")
    vd.assert_called_once_with(["vault-uuid-1"])   # old ciphertext cleaned up
    assert result["last4"] == "ABCD"


def test_rotate_unknown_raises_not_found(secrets):
    with pytest.raises(NotFound):
        secrets.rotate("org-1", "GHOST", "x")


def test_delete_removes_row_and_vault_entry(secrets):
    with patch("software_factory.services.secrets.vault_store", return_value="vault-uuid-1"):
        secrets.create("org-1", "TO_DEL", "abcd1234", "api_key")
    with patch("software_factory.services.secrets.vault_delete_many") as vd:
        secrets.delete("org-1", "TO_DEL")
    vd.assert_called_once_with(["vault-uuid-1"])
    assert secrets.list("org-1") == []


def test_delete_unknown_raises_not_found(secrets):
    with pytest.raises(NotFound):
        secrets.delete("org-1", "GHOST")


def test_get_ref_never_returns_the_value(secrets):
    with patch("software_factory.services.secrets.vault_store", return_value="vault-uuid-1"):
        secrets.create("org-1", "DB_PASS", "p@ssword99", "password")
    ref = secrets.get_ref("org-1", "DB_PASS")
    assert ref == {"name": "DB_PASS", "kind": "password"}


def test_get_value_resolves_the_real_secret_via_vault(secrets):
    # The mock this replaces could never do this at all — it's the actual capability gap SOF-45 closes.
    with patch("software_factory.services.secrets.vault_store", return_value="vault-uuid-1"):
        secrets.create("org-1", "API_KEY", "sk-real-value", "api_key")
    with patch("software_factory.services.secrets.vault_retrieve_many",
              return_value={"API_KEY": "sk-real-value"}) as vr:
        value = secrets.get_value("org-1", "API_KEY")
    vr.assert_called_once_with({"API_KEY": "vault-uuid-1"})
    assert value == "sk-real-value"


def test_get_value_undecryptable_raises_not_found(secrets):
    with patch("software_factory.services.secrets.vault_store", return_value="vault-uuid-1"):
        secrets.create("org-1", "API_KEY", "sk-real-value", "api_key")
    with patch("software_factory.services.secrets.vault_retrieve_many", return_value={}):
        with pytest.raises(NotFound):
            secrets.get_value("org-1", "API_KEY")


def test_get_value_unknown_raises_not_found(secrets):
    with pytest.raises(NotFound):
        secrets.get_value("org-1", "GHOST")
