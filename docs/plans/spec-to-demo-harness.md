# Plan — Spec-to-Demo Harness in the Software Factory

## Context
The GK9 "AI cargo screening" demo was hand-built from a structured PRD + wireframe images
(2026-06-12/13). `~/gk9/docs/harness/spec-to-demo-harness.md` distills that into a deterministic
S0–S6 pipeline, and `~/gk9/tools/docx2md.py` is its Google-Doc→(markdown + `images/image-NN.png`)
ingest. This plan folds that harness into the existing factory **as a new run mode**, not a fork —
the factory already owns the back half (run lifecycle, stages, deploy, Playwright gate, pg state,
multi-tenant ownership, the vendored tenexity-design tokens). The harness replaces the *front half*
(free-form research → structured spec+images → typed Build IR) and adds one new gate (screenshot-vs-
wireframe). **Hard requirement from the operator: every spec build emits TWO apps — a mobile-web PWA
that replicates a native mobile app, and a web app — from one spec/IR.**

## Strategy: a `spec` run mode, mapped onto the existing 3 stages
Add `RunRequest.mode = "spec"` (default `"freeform"` = today's behavior, untouched). In spec mode the
existing stages keep their lifecycle/gates but swap contracts + artifacts:

| Harness stage | Lands in | What changes |
|---|---|---|
| **S0 Lint** + **S1 Extract** | **Stage 1** | Deterministic Input-Contract lint (C1–C8) → hard-fail surfaces as a blocker ("fix the doc"). Then docx2md ingest (spec.md + `images/image-NN.png`, caption-keyed) → deterministic table parse + **vision pass per v1 screen** (Opus 4.8 reads each PNG → layout/copy/seed/nav) → **`build-ir.json`** (the spine). Also emit a `PRD.md` projection so existing gates/console still work. |
| **S2 IR review** | new gate before Stage 2 | Render IR as a readable summary in the console; operator approves/edits (reuse the deps-gate / gated-hold human-checkpoint machinery). `--yolo` skips for trusted specs. Blocks Stage 2 until approved. |
| **S3 Plan synthesis** | **Stage 2** | Deterministic IR → `architecture.md` (pnpm monorepo: `apps/mobile-web`, `apps/web`, `packages/api`, `packages/ui`) + DB schema from `entities` + validation spec from `rules` + tickets **tagged per app**. TicketStore gains an `app` column. |
| **S4 Generate** | **Stage 3** | Scaffold (deterministic templates) both frontends + shared API + design tokens; per-screen components (LLM, one per v1 screen per app); logic via TDD from enumerated rules; idempotent seed; fidelity wiring (live/simulated/mock + `SIMULATED` badges). |
| **S5 Verify** | **Stage 3 gate** | Existing Playwright happy-flow + brand-token check **plus** the new **screenshot-diff-vs-wireframe** gate (capture each screen, perceptual diff + LLM-judge vs `image-NN.png`, threshold-gated, bounded repair). |
| **S6 Deploy** | **Stage 3 deploy** | Deploy both apps (see topology below); return both public URLs as demo links. Idempotent per run. |

Determinism boundary held exactly as the harness spec mandates: model only on vision-extract,
per-screen component gen, test/impl-from-prose, screenshot-judge, and bounded repair. Lint, table
parse, plan synthesis, scaffold, migrations, capture, deploy stay deterministic.

## The two-app requirement (load-bearing)
- IR carries `platforms: ["mobile-web","web"]` and every screen has `app ∈ {mobile-web, web}` (GK9's
  `M-*` screens → mobile-web; `W-*` → web).
- **mobile-web** = installable PWA, mobile viewport, device-capability hooks the screens imply
  (camera for document/AWB capture, geolocation, file upload) — it must *feel* like the native app
  the wireframes depict.
- **web** = desktop web app for the management/dashboard screens.
- **Shared, not duplicated:** one Fastify+pg API, one DB schema + seed, one `packages/ui` design-token
  package seeded from the already-vendored **tenexity-design** canon. Monorepo via pnpm workspaces.
- **Deploy topology (recommended):** two frontend Railway services (`sf-<run_id>-mobile`,
  `sf-<run_id>-web`) + one API service + one Supabase DB — both URLs surfaced in the console. (Alt:
  single service serving both roots; rejected — muddier per-app screenshot-diff + scaling.)
- S5 screenshot-diff runs per app against that app's wireframes.

## New modules / seams (concrete)
- `src/software_factory/spec_ingest.py` — vendored from `gk9/tools/docx2md.py`: Google Doc `.docx`
  (or Drive JSON) → `input/spec.md` + `input/images/image-NN.png`, caption-keyed. Hook in
  `input_pipeline.persist_and_compose` when `mode=spec`.
- `src/software_factory/spec_lint.py` — deterministic C1–C8 conformance; returns `(missing, where, fix)`.
- `src/software_factory/build_ir.py` — typed Build IR schema + validation + load/save (`build-ir.json`).
- `src/software_factory/ir_extract.py` — text table-parse (deterministic) + vision pass (Opus 4.8 per
  screen, cached by image hash) → IR.
- `src/software_factory/screenshot_gate.py` — Playwright capture + perceptual diff + LLM-judge vs
  wireframe; wired into `gate.py`/Stage-3 verify with bounded K-repair.
- Stage contracts: new `skills/stage-1-spec/` (lint+extract+IR) and spec variants of stage-2/stage-3
  SKILLs that read `build-ir.json` and build the monorepo + two apps. Keep the freeform SKILLs intact.
- `TicketStore`: add `app` column; `workspace_setup`: monorepo layout + copy `build-ir.json`/`images/`
  into the Stage-2/3 workspaces; `deploy.py`: multi-app deploy.
- `SPEC_TEMPLATE.md` at repo root — fill-in-the-blanks author guide that keeps specs on-contract.

## Build order (phased; each increment shippable + tested)
Mirrors harness §10, as factory increments:
1. **Input Contract + linter (S0)** + `SPEC_TEMPLATE.md` + docx2md ingest. Round-trip the GK9 spec to
   green lint. (No build yet.)
2. **IR schema + extractor (S1):** text parser first, then vision pass. Validate by round-tripping the
   GK9 spec → IR and diffing against a hand-authored **golden GK9 IR** committed as a fixture.
3. **IR review gate (S2)** in the console (reuse deps-gate UI).
4. **Plan synthesis + generator (S3/S4)**, default profile, **both apps** — target reproducing GK9
   screen-for-screen.
5. **Screenshot-diff verify (S5)** — the centerpiece fidelity gate + bounded repair.
6. **Deploy (S6)** — Railway + Supabase, two frontends + API.

**Acceptance (harness v1):** feed the unmodified GK9 spec + images → both apps deployed, every S5
screenshot gate green, zero hand-coding; a stakeholder can't distinguish it from the hand-built demo.

## Risks
- Pixel-faithful UI is the hard part → S5 screenshot gate is non-negotiable (bounded repair).
- Two apps ~doubles vision + codegen cost → cache vision by image hash, batch, cap per-screen attempts.
- Don't regress the existing freeform pipeline → spec mode is additive; default path unchanged; all
  current tests stay green.
- Garbage-in → S0 strict-fail with actionable `(missing, where, fix)`, never guess.

## Verification of the harness itself
- Unit: linter PASS on GK9 spec + correct C-coded failures on a broken spec; IR round-trip vs golden
  fixture; screenshot-judge on a known match/mismatch pair; spec_ingest image-count/ref integrity
  (reuse docx2md's own verify()).
- E2E (live, gated): the GK9 acceptance test above.

## Branching (operator-directed)
1. roles-ownership (my work) + opencode-kimi (peer) → peer merges → combined branch → PR → main →
   shipped together. 2. This harness work starts in a **new feature branch created off that merged
   tip** (`feature/spec-to-demo-harness`), so it builds on both. This plan file is the first commit there.
