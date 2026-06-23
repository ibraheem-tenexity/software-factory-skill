// StageRail.tsx — the pipeline stage-rail (design: buildboard.jsx StageRail). A horizontal flow
// of mono-label pills + the two Stage-gate diamonds + the wait-for-deps pill. Every node's
// state (done / active / queued / waiting) comes from the server-derived graph
// (phaseStatesFromGraph), never invented client-side — the rail reflects the run's ACTUAL
// progress. The active phase gets the pulsing brand pill + a NEW badge.
import React from "react";
import { T, Icon } from "../onboarding/design";
import { PIPELINE_ORDER, STAGES, PhaseStatus, gatePassedFromGraph } from "./pipeline";
import { Graph } from "../../api";

function Connector() {
  return <span style={{ width: 13, height: 1.5, background: T.borderDefault, flexShrink: 0 }} />;
}

function GateDiamond({ passed, title }: { passed: boolean; title: string }) {
  return <span title={title} style={{ width: 12, height: 12, background: passed ? T.success : T.borderDefault,
    transform: "rotate(45deg)", borderRadius: 2, flexShrink: 0 }} />;
}

function PhasePill({ label, status, isNew }: { label: string; status: PhaseStatus; isNew?: boolean }) {
  const active = status === "active";
  const done = status === "done";
  const bg = active ? T.raised : done ? T.brandSoft : T.sunken;
  const bd = active ? T.brand : done ? "transparent" : T.borderSubtle;
  const col = active ? T.brandDeep : done ? T.brandDeep : T.tertiary;
  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: 6, padding: "6px 11px", borderRadius: T.rMd,
      background: bg, border: `1px solid ${bd}`, flexShrink: 0, boxShadow: active ? `0 0 0 3px ${T.brand}1f` : "none" }}>
      {active && <span style={{ width: 6, height: 6, borderRadius: "50%", background: T.brand, animation: "sfPulse 1.4s ease-in-out infinite" }} />}
      {done && <Icon name="check" size={12} color={T.success} />}
      <span style={{ font: `500 12px/1 ${T.mono}`, color: col }}>{label}</span>
      {isNew && <span style={{ font: `600 9px/1 ${T.sans}`, letterSpacing: "0.06em", color: "#fff", background: T.brand, padding: "2px 5px", borderRadius: 3 }}>NEW</span>}
    </span>
  );
}

// Three states — never amber unless the run is ACTUALLY at the deps gate (Stage 2 done, deps not yet
// satisfied). A run that hasn't reached Stage 2 renders this as a neutral/pending step, not a warning,
// so the rail can't claim "wait for deps" about a run stuck somewhere earlier.
function DepsPill({ state }: { state: "satisfied" | "waiting" | "pending" }) {
  const satisfied = state === "satisfied";
  const waiting = state === "waiting";
  const bg = satisfied ? T.successSoft : waiting ? T.warningSoft : T.sunken;
  const bd = satisfied ? T.success : waiting ? T.warning : T.borderSubtle;
  const col = satisfied ? T.success : waiting ? T.warning : T.tertiary;
  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: 6, padding: "6px 11px", borderRadius: T.rMd,
      background: bg, border: `1px solid ${bd}`, flexShrink: 0 }}>
      {satisfied ? <Icon name="check" size={12} color={T.success} />
        : <span style={{ width: 6, height: 6, borderRadius: "50%", background: waiting ? T.warning : T.borderDefault }} />}
      <span style={{ font: `500 12px/1 ${T.mono}`, color: col }}>wait for deps</span>
    </span>
  );
}

const PHASE_LABEL: Record<string, string> = Object.fromEntries(
  STAGES.flatMap((s) => s.phases.map((p) => [p.id, p.label.toLowerCase()])));

export function StageRail({ graph, phaseStates, depsSatisfied, atDeps }:
  { graph: Graph; phaseStates: Record<string, PhaseStatus>; depsSatisfied: boolean; atDeps: boolean }) {
  const s1 = gatePassedFromGraph(graph.nodes, "gate:stage1");
  const s2 = gatePassedFromGraph(graph.nodes, "gate:stage2");
  // satisfied wins; amber "waiting" only when the run is truly at the deps gate (atWaitForDeps);
  // otherwise neutral/pending so an early-stage run isn't mislabeled as waiting-for-deps.
  const depsState: "satisfied" | "waiting" | "pending" = depsSatisfied ? "satisfied" : atDeps ? "waiting" : "pending";
  // Render in pipeline order; drop a gate diamond after research and after tickets, and the
  // wait-for-deps pill after Gate 2 — exactly where the backend graph places them.
  const items: React.ReactNode[] = [];
  PIPELINE_ORDER.forEach((id, i) => {
    if (i > 0) items.push(<Connector key={`c${i}`} />);
    const st = phaseStates[id] || "pending";
    items.push(<PhasePill key={id} label={PHASE_LABEL[id] || id} status={st} isNew={st === "active"} />);
    if (id === "research") {
      items.push(<Connector key="cg1" />, <GateDiamond key="g1" passed={s1} title="Stage 1 gate" />);
    } else if (id === "tickets") {
      items.push(<Connector key="cg2" />, <GateDiamond key="g2" passed={s2} title="Stage 2 gate" />,
        <Connector key="cd" />, <DepsPill key="deps" state={depsState} />);
    }
  });
  return (
    <div style={{ display: "flex", alignItems: "center", flexWrap: "wrap", rowGap: 9,
      padding: "14px 16px", background: T.raised, border: `1px solid ${T.borderSubtle}`, borderRadius: T.rLg, boxShadow: T.shadowXs }}>
      {items}
    </div>
  );
}
