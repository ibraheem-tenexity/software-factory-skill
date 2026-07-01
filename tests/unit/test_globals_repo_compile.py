"""Pure (no-DB) checks for the B5 global-lane repositories: blobs, sow, agent_prompts, registries.
FakeExec mirrors GlobalExec's real contract exactly: fetchall/fetchone return captured rows,
execute() returns None — this is what caught the .execute(stmt).fetchone() bug (GlobalExec.execute
discards rows; RETURNING writes must go through fetchone/fetchall directly)."""
from software_factory.repositories._compile import to_sql
from software_factory.repositories.blobs_repo import BlobRepository
from software_factory.repositories.sow_repo import SowRepository
from software_factory.repositories.agent_prompts_repo import AgentPromptRepository
from software_factory.repositories.registries_repo import ToolRepository, AgentRegistryRepository


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


# -- sow ----------------------------------------------------------------------------------------
def test_sow_insert_returning_star():
    fx = FakeExec(fetchone_result={"id": 1, "title": "t"})
    row = SowRepository(fx).insert(title="t", status="Draft", version=1)
    assert row == {"id": 1, "title": "t"}
    assert "RETURNING" in fx.sql and "sow.id" in fx.sql


def test_sow_update_sets_updated_at_now():
    fx = FakeExec(fetchone_result={"id": 1})
    SowRepository(fx).update_fields(1, status="Sent")
    assert "sow.updated_at" in fx.sql and "now()" in fx.sql.lower()


# -- agent_prompts --------------------------------------------------------------------------------
def test_prompt_upsert_version_self_increment_not_excluded():
    fx = FakeExec()
    AgentPromptRepository(fx).upsert("ATLAS", "new prompt", "op@x.com")
    _clean(fx.sql)
    assert "ON CONFLICT (agent_prompts.callsign)" in fx.sql or "ON CONFLICT (callsign)" in fx.sql
    # version increments relative to the table's OWN column, not the inserted literal
    assert "agent_prompts.version" in fx.sql


# -- registries -----------------------------------------------------------------------------------
def test_tool_insert_returning_via_fetchone():
    fx = FakeExec(fetchone_result={"id": 1, "name": "X"})
    row = ToolRepository(fx).insert_returning("X", "MCP", "P", "s", "available", "none")
    assert row == {"id": 1, "name": "X"}


def test_agent_registry_upsert_excluded_columns():
    fx = FakeExec()
    AgentRegistryRepository(fx).upsert("STAGE-1", "Stage 1", "stage-orchestrator", "opus", 3, "d")
    _clean(fx.sql)
    assert "DO UPDATE SET" in fx.sql


def test_agent_registry_insert_if_absent_do_nothing():
    fx = FakeExec()
    AgentRegistryRepository(fx).insert_if_absent("STAGE-2", "Stage 2", "stage-orchestrator", "opus", 3, "d")
    assert "DO NOTHING" in fx.sql
