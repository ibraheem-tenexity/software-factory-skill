"""Statement-of-Work store (PRD §2.x SOW editor, wsp0uq99 FE task).

Direct Postgres CRUD over the `public.sow` table. Same dbshim pattern as
registries.py — no ORM, plain psycopg3 via _pg_connect.
"""
from __future__ import annotations

import os
import time
from typing import Optional

from . import dbshim

SOW_STATUSES = ("Template", "Draft", "In review", "Sent", "Signed")


def _conn():
    return dbshim._pg_connect(os.environ["DATABASE_URL"])


def _exec(sql: str, params=()):
    conn = _conn()
    with conn.cursor() as cur:
        cur.execute(sql, params)
        conn.commit()


def _rows(sql: str, params=()):
    conn = _conn()
    with conn.cursor() as cur:
        cur.execute(sql, params)
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]


def _row(sql: str, params=()):
    rows = _rows(sql, params)
    return rows[0] if rows else None


class SowStore:
    """CRUD store for the sow table. Staff-only; no per-user ownership."""

    def list_all(self) -> list[dict]:
        return _rows("SELECT * FROM public.sow ORDER BY id DESC")

    def get(self, sow_id: int) -> Optional[dict]:
        return _row("SELECT * FROM public.sow WHERE id=%s", (sow_id,))

    def create(self, title: str, *, org: str = None, project: str = None,
               value: str = None, file: str = None, version: int = 1,
               status: str = "Draft", body: str = None) -> dict:
        if status not in SOW_STATUSES:
            raise ValueError(f"invalid status {status!r}; must be one of {SOW_STATUSES}")
        row = _row(
            "INSERT INTO public.sow (title,org,project,value,file,version,status,body) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *",
            (title, org, project, value, file, version, status, body),
        )
        return row

    def update(self, sow_id: int, fields: dict) -> Optional[dict]:
        allowed = {"title", "org", "project", "value", "file", "version", "status", "body"}
        updates = {k: v for k, v in fields.items() if k in allowed and v is not None}
        if not updates:
            return self.get(sow_id)
        if "status" in updates and updates["status"] not in SOW_STATUSES:
            raise ValueError(f"invalid status {updates['status']!r}")
        sets = ", ".join(f"{k}=%s" for k in updates)
        vals = list(updates.values()) + [sow_id]
        return _row(
            f"UPDATE public.sow SET {sets}, updated_at=now() WHERE id=%s RETURNING *",
            vals,
        )
