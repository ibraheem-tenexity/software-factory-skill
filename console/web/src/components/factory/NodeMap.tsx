// NodeMap.tsx — Tree and Map views, both built from the REAL graph (/api/projects/{id}/graph →
// console.graph). The graph is a Cytoscape-shaped projection of the project store:
//   nodes: { data: { id, label, kind, status, ... } }
//   edges: { data: { source, target, etype } }   etype ∈ flow | hierarchy | feedback
// kinds: orchestrator | phase | gate | deps | agent | artifact | blocker
//
// Tree  = the hierarchy edges (orchestrator → agents → artifacts), an indented outline.
// Map   = a force-directed Cytoscape graph of the same nodes/edges (curved edges), reusing the
//          cytoscape dep already in the bundle.
import { useEffect, useRef } from "react";
import cytoscape, { Core } from "cytoscape";
import { T, Icon } from "../onboarding/design";
import { Graph, GraphNode } from "../../api";

const KIND_ICON: Record<string, string> = {
  orchestrator: "bot", phase: "layers", gate: "lock", deps: "zap",
  agent: "bot", artifact: "file", blocker: "x",
};
const STATUS_COLOR: Record<string, string> = {
  done: T.success, passed: T.success, satisfied: T.success, active: T.brand,
  created: T.cHigh, awaiting: T.warning, open: T.danger, missing: T.danger,
  pending: T.tertiary, skipped: T.tertiary,
};

function statusColor(s?: string): string { return (s && STATUS_COLOR[s]) || T.tertiary; }

// ── Tree view: walk hierarchy edges from the orchestrator down ──────────────────────────────
export function TreeView({ graph, onOpenArtifact }:
  { graph: Graph; onOpenArtifact: (path: string, label: string, id?: number) => void }) {
  const byId: Record<string, GraphNode> = {};
  for (const n of graph.nodes) byId[n.data.id] = n;
  const children: Record<string, string[]> = {};
  for (const e of graph.edges) {
    if (e.data.etype === "hierarchy") (children[e.data.source] ||= []).push(e.data.target);
  }
  const root = graph.nodes.find((n) => n.data.kind === "orchestrator");
  if (!root) {
    return <div style={{ padding: 40, textAlign: "center", color: T.tertiary, font: `400 13px/1.5 ${T.sans}` }}>No graph yet.</div>;
  }

  const Row = ({ id, depth }: { id: string; depth: number }) => {
    const n = byId[id];
    if (!n) return null;
    const d = n.data;
    const kids = children[id] || [];
    const isArtifact = d.kind === "artifact" && d.path;
    return (
      <>
        <div onClick={isArtifact ? () => onOpenArtifact(d.path, d.label, d.artifact_id) : undefined}
          style={{ display: "flex", alignItems: "center", gap: 8, padding: "6px 8px", paddingLeft: 8 + depth * 22,
            borderRadius: T.rMd, cursor: isArtifact ? "pointer" : "default",
            background: depth === 0 ? T.brandSoft + "66" : "transparent" }}>
          <span style={{ width: 22, height: 22, borderRadius: 6, display: "grid", placeItems: "center", flexShrink: 0,
            background: T.sunken, boxShadow: `inset 0 0 0 1px ${statusColor(d.status)}55` }}>
            <Icon name={KIND_ICON[d.kind] || "file"} size={12} color={statusColor(d.status)} />
          </span>
          <span style={{ font: `${depth === 0 ? 600 : 500} 13px/1.2 ${T.sans}`, color: T.fg }}>{d.label}</span>
          {d.status && <span style={{ font: `400 10px/1 ${T.mono}`, color: statusColor(d.status) }}>{d.status}</span>}
          {isArtifact && <Icon name="chevronRight" size={13} color={T.tertiary} style={{ marginLeft: "auto" }} />}
        </div>
        {kids.map((k) => <Row key={k} id={k} depth={depth + 1} />)}
      </>
    );
  };

  return (
    <div style={{ background: T.raised, border: `1px solid ${T.borderSubtle}`, borderRadius: T.rXl, padding: 8, boxShadow: T.shadowXs }}>
      <Row id={root.data.id} depth={0} />
    </div>
  );
}

// ── Map view: force-directed Cytoscape graph ────────────────────────────────────────────────
const NODE_COLORS: Record<string, string> = {
  orchestrator: T.brandDeep, phase: T.brand, agent: "#7c3aed", artifact: T.cHigh,
  blocker: T.danger, gate: T.cHigh, deps: T.warning,
};

export function MapView({ graph }: { graph: Graph }) {
  const ref = useRef<HTMLDivElement>(null);
  const cyRef = useRef<Core | null>(null);
  const laidOut = useRef(false);

  useEffect(() => {
    if (!ref.current) return;
    const cy = cytoscape({
      container: ref.current,
      style: [
        { selector: "node", style: {
            "background-color": (n: any) => NODE_COLORS[n.data("kind")] || T.tertiary,
            label: "data(label)", color: T.fg, "font-size": "9px", "font-family": "sans-serif",
            "text-valign": "bottom", "text-margin-y": 4, width: 22, height: 22 } },
        { selector: "node[status = 'done']", style: { "background-color": T.success } },
        { selector: "node[status = 'passed']", style: { "background-color": T.success } },
        { selector: "node[status = 'active']", style: { "background-color": T.brand, "border-width": 3, "border-color": T.brandSoft } },
        { selector: "edge", style: {
            width: 1.5, "line-color": T.borderDefault, "target-arrow-color": T.borderDefault,
            "target-arrow-shape": "triangle", "curve-style": "bezier" } },
        { selector: "edge[etype = 'feedback']", style: { "line-color": T.warning, "target-arrow-color": T.warning, "line-style": "dashed" } },
      ],
      elements: [],
    });
    cyRef.current = cy;
    laidOut.current = false;
    return () => { cy.destroy(); cyRef.current = null; };
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
    if (!laidOut.current && graph.nodes.length) {
      cy.layout({ name: "cose", animate: false }).run();
      laidOut.current = true;
    }
  }, [graph]);

  return (
    <div style={{ position: "relative" }}>
      {/* legend (design: nodemap.jsx) — same colour scheme the cytoscape style uses */}
      <div style={{ position: "absolute", top: 12, left: 12, zIndex: 2, display: "flex", flexWrap: "wrap", gap: 12,
        padding: "8px 12px", background: T.raised + "e6", border: `1px solid ${T.borderSubtle}`, borderRadius: T.rMd }}>
        {([[T.brandDeep, "orchestrator"], [T.success, "done · agent"], [T.brand, "active"],
           [T.warning, "deps"], [T.cHigh, "artifact / gate"]] as [string, string][]).map(([c, l]) => (
          <span key={l} style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
            <span style={{ width: 9, height: 9, background: c, borderRadius: "50%" }} />
            <span style={{ font: `500 10.5px/1 ${T.sans}`, color: T.secondary }}>{l}</span>
          </span>
        ))}
      </div>
      <div ref={ref} style={{ width: "100%", height: 460, background: T.raised,
        border: `1px solid ${T.borderSubtle}`, borderRadius: T.rXl, boxShadow: T.shadowXs }} />
    </div>
  );
}
