"""Regression test for the UUID-object-leak bug found on the phase-2-concierge preview
(y96ilz0o, /converse 500 — ResponseValidationError since ConverseOut.message_id: str strictly
rejects a raw uuid.UUID). GlobalExec's raw-SQL path bypasses SQLAlchemy's UUID(as_uuid=False)
type coercion, so a plain `conversation.c.id`/`session_id`/`user_id` in a SELECT list or
RETURNING clause comes back as psycopg3's own native uuid.UUID object, not a string.

Pure SQL-compilation checks — `to_sql()` never opens a connection (matches the pattern in
test_conversation_repo_rollup.py), so this is DB-free and safe on this box."""
from sqlalchemy import insert

from software_factory.repositories.conversation import ConversationRepository, _COLS
from software_factory.repositories._compile import to_sql
from software_factory.models import conversation


class _CapturingExec:
    def __init__(self, rows=None):
        self.rows = rows if rows is not None else []
        self.sql = None

    def fetchall(self, stmt):
        self.sql, _ = to_sql(stmt)
        return self.rows

    def fetchone(self, stmt):
        self.sql, _ = to_sql(stmt)
        return self.rows[0] if self.rows else None


def test_cols_casts_id_session_id_and_user_id_to_text():
    sql, _ = to_sql(select_all_for_cols())
    assert "CAST(conversation.id AS TEXT)" in sql
    assert "CAST(conversation.session_id AS TEXT)" in sql
    assert "CAST(conversation.user_id AS TEXT)" in sql
    # project_id/org_id are Text columns already — must NOT be (redundantly) cast.
    assert "CAST(conversation.project_id" not in sql
    assert "CAST(conversation.org_id" not in sql


def select_all_for_cols():
    from sqlalchemy import select
    return select(*_COLS)


def test_all_for_session_compiles_with_the_cast_cols():
    x = _CapturingExec(rows=[])
    ConversationRepository(x).all_for_session("sess-1")
    assert "CAST(conversation.id AS TEXT)" in x.sql
    assert "CAST(conversation.session_id AS TEXT)" in x.sql
    assert "CAST(conversation.user_id AS TEXT)" in x.sql


def test_insert_returning_casts_id_to_text():
    x = _CapturingExec(rows=[{"id": "11111111-1111-1111-1111-111111111111"}])
    ConversationRepository(x).insert(session_id="sess-1", seq=0, role="user", json_blob=[])
    assert "RETURNING CAST(conversation.id AS TEXT)" in x.sql


def test_rollup_casts_session_id_and_user_id_but_not_the_group_by():
    x = _CapturingExec(rows=[])
    ConversationRepository(x).rollup(limit=10)
    assert "CAST(conversation.session_id AS TEXT) AS session_id" in x.sql
    assert "CAST(conversation.user_id AS TEXT) AS user_id" in x.sql
    # GROUP BY must reference the RAW column, not the cast — casting there too would still be
    # valid SQL, but this locks in the deliberate choice (cast is a function OF the grouped
    # column, doesn't need to itself appear in GROUP BY).
    group_by_clause = x.sql.split("GROUP BY", 1)[1]
    assert "CAST" not in group_by_clause.split("ORDER BY")[0]


def test_rollup_returns_string_ids_end_to_end_through_a_fake_row():
    """The actual regression this bug produced: a real psycopg3 row would hand back uuid.UUID
    objects for session_id/user_id if the cast weren't in the SELECT list. Can't fake psycopg3's
    own type decoding here (that's the real bug, not something a fake can reproduce) — this just
    confirms the plumbing doesn't itself coerce/mangle a plain string row, so once cast() forces
    Postgres to hand back a string, this class's own code preserves it faithfully to the caller."""
    x = _CapturingExec(rows=[{"session_id": "sess-1", "org_id": None, "project_id": "proj-1",
                              "user_id": "user-1", "turn_count": 2, "last_activity": "2026-01-01",
                              "total_cost": 0.1}])
    rows = ConversationRepository(x).rollup(limit=10)
    assert isinstance(rows[0]["session_id"], str)
    assert isinstance(rows[0]["user_id"], str)
