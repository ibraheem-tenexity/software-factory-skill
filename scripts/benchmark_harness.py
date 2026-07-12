#!/usr/bin/env python3
"""SOF-92 benchmark harness: a headless, unattended E2E factory run.

Drives the whole loop against a live console over HTTP — no browser:
  1. Authenticate as the pre-provisioned sf-benchmark identity (see get_benchmark_session).
  2. Create a draft (owner resolves from the session, per the SOF-92-locked convention).
  3. Drive the onboarding concierge interview via POST /converse — an LLM plays the customer,
     answering from a reference brief — until a product brief is finalized.
  4. Hand off (POST /promote) and poll to a terminal state (deployed / budget-stopped / crashed /
     blocked / timeout).
  5. Write a structured friction report as JSON, one file per run — the exact report{} shape
     `software_factory.run_autopsy.classify_run` already consumes (SOF-93/PR #330), reusing that
     module's own `build_report_from_console` adapter rather than re-deriving the schema.

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
  SF_BENCHMARK_TIMEOUT_HOURS  wall-clock cap on the poll loop (default: 6, matches run_autopsy's
                              own TIMEOUT_HOURS so a stalled run gets classified the same way)
  SF_BENCHMARK_REPORTS_DIR  where per-run JSON reports are written (default: benchmark_reports/)
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone

import httpx

sys.path.insert(0, "src")

from software_factory.constants import OPENROUTER_BASE_URL, CONCIERGE_KIMI_MODEL  # noqa: E402
from software_factory.run_autopsy import (  # noqa: E402
    BENCHMARK_OWNER, build_report_from_console, classify_run,
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


class HarnessError(RuntimeError):
    """A harness-specific failure with an honest, actionable reason — never a guess."""


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


def write_report(list_entry: dict, status: dict, events: list, out_dir: str,
                 extra_friction_findings: list | None = None):
    """Build the report via run_autopsy's own adapter (same shape classify_run already consumes,
    zero re-derivation), write it to <out_dir>/<project_id>.json, and return the classification
    for a human-readable console line."""
    report = build_report_from_console(list_entry, status, events, env="staging")
    if extra_friction_findings:
        report["friction_findings"].extend(extra_friction_findings)
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, f"{report['run']['project_id']}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    record = classify_run(report)
    print(f"[benchmark] {record.project_id}: {record.classification} — {record.reason} "
          f"(${record.cost_usd:.2f}/${record.ceiling_usd:.2f} ceiling) -> {path}")
    return record


def _fetch_current_state(client: httpx.Client, base_url: str, project_id: str) -> tuple[dict, dict, list]:
    projects = _get_json(client, f"{base_url}/api/projects")["projects"]
    list_entry = next((p for p in projects if p["project_id"] == project_id), {})
    status = _get_json(client, f"{base_url}/api/projects/{project_id}")
    events = _get_json(client, f"{base_url}/api/projects/{project_id}/events")["events"]
    return list_entry, status, events


def main() -> None:
    parser = argparse.ArgumentParser(description="SOF-92 headless benchmark harness")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--brief", default=DEFAULT_BRIEF)
    args = parser.parse_args()

    brief = load_reference_brief(args.brief)
    brief_title = os.path.splitext(os.path.basename(args.brief))[0].replace("_", " ")

    with httpx.Client(timeout=30) as client:
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
            write_report(list_entry, status, events, REPORTS_DIR, extra_friction_findings=[{
                "severity": "high", "type": "interview_non_convergence",
                "finding": f"customer-simulator did not reach a finalized brief in {MAX_INTERVIEW_TURNS} turns",
                "action": "review transcript (no dedicated GET route exists; see recent_events)",
                "transcript": transcript,
            }])
            return

        print(f"[benchmark] {project_id}: brief finalized, handing off")
        promote(client, args.base_url, project_id)

        list_entry, status, events = poll_to_terminal(client, args.base_url, project_id)
        write_report(list_entry, status, events, REPORTS_DIR)


if __name__ == "__main__":
    main()
