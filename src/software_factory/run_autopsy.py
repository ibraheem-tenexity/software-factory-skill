"""Run autopsy (SOF-93): classify a terminal benchmark run, dedup against known failure
signatures, and file/comment on a Linear ticket.

`classify_run` consumes the SOF-92/SOF-93 report contract agreed with r8ggdcx6 (2026-07-10):
    run{project_id,name,env}
    terminal{reason,detail,reached_deploy,deploy_url}
    budget{ceiling_usd,spent_usd,launch_reserve_usd,stopped_at_phase,stopped_at_stage}
    signals{budget_stopped,crashed_at_node,auto_resume_count,held,done}
    pipeline_progress{phases_reached,stage1_done,stage2_done}
    timings{phase_first_seen_secs,wall_secs}
    friction_findings[]
    recent_events[]
    log_excerpt (failing-stage tail, 60 lines / 4000 chars, front-truncated)
Once the SOF-92 harness lands and writes this report as JSON, the scan script swaps its report
source from `build_report_from_console` (the interim, API-polling adapter below) to reading those
files directly — `classify_run` itself does not change.

Minimum Machinery: this is a consumer of run reports, not a new pipeline — a small module the
scan script (or eventually the poller) calls, not a service.
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass

from .repositories._exec import GlobalExec
from .repositories.run_autopsy import RunAutopsyRepository

BENCHMARK_OWNER = "sf-benchmark@tenexity.ai"

TIMEOUT_HOURS = 6.0     # harness gives up waiting past this with no terminal signal
STALL_HOURS = 1.0       # sub-classifies TIMEOUT: no activity this long = a stall, not just slow

LOG_EXCERPT_MAX_LINES = 60
LOG_EXCERPT_MAX_CHARS = 4000

_NUM_RE = re.compile(r"\d+(\.\d+)?")
_SIGNED_URL_QUERY_RE = re.compile(r"(\?|&)(token|signature)=[^\s&]+", re.IGNORECASE)


def _redact_signed_urls(text: str) -> str:
    """Artifact events carry signed Supabase Storage download URLs (product-brief.md etc) — the
    query-string token grants read access to that file. Never let it leave the console into a
    third-party system (a Linear ticket body): strip the token/signature query param, keep the
    rest of the URL for context."""
    return _SIGNED_URL_QUERY_RE.sub(r"\1\2=[redacted]", text)


def _normalize(text: str) -> str:
    """Collapse volatile numbers/whitespace so two occurrences of "the same" failure share a
    signature even when the specific dollar amount, timestamp, or id differs."""
    text = _NUM_RE.sub("#", text or "")
    return " ".join(text.split()).strip().lower()


def _log_excerpt_from_events(events: list[dict]) -> str:
    """Interim proxy for the harness's real project.log tail: per r8ggdcx6 (2026-07-10), there is
    no raw-log API endpoint for a polling-only consumer, so recent_events[] stands in until the
    harness writes log_excerpt directly from project.log."""
    lines = [f"{e.get('type')}: {e.get('payload')}" for e in events[-LOG_EXCERPT_MAX_LINES:]]
    text = _redact_signed_urls("\n".join(lines))
    if len(text) > LOG_EXCERPT_MAX_CHARS:
        text = text[-LOG_EXCERPT_MAX_CHARS:]
    return text


def build_report_from_console(list_entry: dict, status: dict, events: list[dict],
                              *, env: str = "staging") -> dict:
    """INTERIM adapter: assembles the agreed report shape from the console's live API (a
    /api/projects list entry + a /api/projects/{id} detail + its /events) — until the SOF-92
    harness writes this report directly from project.log. list_entry carries budget_stopped/
    created_at (list-endpoint-only fields, SOF-145: the detail endpoint's budget_stopped lies with
    null); status carries crashed_at_node/deps_*/budget_ceiling/held (detail-only fields)."""
    stage = status.get("stage") or list_entry.get("stage") or 1
    budget_blocker = next(
        (e for e in events if e.get("type") == "blocker"
         and "budget" in (e.get("payload", {}).get("what") or "").lower()),
        None)
    crash_blockers = [e for e in events if e.get("type") == "blocker"]
    created_at = list_entry.get("created_at") or (events[0]["ts"] if events else time.time())

    return {
        "run": {"project_id": status.get("project_id") or list_entry.get("project_id"),
               "name": status.get("name") or list_entry.get("name"), "env": env},
        "terminal": {
            "reached_deploy": bool(status.get("done") and status.get("deploy_url")),
            "deploy_url": status.get("deploy_url"),
        },
        "budget": {
            "ceiling_usd": float(status.get("budget_ceiling") or 0.0),
            "spent_usd": float(status.get("spent_usd") or list_entry.get("spent_usd") or 0.0),
            "launch_reserve_usd": 5.0,  # SF_STAGE_RESERVE's default — see console.py's _launch_stage
            "stopped_at_phase": status.get("phase") or list_entry.get("phase"),
            "stopped_at_stage": stage,
        },
        "signals": {
            "budget_stopped": bool(list_entry.get("budget_stopped") or budget_blocker),
            "crashed_at_node": status.get("crashed_at_node") or None,
            "auto_resume_count": status.get("auto_resume_count") or 0,
            "held": bool(status.get("held") or list_entry.get("held")),
            "done": bool(status.get("done")),
        },
        "pipeline_progress": {
            "stage1_done": bool(status.get("stage1_done")),
            "stage2_done": bool(status.get("stage2_done")),
            "deps_required": status.get("deps_required") or [],
            "deps_satisfied": bool(status.get("deps_satisfied")),
        },
        "timings": {
            "created_at": created_at,
            "wall_secs": max(0.0, time.time() - created_at),
            "last_event_at": events[-1]["ts"] if events else created_at,
        },
        "friction_findings": [],   # populated by the harness once it lands; honestly empty until then
        "recent_events": events,
        "log_excerpt": _log_excerpt_from_events(events),
        # the last blocker's text, if any — used to build the CRASHED/BLOCKED signature fragment
        "_last_blocker_what": crash_blockers[-1]["payload"]["what"] if crash_blockers else None,
    }


@dataclass
class AutopsyRecord:
    project_id: str
    classification: str          # DEPLOYED | BUDGET_STOPPED | CRASHED | BLOCKED | TIMEOUT | UNKNOWN
    signature: str                # "" for DEPLOYED/UNKNOWN — dedup/tickets don't apply
    stage: int
    reason: str                   # one-line human reason
    cost_usd: float
    ceiling_usd: float
    log_excerpt: str


def classify_run(report: dict, *, now_ts: float | None = None) -> AutopsyRecord:
    """Pure classification — no DB, no network. `report` is shaped per this module's docstring
    (either build_report_from_console's interim output, or the harness's real JSON once it lands —
    same field names, so this function does not change at the swap)."""
    now_ts = time.time() if now_ts is None else now_ts
    pid = report["run"]["project_id"]
    stage = report["budget"]["stopped_at_stage"]
    cost = report["budget"]["spent_usd"]
    ceiling = report["budget"]["ceiling_usd"]
    excerpt = report.get("log_excerpt", "")
    sig = report.get("signals", {})

    if report["terminal"]["reached_deploy"]:
        return AutopsyRecord(pid, "DEPLOYED", "", stage, "deployed successfully", cost, ceiling, excerpt)

    if sig.get("budget_stopped"):
        reason = report.get("_last_blocker_what") or "budget stopped"
        return AutopsyRecord(pid, "BUDGET_STOPPED", f"stage{stage}:budget", stage, reason, cost, ceiling, excerpt)

    if sig.get("crashed_at_node"):
        node = sig["crashed_at_node"]
        blocker_text = report.get("_last_blocker_what")
        fragment = _normalize(blocker_text) if blocker_text else "no-blocker-text"
        signature = f"stage{stage}:crashed:{node}:{fragment}"
        reason = f"crashed at {node}" + (f" — {blocker_text}" if blocker_text else "")
        return AutopsyRecord(pid, "CRASHED", signature, stage, reason, cost, ceiling, excerpt)

    progress = report.get("pipeline_progress", {})
    if sig.get("held") and progress.get("deps_required") and not progress.get("deps_satisfied"):
        missing = ",".join(sorted(progress["deps_required"]))
        signature = f"stage{stage}:blocked:{_normalize(missing)}"
        return AutopsyRecord(pid, "BLOCKED", signature, stage, f"held on deps: {missing}", cost, ceiling, excerpt)

    timings = report.get("timings", {})
    created_at = timings.get("created_at") or now_ts
    elapsed_hours = (now_ts - created_at) / 3600.0
    if elapsed_hours >= TIMEOUT_HOURS:
        last_event_at = timings.get("last_event_at") or created_at
        stall_hours = (now_ts - last_event_at) / 3600.0
        kind = "stall" if stall_hours >= STALL_HOURS else "timeout"
        signature = f"stage{stage}:{kind}"
        reason = f"no terminal signal after {elapsed_hours:.1f}h" + (
            f", no activity for {stall_hours:.1f}h" if kind == "stall" else "")
        return AutopsyRecord(pid, "TIMEOUT", signature, stage, reason, cost, ceiling, excerpt)

    return AutopsyRecord(pid, "UNKNOWN", "", stage, "still running / no terminal signal", cost, ceiling, excerpt)


class RunAutopsyStore:
    """DB-backed dedup + idempotency ledger. Never in process memory (SOF-116's lesson): a console
    or scan-script restart must not re-file a known failure or reprocess an already-seen run."""

    def __init__(self, repo: RunAutopsyRepository | None = None):
        self._repo = repo if repo is not None else RunAutopsyRepository(GlobalExec())

    def already_processed(self, project_id: str) -> bool:
        return self._repo.already_processed(project_id)

    def mark_processed(self, project_id: str, signature: str, classification: str) -> None:
        self._repo.mark_processed(project_id, signature, classification, time.time())

    def known_signature(self, signature: str) -> dict | None:
        row = self._repo.get_signature(signature)
        return dict(row) if row else None

    def record_occurrence(self, signature: str, classification: str, project_id: str,
                          linear_issue_id: str | None = None,
                          linear_issue_identifier: str | None = None) -> None:
        self._repo.upsert_signature(signature, classification, project_id, time.time(),
                                    linear_issue_id, linear_issue_identifier)


def _ticket_body(record: AutopsyRecord) -> str:
    return (
        f"**Classification:** {record.classification}\n"
        f"**Run:** {record.project_id} (stage {record.stage})\n"
        f"**Cost at failure:** ${record.cost_usd:.2f} / ${record.ceiling_usd:.2f} ceiling\n"
        f"**Reason:** {record.reason}\n\n"
        f"**Log excerpt** (interim: recent events, not the raw log — see run_autopsy.py):\n"
        f"```\n{record.log_excerpt}\n```\n"
    )


def autopsy_and_file(report: dict, store: RunAutopsyStore, *, linear=None) -> AutopsyRecord:
    """The full pipeline for ONE terminal run: classify, dedup against known signatures, file a
    new ticket or comment on the existing one, and record everything durably. `linear` defaults
    to this package's linear_filer module (injectable for testing)."""
    if linear is None:
        from . import linear_filer as linear
    record = classify_run(report)

    if record.classification in ("DEPLOYED", "UNKNOWN"):
        store.mark_processed(record.project_id, record.signature, record.classification)
        return record

    known = store.known_signature(record.signature)
    if known and known.get("linear_issue_id"):
        linear.create_comment(known["linear_issue_id"],
                              f"Seen again on run {record.project_id}, cost ${record.cost_usd:.2f}.")
        store.record_occurrence(record.signature, record.classification, record.project_id)
    else:
        title = f"[autopsy] {record.classification}: {record.reason[:80]}"
        issue = linear.create_issue(title, _ticket_body(record))
        if issue:
            store.record_occurrence(record.signature, record.classification, record.project_id,
                                    issue["id"], issue["identifier"])
        else:
            # Honest degrade (no LINEAR_API_KEY yet, or the API call failed): the signature is
            # STILL recorded (issue ids None) so dedup/occurrence-counting works retroactively the
            # moment a key is provisioned — nothing is lost to the config gap.
            store.record_occurrence(record.signature, record.classification, record.project_id)

    store.mark_processed(record.project_id, record.signature, record.classification)
    return record
