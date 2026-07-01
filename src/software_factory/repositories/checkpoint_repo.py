"""Pure CRUD for the `checkpoint` table (SQLAlchemy Core). Global infrastructure scoped per-call by
`project_id` (not per-project-path), so it uses the `GlobalExec` lane and takes `project_id` as a
method argument. All `checkpoint` SQL lives here; the ordering/invalidation logic (NODE_ORDER,
_node_pos) stays in `checkpoint.py`.

JSONB note: `output` is a JSONB column — we `json.dumps` the value on write (bind a string; the
compiled `::JSONB` cast handles it), matching the previous raw-SQL behavior; reads come back parsed.
"""
from __future__ import annotations

import json

from sqlalchemy import select, delete, or_
from sqlalchemy.dialects.postgresql import insert as pg_insert

from ..models import checkpoint


class CheckpointRepository:
    def __init__(self, exec_):
        self._x = exec_

    def insert_if_absent(self, project_id: str, node: str, output: dict | None, stamped_at: float) -> bool:
        """INSERT … ON CONFLICT (project_id, node) DO NOTHING RETURNING id. True if a new row was
        inserted, False if it already existed (idempotent)."""
        stmt = (pg_insert(checkpoint)
                .values(project_id=project_id, node=node, output=json.dumps(output or {}),
                        stamped_at=stamped_at)
                .on_conflict_do_nothing(index_elements=["project_id", "node"])
                .returning(checkpoint.c.id))
        return self._x.fetchone(stmt) is not None

    def all_for(self, project_id: str) -> list:
        return self._x.fetchall(
            select(checkpoint.c.node, checkpoint.c.output, checkpoint.c.stamped_at)
            .where(checkpoint.c.project_id == project_id)
            .order_by(checkpoint.c.stamped_at.asc()))

    def nodes_for(self, project_id: str) -> list:
        return self._x.fetchall(
            select(checkpoint.c.node).where(checkpoint.c.project_id == project_id))

    def delete_nodes(self, project_id: str, nodes: list) -> list:
        """Delete the given node checkpoints plus all per-ticket ones (node LIKE 'ticket:%'),
        RETURNING the deleted node names. `nodes` may be empty (only ticket nodes get deleted then)."""
        stmt = (delete(checkpoint)
                .where(checkpoint.c.project_id == project_id,
                       or_(checkpoint.c.node.in_(nodes), checkpoint.c.node.like("ticket:%")))
                .returning(checkpoint.c.node))
        return self._x.fetchall(stmt)

    def ticket_nodes_for(self, project_id: str) -> list:
        return self._x.fetchall(
            select(checkpoint.c.node)
            .where(checkpoint.c.project_id == project_id, checkpoint.c.node.like("ticket:%")))
