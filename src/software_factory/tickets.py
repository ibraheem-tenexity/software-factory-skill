"""Ticket store (Postgres) with an enforced 6-state lifecycle + QA loop.

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

DATA ACCESS: all `tickets` SQL lives in `repositories.tickets.TicketRepository` (SQLAlchemy
Core); this store keeps only the lifecycle rules, the `Ticket` dataclass mapping, and the small
Python folds (`buildable_count`/`all_approved`), delegating every query/write to that repository.
"""
from __future__ import annotations


from .db import project_id_from_path
from .repositories._exec import PathExec
from .repositories.tickets import TicketRepository
import json
import re
import time
import weakref
from dataclasses import dataclass
from typing import Optional

# The lifecycle, in order.
STATES = ("open", "in_progress", "done", "deployed", "qa_testing", "approved")
# Tickets that still need build work — what the swarm hands to build agents (incl. QA-bounced
# tickets, which return to `open`). Everything past `in_progress` is built and out of the queue.
_BUILDABLE = ("open", "in_progress")
# "Built or beyond" — passed the hollow gate. Stage-3 proof + done_tickets() count these.
_BUILT_OR_BEYOND = ("done", "deployed", "qa_testing", "approved")


def _decode_row(row) -> dict:
    """JSON-decode `design_refs`/`dependencies` for the `Ticket` dataclass — SQL NULL stays
    Python `None` (never addressed); a JSON array (including `'[]'`) decodes to a real list."""
    d = dict(row)
    for key in ("design_refs", "dependencies"):
        raw = d.get(key)
        d[key] = json.loads(raw) if raw is not None else None
    return d


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
    goal: str = ""               # SOF-100: one-sentence purpose, alongside the mechanical acceptance/dod
    # SOF-100: None = never addressed (fails the depth gate); [] = explicitly "no screens apply"
    # (honest for a backend-only ticket) — real depth gate distinguishes these, so keep the None.
    design_refs: Optional[list] = None    # PRD v1 screen IDs this ticket implements
    dependencies: Optional[list] = None   # other tickets this one depends on (title/in-batch ref)
    scope_genre: Optional[str] = None     # the PRD genre-module heading this ticket belongs to
    implementation_notes: str = ""        # concrete build guidance beyond acceptance/dod


class TicketStore:
    def __init__(self, path: str):
        self._project_id = project_id_from_path(path)
        # Postgres; schema owned by Alembic (prod) / tests. All SQL is in TicketRepository. The repo
        # reads project_id LIVE (getter) so reassigning self._project_id still re-scopes every query.
        # A WEAKREF, not a closure over `self` directly: `self._repo` holding a closure that captures
        # `self` is a reference CYCLE, which delays returning the pooled connection to dbshim's pool
        # until the cyclic GC runs — exhausting the pool under call sites that construct many
        # short-lived TicketStores (e.g. a per-call helper in a loop).
        _self_ref = weakref.ref(self)
        self._repo = TicketRepository(PathExec(path), lambda: _self_ref()._project_id)

    def create_ticket(self, title: str, acceptance: str, dod: str, wave: int,
                      app: Optional[str] = None, description: str = "", goal: str = "",
                      design_refs: Optional[list] = None, dependencies: Optional[list] = None,
                      scope_genre: Optional[str] = None, implementation_notes: str = "") -> int:
        """`design_refs`/`dependencies` left as `None` (the default) are stored as SQL NULL — the
        depth gate reads that as "never addressed." Pass `[]` explicitly to record a real,
        honest "none apply" (e.g. a backend-only ticket has no screen to reference)."""
        return self._repo.insert(
            title=title, acceptance=acceptance, dod=dod, wave=wave, app=app,
            description=description or "", goal=goal or "",
            design_refs=None if design_refs is None else json.dumps(design_refs),
            dependencies=None if dependencies is None else json.dumps(dependencies),
            scope_genre=scope_genre, implementation_notes=implementation_notes or "")

    def get(self, ticket_id: int) -> Ticket:
        row = self._repo.by_id(ticket_id)
        if row is None:
            raise KeyError(f"no ticket {ticket_id}")
        return Ticket(**_decode_row(row))

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
        self._repo.update(ticket_id, status="in_progress", agent=agent)

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
        self._repo.update(ticket_id, status="done", provenance=provenance,
                          provenance_type=provenance_type, diff_lines=diff_lines)

    def mark_deployed(self, ticket_id: int) -> None:
        self._require(ticket_id, ("done",), "deployed")
        self._repo.update(ticket_id, status="deployed")

    def start_qa(self, ticket_id: int) -> None:
        self._require(ticket_id, ("deployed",), "qa_testing")
        self._repo.update(ticket_id, status="qa_testing")

    def qa_approve(self, ticket_id: int) -> None:
        self._require(ticket_id, ("qa_testing",), "approved")
        self._repo.update(ticket_id, status="approved")

    def qa_reject(self, ticket_id: int, bug_markdown: str) -> None:
        """QA found a bug: bounce the ticket back to `open` carrying a markdown bug report
        (what failed + repro + screenshot links) appended to its description, and clear the
        agent so a fresh build agent re-claims it."""
        self._require(ticket_id, ("qa_testing",), "open")
        t = self.get(ticket_id)
        stamp = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())
        report = (t.description or "").rstrip()
        report = (report + "\n\n" if report else "") + f"## QA bug (rejected {stamp})\n\n{bug_markdown.strip()}\n"
        self._repo.update(ticket_id, status="open", agent=None, description=report)

    # ---- queries ---------------------------------------------------------------------
    def open_waves(self) -> list[int]:
        """Waves that still have buildable tickets, ascending — the swarm driver's
        wave-serialization order (parallel within a wave, waves in sequence). A QA-bounced
        ticket (back to `open`) re-opens its wave."""
        return [r["wave"] for r in self._repo.distinct_waves(_BUILDABLE)]

    def open_tickets(self, wave: int) -> list[Ticket]:
        return [Ticket(**_decode_row(r)) for r in self._repo.rows_in_wave(wave, _BUILDABLE)]

    def buildable_count(self) -> int:
        """Number of tickets Stage 3 can actually build: a real (non-empty) acceptance
        AND definition of done. Empty-string acceptance/dod don't count — they'd be hollow
        and `mark_done` (which enforces DoD) couldn't verify them. This is the mechanical
        gate that proves Stage 2 PERSISTED its tickets, not just emitted ticket events."""
        rows = self._repo.acceptance_dod_rows()
        return sum(1 for r in rows if (r["acceptance"] or "").strip() and (r["dod"] or "").strip())

    def depth_ok(self, v1_screen_ids: Optional[list] = None,
                genres: Optional[list] = None) -> tuple[bool, list[str]]:
        """SOF-100: the depth gate, separate from (and in addition to) `buildable_count()`'s
        bare-hollow check. See `tickets_meet_depth_bar` for what it actually checks."""
        return tickets_meet_depth_bar(self.all_tickets(), v1_screen_ids, genres)

    def done_tickets(self) -> list[Ticket]:
        """Tickets that passed the hollow-done gate — `done` and everything beyond it
        (deployed/qa_testing/approved). Stage-3 proof counts these."""
        return [Ticket(**_decode_row(r)) for r in self._repo.rows_by_status(_BUILT_OR_BEYOND)]

    def reset_in_progress_tickets(self) -> int:
        """Reset all 'in_progress' tickets back to 'open', clearing the agent assignment.
        Called on resume/retry so a crashed swarm re-dispatches orphaned in-flight tickets."""
        return self._repo.bulk_reset_in_progress()

    def all_approved(self) -> bool:
        """True when at least one ticket exists and every ticket is `approved` — the
        QA-complete gate for Stage 3 (set by the QA agent's qa_approve calls)."""
        rows = self._repo.status_rows()
        return bool(rows) and all(r["status"] == "approved" for r in rows)

    def all_tickets(self) -> list[Ticket]:
        """Every ticket regardless of status, in wave then id order — the kanban projection."""
        return [Ticket(**_decode_row(r)) for r in self._repo.all_rows()]

    def render_markdown(self) -> str:
        rows = self._repo.all_rows()
        lines = ["# Tickets", "", "| # | wave | status | title | acceptance |", "|---|---|---|---|---|"]
        for r in rows:
            lines.append(f"| {r['id']} | {r['wave']} | {r['status']} | {r['title']} | {r['acceptance']} |")
        return "\n".join(lines) + "\n"


def _normalize_genre(s: str) -> str:
    """Case/whitespace/punctuation-insensitive form — same normalization as artifacts.py's
    genre-heading matching, so 'AP/AR' on a ticket and 'AP / AR' in the PRD compare equal."""
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()


def tickets_meet_depth_bar(tickets: list[Ticket], v1_screen_ids: Optional[list] = None,
                          genres: Optional[list] = None) -> tuple[bool, list[str]]:
    """SOF-100: the ticket depth gate — mechanical presence/structure checks only, same spirit as
    SOF-96/99's PRD and mockup gates. What it checks:
    - `goal`/`acceptance`/`dod` are real, non-empty text on every ticket.
    - `design_refs`/`dependencies` were explicitly addressed (not SQL NULL) — `[]` is an honest
      answer for a ticket with no screen or no dependency, and passes; never having been set does
      not.
    - When `design_refs` is non-empty, every ID must exist in the real v1 screen catalog — a
      reference to a screen that was never built (typo or hallucination) fails the gate.
    - `dependencies` entries are NOT validated against real ticket IDs — deliberately lenient,
      since tickets are written before IDs are assigned; a title-level reference is enough.
    - When `genres` (the project's selected scope genres) is non-empty, at least one ticket must
      carry a matching `scope_genre` for EACH selected genre — the per-area coverage check.
    Depth/quality of what's IN each field stays the writing agent's judgment; this only catches a
    ticket that skipped a required field outright."""
    reasons = []
    v1_ids = set(v1_screen_ids or [])
    covered_genres = set()
    for t in tickets:
        label = f"ticket #{t.id} ({t.title!r})"
        if not (t.goal or "").strip():
            reasons.append(f"{label}: missing goal")
        if not (t.acceptance or "").strip():
            reasons.append(f"{label}: missing acceptance criteria")
        if not (t.dod or "").strip():
            reasons.append(f"{label}: missing definition of done")
        if t.design_refs is None:
            reasons.append(f"{label}: design_refs was never addressed (use [] if no screen applies)")
        else:
            bad_refs = [r for r in t.design_refs if r not in v1_ids]
            if bad_refs:
                reasons.append(f"{label}: design_refs references nonexistent v1 screen(s): {', '.join(bad_refs)}")
        if t.dependencies is None:
            reasons.append(f"{label}: dependencies was never addressed (use [] if none)")
        if t.scope_genre:
            covered_genres.add(_normalize_genre(t.scope_genre))
    for genre in (genres or []):
        name = (genre or "").strip()
        if name and _normalize_genre(name) not in covered_genres:
            reasons.append(f"no ticket carries scope_genre for selected genre: {name}")
    return (len(reasons) == 0, reasons)
