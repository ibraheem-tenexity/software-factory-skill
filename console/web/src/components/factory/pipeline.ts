// pipeline.ts — the real Software Factory pipeline model, mirrored from the backend.
//
// Source of truth is the server: PIPELINE = STAGE_1 + STAGE_2 + STAGE_3 in
// src/software_factory/console.py (extract·provision·research | architect·tickets |
// build·deploy·test·teardown). The console's graph() endpoint already emits a node per phase
// with a derived `status` (pending|active|done|skipped) plus the two Stage gates and the deps
// node, so the StageRail reads those node statuses directly rather than re-deriving them.
//
// We keep human labels + the stage grouping here so the rail can render the design's stage-rail
// with Stage-gate diamonds without inventing any "done" states the run hasn't actually reached.

export type PhaseStatus = "pending" | "active" | "done" | "skipped";

// The halted-run tone mapping, shared by Dashboard.statusOf() and FactoryConsole's phase pill —
// duplicating this if-chain in both places let them drift (fixed in #128: the dashboard card
// fell through to "Building" for stopped/crashed/paused because it lacked this branch).
export function toneForHaltedPhase(phase?: string): "success" | "warning" | "danger" | undefined {
  if (phase === "done") return "success";
  if (phase === "stopped" || phase === "crashed") return "danger";
  if (phase === "paused") return "warning";
  return undefined;
}

export const STAGES: { stage: number; title: string; phases: { id: string; label: string }[] }[] = [
  {
    stage: 1, title: "Research",
    phases: [
      { id: "extract", label: "Extract" },
      { id: "provision", label: "Provision" },
      { id: "research", label: "Research" },
    ],
  },
  {
    stage: 2, title: "Design",
    phases: [
      { id: "architect", label: "Architect" },
      { id: "tickets", label: "Tickets" },
    ],
  },
  {
    stage: 3, title: "Build & Ship",
    phases: [
      { id: "build", label: "Build" },
      { id: "deploy", label: "Deploy" },
      { id: "test", label: "Test" },
      { id: "teardown", label: "Teardown" },
    ],
  },
];

// All phase ids in pipeline order (matches server PIPELINE).
export const PIPELINE_ORDER = STAGES.flatMap((s) => s.phases.map((p) => p.id));

// Index map for O(1) downstream-of checks.
const PIPELINE_INDEX: Record<string, number> = Object.fromEntries(PIPELINE_ORDER.map((id, i) => [id, i]));

// True if `candidate` is strictly downstream of `halted` (comes after it in pipeline order).
export function isDownstreamOf(candidate: string, halted: string): boolean {
  const hi = PIPELINE_INDEX[halted], ci = PIPELINE_INDEX[candidate];
  return hi !== undefined && ci !== undefined && ci > hi;
}

// The run is "at the wait-for-deps stage" when Stage 2 has completed (its gate passed) but deps
// are not yet satisfied and Stage 3 has not started — the only moment the deps bar should show.
// Derived from real status fields (stage2_done, deps_satisfied) + phase.
export function atWaitForDeps(status: { stage2_done?: boolean; deps_satisfied?: boolean; phase?: string }): boolean {
  if (!status.stage2_done) return false;
  if (status.deps_satisfied) return false;
  // once a Stage-3 phase is active the deps were satisfied; guard anyway on phase position.
  return !["build", "deploy", "test", "teardown", "done", "stopped"].includes(status.phase || "");
}

// Pull the per-phase status the server derived, keyed by phase id, out of the graph nodes.
export function phaseStatesFromGraph(nodes: { data: Record<string, any> }[]): Record<string, PhaseStatus> {
  const out: Record<string, PhaseStatus> = {};
  for (const n of nodes) {
    if (n.data.kind === "phase" && typeof n.data.id === "string" && n.data.id.startsWith("phase:")) {
      out[n.data.id.slice("phase:".length)] = (n.data.status as PhaseStatus) || "pending";
    }
  }
  return out;
}

// Gate pass-state from the graph (gate:stage1 / gate:stage2 nodes carry status "passed"|"pending").
export function gatePassedFromGraph(nodes: { data: Record<string, any> }[], gateId: string): boolean {
  const g = nodes.find((n) => n.data.id === gateId);
  return g ? g.data.status === "passed" : false;
}
