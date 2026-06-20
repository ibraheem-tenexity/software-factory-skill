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


# -- org membership (Team & access, PRD §2.3) -------------------------------------------
def test_list_org_members_scoped_and_ordered(store):
    oid = store.create_org("Acme")
    other = store.create_org("Beta")
    store.set_profile("zoe@t.ai", org_id=oid, designation="Sales")
    store.set_profile("amy@t.ai", org_id=oid, designation="Ops")
    store.set_profile("ben@t.ai", org_id=other, designation="Ops")   # different org
    members = store.list_org_members(oid)
    assert [m["email"] for m in members] == ["amy@t.ai", "zoe@t.ai"]   # ordered, org-scoped
    assert members[0]["designation"] == "Ops"
    assert members[1]["role"] == "member"


def test_invite_member_creates_user_linked_to_org(store):
    oid = store.create_org("Acme")
    store.invite_member("new@t.ai", oid, role="member", designation="Procurement", by="boss@t.ai")
    u = store.get_user("new@t.ai")
    assert u["org_id"] == oid
    assert u["role"] == "member"
    assert u["designation"] == "Procurement"
    assert [m["email"] for m in store.list_org_members(oid)] == ["new@t.ai"]


def test_invite_member_can_grant_admin(store):
    oid = store.create_org("Acme")
    store.invite_member("lead@t.ai", oid, role="admin", by="boss@t.ai")
    assert store.get_role("lead@t.ai") == "admin"


def test_org_plan_and_budget_cap_round_trip(store):
    oid = store.create_org("Acme")
    assert store.get_org(oid)["plan"] is None            # unset by default
    store.update_org(oid, plan="Team", monthly_budget_cap=120.0)
    org = store.get_org(oid)
    assert org["plan"] == "Team"
    assert org["monthly_budget_cap"] == 120.0
