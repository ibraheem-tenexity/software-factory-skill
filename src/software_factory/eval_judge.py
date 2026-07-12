"""SOF-102 (B5) — Eval judge: score a benchmark run's built app against what the PRD intended,
diff built screens against the design mockups, and attribute every miss to the pipeline stage that
caused it. Scores persist (trendable across runs) via EvalScoreStore, mirroring run_autopsy's
Store→Repository→GlobalExec triple.

Two layers, deliberately separate (same split as run_autopsy / mcp_server):
- PURE core — `build_rubric`, `score_run`, `attribute_stage` — no DB, no network, no browser. Takes
  the PRD text + design artifacts + a list of Observations (what a browser-walk found) and returns
  an EvalScore. Fully testable against fixtures; this is the heart of the judge.
- I/O — the browser-walk that produces Observations lives in `eval_browser.py`; persistence in
  `EvalScoreStore` below; the CLI + the (SOF-148-gated) post-deploy hook in scripts/eval_judge_run.py.

The rubric is derived from the PRD the pipeline itself produced, so criteria exist by construction —
the judge scores whether the BUILD satisfied the run's own PRD/designs, not an external spec.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, asdict

from . import artifacts
from .repositories._exec import GlobalExec
from .repositories.eval_scores import EvalScoreRepository

# Stage attribution buckets — which pipeline stage a miss is charged to.
STAGE_PRODUCT = "stage1-product"   # PRD gap: the intent was never specified/complete
STAGE_DESIGN = "stage2-design"     # design gap: no mockup for a V1 screen the PRD called for
STAGE_BUILD = "stage3-build"       # build/QA gap: mockup/AC exists but the deployed app misses it


@dataclass
class Criterion:
    """One mechanically-checkable expectation extracted from the run's own PRD."""
    id: str
    kind: str            # "feature" (a given/when/then acceptance criterion) | "screen" (a V1 screen)
    text: str
    screen_id: str = ""  # set for kind="screen"


@dataclass
class Observation:
    """What the browser-walk (eval_browser) found for one criterion. Produced by I/O, consumed by
    the pure scorer — decouples scoring from browser mechanics."""
    criterion_id: str
    passed: bool
    evidence: str = ""
    screenshot_url: str = ""


@dataclass
class ScoredCriterion:
    id: str
    kind: str
    passed: bool
    stage: str = ""      # attribution bucket when failed; "" when passed
    evidence: str = ""
    screenshot_url: str = ""


@dataclass
class ScreenDiff:
    screen_id: str
    mockup_present: bool
    built_present: bool
    note: str = ""


@dataclass
class EvalScore:
    project_id: str
    brief_title: str
    total: int
    passed: int
    score: float                       # passed / total, 0.0 when total == 0
    by_stage: dict                     # {stage bucket: miss count}
    criteria: list                     # list[ScoredCriterion as dict]
    screen_diffs: list                 # list[ScreenDiff as dict]

    def to_row(self) -> dict:
        return asdict(self)


# ── PURE CORE ───────────────────────────────────────────────────────────────────────────────────

_GWT_RE = re.compile(r"(given\b.*?\bthen\b.+?)(?=\n\s*\n|\ngiven\b|\Z)", re.I | re.S)


def _acceptance_criteria(prd_text: str) -> list[str]:
    """Extract given/when/then acceptance-criteria blocks from the PRD. Best-effort, same spirit as
    artifacts.parse_v1_screen_ids: an unparseable PRD yields [] rather than raising. Each returned
    block is a single collapsed criterion string."""
    blocks = []
    for m in _GWT_RE.finditer(prd_text or ""):
        block = " ".join(m.group(1).split())
        if block:
            blocks.append(block)
    return blocks


def build_rubric(prd_text: str) -> list[Criterion]:
    """Derive the run's rubric from its own PRD: one 'feature' criterion per given/when/then
    acceptance block, one 'screen' criterion per V1 screen id in the catalog. Deterministic +
    pure. Empty PRD → empty rubric (the caller decides what an empty rubric means)."""
    rubric: list[Criterion] = []
    for i, ac in enumerate(_acceptance_criteria(prd_text), 1):
        rubric.append(Criterion(id=f"AC{i}", kind="feature", text=ac))
    for sid in artifacts.parse_v1_screen_ids(prd_text or ""):
        rubric.append(Criterion(id=f"SCREEN:{sid}", kind="screen", text=f"V1 screen {sid} is built", screen_id=sid))
    return rubric


def attribute_stage(crit: Criterion, *, mockup_present: bool) -> str:
    """Charge a failed criterion to the stage that most plausibly caused it (explainable heuristic,
    refined as the tuning loop teaches us):
    - a V1 SCREEN with no mockup artifact → the design stage never produced it (stage2).
    - a V1 SCREEN whose mockup exists but the deployed app doesn't render it → build (stage3).
    - a FEATURE acceptance criterion that fails at runtime → build/QA (stage3).
    """
    if crit.kind == "screen":
        return STAGE_DESIGN if not mockup_present else STAGE_BUILD
    return STAGE_BUILD


def score_run(project_id: str, brief_title: str, rubric: list[Criterion],
              observations: list[Observation], mockup_screen_ids: list[str]) -> EvalScore:
    """Pure scoring: fold observations onto the rubric, attribute misses, diff screens vs mockups.
    `mockup_screen_ids` is which screens actually have a design mockup artifact (from
    artifacts.mockups_cover_v1_screens / the design-stage output) — drives screen attribution and
    the screen-vs-mockup diff. An observation is matched to its criterion by id; a criterion with no
    observation counts as FAILED with 'not exercised' evidence (a gap the judge must not hide)."""
    obs_by_id = {o.criterion_id: o for o in observations}
    have_mockup = set(mockup_screen_ids)
    scored: list[ScoredCriterion] = []
    by_stage: dict[str, int] = {}
    passed = 0
    for crit in rubric:
        o = obs_by_id.get(crit.id)
        ok = bool(o and o.passed)
        sc = ScoredCriterion(id=crit.id, kind=crit.kind, passed=ok,
                             evidence=(o.evidence if o else "not exercised (no observation)"),
                             screenshot_url=(o.screenshot_url if o else ""))
        if ok:
            passed += 1
        else:
            mp = crit.screen_id in have_mockup if crit.kind == "screen" else True
            sc.stage = attribute_stage(crit, mockup_present=mp)
            by_stage[sc.stage] = by_stage.get(sc.stage, 0) + 1
        scored.append(sc)

    screen_diffs: list[ScreenDiff] = []
    for crit in rubric:
        if crit.kind != "screen":
            continue
        o = obs_by_id.get(crit.id)
        built = bool(o and o.passed)
        mp = crit.screen_id in have_mockup
        note = ("ok" if (built and mp) else
                "mockup missing (design gap)" if not mp else
                "built screen missing/broken vs mockup (build gap)")
        screen_diffs.append(ScreenDiff(screen_id=crit.screen_id, mockup_present=mp,
                                       built_present=built, note=note))

    total = len(rubric)
    return EvalScore(
        project_id=project_id, brief_title=brief_title,
        total=total, passed=passed, score=(passed / total if total else 0.0),
        by_stage=by_stage,
        criteria=[asdict(s) for s in scored],
        screen_diffs=[asdict(d) for d in screen_diffs],
    )


# ── PERSISTENCE (mirrors RunAutopsyStore's Store→Repository→GlobalExec triple) ────────────────────

class EvalScoreStore:
    """Persist eval scores to the global `eval_scores` table. One row per run; trends come from
    `recent()` across runs. Injectable repo for tests, like RunAutopsyStore."""

    def __init__(self, repo: EvalScoreRepository | None = None):
        self._repo = repo or EvalScoreRepository(GlobalExec())

    def save(self, score: EvalScore, scored_at: float) -> None:
        self._repo.upsert(
            score.project_id, score.brief_title, score.total, score.passed, score.score,
            score.by_stage, {"criteria": score.criteria, "screen_diffs": score.screen_diffs},
            scored_at)

    def get(self, project_id: str) -> dict | None:
        return self._repo.by_project(project_id)

    def recent(self, limit: int = 50, brief_title: str | None = None) -> list[dict]:
        return self._repo.recent(limit, brief_title)
