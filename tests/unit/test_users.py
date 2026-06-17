"""User directory + roles (sqlite backend; pg path is the same SQL via dbshim)."""
import pytest

from software_factory import users


@pytest.fixture()
def store(tmp_path, monkeypatch):
    monkeypatch.delenv("SF_DB", raising=False)            # sqlite
    monkeypatch.setenv("SF_ADMIN_EMAILS", "boss@t.ai")
    return users.UserStore(str(tmp_path / "users.db"))


def test_env_admins_seeded(store):
    assert store.get_role("boss@t.ai") == "admin"
    assert store.is_member("boss@t.ai")


def test_upsert_and_role(store):
    store.upsert("m@t.ai", "member", "boss@t.ai")
    assert store.get_role("m@t.ai") == "member"
    assert store.is_member("m@t.ai")
    store.upsert("m@t.ai", "admin", "boss@t.ai")           # promote
    assert store.get_role("m@t.ai") == "admin"


def test_case_insensitive(store):
    store.upsert("Mixed@T.ai", "member")
    assert store.get_role("mixed@t.ai") == "member"
    assert store.is_member("MIXED@T.AI")


def test_remove_member_but_not_env_admin(store):
    store.upsert("m@t.ai", "member")
    store.remove("m@t.ai")
    assert not store.is_member("m@t.ai")
    store.remove("boss@t.ai")                              # env-bootstrap admin: protected
    assert store.get_role("boss@t.ai") == "admin"


def test_unknown_email(store):
    assert store.get_role("nobody@t.ai") is None
    assert not store.is_member("nobody@t.ai")
    assert store.get_role("") is None
