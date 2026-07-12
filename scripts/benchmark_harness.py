#!/usr/bin/env python3
"""SOF-92 benchmark harness: a headless, unattended E2E factory run.

Drives the whole loop against a live console over HTTP — no browser:
  1. Authenticate as the pre-provisioned sf-benchmark identity (see get_benchmark_session).
  2. Create a draft (owner resolves from the session, per the SOF-92-locked convention).
  3. Drive the onboarding concierge interview via POST /converse — an LLM plays the customer,
     answering from a reference brief — until a product brief is finalized.
  4. Hand off (POST /promote) and poll to a terminal state (deployed / budget-stopped / crashed /
     blocked / timeout).
  5. Classify + file: build the report via `run_autopsy.build_report_from_console` and hand it to
     `run_autopsy.autopsy_and_file` DIRECTLY, in-process — this both writes a durable Postgres
     ledger row for EVERY terminal run (including DEPLOYED, the positive "the cron actually fired"
     signal) and files/comments on Linear for anything that isn't DEPLOYED. Also writes the same
     report as JSON to SF_BENCHMARK_REPORTS_DIR/<project_id>.json — the file-path contract
     run_autopsy_scan.py's docstring already anticipates.
  6. Self-cleanup: archive the benchmark project and, if it provisioned a deploy-DB, tear it down
     directly via `deploy_db.teardown()` (the same vetted function the console's own reaper uses)
     — an unattended, disposable-project loop must not silt up the environment.

An internal wall-clock alarm (SIGALRM) guards the whole run: a hang self-terminates from INSIDE
the process (raising HarnessTimeout) well before any external kill could apply, so cleanup +
reporting still run even when something further downstream never returns.

Usage: python3 scripts/benchmark_harness.py [--base-url URL] [--brief PATH]

Env:
  SF_BENCHMARK_BASE_URL     console base URL (default: staging)
  SF_BENCHMARK_EMAIL        benchmark identity email (default: run_autopsy.BENCHMARK_OWNER)
  SF_BENCHMARK_PASSWORD     required — the ONE seam this harness never mints itself (SOF-148).
  OPENROUTER_API_KEY        required — powers the customer-simulator LLM.
  SF_BENCHMARK_SIM_MODEL    simulator model id (default: the concierge's own OpenRouter fallback)
  SF_BENCHMARK_BUDGET       per-run budget_ceiling (default: 30, per operator directive 2026-07-10)
  SF_BENCHMARK_MAX_TURNS    interview turn cap before giving up (default: 20)
  SF_BENCHMARK_POLL_SECS    poll interval while waiting for a terminal state (default: 30)
  SF_BENCHMARK_TIMEOUT_HOURS  wall-clock cap on the poll loop AND the internal SIGALRM safety net
                              (default: 6, matches run_autopsy's own TIMEOUT_HOURS so a stalled
                              run gets classified the same way)
  SF_BENCHMARK_REPORTS_DIR  where per-run JSON reports are written (default: benchmark_reports/)
  DATABASE_URL / SF_STATE_DB_URL   required for the autopsy dedup ledger (RunAutopsyStore)
  LINEAR_API_KEY / SF_LINEAR_TEAM_ID   optional — filing degrades honestly without them
  RAILWAY_TOKEN             required to tear down a provisioned deploy-DB (scoped to the
                            software-factory-projects STAGING environment)
"""
from __future__ import annotations

import argparse
import json
import os
import signal
import sys
import time
import traceback
from datetime import datetime, timezone

import httpx

sys.path.insert(0, "src")

from software_factory import deploy_db  # noqa: E402
from software_factory import linear_filer  # noqa: E402
from software_factory.constants import OPENROUTER_BASE_URL, CONCIERGE_KIMI_MODEL  # noqa: E402
from software_factory.run_autopsy import (  # noqa: E402
    BENCHMARK_OWNER, RunAutopsyStore, autopsy_and_file, build_report_from_console, classify_run,
)

DEFAULT_BASE_URL = os.environ.get(
    "SF_BENCHMARK_BASE_URL", "https://factory-console-staging.up.railway.app")
DEFAULT_BRIEF = "tests/fixtures/benchmark_briefs/quote_followup_automation.md"
SIM_MODEL = os.environ.get("SF_BENCHMARK_SIM_MODEL", CONCIERGE_KIMI_MODEL)
MAX_INTERVIEW_TURNS = int(os.environ.get("SF_BENCHMARK_MAX_TURNS", "20"))
POLL_INTERVAL_SECS = int(os.environ.get("SF_BENCHMARK_POLL_SECS", "30"))
WALL_CLOCK_TIMEOUT_HOURS = float(os.environ.get("SF_BENCHMARK_TIMEOUT_HOURS", "6"))
REPORTS_DIR = os.environ.get("SF_BENCHMARK_REPORTS_DIR", "benchmark_reports")
BUDGET_CEILING = float(os.environ.get("SF_BENCHMARK_BUDGET", "30"))
# A hang must self-terminate from inside the process before any external kill could matter (an
# external kill runs no Python cleanup) — arm the alarm past the poll loop's own deadline, not at
# the same instant, so poll_to_terminal's own honest timeout classification gets first say.
ALARM_BUFFER_SECS = 600


class HarnessError(RuntimeError):
    """A harness-specific failure with an honest, actionable reason — never a guess."""


class HarnessTimeout(RuntimeError):
    """Raised by the internal SIGALRM handler — a hang self-terminating from inside the process."""


def _alarm_handler(signum, frame) -> None:
    raise HarnessTimeout(
        f"harness exceeded its internal wall-clock cap ({WALL_CLOCK_TIMEOUT_HOURS}h + "
        f"{ALARM_BUFFER_SECS}s buffer) — self-terminating so cleanup/reporting still run")


def get_benchmark_session(client: httpx.Client, base_url: str) -> None:
    """Authenticate as the pre-provisioned sf-benchmark identity (mutates client's cookies).

    This is the ONE deliberate seam: the harness AUTHENTICATES as an operator-provisioned identity,
    it never mints one (see SOF-92/SOF-148 discussion — self-provisioning would make a benchmark
    script perform a privileged, stateful users-table mutation, which is worse hygiene than a
    one-time manual/admin setup). Swap this function's body, nothing else, once the provisioning
    path is finalized."""
    email = os.environ.get("SF_BENCHMARK_EMAIL", BENCHMARK_OWNER)
    password = os.environ.get("SF_BENCHMARK_PASSWORD", "")
    if not password:
        raise HarnessError(
            f"SF_BENCHMARK_PASSWORD is not set — the {email} identity must be provisioned "
            "(admin-invited with a password, status=active) before the harness can authenticate. "
            "See SOF-148/SOF-92 for the provisioning decision."
        )
    resp = client.post(f"{base_url}/api/auth/password", json={"email": email, "password": password})
    if resp.status_code != 200:
        raise HarnessError(f"benchmark login failed ({resp.status_code}): {resp.text[:300]}")


def load_reference_brief(path: str) -> str:
    with open(path, encoding="utf-8") as f:
        return f.read()


def simulate_customer_reply(brief: str, question: str, suggested: list, transcript: list) -> str:
    """Ask an LLM to play the customer, answering the concierge's latest question using only the
    reference brief as ground truth — never inventing facts the brief doesn't contain."""
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        raise HarnessError("OPENROUTER_API_KEY is not set — required for the customer-simulator")
    history_text = "\n".join(
        f"{'Concierge' if t['role'] == 'concierge' else 'You'}: {t['text']}" for t in transcript)
    suggestions = "\n".join(f"- {s.get('response', '')}" for s in suggested) if suggested else ""
    prompt = (
        "You are the customer being onboarded onto a software-build platform. Answer the "
        "concierge's question truthfully and concisely, using ONLY the reference brief below as "
        "your company's ground truth. Do not invent facts the brief doesn't contain — if it's not "
        "in the brief, say you're not sure or give a reasonable, clearly-hedged guess.\n\n"
        f"=== REFERENCE BRIEF ===\n{brief}\n=== END BRIEF ===\n\n"
        f"=== CONVERSATION SO FAR ===\n{history_text}\n=== END CONVERSATION ===\n\n"
        f"Concierge's latest question:\n{question}\n\n"
        + (f"Suggested quick-replies (prefer one verbatim if it fits):\n{suggestions}\n\n"
           if suggestions else "")
        + "Reply as the customer, in 1-4 sentences."
    )
    resp = httpx.post(
        f"{OPENROUTER_BASE_URL}/chat/completions",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={"model": SIM_MODEL, "messages": [{"role": "user", "content": prompt}]},
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"].strip()


def create_benchmark_draft(client: httpx.Client, base_url: str, brief_title: str) -> str:
    date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    name = f"[bench] {brief_title} {date}"
    resp = client.post(f"{base_url}/api/drafts", json={"project_name": name, "budget": BUDGET_CEILING})
    resp.raise_for_status()
    return resp.json()["project_id"]


def run_interview(client: httpx.Client, base_url: str, project_id: str, brief: str) -> tuple[bool, list]:
    """Drive the onboarding concierge interview via /converse (NOT /api/chat — that's the
    post-onboarding ChatDock rail, a different surface with a different persisted history; there
    is no dedicated GET route for the onboarding conversation, so the transcript this function
    returns is the only record of it). Returns (finalized, transcript); finalized is False if
    MAX_INTERVIEW_TURNS is exhausted first — an honest non-convergence, not an exception, since the
    caller decides what to do with it."""
    transcript: list[dict] = []
    message = ""  # first call: empty message = "the agent opens" (console.py's DbConversation.turn)
    for _ in range(MAX_INTERVIEW_TURNS):
        resp = client.post(f"{base_url}/api/projects/{project_id}/converse", json={"message": message})
        resp.raise_for_status()
        turn = resp.json()
        question = turn["response"]
        transcript.append({"role": "concierge", "text": question})

        brief_resp = client.get(f"{base_url}/api/projects/{project_id}/brief")
        brief_resp.raise_for_status()
        if brief_resp.json().get("brief_markdown"):
            return True, transcript

        message = simulate_customer_reply(brief, question, turn.get("suggested_responses") or [], transcript)
        transcript.append({"role": "customer", "text": message})
    return False, transcript


def promote(client: httpx.Client, base_url: str, project_id: str) -> None:
    resp = client.post(f"{base_url}/api/projects/{project_id}/promote", json={})
    if resp.status_code >= 400:
        raise HarnessError(f"hand-off (promote) failed ({resp.status_code}): {resp.text[:300]}")


def _is_terminal(list_entry: dict, status: dict) -> bool:
    """Mirrors scripts/run_autopsy_scan.py's own terminal check — deliberately duplicated (3
    lines) rather than imported from a script not meant to be a library."""
    return bool(status.get("done") or status.get("crashed_at_node") or status.get("held")
                or list_entry.get("budget_stopped"))


def _get_json(client: httpx.Client, url: str, *, retries: int = 3, backoff: float = 5.0) -> dict:
    """GET with a short retry-with-backoff — live testing hit a one-off malformed/error response
    mid-poll (staging redeployed under the run); a multi-hour unattended poll must survive a
    transient blip like that instead of crashing the whole harness run on it."""
    last_exc: Exception | None = None
    for attempt in range(retries):
        try:
            resp = client.get(url)
            resp.raise_for_status()
            return resp.json()
        except (httpx.HTTPError, KeyError, ValueError) as exc:
            last_exc = exc
            if attempt < retries - 1:
                time.sleep(backoff)
    raise HarnessError(f"GET {url} failed after {retries} attempts: {last_exc}")


def find_active_benchmark_run(client: httpx.Client, base_url: str) -> str | None:
    """Refuse to double-launch: return the project_id of an already-in-progress benchmark-owned
    run, if any. A cron scheduler that double-fires or overlaps a still-running benchmark would
    otherwise silently spawn a second real, cost-incurring run — this happened once during live
    testing (a killed local process left its already-launched server-side run going unnoticed,
    burning $25 unattended) — so this check is a mechanical prerequisite, not optional polish."""
    email = os.environ.get("SF_BENCHMARK_EMAIL", BENCHMARK_OWNER)
    projects = _get_json(client, f"{base_url}/api/projects")["projects"]
    for p in projects:
        if p.get("archived") or p.get("budget_stopped"):
            continue
        is_ours = (p.get("owner") or "") == email or (p.get("name") or "").startswith("[bench]")
        if not is_ours:
            continue
        status = _get_json(client, f"{base_url}/api/projects/{p['project_id']}")
        if status.get("done") or status.get("crashed_at_node"):
            continue
        return p["project_id"]
    return None


def poll_to_terminal(client: httpx.Client, base_url: str, project_id: str) -> tuple[dict, dict, list]:
    """Poll both the list endpoint (budget_stopped — SOF-145: the detail endpoint lies null) and
    the detail endpoint (crashed_at_node/done/held/auto_resume_count) until a terminal signal or
    the wall-clock cap. Returns whatever was last observed either way — classify_run's own
    TIMEOUT_HOURS logic (fed by timings.created_at) makes the honest call if nothing terminal
    happened, this loop does not guess."""
    deadline = time.time() + WALL_CLOCK_TIMEOUT_HOURS * 3600
    while True:
        projects = _get_json(client, f"{base_url}/api/projects")["projects"]
        list_entry = next((p for p in projects if p["project_id"] == project_id), {})
        status = _get_json(client, f"{base_url}/api/projects/{project_id}")
        if _is_terminal(list_entry, status) or time.time() >= deadline:
            events = _get_json(client, f"{base_url}/api/projects/{project_id}/events")["events"]
            return list_entry, status, events
        time.sleep(POLL_INTERVAL_SECS)


def _fetch_current_state(client: httpx.Client, base_url: str, project_id: str) -> tuple[dict, dict, list]:
    projects = _get_json(client, f"{base_url}/api/projects")["projects"]
    list_entry = next((p for p in projects if p["project_id"] == project_id), {})
    status = _get_json(client, f"{base_url}/api/projects/{project_id}")
    events = _get_json(client, f"{base_url}/api/projects/{project_id}/events")["events"]
    return list_entry, status, events


def report_and_file(list_entry: dict, status: dict, events: list, project_id: str,
                    extra_friction_findings: list | None = None):
    """Build the report via run_autopsy's own adapter (same shape classify_run already consumes,
    zero re-derivation), write it to REPORTS_DIR/<project_id>.json, and hand it directly to
    `autopsy_and_file` — a durable Postgres ledger row for EVERY terminal run (the positive "the
    cron actually fired" signal, present even for DEPLOYED) plus a filed/commented Linear ticket
    for anything that isn't DEPLOYED. Returns the AutopsyRecord."""
    report = build_report_from_console(list_entry, status, events, env="staging")
    if extra_friction_findings:
        report["friction_findings"].extend(extra_friction_findings)
    os.makedirs(REPORTS_DIR, exist_ok=True)
    path = os.path.join(REPORTS_DIR, f"{project_id}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    store = RunAutopsyStore()
    record = autopsy_and_file(report, store)
    print(f"[benchmark] {record.project_id}: {record.classification} — {record.reason} "
          f"(${record.cost_usd:.2f}/${record.ceiling_usd:.2f} ceiling) -> {path}")
    return record


def _best_effort_report(client: httpx.Client, base_url: str, project_id: str | None, *, note: str) -> None:
    """Called from the harness's own crash/timeout handlers: assemble whatever state exists and
    file it, so a harness-level failure (not just a pipeline-level one) still leaves a durable
    signal. If classify_run's own inference would land on UNKNOWN (a genuine code crash early in
    the run, before any pipeline-level terminal signal exists), that's not loud enough on its own —
    file a distinct harness-error ticket directly so it's never silently swallowed."""
    if not project_id:
        print(f"[benchmark] no project was created yet — nothing to report ({note})")
        return
    try:
        list_entry, status, events = _fetch_current_state(client, base_url, project_id)
    except Exception as exc:
        print(f"[benchmark] {project_id}: could not fetch state for the crash/timeout report: {exc}")
        linear_filer.create_issue(
            f"[benchmark] harness error on {project_id} — could not even fetch state",
            f"**Note:** {note}\n\n**Follow-up fetch also failed:** {exc}", priority=2)
        return
    record = report_and_file(list_entry, status, events, project_id, extra_friction_findings=[{
        "severity": "high", "type": "harness_error", "finding": note, "action": "review harness logs",
    }])
    if record.classification == "UNKNOWN":
        # classify_run had no pipeline-level terminal signal to go on — that's expected for an
        # early harness crash, but UNKNOWN alone files no ticket. File one directly so a genuine
        # code bug is never silent just because the pipeline itself never got far enough to fail.
        linear_filer.create_issue(
            f"[benchmark] harness error on {project_id}",
            f"**Note:** {note}\n\n(classify_run returned UNKNOWN — no pipeline-level terminal "
            "signal yet, so this is a harness-side failure, not a pipeline one.)", priority=2)


def cleanup_benchmark_project(client: httpx.Client, base_url: str, project_id: str) -> None:
    """Self-cleanup for a disposable benchmark run: tear down its deploy-DB (if it provisioned
    one — most runs budget-stop before reaching stage-3 deploy and never do) via the SAME vetted
    `deploy_db.teardown()` the console's own reaper uses, then archive the project. Deletes only
    the resource_id THIS run's own context/deploy-db.json artifact names — never a scan or a
    shared/default DB, so it can't hit the shared-DB exclusivity bug found in the prod sweep.
    Best-effort: a cleanup hiccup must never raise past the harness's own finally-path."""
    try:
        resp = client.get(f"{base_url}/api/projects/{project_id}/artifact",
                         params={"path": "context/deploy-db.json"})
        if resp.status_code == 200:
            info = json.loads(resp.json()["content"])
            service_id = (info.get("service_id") or "").strip()
            if service_id:
                result = deploy_db.teardown(service_id, volume_id=info.get("volume_id", ""))
                print(f"[benchmark] {project_id}: deploy-DB teardown {result}")
        elif resp.status_code != 404:
            print(f"[benchmark] {project_id}: deploy-db.json fetch returned {resp.status_code}, skipping DB teardown")
    except Exception as exc:
        print(f"[benchmark] {project_id}: deploy-DB teardown failed (non-fatal): {exc}")

    try:
        resp = client.delete(f"{base_url}/api/projects/{project_id}")
        print(f"[benchmark] {project_id}: archived ({resp.status_code})")
    except Exception as exc:
        print(f"[benchmark] {project_id}: archive failed (non-fatal): {exc}")


def main() -> None:
    parser = argparse.ArgumentParser(description="SOF-92 headless benchmark harness")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--brief", default=DEFAULT_BRIEF)
    args = parser.parse_args()

    brief = load_reference_brief(args.brief)
    brief_title = os.path.splitext(os.path.basename(args.brief))[0].replace("_", " ")

    client = httpx.Client(timeout=30)
    project_id: str | None = None
    try:
        signal.signal(signal.SIGALRM, _alarm_handler)
        signal.alarm(int(WALL_CLOCK_TIMEOUT_HOURS * 3600) + ALARM_BUFFER_SECS)

        get_benchmark_session(client, args.base_url)

        active = find_active_benchmark_run(client, args.base_url)
        if active:
            print(f"[benchmark] refusing to start — {active} is already an active benchmark run; "
                  "a cron-driven harness must not overlap runs. Exiting without creating a new one.")
            return

        project_id = create_benchmark_draft(client, args.base_url, brief_title)
        print(f"[benchmark] created draft {project_id}")

        finalized, transcript = run_interview(client, args.base_url, project_id, brief)
        if not finalized:
            print(f"[benchmark] {project_id}: interview did not finalize a product brief within "
                  f"{MAX_INTERVIEW_TURNS} turns — not handing off; run stays a draft")
            list_entry, status, events = _fetch_current_state(client, args.base_url, project_id)
            report_and_file(list_entry, status, events, project_id, extra_friction_findings=[{
                "severity": "high", "type": "interview_non_convergence",
                "finding": f"customer-simulator did not reach a finalized brief in {MAX_INTERVIEW_TURNS} turns",
                "action": "review transcript (no dedicated GET route exists; see recent_events)",
                "transcript": transcript,
            }])
            return

        print(f"[benchmark] {project_id}: brief finalized, handing off")
        promote(client, args.base_url, project_id)

        list_entry, status, events = poll_to_terminal(client, args.base_url, project_id)
        report_and_file(list_entry, status, events, project_id)
    except HarnessTimeout as exc:
        print(f"[benchmark] {project_id or '(no project yet)'}: TIMEOUT — {exc}")
        _best_effort_report(client, args.base_url, project_id, note=str(exc))
    except Exception as exc:
        print(f"[benchmark] {project_id or '(no project yet)'}: harness crashed — {exc}")
        _best_effort_report(client, args.base_url, project_id,
                            note=f"{exc}\n\n{traceback.format_exc()}")
    finally:
        signal.alarm(0)
        if project_id:
            try:
                cleanup_benchmark_project(client, args.base_url, project_id)
            except Exception as exc:
                print(f"[benchmark] {project_id}: cleanup failed: {exc}")
        client.close()


if __name__ == "__main__":
    main()
