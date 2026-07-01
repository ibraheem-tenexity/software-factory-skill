"""Pure (no-DB) checks that CheckpointRepository builds the intended SQL — focused on the gnarly
features (JSONB write via json.dumps + ::JSONB cast, ON CONFLICT DO NOTHING RETURNING, IN-expansion
incl. the empty case, LIKE 'ticket:%'). Behavior-equivalence round-trip is the existing DB tests
(test_checkpoint.py / test_pg_stores.py), run in a serialized slot."""
from software_factory.repositories._compile import to_sql
from software_factory.repositories.checkpoint_repo import CheckpointRepository


class FakeExec:
    def __init__(self):
        self.sql = None
        self.params = None

    def _cap(self, stmt):
        self.sql, self.params = to_sql(stmt)

    def fetchall(self, stmt):
        self._cap(stmt)
        return []

    def fetchone(self, stmt):
        self._cap(stmt)
        return {"id": 1}


def _repo():
    fx = FakeExec()
    return CheckpointRepository(fx), fx


def _clean(sql):
    assert "?" not in sql and "%(" not in sql


def test_insert_if_absent_jsonb_and_on_conflict():
    r, fx = _repo()
    assert r.insert_if_absent("p1", "build", {"a": 1}, 123.0) is True
    _clean(fx.sql)
    assert "ON CONFLICT (project_id, node) DO NOTHING" in fx.sql
    assert "RETURNING checkpoint.id" in fx.sql
    assert "%s::JSONB" in fx.sql                      # JSONB cast present
    assert '{"a": 1}' in fx.params                    # output json.dumps'd to a STRING (not a dict)
    assert not any(isinstance(p, dict) for p in fx.params)   # never bind a raw dict


def test_all_for_order_asc():
    r, fx = _repo()
    r.all_for("p1")
    assert "FROM checkpoint" in fx.sql and "ORDER BY checkpoint.stamped_at ASC" in fx.sql
    assert fx.params == ("p1",)


def test_delete_nodes_in_expansion_and_like():
    r, fx = _repo()
    r.delete_nodes("p1", ["build", "deploy"])
    _clean(fx.sql)
    assert fx.sql.startswith("DELETE FROM checkpoint")
    assert "checkpoint.node IN (%s, %s)" in fx.sql
    assert "checkpoint.node LIKE %s" in fx.sql
    assert "RETURNING checkpoint.node" in fx.sql
    assert fx.params == ("p1", "build", "deploy", "ticket:%")   # LIKE pattern is a bound param, no %% escaping


def test_delete_nodes_empty_list_still_valid():
    r, fx = _repo()
    r.delete_nodes("p1", [])              # unknown node → empty ordered set; only ticket:% deleted
    _clean(fx.sql)
    assert fx.sql.startswith("DELETE FROM checkpoint")
    assert "checkpoint.node LIKE %s" in fx.sql
    assert "p1" in fx.params and "ticket:%" in fx.params


def test_ticket_nodes_for_like():
    r, fx = _repo()
    r.ticket_nodes_for("p1")
    assert "checkpoint.node LIKE %s" in fx.sql
    assert fx.params == ("p1", "ticket:%")
