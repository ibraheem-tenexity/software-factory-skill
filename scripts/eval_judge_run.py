#!/usr/bin/env python3
"""SOF-102 — run the eval judge on one completed run and persist the score.

Two modes:
- API mode (real run): `--project-id P --base-url URL --token T` pulls the run's PRD.md, its design
  mockup coverage, and deploy_url from the deployed console, builds the rubric, scores the supplied
  observations, and persists via EvalScoreStore.
- Offline mode (fixtures / a walk producer's output): `--prd-file --mockups-dir --deploy-url` plus
  `--observations walk.json` — no console needed. Used to validate the judge end-to-end at $0.

Observations (what the app actually did) come from `--observations` (a JSON list of
{criterion_id, passed, evidence?, screenshot_url?}). This is the seam the browser-walk PRODUCER
(eval_browser, a separate component) writes — the judge deliberately consumes observations rather
than hard-coding a brittle generic click-scripter (agent judgment over machinery). With no
observations file, every criterion scores as failed 'not exercised' (an honest all-miss baseline,
never a silent pass).

Persistence requires DATABASE_URL/SF_STATE_DB_URL (the eval_scores table). Omit `--no-persist` to write.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from software_factory import artifacts, eval_judge  # noqa: E402


def maybe_judge_after_deploy(project_id: str, base_url: str, token: str,
                             observations: list[dict] | None = None,
                             enabled: bool | None = None) -> dict | None:
    """DORMANT auto-trigger hook (SOF-102) — for the SOF-92 harness / cron to call post-terminal.

    Gated OFF by default (`SF_EVAL_JUDGE` unset → no-op) and DORMANT pending TWO things:
    (1) SOF-148 — staging benchmark runs can't yet reach DEPLOY (GH_TOKEN invalid + OPENROUTER
    unset), so there's nothing deployed to judge; (2) the eval_browser walk PRODUCER (a later PR)
    that supplies real observations — until then a judged run scores all-'not exercised'. When both
    land, flip SF_EVAL_JUDGE=1 and this scores every deployed benchmark run automatically.

    hd2ut063 owns benchmark_harness.py/cron; the intended wire-in is a single call from
    report_and_file (or the cron) when status.deploy_url is set — kept OUT of that file here to
    avoid colliding with the in-flight cron work. Returns the persisted score dict, or None when
    dormant / not deployed."""
    on = enabled if enabled is not None else os.environ.get("SF_EVAL_JUDGE") == "1"
    if not on:
        return None
    prd_text, mockup_ids, deploy_url, brief_title = _from_api(base_url, project_id, token)
    if not deploy_url:
        return None   # nothing deployed to judge (the SOF-148 case) — dormant, not an error
    rubric = eval_judge.build_rubric(prd_text)
    obs = [eval_judge.Observation(criterion_id=o["criterion_id"], passed=bool(o["passed"]),
                                  evidence=o.get("evidence", ""), screenshot_url=o.get("screenshot_url", ""))
           for o in (observations or [])]
    score = eval_judge.score_run(project_id, brief_title, rubric, obs, mockup_ids)
    eval_judge.EvalScoreStore().save(score, scored_at=time.time())
    return score.to_row()


def _get(url: str, token: str) -> bytes:
    req = urllib.request.Request(url, headers={"X-SF-Service-Token": token})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()


def _from_api(base: str, pid: str, token: str) -> tuple[str, list[str], str, str]:
    """Return (prd_text, mockup_screen_ids, deploy_url, brief_title) for a real run."""
    status = json.loads(_get(f"{base}/api/projects/{pid}", token))
    deploy_url = status.get("deploy_url") or ""
    brief_title = status.get("name") or pid
    prd_text = _get(f"{base}/api/projects/{pid}/artifact?path=PRD.md", token).decode("utf-8", "replace")
    # Which V1 screens have a mockup artifact: probe mockups/<SCREEN_ID>.html per V1 screen id.
    v1 = artifacts.parse_v1_screen_ids(prd_text)
    have = []
    for sid in v1:
        try:
            body = _get(f"{base}/api/projects/{pid}/artifact?path=mockups/{sid}.html", token)
            if body and (b"<html" in body.lower() or b"<style" in body.lower()):
                have.append(sid)
        except Exception:
            pass
    return prd_text, have, deploy_url, brief_title


def _from_files(prd_file: str, mockups_dir: str) -> tuple[str, list[str]]:
    prd_text = open(prd_file, encoding="utf-8").read()
    v1 = artifacts.parse_v1_screen_ids(prd_text)
    ok, missing = artifacts.mockups_cover_v1_screens(mockups_dir, v1) if mockups_dir else (False, v1)
    have = [s for s in v1 if s not in set(missing)]
    return prd_text, have


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--project-id", required=True)
    ap.add_argument("--base-url"); ap.add_argument("--token")
    ap.add_argument("--prd-file"); ap.add_argument("--mockups-dir"); ap.add_argument("--deploy-url", default="")
    ap.add_argument("--brief-title", default="")
    ap.add_argument("--observations", help="JSON list of {criterion_id,passed,evidence?,screenshot_url?}")
    ap.add_argument("--no-persist", action="store_true")
    a = ap.parse_args()

    if a.base_url and a.token:
        prd_text, mockup_ids, deploy_url, brief_title = _from_api(a.base_url, a.project_id, a.token)
    elif a.prd_file:
        prd_text, mockup_ids = _from_files(a.prd_file, a.mockups_dir)
        deploy_url, brief_title = a.deploy_url, (a.brief_title or a.project_id)
    else:
        print("need either --base-url+--token (API) or --prd-file (offline)", file=sys.stderr)
        return 2

    rubric = eval_judge.build_rubric(prd_text)
    obs = []
    if a.observations:
        for o in json.loads(open(a.observations).read()):
            obs.append(eval_judge.Observation(
                criterion_id=o["criterion_id"], passed=bool(o["passed"]),
                evidence=o.get("evidence", ""), screenshot_url=o.get("screenshot_url", "")))

    score = eval_judge.score_run(a.project_id, brief_title, rubric, obs, mockup_ids)
    print(json.dumps({"project_id": score.project_id, "brief_title": score.brief_title,
                     "deploy_url": deploy_url, "total": score.total, "passed": score.passed,
                     "score": round(score.score, 4), "by_stage": score.by_stage,
                     "screen_diffs": score.screen_diffs}, indent=2))
    if not a.no_persist:
        eval_judge.EvalScoreStore().save(score, scored_at=time.time())
        print(f"[eval] persisted score for {score.project_id}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
