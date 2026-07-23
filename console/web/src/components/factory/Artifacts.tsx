// Artifacts.tsx — the produced-artifacts list (left rail) + the DocViewer modal.
//
// Artifacts are the artifact-kind nodes in the real graph (projected from the project store's artifacts
// table). Each carries { label, path, status, url } plus, followed through the hierarchy edges, the
// agent that produced it and the pipeline node that agent ran under (artifact ← agent ← phase).
// An http path is an external link (repo / live app) opened in a new tab; a file path opens in the
// DocViewer, which fetches the content from /api/projects/{id}/artifact?path=… (api.artifact) and
// renders by extension:
//   .md/.mdx → rich Markdown (shared MarkdownBody, SOF-21) · .svg → inline · everything else → text.
import { useEffect, useState } from "react";
import { T, Icon, CategoryLabel, ArtifactChip, kindBadgeFor } from "../onboarding/design";
import { api, Graph, GraphNode } from "../../api";
import { ArtifactBody } from "../../viewer/ArtifactBody";

export type ArtifactRef = {
  label: string; path: string; url: string | null; status?: string; id?: number;
  kind?: string;          // badge kind (md/svg/fig/repo/…), derived from path/url
  agent?: string;         // producing agent role (hierarchy parent), if recorded
  node?: string;          // pipeline node label the producing agent ran under
};

// Open the standalone artifact viewer in a new tab by artifact id.
export function openArtifact(id: number | string) {
  window.open(`/ArtifactViewer.html?doc=${id}`, "_blank");
}

// Open the standalone artifact viewer in a new tab for an ORG-scope knowledge-base blob (a
// different table/id-space from the project `artifacts` above — e.g. codebase-discovery's
// generated AGENTS.md/CLAUDE.md/integrations.md). `name` carries the filename through so the
// viewer can title/render it without a second round trip.
export function openOrgDoc(id: number | string, name: string) {
  window.open(`/ArtifactViewer.html?blob=${id}&name=${encodeURIComponent(name)}`, "_blank");
}

// Badge kind from the artifact's path/url (design KIND_BADGE keys; unknown ⇒ the raw extension).
export function artifactKind(path: string, url?: string | null): string {
  const p = (path || "").toLowerCase();
  if (url || p.startsWith("http")) return /github/i.test(url || p) ? "repo" : "link";
  if (p.endsWith(".md") || p.endsWith(".mdx")) return "md";
  if (p.endsWith(".svg")) return "svg";
  if (p.endsWith(".fig")) return "fig";
  const ext = p.includes(".") ? p.split(".").pop()! : "";
  return ext || "doc";
}

export function artifactsFromGraph(graph: Graph): ArtifactRef[] {
  // hierarchy edges: phase → agent and agent/orchestrator → artifact. Resolve each artifact's
  // producing agent (edge source) and that agent's pipeline node (its own hierarchy source).
  const byId: Record<string, GraphNode> = {};
  for (const n of graph.nodes) byId[n.data.id] = n;
  const parentOf: Record<string, string> = {};
  for (const e of graph.edges) {
    if (e.data.etype === "hierarchy") parentOf[e.data.target] = e.data.source;
  }
  return graph.nodes
    .filter((n: GraphNode) => n.data.kind === "artifact")
    .map((n) => {
      const owner = byId[parentOf[n.data.id] || ""];
      const isAgent = owner?.data.kind === "agent";
      const phase = isAgent ? byId[parentOf[owner.data.id] || ""] : undefined;
      return {
        label: n.data.label, path: n.data.path || "", url: n.data.url || null,
        status: n.data.status, id: n.data.artifact_id,
        kind: artifactKind(n.data.path || "", n.data.url),
        agent: isAgent ? owner.data.label : undefined,
        node: phase?.data.kind === "phase" ? phase.data.label : undefined,
      };
    });
}

// Concierge-surfaced list of produced artifacts, grouped by the pipeline node that made them
// (design: artifacts.jsx:137-160 ArtifactList) — header "Artifacts produced · N files".
export function ArtifactList({ artifacts, onOpen }:
  { artifacts: ArtifactRef[]; onOpen: (a: ArtifactRef) => void }) {
  if (!artifacts.length) {
    return <p style={{ margin: 0, font: `400 12px/1.5 ${T.sans}`, color: T.tertiary }}>No artifacts produced yet.</p>;
  }
  // Group per producing node (insertion order); un-attributed artifacts fall into "factory".
  const groups: { node: string; agent?: string; items: ArtifactRef[] }[] = [];
  for (const a of artifacts) {
    const node = a.node || "factory";
    let g = groups.find((x) => x.node === node);
    if (!g) { g = { node, agent: a.agent, items: [] }; groups.push(g); }
    g.items.push(a);
  }
  const open = (a: ArtifactRef) => (a.url ? window.open(a.url, "_blank") : onOpen(a));
  return (
    <div style={{ border: `1px solid ${T.borderSubtle}`, borderRadius: T.rLg, overflow: "hidden" }}>
      <div style={{ padding: "9px 12px", borderBottom: `1px solid ${T.borderSubtle}`, background: T.sunken,
        display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <CategoryLabel>Artifacts produced</CategoryLabel>
        <span style={{ font: `500 10px/1 ${T.mono}`, color: T.tertiary }}>{artifacts.length} files</span>
      </div>
      <div style={{ display: "flex", flexDirection: "column" }}>
        {groups.map((g) => (
          <div key={g.node} style={{ padding: "10px 12px", borderBottom: `1px solid ${T.borderSubtle}` }}>
            <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 7 }}>
              <span style={{ font: `500 11px/1 ${T.mono}`, color: T.tertiary }}>{g.node}</span>
              {g.agent && <span style={{ font: `400 11px/1 ${T.sans}`, color: T.tertiary }}>· {g.agent}</span>}
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 6, alignItems: "stretch" }}>
              {g.items.map((a, i) => (
                <ArtifactChip key={`${a.path}-${i}`} small onOpen={open}
                  a={{ ...a, note: a.status === "missing" ? "missing" : undefined }} />
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

// DocViewer — modal that fetches + renders one artifact (or arbitrary content, e.g. a ticket body).
// Header (design: artifacts.jsx:118-123): KIND badge · mono filename · "· produced by {agent}".
export function DocViewer({ projectId, doc, onClose, preview = false }:
  { projectId: string;
    doc: { label: string; path?: string; content?: string; id?: number; url?: string | null; agent?: string; kind?: string } | null;
    onClose: () => void; preview?: boolean }) {
  const [content, setContent] = useState<string | null>(doc?.content ?? null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!doc) return;
    setContent(doc.content ?? null);
    // SOF-199: a URL-backed doc (doc.url set — e.g. Product Brief, GitHub Repo) has no repo-
    // relative path to resolve server-side; fetching by path there always 404s ("Could not load:
    // not found") even though the SAME node's full-viewer button opens it fine via doc.id/doc.url.
    // Render it as a link instead (below) — never attempt the by-path fetch for it.
    if (doc.content != null || !doc.path || doc.url) return;
    setLoading(true);
    api.artifact(projectId, doc.path)
      .then((r) => setContent(r.content ?? (r.error ? `Could not load: ${r.error}` : "")))
      .catch((e) => setContent(`Could not load: ${e}`))
      .finally(() => setLoading(false));
  }, [doc, projectId]);

  if (!doc) return null;
  const k = kindBadgeFor(doc.kind || (doc.path ? artifactKind(doc.path) : "doc"));
  // Render the body through the ONE shared renderer (SOF-245): a URL-backed doc with no inline
  // content routes to the shared external-link/unavailable framing; otherwise Markdown/SVG/code
  // dispatch off the real path — no second parser lives here anymore.
  const bodyPath = content == null && doc.url ? doc.url : (doc.path || "");
  const openFull = () => {
    if (doc.id != null) openArtifact(doc.id);
    else if (doc.url) window.open(doc.url, "_blank");
  };
  const canOpenFull = doc.id != null || !!doc.url;

  return (
    <div onClick={onClose} style={{ position: "fixed", inset: 0, background: "rgba(6,7,9,0.45)", zIndex: 50,
      display: "grid", placeItems: "center", padding: 24 }}>
      <div onClick={(e) => e.stopPropagation()} style={{ width: preview ? "min(560px, 100%)" : "min(820px, 100%)", maxHeight: preview ? "58vh" : "86vh",
        background: T.raised, borderRadius: T.rXl, boxShadow: T.shadowMd, display: "flex", flexDirection: "column", overflow: "hidden" }}>
        <header style={{ display: "flex", alignItems: "center", gap: 9, padding: "13px 16px", borderBottom: `1px solid ${T.borderSubtle}` }}>
          <span style={{ font: `700 9px/1 ${T.mono}`, letterSpacing: "0.04em", color: k[2], background: k[1],
            padding: "4px 5px", borderRadius: 3, flexShrink: 0 }}>{k[0]}</span>
          <span title={doc.path || undefined} style={{ font: `600 14px/1.2 ${T.mono}`, color: T.fg,
            overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{doc.label}</span>
          {doc.agent && <span style={{ font: `400 12px/1 ${T.sans}`, color: T.tertiary, whiteSpace: "nowrap" }}>· produced by {doc.agent}</span>}
          <span style={{ flex: 1 }} />
          {canOpenFull && (
            <button onClick={openFull} title="Open full viewer"
              style={{ width: 28, height: 28, display: "grid", placeItems: "center", borderRadius: T.rMd,
                border: "none", background: "transparent", cursor: "pointer", color: T.secondary }}>
              <Icon name="external" size={14} />
            </button>
          )}
          <button onClick={onClose} style={{ width: 28, height: 28, display: "grid", placeItems: "center", borderRadius: T.rMd,
            border: "none", background: "transparent", cursor: "pointer", color: T.secondary }}><Icon name="x" size={16} /></button>
        </header>
        <div style={{ flex: 1, minHeight: 0, display: "flex", flexDirection: "column" }}>
          {loading
            ? <div style={{ padding: 18 }}><span style={{ font: `400 13px/1 ${T.sans}`, color: T.tertiary }}>Loading…</span></div>
            : <ArtifactBody data={{ kind: doc.kind || (doc.path ? artifactKind(doc.path) : "doc"), path: bodyPath, content: content ?? null, project_id: projectId, title: doc.label }} />}
        </div>
      </div>
    </div>
  );
}
