"""Cross-run aggregate reads (SQLAlchemy Core) — direct reads over the flat `runtime_agents`/`tickets`
tables that no per-run accessor exposes (today's burn, per-role rollups, in-flight ticket counts).
Global lane; read-only. Every aggregate carries a `.label(...)` matching the original SQL's alias —
losing one silently breaks the row-key contract callers rely on (`r["runs"]`, `r["cost_usd"]`, ...).
"""
from __future__ import annotations

from sqlalchemy import select, func, distinct

from ..models import runtime_agents, tickets


class AggregatesRepository:
    def __init__(self, exec_):
        self._x = exec_

    def agent_rollups(self) -> list:
        """Per-role aggregates across ALL runs: distinct runs, total spend, success rate, active count."""
        stmt = (select(
                    runtime_agents.c.role,
                    func.count(distinct(runtime_agents.c.project_id)).label("runs"),
                    func.coalesce(func.sum(runtime_agents.c.cost_usd), 0).label("cost_usd"),
                    func.count().label("total"),
                    func.count().filter(runtime_agents.c.status == "running").label("active"),
                    func.count().filter(runtime_agents.c.outcome.in_(("real_diff", "success"))).label("successes"),
                    func.max(runtime_agents.c.model).label("model"))
                .group_by(runtime_agents.c.role))
        return self._x.fetchall(stmt)

    def agents_active_count(self) -> int:
        row = self._x.fetchone(select(func.count().label("n")).where(runtime_agents.c.status == "running"))
        return int(row["n"]) if row else 0

    def today_burn(self, since_epoch: float) -> float:
        row = self._x.fetchone(select(func.coalesce(func.sum(runtime_agents.c.cost_usd), 0).label("burn"))
                               .where(runtime_agents.c.started_at >= since_epoch))
        return float(row["burn"]) if row else 0.0

    def open_tickets_by_project(self) -> list:
        stmt = (select(tickets.c.project_id, func.count().label("n"))
                .where(tickets.c.status.in_(("open", "in_progress")))
                .group_by(tickets.c.project_id))
        return self._x.fetchall(stmt)

    def ticket_counts_by_project(self) -> list:
        """{project_id} rows with total + done (delivered = done/deployed/approved)."""
        stmt = (select(tickets.c.project_id, func.count().label("total"),
                       func.count().filter(tickets.c.status.in_(("done", "deployed", "approved")))
                           .label("done"))
                .group_by(tickets.c.project_id))
        return self._x.fetchall(stmt)
