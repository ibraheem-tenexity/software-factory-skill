"""User directory + roles + organizations (Postgres via dbshim)."""
import pytest

from software_factory import users


@pytest.fixture()
def store(tmp_path, monkeypatch):
    monkeypatch.setenv("SF_ADMIN_EMAILS", "boss@t.ai")
    return users.UserStore()


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


# -- org / profile model ----------------------------------------------------------------
def test_create_and_get_org(store):
    oid = store.create_org("Acme Industrial Supply", industry="Industrial Distribution",
                           sub_focus=["MRO / maintenance"], headcount="51–200",
                           revenue="$10M–$50M", website="acme.com",
                           connected_systems=["epicor"], by="boss@t.ai")
    assert oid.startswith("org-")
    org = store.get_org(oid)
    assert org["name"] == "Acme Industrial Supply"
    assert org["headcount"] == "51–200"          # band label stored verbatim, not a number
    assert org["connected_systems"] == ["epicor"]  # json round-trips to a list
    assert org["sub_focus"] == ["MRO / maintenance"]


def test_get_org_unknown(store):
    assert store.get_org("org-nope") is None
    assert store.get_org("") is None


def test_update_org_patches_only_given(store):
    oid = store.create_org("Acme", industry="Distribution", connected_systems=["epicor"])
    store.update_org(oid, headcount="201–1,000", connected_systems=["epicor", "salesforce"])
    org = store.get_org(oid)
    assert org["industry"] == "Distribution"       # untouched
    assert org["headcount"] == "201–1,000"          # patched
    assert org["connected_systems"] == ["epicor", "salesforce"]


def test_list_orgs(store):
    store.create_org("Zeta")
    store.create_org("Acme")
    names = [o["name"] for o in store.list_orgs()]
    assert names == ["Acme", "Zeta"]               # ordered by name


def test_set_profile_links_org_and_role(store):
    oid = store.create_org("Acme")
    store.set_profile("m@t.ai", org_id=oid, designation="Ops Manager",
                      role_description="runs quoting", tenexity=False)
    u = store.get_user("m@t.ai")
    assert u["org_id"] == oid
    assert u["designation"] == "Ops Manager"
    assert u["role_description"] == "runs quoting"
    assert u["tenexity"] in (0, False)
    assert store.is_member("m@t.ai")               # auto-created as member
    assert store.org_for_user("m@t.ai")["id"] == oid


def test_set_profile_preserves_admin_role(store):
    store.set_profile("boss@t.ai", designation="Founder")  # env-admin
    assert store.get_role("boss@t.ai") == "admin"          # role untouched by profile write
    assert store.get_user("boss@t.ai")["designation"] == "Founder"


def test_tenexity_flag(store):
    store.set_profile("staff@t.ai", tenexity=True)
    assert store.get_user("staff@t.ai")["tenexity"] in (1, True)
