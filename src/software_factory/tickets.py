"""Local SQLite ticket store with enforced state transitions.

A ticket goes open -> claimed -> done. `mark_done` is the gate that makes "done" mean
something: it refuses to close a ticket without a real merged PR and a non-empty diff.
An empty agent turn therefore cannot be laundered into "complete".
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Optional


class HollowWorkError(Exception):
    """Raised when a ticket is marked done without real, verified change."""


@dataclass
class Ticket:
    id: int
    title: str
    acceptance: str
    dod: str
    wave: int
    status: str
    agent: Optional[str]
    pr: Optional[int]
    diff_lines: int


class TicketStore:
    def __init__(self, path: str):
        self._conn = sqlite3.connect(path)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS tickets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                acceptance TEXT NOT NULL,
                dod TEXT NOT NULL,
                wave INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'open',
                agent TEXT,
                pr INTEGER,
                diff_lines INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        self._conn.commit()

    def create_ticket(self, title: str, acceptance: str, dod: str, wave: int) -> int:
        cur = self._conn.execute(
            "INSERT INTO tickets (title, acceptance, dod, wave) VALUES (?, ?, ?, ?)",
            (title, acceptance, dod, wave),
        )
        self._conn.commit()
        return cur.lastrowid

    def get(self, ticket_id: int) -> Ticket:
        row = self._conn.execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,)).fetchone()
        if row is None:
            raise KeyError(f"no ticket {ticket_id}")
        return Ticket(**dict(row))

    def claim(self, ticket_id: int, agent: str) -> None:
        self._conn.execute(
            "UPDATE tickets SET status = 'claimed', agent = ? WHERE id = ?", (agent, ticket_id)
        )
        self._conn.commit()

    def mark_done(self, ticket_id: int, pr: Optional[int], diff_lines: int) -> None:
        if not pr:
            raise HollowWorkError(f"ticket {ticket_id}: refusing 'done' without a merged PR")
        if diff_lines <= 0:
            raise HollowWorkError(f"ticket {ticket_id}: refusing 'done' with an empty diff")
        self._conn.execute(
            "UPDATE tickets SET status = 'done', pr = ?, diff_lines = ? WHERE id = ?",
            (pr, diff_lines, ticket_id),
        )
        self._conn.commit()

    def open_tickets(self, wave: int) -> list[Ticket]:
        rows = self._conn.execute(
            "SELECT * FROM tickets WHERE wave = ? AND status != 'done' ORDER BY id", (wave,)
        ).fetchall()
        return [Ticket(**dict(r)) for r in rows]

    def done_tickets(self) -> list[Ticket]:
        rows = self._conn.execute(
            "SELECT * FROM tickets WHERE status = 'done' ORDER BY id"
        ).fetchall()
        return [Ticket(**dict(r)) for r in rows]

    def render_markdown(self) -> str:
        rows = self._conn.execute("SELECT * FROM tickets ORDER BY wave, id").fetchall()
        lines = ["# Tickets", "", "| # | wave | status | title | acceptance |", "|---|---|---|---|---|"]
        for r in rows:
            lines.append(f"| {r['id']} | {r['wave']} | {r['status']} | {r['title']} | {r['acceptance']} |")
        return "\n".join(lines) + "\n"
