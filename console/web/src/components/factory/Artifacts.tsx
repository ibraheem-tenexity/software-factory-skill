// Artifacts.tsx — the produced-artifacts list (left rail) + the DocViewer modal.
//
// Artifacts are the artifact-kind nodes in the real graph (projected from the project store's artifacts
// table). Each carries { label, path, status, url }. An http path is an external link (repo /
// live app) opened in a new tab; a file path opens in the DocViewer, which fetches the content
// from /api/projects/{id}/artifact?path=… (api.artifact) and renders by extension:
//   .md/.mdx → rich Markdown (shared MarkdownBody, SOF-21) · .svg → inline · everything else → text.
import { useEffect, useState } from "react";
import { T, Icon } from "../onboarding/design";
import { api, Graph, GraphNode } from "../../api";
import { MarkdownBody } from "../../markdown";

export type ArtifactRef = { label: string; path: string; url: string | null; status?: string; id?: number };

// Open the standalone artifact viewer in a new tab by artifact id.
export function openArtifact(id: number | string) {
  window.open(`/ArtifactViewer.html?doc=${id}`, "_blank");
}

export function artifactsFromGraph(graph: Graph): ArtifactRef[] {
  return graph.nodes
    .filter((n: GraphNode) => n.data.kind === "artifact")
    .map((n) => ({ label: n.data.label, path: n.data.path || "", url: n.data.url || null, status: n.data.status, id: n.data.artifact_id }));
}

export function ArtifactList({ artifacts, onOpen }:
  { artifacts: ArtifactRef[]; onOpen: (a: ArtifactRef) => void }) {
  if (!artifacts.length) {
    return <p style={{ margin: 0, font: `400 12px/1.5 ${T.sans}`, color: T.tertiary }}>No artifacts produced yet.</p>;
  }
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
      {artifacts.map((a, i) => {
        const isLink = !!a.url;
        return (
          <button key={i} onClick={() => (isLink ? window.open(a.url!, "_blank") : onOpen(a))}
            style={{ display: "flex", alignItems: "center", gap: 9, textAlign: "left", cursor: "pointer",
              padding: "8px 10px", borderRadius: T.rMd, border: `1px solid ${T.borderSubtle}`, background: T.raised }}>
            <Icon name={isLink ? "external" : "file"} size={14} color={isLink ? T.brandDeep : T.tertiary} />
            <span style={{ flex: 1, font: `500 12.5px/1.3 ${T.sans}`, color: T.fg, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{a.label}</span>
            {a.status === "missing" && <span style={{ font: `400 10px/1 ${T.mono}`, color: T.danger }}>missing</span>}
          </button>
        );
      })}
    </div>
  );
}

// DocViewer — modal that fetches + renders one artifact (or arbitrary content, e.g. a ticket body).
export function DocViewer({ projectId, doc, onClose }:
  { projectId: string; doc: { label: string; path?: string; content?: string; id?: number } | null; onClose: () => void }) {
  const [content, setContent] = useState<string | null>(doc?.content ?? null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!doc) return;
    if (doc.content != null) { setContent(doc.content); return; }
    if (!doc.path) return;
    setLoading(true);
    api.artifact(projectId, doc.path)
      .then((r) => setContent(r.content ?? (r.error ? `Could not load: ${r.error}` : "")))
      .catch((e) => setContent(`Could not load: ${e}`))
      .finally(() => setLoading(false));
  }, [doc, projectId]);

  if (!doc) return null;
  const lowerPath = (doc.path || "").toLowerCase();
  const isSvg = lowerPath.endsWith(".svg");
  const isMd = lowerPath.endsWith(".md") || lowerPath.endsWith(".mdx");

  return (
    <div onClick={onClose} style={{ position: "fixed", inset: 0, background: "rgba(6,7,9,0.45)", zIndex: 50,
      display: "grid", placeItems: "center", padding: 24 }}>
      <div onClick={(e) => e.stopPropagation()} style={{ width: "min(820px, 100%)", maxHeight: "86vh",
        background: T.raised, borderRadius: T.rXl, boxShadow: T.shadowMd, display: "flex", flexDirection: "column", overflow: "hidden" }}>
        <header style={{ display: "flex", alignItems: "center", gap: 10, padding: "13px 16px", borderBottom: `1px solid ${T.borderSubtle}` }}>
          <Icon name="file" size={15} color={T.tertiary} />
          <span style={{ flex: 1, font: `600 14px/1.2 ${T.sans}`, color: T.fg }}>{doc.label}</span>
          {doc.path && <span style={{ font: `400 11px/1 ${T.mono}`, color: T.tertiary }}>{doc.path}</span>}
          {doc.id != null && (
            <button onClick={() => openArtifact(doc.id!)} title="Open full viewer"
              style={{ width: 28, height: 28, display: "grid", placeItems: "center", borderRadius: T.rMd,
                border: "none", background: "transparent", cursor: "pointer", color: T.secondary }}>
              <Icon name="external" size={14} />
            </button>
          )}
          <button onClick={onClose} style={{ width: 28, height: 28, display: "grid", placeItems: "center", borderRadius: T.rMd,
            border: "none", background: "transparent", cursor: "pointer", color: T.secondary }}><Icon name="x" size={16} /></button>
        </header>
        <div style={{ padding: 18, overflow: "auto" }}>
          {loading ? <span style={{ font: `400 13px/1 ${T.sans}`, color: T.tertiary }}>Loading…</span>
            : isSvg && content ? <div style={{ display: "grid", placeItems: "center" }} dangerouslySetInnerHTML={{ __html: content }} />
            : isMd && content ? <MarkdownBody content={content} />
            : <pre style={{ margin: 0, font: `400 12.5px/1.6 ${T.mono}`, color: T.fg, whiteSpace: "pre-wrap", wordBreak: "break-word" }}>{content}</pre>}
        </div>
      </div>
    </div>
  );
}
