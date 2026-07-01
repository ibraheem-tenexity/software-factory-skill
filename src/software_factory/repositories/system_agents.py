"""Pure CRUD for `system_agents` (SQLAlchemy Core). Global table keyed by callsign — the four
operator-configurable agents (CONCIERGE + STAGE-1/2/3), each carrying its editable prompt AND the
LLM (`model_id`) it runs on. Merges the former `agent_registry` (identity) + `agent_prompts`
(prompt) repositories into one.

updated_at: cast(func.extract("epoch", col), Float) — a bare extract() returns Postgres `numeric`,
which psycopg3 decodes to `Decimal`, not the `float` the rest of the app expects (see
repositories/users.py's docstring, SOF-55)."""
from __future__ import annotations

from sqlalchemy import select, delete, func
from sqlalchemy.dialects.postgresql import insert as pg_insert

from ..models import system_agents
from ._compile import epoch_cast

_COLS = (system_agents.c.callsign, system_agents.c.name, system_agents.c.prompt,
         system_agents.c.model_id, system_agents.c.version, system_agents.c.updated_by,
         epoch_cast(system_agents.c.updated_at).label("updated_at"))


class SystemAgentRepository:
    def __init__(self, exec_):
        self._x = exec_

    def by_callsign(self, callsign: str):
        return self._x.fetchone(select(*_COLS).where(system_agents.c.callsign == callsign))

    def all(self) -> list:
        return self._x.fetchall(select(*_COLS).order_by(system_agents.c.callsign))

    def upsert(self, callsign: str, name=None, prompt=None, model_id=None, by: str = "") -> None:
        """Upsert one agent row, bumping its version. A net-new row starts at version 1; an existing
        row's version bumps relative to its OWN current value (`version = system_agents.version + 1`).
        Only the fields explicitly provided (non-None) are updated on conflict — `name`/`prompt`/
        `model_id` each stay as-is when not passed. A net-new row needs a `name` (NOT NULL) and gets
        an empty prompt if none supplied (matching the column's server_default)."""
        stmt = pg_insert(system_agents).values(
            callsign=callsign, name=name or "", prompt=prompt or "", model_id=model_id,
            version=1, updated_by=by, updated_at=func.now())
        set_ = {"version": system_agents.c.version + 1, "updated_by": stmt.excluded.updated_by,
                "updated_at": func.now()}
        if name is not None:
            set_["name"] = stmt.excluded.name
        if prompt is not None:
            set_["prompt"] = stmt.excluded.prompt
        if model_id is not None:
            set_["model_id"] = stmt.excluded.model_id
        stmt = stmt.on_conflict_do_update(index_elements=["callsign"], set_=set_)
        self._x.execute(stmt)

    def set_prompt(self, callsign: str, prompt: str, by: str) -> None:
        self.upsert(callsign, prompt=prompt, by=by)

    def set_model(self, callsign: str, model_id: str, by: str) -> None:
        self.upsert(callsign, model_id=model_id, by=by)

    def delete(self, callsign: str) -> None:
        self._x.execute(delete(system_agents).where(system_agents.c.callsign == callsign))
