// NodeMap.tsx — Tree and Map views, both built from the REAL graph (/api/projects/{id}/graph →
// console.graph). The graph is a Cytoscape-shaped projection of the project store:
//   nodes: { data: { id, label, kind, status, ... } }
//   edges: { data: { source, target, etype } }   etype ∈ flow | hierarchy | feedback
// kinds: orchestrator | phase | gate | deps | agent | artifact | blocker
//
// Tree = the design's GraphView spine (buildboard.jsx:127-205): orchestrator root, vertical spine
//        of state dots + gate diamonds, per-node StatusPill, dashed agent sub-branch with sparkle
//        avatar, ArtifactChip rows, and the build node's avatar stack + ticket count + board link.
// Map  = Cytoscape restyled per nodemap.jsx: dotted-grid background, curved edges with the active
//        path in brand blue, rounded-rect colour-coded process nodes with mono labels, a pulsing
//        ring on the active node, teal gate diamonds, green agent / purple artifact satellites
//        (artifact nodes are clickable → DocViewer), and the 6-entry legend.
import React, { useEffect, useRef } from "react";
import cytoscape, { Core } from "cytoscape";
import { T, Icon, Sparkle, Avatar, StatusPill, ArtifactChip } from "../onboarding/design";
import { Graph, GraphNode } from "../../api";
import { NEW_PHASES } from "./pipeline";
import { ArtifactRef, artifactsFromGraph } from "./Artifacts";

// Design constants from nodemap.jsx with no T-token equivalent (kept verbatim like the design).
const MAP_ORCH = "#16243f";      // orchestrator ink
const MAP_ORCH_CORE = "#2f4a78"; // orchestrator inner dot
const MAP_ARTIFACT = "#8B5CF6";  // artifact purple
const MAP_EDGE = "#C7C9CF";      // main-path edge grey
const MAP_SAT_EDGE = "#DCDCD8";  // satellite edge grey

// cytoscape rejects CSS font-family STACKS (a single concrete family name only), so labels styled
// with T.sans/T.mono silently fell back to the renderer default — feed it the stack's first font.
const firstFont = (stack: string) => stack.split(",")[0].trim().replace(/^['"]|['"]$/g, "");
const MAP_FONT_SANS = firstFont(T.sans);
const MAP_FONT_MONO = firstFont(T.mono);

type SpineState = "done" | "active" | "deps" | "todo" | "skipped" | "gate";

function NewBadge() {
  return <span style={{ font: `600 9px/1 ${T.sans}`, letterSpacing: "0.06em", color: "#fff",
    background: T.brand, padding: "2px 5px", borderRadius: 3 }}>NEW</span>;
}

// ── Tree view: the design's GraphView spine driven by the real graph ────────────────────────
export function TreeView({ graph, onOpenArtifact, ticketsDone = 0, ticketsTotal = 0, onViewBoard }:
  { graph: Graph; onOpenArtifact: (a: ArtifactRef) => void;
    ticketsDone?: number; ticketsTotal?: number; onViewBoard?: () => void }) {
  const byId: Record<string, GraphNode> = {};
  for (const n of graph.nodes) byId[n.data.id] = n;

  const root = graph.nodes.find((n) => n.data.kind === "orchestrator");
  if (!root) {
    return <div style={{ padding: 40, textAlign: "center", color: T.tertiary, font: `400 13px/1.5 ${T.sans}` }}>No graph yet.</div>;
  }

  // Spine order: walk the single flow chain from the orchestrator (each spine node has exactly
  // one outgoing flow edge; awaiting-review gates point INTO a phase, so the walk skips them).
  const flowNext: Record<string, string> = {};
  for (const e of graph.edges) {
    if (e.data.etype === "flow" && !(e.data.source in flowNext)) flowNext[e.data.source] = e.data.target;
  }
  const spine: GraphNode[] = [];
  const seen = new Set<string>([root.data.id]);
  let cur = flowNext[root.data.id];
  while (cur && !seen.has(cur) && byId[cur]) {
    seen.add(cur);
    spine.push(byId[cur]);
    cur = flowNext[cur];
  }

  // Agents per phase + artifacts per producing node (via the shared hierarchy resolution).
  const agentsOf: Record<string, GraphNode[]> = {};
  for (const e of graph.edges) {
    if (e.data.etype !== "hierarchy") continue;
    const child = byId[e.data.target];
    if (child?.data.kind === "agent") (agentsOf[e.data.source] ||= []).push(child);
  }
  const allArtifacts = artifactsFromGraph(graph);
  const artifactsOf = (nodeLabel?: string) => allArtifacts.filter((a) => a.node === nodeLabel);
  const rootArtifacts = allArtifacts.filter((a) => !a.node);

  const stateOf = (n: GraphNode): SpineState => {
    const d = n.data;
    if (d.kind === "gate") return "gate";
    if (d.kind === "deps") {
      if (d.status === "satisfied") return "done";
      // amber only when the run actually reached the deps gate (Stage 2 gate passed)
      return byId["gate:stage2"]?.data.status === "passed" ? "deps" : "todo";
    }
    if (d.status === "done") return "done";
    if (d.status === "active") return "active";
    if (d.status === "skipped") return "skipped";
    return "todo";
  };
  const DOT: Record<SpineState, string> = {
    done: T.success, active: T.brand, deps: T.warning, gate: T.brand, todo: T.borderDefault, skipped: T.borderDefault,
  };

  const open = (a: ArtifactRef) => (a.url ? window.open(a.url, "_blank") : onOpenArtifact(a));

  const SubBranch = ({ agents, artifacts, extra }:
    { agents: GraphNode[]; artifacts: ArtifactRef[]; extra?: React.ReactNode }) => (
    <div style={{ marginTop: 9, paddingLeft: 14, borderLeft: `2px dashed ${T.borderSubtle}`,
      display: "flex", flexDirection: "column", gap: 9 }}>
      {agents.map((a) => (
        <div key={a.data.id} style={{ display: "flex", alignItems: "center", gap: 7 }}>
          <span style={{ width: 20, height: 20, borderRadius: "50%", display: "grid", placeItems: "center",
            background: T.brandSoft, color: T.brand, boxShadow: `inset 0 0 0 1px ${T.brand}33` }}><Sparkle size={10} color={T.brand} /></span>
          <span style={{ font: `500 12.5px/1.2 ${T.sans}`, color: T.secondary }}>{a.data.label} spawned</span>
        </div>
      ))}
      {artifacts.length > 0 && (
        <div style={{ display: "flex", flexWrap: "wrap", gap: 7 }}>
          {artifacts.map((a, i) => (
            <ArtifactChip key={`${a.path}-${i}`} onOpen={open}
              a={{ ...a, note: a.status === "missing" ? "missing" : undefined }} />
          ))}
        </div>
      )}
      {extra}
    </div>
  );

  return (
    <div style={{ background: T.raised, border: `1px solid ${T.borderSubtle}`, borderRadius: T.rXl,
      padding: "14px 16px", boxShadow: T.shadowXs, overflow: "auto" }}>
      <div style={{ maxWidth: 720 }}>
        {/* orchestrator root */}
        <div style={{ display: "flex", gap: 14, alignItems: "stretch" }}>
          <div style={{ display: "flex", flexDirection: "column", alignItems: "center", width: 18, flexShrink: 0 }}>
            <span style={{ width: 16, height: 16, borderRadius: "50%", marginTop: 2, background: MAP_ORCH,
              display: "grid", placeItems: "center", flexShrink: 0 }}>
              <span style={{ width: 6, height: 6, borderRadius: "50%", background: MAP_ORCH_CORE }} />
            </span>
            {spine.length > 0 && <span style={{ flex: 1, width: 2, background: T.borderSubtle, marginTop: 4, minHeight: 16 }} />}
          </div>
          <div style={{ flex: 1, minWidth: 0, paddingBottom: 16 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 9, flexWrap: "wrap" }}>
              <span style={{ font: `600 14px/1.2 ${T.sans}`, color: T.fg }}>{root.data.label}</span>
              <StatusPill tone="neutral" dot={false}>orchestrator</StatusPill>
            </div>
            <p style={{ font: `400 12px/1.4 ${T.sans}`, color: T.tertiary, margin: "4px 0 0" }}>
              Spawns and supervises every node below; each node spins up its own sub-agents.
            </p>
            {((agentsOf[root.data.id] || []).length > 0 || rootArtifacts.length > 0) && (
              <SubBranch agents={agentsOf[root.data.id] || []} artifacts={rootArtifacts} />
            )}
          </div>
        </div>

        {spine.map((n, i) => {
          const d = n.data;
          const state = stateOf(n);
          const last = i === spine.length - 1;
          const isGate = state === "gate";
          const agents = agentsOf[d.id] || [];
          const arts = d.kind === "phase" ? artifactsOf(d.label) : [];
          const phaseId = d.kind === "phase" ? String(d.id).slice("phase:".length) : "";
          const isBuild = phaseId === "build";
          const showSub = !isGate && (state === "done" || state === "active") && (agents.length > 0 || arts.length > 0 || (isBuild && ticketsTotal > 0));
          return (
            <div key={d.id} style={{ display: "flex", gap: 14, alignItems: "stretch" }}>
              {/* spine */}
              <div style={{ display: "flex", flexDirection: "column", alignItems: "center", width: 18, flexShrink: 0 }}>
                {isGate
                  ? <span style={{ width: 13, height: 13, background: T.brand, transform: "rotate(45deg)", borderRadius: 2, marginTop: 4, flexShrink: 0 }} />
                  : <span style={{ width: 14, height: 14, borderRadius: "50%", marginTop: 3, flexShrink: 0,
                      background: state === "todo" || state === "skipped" ? T.raised : DOT[state],
                      border: `2px solid ${DOT[state]}`,
                      boxShadow: state === "active" ? `0 0 0 4px ${T.brand}22` : "none",
                      display: "grid", placeItems: "center",
                      animation: state === "active" ? "sfPulse 1.6s ease-in-out infinite" : "none" }}>
                      {state === "done" && <Icon name="check" size={9} color="#fff" strokeWidth={3} />}
                    </span>}
                {!last && <span style={{ flex: 1, width: 2, background: T.borderSubtle, marginTop: 4, minHeight: 14 }} />}
              </div>
              {/* body */}
              <div style={{ flex: 1, minWidth: 0, paddingBottom: 20 }}>
                <div style={{ display: "flex", alignItems: "center", gap: 9, flexWrap: "wrap" }}>
                  <span style={{ font: `${isGate ? 500 : 600} 14px/1.2 ${isGate ? T.mono : T.sans}`, color: isGate ? T.tertiary : T.fg }}>
                    {d.label}
                  </span>
                  {phaseId && NEW_PHASES.has(phaseId) && <NewBadge />}
                  {state === "done" && <StatusPill tone="success">done</StatusPill>}
                  {state === "active" && <StatusPill tone="brand">running</StatusPill>}
                  {state === "deps" && <StatusPill tone="warning">waiting</StatusPill>}
                  {state === "todo" && <StatusPill tone="neutral" dot={false}>queued</StatusPill>}
                  {state === "skipped" && <StatusPill tone="neutral" dot={false}>skipped</StatusPill>}
                </div>
                {showSub && (
                  <SubBranch agents={agents} artifacts={arts}
                    extra={isBuild && ticketsTotal > 0 ? (
                      <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
                        {agents.length > 0 && (
                          <div style={{ display: "flex", alignItems: "center" }}>
                            {agents.slice(0, 4).map((a, j) => (
                              <span key={a.data.id} style={{ marginLeft: j ? -6 : 0 }}>
                                <Avatar name={a.data.label} size={22} />
                              </span>
                            ))}
                          </div>
                        )}
                        <span style={{ font: `500 12px/1.2 ${T.sans}`, color: T.secondary }}>
                          building {ticketsTotal} tickets · {ticketsDone} done
                        </span>
                        {onViewBoard && (
                          <button onClick={onViewBoard} style={{ font: `500 12px/1 ${T.sans}`, color: T.brandDeep,
                            background: "none", border: "none", cursor: "pointer", display: "inline-flex", alignItems: "center", gap: 3 }}>
                            View board <Icon name="arrowRight" size={12} color={T.brandDeep} />
                          </button>
                        )}
                      </div>
                    ) : undefined} />
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ── Map view: Cytoscape restyled to the design's node map (nodemap.jsx:62-140) ──────────────
export function MapView({ graph, onOpenArtifact }:
  { graph: Graph; onOpenArtifact?: (a: ArtifactRef) => void }) {
  const ref = useRef<HTMLDivElement>(null);
  const cyRef = useRef<Core | null>(null);
  const laidOut = useRef(false);
  const graphRef = useRef(graph);
  const openRef = useRef(onOpenArtifact);
  graphRef.current = graph;
  openRef.current = onOpenArtifact;

  useEffect(() => {
    if (!ref.current) return;
    const container = ref.current;
    // Edges touching the ACTIVE node are the hot path — brand blue (design nodemap.jsx:85-89).
    const hot = (e: any) => e.source().data("status") === "active" || e.target().data("status") === "active";
    const cy = cytoscape({
      container,
      style: [
        // process nodes: rounded rects, colour-coded, mono labels inside
        { selector: "node[kind = 'phase'], node[kind = 'deps']", style: {
            shape: "round-rectangle", width: "label", height: 14, padding: "7px",
            "background-color": T.sunken, "border-width": 1, "border-color": T.borderDefault,
            label: "data(label)", color: T.tertiary, "font-size": "10px", "font-weight": 600,
            "font-family": MAP_FONT_MONO, "text-valign": "center", "text-halign": "center" } },
        { selector: "node[kind = 'phase'][status = 'done']", style: {
            "background-color": T.success, "border-width": 0, color: "#fff" } },
        { selector: "node[kind = 'phase'][status = 'active']", style: {
            "background-color": T.brand, color: "#fff",
            "border-width": 3, "border-color": T.brand, "border-opacity": 0.75,
            "transition-property": "border-opacity", "transition-duration": 700 } as any },
        { selector: "node[kind = 'deps'][status != 'satisfied']", style: {
            "background-color": T.warning, "border-width": 0, color: "#fff" } },
        { selector: "node[kind = 'deps'][status = 'satisfied']", style: {
            "background-color": T.success, "border-width": 0, color: "#fff" } },
        // pulsing ring phase B (interval toggles .nm-dim on the active node)
        { selector: "node.nm-dim", style: { "border-opacity": 0.12 } as any },
        // orchestrator: dark circle
        { selector: "node[kind = 'orchestrator']", style: {
            shape: "ellipse", width: 30, height: 30, "background-color": MAP_ORCH,
            label: "data(label)", color: T.fg, "font-size": "10px", "font-weight": 600,
            "font-family": MAP_FONT_SANS, "text-valign": "bottom", "text-margin-y": 5 } },
        // gates: teal diamonds
        { selector: "node[kind = 'gate']", style: {
            shape: "diamond", width: 18, height: 18, "background-color": T.cHigh,
            label: "data(label)", color: T.tertiary, "font-size": "9px", "font-family": MAP_FONT_SANS,
            "text-valign": "bottom", "text-margin-y": 5 } },
        { selector: "node[kind = 'gate'][status = 'awaiting']", style: { "background-color": T.warning } },
        // satellites: green agents, purple clickable artifacts, danger blockers
        { selector: "node[kind = 'agent']", style: {
            shape: "ellipse", width: 13, height: 13, "background-color": T.success,
            label: "data(label)", color: T.secondary, "font-size": "9px", "font-family": MAP_FONT_SANS,
            "text-valign": "bottom", "text-margin-y": 4 } },
        { selector: "node[kind = 'artifact']", style: {
            shape: "ellipse", width: 13, height: 13, "background-color": MAP_ARTIFACT,
            label: "data(label)", color: T.secondary, "font-size": "9px", "font-family": MAP_FONT_SANS,
            "text-valign": "bottom", "text-margin-y": 4 } },
        { selector: "node[kind = 'blocker']", style: {
            shape: "ellipse", width: 13, height: 13, "background-color": T.danger,
            label: "data(label)", color: T.danger, "font-size": "9px", "font-family": MAP_FONT_SANS,
            "text-valign": "bottom", "text-margin-y": 4 } },
        // edges: curved; the active path in brand blue, satellites fainter, feedback dashed
        { selector: "edge", style: {
            "curve-style": "bezier",
            width: (e: any) => (hot(e) ? 2 : 1.6),
            "line-color": (e: any) => (hot(e) ? T.brand : MAP_EDGE) } as any },
        { selector: "edge[etype = 'hierarchy']", style: { width: 1.2, "line-color": MAP_SAT_EDGE } as any },
        { selector: "edge[etype = 'feedback']", style: { "line-color": T.warning, "line-style": "dashed" } },
      ] as any,
      elements: [],
    });
    cyRef.current = cy;
    laidOut.current = false;

    // artifact nodes are clickable → open the DocViewer (or the external url)
    cy.on("tap", "node[kind = 'artifact']", (ev) => {
      const d = ev.target.data();
      if (d.url) { window.open(d.url, "_blank"); return; }
      if (!openRef.current) return;
      // resolve the producing agent via the hierarchy edge, like artifactsFromGraph
      const g = graphRef.current;
      const owner = g.edges.find((e) => e.data.etype === "hierarchy" && e.data.target === d.id);
      const agentNode = owner && g.nodes.find((n) => n.data.id === owner.data.source && n.data.kind === "agent");
      openRef.current({ label: d.label, path: d.path || "", url: d.url || null, status: d.status,
        id: d.artifact_id, agent: agentNode?.data.label });
    });
    cy.on("mouseover", "node[kind = 'artifact']", () => { container.style.cursor = "pointer"; });
    cy.on("mouseout", "node[kind = 'artifact']", () => { container.style.cursor = "default"; });

    // pulsing ring on the active node (border-opacity transition toggled on an interval)
    const pulse = setInterval(() => {
      const c = cyRef.current;
      if (!c) return;
      c.nodes(".nm-dim[status != 'active']").removeClass("nm-dim");   // node stopped being active
      c.nodes("[status = 'active']").toggleClass("nm-dim");
    }, 750);

    return () => { clearInterval(pulse); cy.destroy(); cyRef.current = null; };
  }, []);

  useEffect(() => {
    const cy = cyRef.current;
    if (!cy) return;
    // Cytoscape needs an id on every element; the server's edges carry only {source,target,etype},
    // so synthesize a stable edge id (source→target) — otherwise cy.json() drops the edges.
    const edges = graph.edges.map((e) => ({
      data: { id: e.data.id || `${e.data.source}->${e.data.target}`, ...e.data },
    }));
    cy.json({ elements: { nodes: graph.nodes, edges } });
    cy.style().update();   // re-evaluate the hot-path edge functions against the new statuses
    if (!laidOut.current && graph.nodes.length) {
      cy.layout({ name: "cose", animate: false }).run();
      laidOut.current = true;
    }
  }, [graph]);

  return (
    <div style={{ position: "relative" }}>
      {/* legend (design: nodemap.jsx:67-74) — 6 entries incl. the gate diamond */}
      <div style={{ position: "absolute", top: 12, left: 12, zIndex: 2, display: "flex", flexWrap: "wrap", gap: 12,
        padding: "8px 12px", background: T.raised + "e6", border: `1px solid ${T.borderSubtle}`, borderRadius: T.rMd,
        backdropFilter: "blur(4px)" }}>
        {([[MAP_ORCH, "orchestrator", "dot"], [T.success, "done · agent", "dot"], [T.brand, "active", "dot"],
           [T.warning, "deps", "dot"], [MAP_ARTIFACT, "artifact", "dot"], [T.cHigh, "gate", "diamond"]] as [string, string, string][]).map(([c, l, s]) => (
          <span key={l} style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
            <span style={{ width: 9, height: 9, background: c, borderRadius: s === "diamond" ? 2 : "50%",
              transform: s === "diamond" ? "rotate(45deg)" : "none" }} />
            <span style={{ font: `500 10.5px/1 ${T.sans}`, color: T.secondary }}>{l}</span>
          </span>
        ))}
      </div>
      <div ref={ref} style={{ width: "100%", height: 460,
        backgroundColor: T.bg,
        backgroundImage: `radial-gradient(${T.borderSubtle} 1px, transparent 1px)`,
        backgroundSize: "26px 26px",
        border: `1px solid ${T.borderSubtle}`, borderRadius: T.rXl, boxShadow: T.shadowXs }} />
    </div>
  );
}
