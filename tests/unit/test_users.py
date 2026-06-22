"""User directory + RBAC roles + organizations (Postgres via dbshim).

The users table is the single source of truth for access: status invited→active→disabled, role via
role_id→roles, google_sub set on first sign-in. No env allowlist; cold-start admin from
SF_BOOTSTRAP_ADMIN_EMAIL.
"""
import pytest

from software_factory import users


@pytest.fixture()
def store(tmp_path, monkeypatch):
    monkeypatch.setenv("SF_BOOTSTRAP_ADMIN_EMAIL", "boss@t.ai")
    return users.UserStore()


# -- bootstrap + roles ------------------------------------------------------------------
def test_bootstrap_admin_seeded_as_internal_admin(store):
    u = store.get_user("boss@t.ai")
    assert u and u["role"] == "admin"
    assert u["is_internal"] in (1, True)            # internal staff → can reach /admin after sign-in
    assert u["status"] == "invited"                 # net-new row; flips to active on first sign-in


def test_upsert_and_role(store):
    store.upsert("m@t.ai", "member", "boss@t.ai")
    assert store.get_user("m@t.ai")["role"] == "member"
    store.upsert("m@t.ai", "admin", "boss@t.ai")    # promote (status preserved)
    assert store.get_user("m@t.ai")["role"] == "admin"


def test_case_insensitive(store):
    store.upsert("Mixed@T.ai", "member")
    assert store.get_user("mixed@t.ai")["role"] == "member"
    assert store.get_user("MIXED@T.AI") is not None


def test_remove_member_but_not_bootstrap_admin(store):
    store.upsert("m@t.ai", "member")
    store.remove("m@t.ai")
    assert store.get_user("m@t.ai") is None
    store.remove("boss@t.ai")                        # bootstrap admin is protected
    assert store.get_user("boss@t.ai")["role"] == "admin"


def test_unknown_email(store):
    assert store.get_user("nobody@t.ai") is None
    assert store.get_user("") is None


# -- sign-in lifecycle ------------------------------------------------------------------
def test_authenticate_first_signin_activates_and_records_identity(store):
    store.upsert("m@t.ai", "member")                # invited
    assert store.get_user("m@t.ai")["status"] == "invited"
    u = store.authenticate("google-sub-xyz", "m@t.ai")   # first sign-in matches on email
    assert u and u["status"] == "active" and u["onboarded_at"]
    # subsequent sign-in matches on the stable google_sub (even if email is passed differently)
    u2 = store.authenticate("google-sub-xyz", "ANYTHING@t.ai")
    assert u2 and u2["email"] == "m@t.ai" and u2["status"] == "active"


def test_authenticate_rejects_unknown_email(store):
    assert store.authenticate("sub-1", "stranger@t.ai") is None    # not on the allowlist (no row)


def test_authenticate_rejects_disabled(store):
    store.upsert("m@t.ai", "member")
    store.disable("m@t.ai")
    assert store.authenticate("sub-1", "m@t.ai") is None


def test_disable_sets_status_and_bumps_token_version(store):
    store.upsert("m@t.ai", "member")
    assert int(store.get_user("m@t.ai")["token_version"]) == 0
    store.disable("m@t.ai")
    u = store.get_user("m@t.ai")
    assert u["status"] == "disabled" and int(u["token_version"]) == 1


def test_get_by_id_round_trips(store):
    store.upsert("m@t.ai", "member")
    uid = store.get_user("m@t.ai")["id"]
    assert store.get_by_id(uid)["email"] == "m@t.ai"
    assert store.get_by_id("00000000-0000-0000-0000-000000000000") is None
    assert store.get_by_id("") is None


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
    # "Tenexity" is the canonical internal org, seeded at UserStore init (ensure_tenexity_org).
    assert names == ["Acme", "Tenexity", "Zeta"]   # ordered by name


def test_set_profile_links_org_and_role(store):
    oid = store.create_org("Acme")
    store.set_profile("m@t.ai", org_id=oid, designation="Ops Manager",
                      role_description="runs quoting", is_internal=False)
    u = store.get_user("m@t.ai")
    assert u["org_id"] == oid
    assert u["designation"] == "Ops Manager"
    assert u["role_description"] == "runs quoting"
    assert u["is_internal"] in (0, False)
    assert u["role"] == "member"                   # auto-created as member
    assert store.org_for_user("m@t.ai")["id"] == oid


def test_set_profile_preserves_role(store):
    store.set_profile("boss@t.ai", designation="Founder")  # bootstrap admin
    assert store.get_user("boss@t.ai")["role"] == "admin"  # role untouched by profile write
    assert store.get_user("boss@t.ai")["designation"] == "Founder"


def test_is_internal_flag(store):
    store.set_profile("staff@t.ai", is_internal=True)
    assert store.get_user("staff@t.ai")["is_internal"] in (1, True)


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
    assert store.get_user("lead@t.ai")["role"] == "admin"


def test_org_plan_and_budget_cap_round_trip(store):
    oid = store.create_org("Acme")
    assert store.get_org(oid)["plan"] is None            # unset by default
    store.update_org(oid, plan="Team", monthly_budget_cap=120.0)
    org = store.get_org(oid)
    assert org["plan"] == "Team"
    assert org["monthly_budget_cap"] == 120.0
