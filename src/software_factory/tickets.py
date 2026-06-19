"""Local SQLite ticket store with an enforced 6-state lifecycle + QA loop.

    open → in_progress → done → deployed → qa_testing → approved
                                              │
                                              └── qa_reject ──▶ open  (carries a bug report)

`mark_done` is the gate that makes "done" mean something: it refuses to close a ticket
without a real merged PR (or commit sha) and a non-empty diff. An empty agent turn
therefore cannot be laundered into "complete". The later transitions drive deploy + the
QA loop: a deployed ticket is exercised on its live URL; on a bug it bounces back to
`open` carrying a markdown bug report (with Supabase Storage screenshot links) in its
`description`, so the next build agent that grabs it sees exactly what failed.

Illegal transitions (e.g. approving a ticket that was never QA'd, deploying an open
ticket) raise `IllegalTransition`.
"""
from __future__ import annotations


from . import dbshim
import time
from dataclasses import dataclass
from typing import Optional

# The lifecycle, in order.
STATES = ("open", "in_progress", "done", "deployed", "qa_testing", "approved")
# Tickets that still need build work — what the swarm hands to build agents (incl. QA-bounced
# tickets, which return to `open`). Everything past `in_progress` is built and out of the queue.
_BUILDABLE = ("open", "in_progress")
# "Built or beyond" — passed the hollow gate. Stage-3 proof + done_tickets() count these.
_BUILT_OR_BEYOND = ("done", "deployed", "qa_testing", "approved")


class HollowWorkError(Exception):
    """Raised when a ticket is marked done without real, verified change."""


class IllegalTransition(Exception):
    """Raised when a ticket is moved between states the lifecycle does not allow."""


@dataclass
class Ticket:
    id: int
    title: str
    acceptance: str
    dod: str
    wave: int
    status: str
    agent: Optional[str]
    provenance: Optional[str]
    provenance_type: Optional[str]
    diff_lines: int
    app: Optional[str] = None   # target deliverable: mobile-web | web | api | ... (multi-deliverable runs)
    description: str = ""       # human-facing detail; on a QA bounce, the markdown bug report


class TicketStore:
    def __init__(self, path: str):
        self._conn = dbshim.connect(path)  # sqlite today, pg when SF_DB=postgres
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
                provenance TEXT,
                provenance_type TEXT,
                diff_lines INTEGER NOT NULL DEFAULT 0,
                app TEXT,
                description TEXT NOT NULL DEFAULT ''
            )
            """
        )
        # Pre-existing run.dbs were created before these columns — add them idempotently
        # (no migration framework for the per-run schema).
        for col, ddl in (("app", "ALTER TABLE tickets ADD COLUMN app TEXT"),
                         ("description", "ALTER TABLE tickets ADD COLUMN description TEXT NOT NULL DEFAULT ''")):
            try:
                self._conn.execute(ddl)
                self._conn.commit()
            except Exception:
                pass  # column already present
        self._conn.commit()

    def create_ticket(self, title: str, acceptance: str, dod: str, wave: int,
                      app: Optional[str] = None, description: str = "") -> int:
        cur = self._conn.execute(
            "INSERT INTO tickets (title, acceptance, dod, wave, app, description) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (title, acceptance, dod, wave, app, description or ""),
        )
        self._conn.commit()
        return cur.lastrowid

    def get(self, ticket_id: int) -> Ticket:
        row = self._conn.execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,)).fetchone()
        if row is None:
            raise KeyError(f"no ticket {ticket_id}")
        return Ticket(**dict(row))

    # ---- transitions -----------------------------------------------------------------
    def _require(self, ticket_id: int, allowed: tuple, target: str) -> Ticket:
        t = self.get(ticket_id)
        if t.status not in allowed:
            raise IllegalTransition(
                f"ticket {ticket_id}: {t.status} → {target} is not a legal transition")
        return t

    def claim(self, ticket_id: int, agent: str) -> None:
        # → in_progress. Allowed from open (the norm), in_progress (a /loop resume replays the
        # claim), or done (re-attribution/rework — a monolithically-completed ticket is re-claimed
        # by a real native-Task agent to attach provenance). Claiming a shipped ticket
        # (deployed/qa_testing/approved) raises.
        self._require(ticket_id, ("open", "in_progress", "done"), "in_progress")
        self._conn.execute(
            "UPDATE tickets SET status = 'in_progress', agent = ? WHERE id = ?", (agent, ticket_id)
        )
        self._conn.commit()

    def mark_done(self, ticket_id: int, provenance, diff_lines: int,
                  provenance_type: str | None = None) -> None:
        """Close a ticket against REAL, attributable work. `provenance` is the work's
        proof: a merged PR number or URL (claude orchestrator workflow) OR a commit sha
        string (monolithic opencode workflow — direct commits to main have no PRs;
        run-45b8c4d5 proved the gate was unsatisfiable for Kimi as previously specced).
        Either way the no-hollow-close property holds: non-empty provenance + a non-zero
        diff. Allowed from open/in_progress (claim is the norm but not required)."""
        self._require(ticket_id, ("open", "in_progress"), "done")
        if provenance is None:
            provenance = ""
        if not isinstance(provenance, str):
            provenance = str(provenance)
        provenance = provenance.strip()
        if not provenance:
            raise HollowWorkError(f"ticket {ticket_id}: refusing 'done' without a merged PR or commit sha")
        if provenance_type is None:
            provenance_type = "pr" if provenance.isdigit() else "commit"
        if provenance_type == "commit" and len(provenance) < 7:
            raise HollowWorkError(f"ticket {ticket_id}: refusing 'done' without a merged PR or commit sha")
        if diff_lines <= 0:
            raise HollowWorkError(f"ticket {ticket_id}: refusing 'done' with an empty diff")
        self._conn.execute(
            "UPDATE tickets SET status = 'done', provenance = ?, provenance_type = ?, diff_lines = ? WHERE id = ?",
            (provenance, provenance_type, diff_lines, ticket_id),
        )
        self._conn.commit()

    def mark_deployed(self, ticket_id: int) -> None:
        self._require(ticket_id, ("done",), "deployed")
        self._conn.execute("UPDATE tickets SET status = 'deployed' WHERE id = ?", (ticket_id,))
        self._conn.commit()

    def start_qa(self, ticket_id: int) -> None:
        self._require(ticket_id, ("deployed",), "qa_testing")
        self._conn.execute("UPDATE tickets SET status = 'qa_testing' WHERE id = ?", (ticket_id,))
        self._conn.commit()

    def qa_approve(self, ticket_id: int) -> None:
        self._require(ticket_id, ("qa_testing",), "approved")
        self._conn.execute("UPDATE tickets SET status = 'approved' WHERE id = ?", (ticket_id,))
        self._conn.commit()

    def qa_reject(self, ticket_id: int, bug_markdown: str) -> None:
        """QA found a bug: bounce the ticket back to `open` carrying a markdown bug report
        (what failed + repro + screenshot links) appended to its description, and clear the
        agent so a fresh build agent re-claims it."""
        self._require(ticket_id, ("qa_testing",), "open")
        t = self.get(ticket_id)
        stamp = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())
        report = (t.description or "").rstrip()
        report = (report + "\n\n" if report else "") + f"## QA bug (rejected {stamp})\n\n{bug_markdown.strip()}\n"
        self._conn.execute(
            "UPDATE tickets SET status = 'open', agent = NULL, description = ? WHERE id = ?",
            (report, ticket_id),
        )
        self._conn.commit()

    # ---- queries ---------------------------------------------------------------------
    def open_waves(self) -> list[int]:
        """Waves that still have buildable tickets, ascending — the swarm driver's
        wave-serialization order (parallel within a wave, waves in sequence). A QA-bounced
        ticket (back to `open`) re-opens its wave."""
        rows = self._conn.execute(
            "SELECT DISTINCT wave FROM tickets WHERE status IN ('open','in_progress') ORDER BY wave"
        ).fetchall()
        return [r["wave"] for r in rows]

    def open_tickets(self, wave: int) -> list[Ticket]:
        rows = self._conn.execute(
            "SELECT * FROM tickets WHERE wave = ? AND status IN ('open','in_progress') ORDER BY id",
            (wave,)
        ).fetchall()
        return [Ticket(**dict(r)) for r in rows]

    def buildable_count(self) -> int:
        """Number of tickets Stage 3 can actually build: a real (non-empty) acceptance
        AND definition of done. Empty-string acceptance/dod don't count — they'd be hollow
        and `mark_done` (which enforces DoD) couldn't verify them. This is the mechanical
        gate that proves Stage 2 PERSISTED its tickets, not just emitted ticket events."""
        rows = self._conn.execute("SELECT acceptance, dod FROM tickets").fetchall()
        return sum(1 for r in rows if (r["acceptance"] or "").strip() and (r["dod"] or "").strip())

    def done_tickets(self) -> list[Ticket]:
        """Tickets that passed the hollow-done gate — `done` and everything beyond it
        (deployed/qa_testing/approved). Stage-3 proof counts these."""
        rows = self._conn.execute(
            "SELECT * FROM tickets WHERE status IN ('done','deployed','qa_testing','approved') ORDER BY id"
        ).fetchall()
        return [Ticket(**dict(r)) for r in rows]

    def approved_tickets(self) -> list[Ticket]:
        rows = self._conn.execute(
            "SELECT * FROM tickets WHERE status = 'approved' ORDER BY id"
        ).fetchall()
        return [Ticket(**dict(r)) for r in rows]

    def all_approved(self) -> bool:
        """True when at least one ticket exists and every ticket is `approved` — the
        QA-complete gate for Stage 3 (set by the QA agent's qa_approve calls)."""
        rows = self._conn.execute("SELECT status FROM tickets").fetchall()
        return bool(rows) and all(r["status"] == "approved" for r in rows)

    def all_tickets(self) -> list[Ticket]:
        """Every ticket regardless of status, in wave then id order — the kanban projection."""
        rows = self._conn.execute("SELECT * FROM tickets ORDER BY wave, id").fetchall()
        return [Ticket(**dict(r)) for r in rows]

    def render_markdown(self) -> str:
        rows = self._conn.execute("SELECT * FROM tickets ORDER BY wave, id").fetchall()
        lines = ["# Tickets", "", "| # | wave | status | title | acceptance |", "|---|---|---|---|---|"]
        for r in rows:
            lines.append(f"| {r['id']} | {r['wave']} | {r['status']} | {r['title']} | {r['acceptance']} |")
        return "\n".join(lines) + "\n"
