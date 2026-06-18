import { useEffect, useRef } from "react";
import cytoscape, { Core } from "cytoscape";
import { api } from "../api";

const NODE_COLORS: Record<string, string> = {
  orchestrator: "#002b5c", phase: "#4a8fd4", agent: "#7c3aed", artifact: "#0891b2",
  blocker: "#dc2626", gate: "#0891b2", deps: "#d97706",
};

const STYLE: any[] = [
  { selector: "node", style: {
      "background-color": (n: any) => NODE_COLORS[n.data("kind")] || "#5c6577",
      label: "data(label)", color: "#0f1729", "font-size": "10px",
      "text-valign": "bottom", "text-margin-y": 4, width: 26, height: 26,
  } },
  { selector: "node[status = 'done']", style: { "background-color": "#059669" } },
  { selector: "node[status = 'failed']", style: { "background-color": "#dc2626" } },
  { selector: "edge", style: {
      width: 1.5, "line-color": "#cbd5e1", "target-arrow-color": "#cbd5e1",
      "target-arrow-shape": "triangle", "curve-style": "bezier",
  } },
];

export function GraphView({ runId }: { runId: string }) {
  const ref = useRef<HTMLDivElement>(null);
  const cyRef = useRef<Core | null>(null);
  const laidOut = useRef(false);

  useEffect(() => {
    if (!ref.current) return;
    const cy = cytoscape({ container: ref.current, style: STYLE, elements: [] });
    cyRef.current = cy;
    laidOut.current = false;
    let live = true;

    const tick = async () => {
      try {
        const g = await api.graph(runId);
        if (!live) return;
        cy.json({ elements: { nodes: g.nodes, edges: g.edges } });
        if (!laidOut.current && g.nodes.length) {
          cy.layout({ name: "cose", animate: false }).run();
          laidOut.current = true;
        }
      } catch { /* run may have no graph yet */ }
    };
    tick();
    const h = setInterval(tick, 2000);
    return () => { live = false; clearInterval(h); cy.destroy(); cyRef.current = null; };
  }, [runId]);

  return <div className="graph" ref={ref} />;
}
