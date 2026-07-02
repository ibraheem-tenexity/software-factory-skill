// StageRail.tsx — the pipeline stage-rail (design: buildboard.jsx StageRail). A horizontal flow
// of mono-label pills + the two Stage-gate diamonds + the wait-for-deps pill. Every node's
// state (done / active / queued / waiting) comes from the server-derived graph
// (phaseStatesFromGraph), never invented client-side — the rail reflects the run's ACTUAL
// progress. The active phase gets the pulsing brand pill; the NEW badge is reserved for phases
// flagged in pipeline.ts NEW_PHASES (new node kinds — SOF-73), never the merely-active one.
//
// Recovery extension: when `haltedNode` is set (run is paused/crashed), the halted pill shows
// in danger-red and downstream pills are faded/queued. Done pills become clickable for rewind
// when `onRewind` is provided.
import React from "react";
import { T, Icon } from "../onboarding/design";
import { PIPELINE_ORDER, STAGES, NEW_PHASES, PhaseStatus, gatePassedFromGraph, isDownstreamOf } from "./pipeline";
import { Graph } from "../../api";

function Connector({ faded }: { faded?: boolean }) {
  return <span style={{ width: 13, height: 1.5, background: T.borderDefault, flexShrink: 0, opacity: faded ? 0.35 : 1 }} />;
}

function GateDiamond({ passed, title, faded }: { passed: boolean; title: string; faded?: boolean }) {
  return <span title={title} style={{ width: 12, height: 12, background: passed ? T.success : T.borderDefault,
    transform: "rotate(45deg)", borderRadius: 2, flexShrink: 0, opacity: faded ? 0.35 : 1 }} />;
}

function PhasePill({ label, status, isNew, halted, faded, onClick }:
  { label: string; status: PhaseStatus; isNew?: boolean; halted?: boolean; faded?: boolean; onClick?: () => void }) {
  const active = status === "active";
  const done = status === "done";
  const clickable = !!onClick;

  let bg = active ? T.raised : done ? T.brandSoft : T.sunken;
  let bd = active ? T.brand : done ? "transparent" : T.borderSubtle;
  let col = active ? T.brandDeep : done ? T.brandDeep : T.tertiary;
  if (halted) { bg = "#FFF1F1"; bd = T.danger; col = T.danger; }
  if (faded) { col = T.tertiary; }

  const Tag = clickable ? "button" : "span";
  return (
    <Tag onClick={onClick} title={clickable ? `Rewind to ${label}` : undefined}
      style={{ display: "inline-flex", alignItems: "center", gap: 6, padding: "6px 11px", borderRadius: T.rMd,
        background: bg, border: `1px solid ${bd}`, flexShrink: 0,
        boxShadow: active ? `0 0 0 3px ${T.brand}1f` : "none",
        opacity: faded ? 0.45 : 1,
        cursor: clickable ? "pointer" : "default",
        ...(clickable ? { outline: "none" } : {}),
      } as React.CSSProperties}>
      {active && <span style={{ width: 6, height: 6, borderRadius: "50%", background: T.brand, animation: "sfPulse 1.4s ease-in-out infinite" }} />}
      {halted && <span style={{ width: 6, height: 6, borderRadius: "50%", background: T.danger }} />}
      {done && !halted && <Icon name="check" size={12} color={T.success} />}
      <span style={{ font: `500 12px/1 ${T.mono}`, color: col }}>{label}</span>
      {isNew && <span style={{ font: `600 9px/1 ${T.sans}`, letterSpacing: "0.06em", color: "#fff", background: T.brand, padding: "2px 5px", borderRadius: 3 }}>NEW</span>}
      {clickable && <Icon name="arrowLeft" size={10} color={T.tertiary} />}
    </Tag>
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

export function StageRail({ graph, phaseStates, depsSatisfied, atDeps, haltedNode, onRewind }:
  { graph: Graph; phaseStates: Record<string, PhaseStatus>; depsSatisfied: boolean; atDeps: boolean;
    haltedNode?: string; onRewind?: (node: string) => void }) {
  const s1 = gatePassedFromGraph(graph.nodes, "gate:stage1");
  const s2 = gatePassedFromGraph(graph.nodes, "gate:stage2");
  // satisfied wins; amber "waiting" only when the run is truly at the deps gate (atWaitForDeps);
  // otherwise neutral/pending so an early-stage run isn't mislabeled as waiting-for-deps.
  const depsState: "satisfied" | "waiting" | "pending" = depsSatisfied ? "satisfied" : atDeps ? "waiting" : "pending";
  // Render in pipeline order; drop a gate diamond after research and after tickets, and the
  // wait-for-deps pill after Gate 2 — exactly where the backend graph places them.
  const items: React.ReactNode[] = [];
  PIPELINE_ORDER.forEach((id, i) => {
    const st = phaseStates[id] || "pending";
    const isHalted = id === haltedNode;
    const isDownstream = !!haltedNode && isDownstreamOf(id, haltedNode);
    const faded = isDownstream;
    // Done pills are rewindable when onRewind is provided (except the halted node itself)
    const rewindable = !!onRewind && st === "done" && !isHalted;
    if (i > 0) items.push(<Connector key={`c${i}`} faded={isDownstream} />);
    items.push(
      <PhasePill key={id} label={PHASE_LABEL[id] || id} status={st} isNew={NEW_PHASES.has(id)}
        halted={isHalted} faded={faded}
        onClick={rewindable ? () => onRewind(id) : undefined} />
    );
    if (id === "research") {
      const g1faded = !!haltedNode && isDownstreamOf("research", haltedNode);
      items.push(<Connector key="cg1" faded={g1faded} />, <GateDiamond key="g1" passed={s1} title="Stage 1 gate" faded={g1faded} />);
    } else if (id === "tickets") {
      const g2faded = !!haltedNode && isDownstreamOf("tickets", haltedNode);
      items.push(<Connector key="cg2" faded={g2faded} />, <GateDiamond key="g2" passed={s2} title="Stage 2 gate" faded={g2faded} />,
        <Connector key="cd" faded={g2faded} />, <DepsPill key="deps" state={depsState} />);
    }
  });
  return (
    <div style={{ display: "flex", alignItems: "center", flexWrap: "wrap", rowGap: 9,
      padding: "14px 16px", background: T.raised, border: `1px solid ${haltedNode ? T.danger : T.borderSubtle}`, borderRadius: T.rLg, boxShadow: T.shadowXs }}>
      {items}
    </div>
  );
}
