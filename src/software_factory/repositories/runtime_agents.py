"""Pure CRUD for the `runtime_agents` table (SQLAlchemy Core). Every method takes `project_id` explicitly —
mirrors the original raw SQL, which mixed a store attribute (`self._project_id`) and a caller-supplied
project_id across different methods. Taking it explicitly at every call means the repo never stores a
reference back to its owning store, so it can't hit the reference-cycle pitfall a live getter/closure
introduced elsewhere (see #212) — there is nothing here to close over."""
from __future__ import annotations

from sqlalchemy import select, insert, update, func

from ..models import runtime_agents


class AgentRepository:
    def __init__(self, exec_):
        self._x = exec_

    def insert(self, agent_id, project_id, ticket_id, role, model, phase, started_at) -> None:
        self._x.execute(insert(runtime_agents).values(agent_id=agent_id, project_id=project_id,
                                              ticket_id=ticket_id, role=role, model=model,
                                              phase=phase, started_at=started_at))

    def all_for_project(self, project_id) -> list:
        return self._x.fetchall(select(runtime_agents).where(runtime_agents.c.project_id == project_id)
                                .order_by(runtime_agents.c.started_at, runtime_agents.c.agent_id))

    def finalize_orphans(self, project_id, status, ended_at) -> int:
        cur = self._x.execute(update(runtime_agents)
                              .where(runtime_agents.c.project_id == project_id, runtime_agents.c.status == "running")
                              .values(status=status, outcome="unreported", ended_at=ended_at))
        return cur.rowcount

    def set_outcome(self, agent_id, project_id, *, status, outcome, cost_usd, input_tokens,
                    cached_tokens, output_tokens, reasoning_tokens, provenance, provenance_type,
                    diff_lines, ended_at) -> None:
        self._x.execute(update(runtime_agents)
                        .where(runtime_agents.c.agent_id == agent_id, runtime_agents.c.project_id == project_id)
                        .values(status=status, outcome=outcome, cost_usd=cost_usd,
                                input_tokens=input_tokens, cached_tokens=cached_tokens,
                                output_tokens=output_tokens, reasoning_tokens=reasoning_tokens,
                                provenance=provenance, provenance_type=provenance_type,
                                diff_lines=diff_lines, ended_at=ended_at))

    def by_agent_id(self, agent_id, project_id):
        return self._x.fetchone(select(runtime_agents).where(runtime_agents.c.agent_id == agent_id,
                                                      runtime_agents.c.project_id == project_id))

    def running_for_project(self, project_id) -> list:
        return self._x.fetchall(select(runtime_agents).where(runtime_agents.c.project_id == project_id,
                                                      runtime_agents.c.status == "running")
                                .order_by(runtime_agents.c.started_at))

    def status_outcome_rows(self, project_id) -> list:
        return self._x.fetchall(select(runtime_agents.c.status, runtime_agents.c.outcome)
                                .where(runtime_agents.c.project_id == project_id))

    def outcome_rows(self, project_id) -> list:
        return self._x.fetchall(select(runtime_agents.c.outcome)
                                .where(runtime_agents.c.project_id == project_id, runtime_agents.c.outcome.is_not(None)))

    def cost_sum_by_ticket(self, project_id) -> list:
        return self._x.fetchall(select(runtime_agents.c.ticket_id, func.sum(runtime_agents.c.cost_usd).label("c"))
                                .where(runtime_agents.c.project_id == project_id)
                                .group_by(runtime_agents.c.ticket_id))

    def batch_roles(self, project_ids: list) -> list:
        """Agent roles across many projects in one round-trip (console.py's dashboard, N+1
        prevention); rows ordered so the caller can take first-seen-per-project distinct roles."""
        return self._x.fetchall(
            select(runtime_agents.c.project_id, runtime_agents.c.role)
            .where(runtime_agents.c.project_id.in_(project_ids))
            .order_by(runtime_agents.c.started_at, runtime_agents.c.agent_id))
