"""Pure (no-DB) checks for the global-lane repositories: blobs, system_agents, tools.
FakeExec mirrors GlobalExec's real contract exactly: fetchall/fetchone return captured rows,
execute() returns None — this is what caught the .execute(stmt).fetchone() bug (GlobalExec.execute
discards rows; RETURNING writes must go through fetchone/fetchall directly)."""
from software_factory.repositories._compile import to_sql
from software_factory.repositories.blobs import BlobRepository
from software_factory.repositories.system_agents import SystemAgentRepository
from software_factory.repositories.tools import ToolRepository


class FakeExec:
    def __init__(self, fetchone_result=None, fetchall_result=None):
        self.sql = None
        self.params = None
        self._fetchone_result = fetchone_result
        self._fetchall_result = fetchall_result if fetchall_result is not None else []

    def _cap(self, stmt):
        self.sql, self.params = to_sql(stmt)

    def fetchall(self, stmt):
        self._cap(stmt)
        return self._fetchall_result

    def fetchone(self, stmt):
        self._cap(stmt)
        return self._fetchone_result

    def execute(self, stmt):
        """Mirrors the REAL GlobalExec.execute(): always returns None. A repo that calls
        `.execute(stmt).fetchone()` for a RETURNING write would AttributeError here — exactly
        the bug this test class is designed to catch."""
        self._cap(stmt)
        return None


def _clean(sql):
    assert "?" not in sql and "%(" not in sql


# -- blobs --------------------------------------------------------------------------------------
def test_blob_insert_returning_via_fetchone_not_execute():
    fx = FakeExec(fetchone_result={"id": 7})
    bid = BlobRepository(fx).insert("org", "org-1", "key", "xlsx", "n", "t", "ct", 10, "sha")
    assert bid == 7          # would raise AttributeError on None if using .execute().fetchone()
    _clean(fx.sql)
    assert "RETURNING blobs.id" in fx.sql


def test_blob_list_org_docs_join_and_group():
    fx = FakeExec()
    BlobRepository(fx).list_org_docs("org-1")
    assert "LEFT OUTER JOIN blob_uses" in fx.sql
    assert "count(DISTINCT blob_uses.project_id)" in fx.sql
    assert "GROUP BY blobs.id" in fx.sql
    assert "ORDER BY blobs.id DESC" in fx.sql


def test_blob_delete_removes_uses_then_blob():
    fx = FakeExec()
    BlobRepository(fx).delete(9)
    assert fx.sql.startswith("DELETE FROM blobs")  # last statement captured


# -- system_agents --------------------------------------------------------------------------------
def test_system_agent_upsert_version_self_increment_not_excluded():
    fx = FakeExec()
    SystemAgentRepository(fx).upsert("CONCIERGE", prompt="new prompt", by="op@x.com")
    _clean(fx.sql)
    assert "ON CONFLICT (system_agents.callsign)" in fx.sql or "ON CONFLICT (callsign)" in fx.sql
    # version increments relative to the table's OWN column, not the inserted literal
    assert "system_agents.version" in fx.sql
    assert "DO UPDATE SET" in fx.sql


def test_system_agent_upsert_only_updates_provided_fields():
    fx = FakeExec()
    SystemAgentRepository(fx).upsert("CONCIERGE", model_id="gpt-5.4", by="op@x.com")
    # model_id provided -> updated on conflict; prompt/name NOT provided -> untouched on conflict
    assert "model_id" in fx.sql.split("DO UPDATE SET", 1)[1]
    assert "prompt" not in fx.sql.split("DO UPDATE SET", 1)[1]


# -- tools ----------------------------------------------------------------------------------------
def test_tool_upsert_inserts_when_absent():
    fx = FakeExec(fetchone_result=None)  # by_name-style existence check finds nothing
    ToolRepository(fx).upsert("exa", {"type": "http"}, ["STAGE-1"], "op@x.com")
    _clean(fx.sql)
    assert fx.sql.startswith("INSERT INTO tools")
    assert "config" in fx.sql and "attached_to" in fx.sql
    # config/attached_to must be JSON-serialized strings, not bare dict/list — GlobalExec's raw-SQL
    # path bypasses SQLAlchemy's own bind processor (see repositories/_compile.py's serialize_jsonb
    # docstring); a bare dict here is exactly the "cannot adapt type 'dict'" psycopg3 crash a FakeExec
    # test can catch without ever touching a real DB.
    import json
    assert json.loads(fx.params[1]) == {"type": "http"}
    assert json.loads(fx.params[2]) == ["STAGE-1"]


def test_tool_upsert_updates_when_present():
    fx = FakeExec(fetchone_result={"name": "exa"})  # existence check finds the row
    ToolRepository(fx).upsert("exa", {"type": "http"}, None, "op@x.com")
    _clean(fx.sql)
    assert fx.sql.startswith("UPDATE tools")
    assert "attached_to" not in fx.sql  # attached_to=None -> left untouched on update
    import json
    assert json.loads(fx.params[0]) == {"type": "http"}


def test_tool_set_key_writes_vault_pointer_and_last4():
    fx = FakeExec()
    ToolRepository(fx).set_key("exa", "vault-uuid-1", "abcd", "op@x.com")
    _clean(fx.sql)
    assert fx.sql.startswith("UPDATE tools")
    assert "key_vault_id" in fx.sql and "key_last4" in fx.sql
