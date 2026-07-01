"""Pure CRUD for `agent_prompts` (SQLAlchemy Core). Global table keyed by callsign."""
from __future__ import annotations

from sqlalchemy import select, delete, func
from sqlalchemy.dialects.postgresql import insert as pg_insert

from ..models import agent_prompts

_COLS = (agent_prompts.c.callsign, agent_prompts.c.prompt, agent_prompts.c.version,
         agent_prompts.c.updated_by, func.extract("epoch", agent_prompts.c.updated_at).label("updated_at"))


class AgentPromptRepository:
    def __init__(self, exec_):
        self._x = exec_

    def by_callsign(self, callsign: str):
        return self._x.fetchone(select(*_COLS).where(agent_prompts.c.callsign == callsign))

    def all(self) -> list:
        return self._x.fetchall(select(*_COLS))

    def upsert(self, callsign: str, prompt: str, by: str) -> None:
        """Upsert the prompt: a net-new row starts at version 1; an existing row's version bumps
        relative to its OWN current value (not the inserted literal), matching the original
        `version = agent_prompts.version + 1`."""
        stmt = pg_insert(agent_prompts).values(callsign=callsign, prompt=prompt, version=1,
                                               updated_by=by, updated_at=func.now())
        stmt = stmt.on_conflict_do_update(
            index_elements=["callsign"],
            set_={"prompt": stmt.excluded.prompt, "version": agent_prompts.c.version + 1,
                  "updated_by": stmt.excluded.updated_by, "updated_at": func.now()})
        self._x.execute(stmt)

    def delete(self, callsign: str) -> None:
        self._x.execute(delete(agent_prompts).where(agent_prompts.c.callsign == callsign))
