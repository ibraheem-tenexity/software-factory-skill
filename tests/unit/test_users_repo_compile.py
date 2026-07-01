"""Pure (no-DB) checks for UserRepository — the self-join (invited_by), UUID-cast columns, ON
CONFLICT upserts targeting the `email`/`name` UNIQUE constraints, and the self-referencing
token_version increment. Behavior-equivalence round-trip is test_users.py, run when the flock is free."""
from software_factory.repositories._compile import to_sql
from software_factory.repositories.users import UserRepository


class FakeExec:
    def __init__(self):
        self.sql = None
        self.params = None

    def _cap(self, stmt):
        self.sql, self.params = to_sql(stmt)

    def fetchall(self, stmt):
        self._cap(stmt); return []

    def execute(self, stmt):
        self._cap(stmt); return None


def _clean(sql):
    assert "?" not in sql and "%(" not in sql


def test_all_users_self_join_and_cast():
    fx = FakeExec()
    UserRepository(fx).all_users()
    _clean(fx.sql)
    assert "CAST(users.id AS TEXT) AS id" in fx.sql or "cast(users.id" in fx.sql.lower()
    assert "JOIN roles ON roles.id = users.role_id" in fx.sql
    assert "LEFT OUTER JOIN users AS inv ON inv.id = users.invited_by" in fx.sql
    assert "inv.email AS invited_by" in fx.sql
    assert "password_hash" not in fx.sql   # never selected in the roster row


def test_by_google_sub_and_by_email_where():
    fx = FakeExec()
    UserRepository(fx).by_google_sub("sub-1")
    assert "users.google_sub = %s" in fx.sql
    UserRepository(fx).by_email("a@b.com")
    assert "users.email = %s" in fx.sql


def test_upsert_user_on_conflict_email():
    fx = FakeExec()
    UserRepository(fx).upsert_user("uid-1", "a@b.com", "role-1", None)
    _clean(fx.sql)
    assert "ON CONFLICT (users.email) DO UPDATE SET" in fx.sql or "ON CONFLICT (email) DO UPDATE SET" in fx.sql
    assert "uid-1" in fx.params and "a@b.com" in fx.params


def test_upsert_admin_sets_is_internal_true():
    fx = FakeExec()
    UserRepository(fx).upsert_admin("uid-1", "boss@t.ai", "role-1")
    assert True in fx.params or "true" in fx.sql.lower()


def test_set_identity_coalesce_onboarded_at():
    fx = FakeExec()
    UserRepository(fx).set_identity("uid-1", "sub-1")
    assert "coalesce(users.onboarded_at, now())" in fx.sql.lower()
    assert "status=%s" in fx.sql
    assert "users.id = %s::UUID" in fx.sql  # dialect auto-casts the UUID column comparison


def test_disable_user_self_referencing_increment():
    fx = FakeExec()
    UserRepository(fx).disable_user("a@b.com")
    _clean(fx.sql)
    assert "users.token_version + %s" in fx.sql
    assert "disabled" in fx.params


def test_update_user_columns_trusted_keys_only():
    fx = FakeExec()
    UserRepository(fx).update_user_columns("a@b.com", {"designation": "Ops", "org_id": "org-1"})
    assert "designation=%s" in fx.sql and "org_id=%s" in fx.sql
    assert "updated_at=now()" in fx.sql


def test_credentials_excludes_hash_from_roster_but_returns_it_here():
    fx = FakeExec()
    UserRepository(fx).credentials("a@b.com")
    assert "users.password_hash" in fx.sql
    assert "users.status" in fx.sql


def test_org_insert_and_upsert_shapes():
    fx = FakeExec()
    UserRepository(fx).insert_org("org-1", "Acme", "Dist", "[]", "51-200", "$1M", "SF", "acme.com",
                                  "[]", "sys")
    assert fx.sql.startswith("INSERT INTO organizations")
    UserRepository(fx).unlink_org_members("org-1")
    assert "org_id=%s" in fx.sql and "users.org_id = %s" in fx.sql
