// DocumentsTab.tsx — Project view §2.5 Documents tab (design orgproject.jsx → ProjectDashboard
// docs view): all project documents as file tiles, split "Uploaded by you" + "Produced by the
// factory". Driven by tjyb5gmy's GET /api/runs/{id}/documents (PR #13); degrades to empty.
import { useEffect, useState } from "react";
import { api, ProjectDocuments, ProjectMaterial, ProjectArtifact } from "../../api";
import { T, CategoryLabel } from "../onboarding/design";

const FILE_KIND: Record<string, [string, string, string]> = {
  pdf: ["PDF", "#fbe3e3", "#c0392f"], xlsx: ["XLS", "#e4f8ef", "#1f8a5b"], csv: ["CSV", "#e4f8ef", "#1f8a5b"],
  doc: ["DOC", "#e8f1ff", "#1A7BFF"], md: ["MD", "#e8f1ff", "#1A7BFF"], svg: ["SVG", "#f3e9fb", "#7a3ea8"],
  video: ["MP4", "#f3e9fb", "#7a3ea8"], img: ["IMG", "#fbefdc", "#b06f12"],
};
function fmtBytes(n?: number): string {
  if (!n) return "";
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${Math.round(n / 1024)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}

function FileTile({ label, kind, sub, tag, onOpen }: { label: string; kind?: string; sub?: string; tag?: string; onOpen?: () => void }) {
  const k = FILE_KIND[kind || "doc"] || FILE_KIND.doc;
  return (
    <button onClick={onOpen} disabled={!onOpen} style={{ textAlign: "left", cursor: onOpen ? "pointer" : "default", background: T.raised, border: `1px solid ${T.borderSubtle}`, borderRadius: T.rLg, padding: "13px 14px", display: "flex", flexDirection: "column", gap: 10, boxShadow: T.shadowXs }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <span style={{ font: `700 9px/1 ${T.mono}`, letterSpacing: "0.05em", color: k[2], background: k[1], padding: "4px 6px", borderRadius: 4 }}>{k[0]}</span>
        {tag && <CategoryLabel style={{ fontSize: 9.5 }}>{tag}</CategoryLabel>}
      </div>
      <span style={{ font: `600 13px/1.3 ${T.sans}`, color: T.fg, wordBreak: "break-word" }}>{label}</span>
      {sub && <span style={{ font: `400 11px/1 ${T.mono}`, color: T.tertiary }}>{sub}</span>}
    </button>
  );
}

export function DocumentsTab({ runId }: { runId: string }) {
  const [docs, setDocs] = useState<ProjectDocuments | null>(null);

  useEffect(() => {
    api.documents(runId).then(setDocs).catch(() => setDocs(null)); // backend pending → graceful empty
  }, [runId]);

  const uploaded: ProjectMaterial[] = docs?.uploaded || [];
  const produced: ProjectArtifact[] = docs?.produced || [];
  const total = uploaded.length + produced.length;

  return (
    <div style={{ flex: 1, overflow: "auto", padding: "22px 24px 36px" }}>
      <div style={{ maxWidth: 920, margin: "0 auto" }}>
        <CategoryLabel style={{ marginBottom: 12 }}>Project documents · {total}</CategoryLabel>

        <h3 style={{ font: `600 13px/1 ${T.sans}`, color: T.secondary, margin: "0 0 10px" }}>Uploaded by you</h3>
        {uploaded.length ? (
          <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 12, marginBottom: 22 }}>
            {uploaded.map((d, i) => <FileTile key={d.name + i} label={d.name} kind={d.kind} sub={fmtBytes(d.size_bytes)} />)}
          </div>
        ) : <div style={{ border: `1px dashed ${T.borderDefault}`, borderRadius: T.rLg, padding: "20px", textAlign: "center", font: `400 12.5px/1.4 ${T.sans}`, color: T.tertiary, marginBottom: 22 }}>Nothing uploaded for this project.</div>}

        <h3 style={{ font: `600 13px/1 ${T.sans}`, color: T.secondary, margin: "0 0 10px" }}>Produced by the factory</h3>
        {produced.length ? (
          <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 12 }}>
            {produced.map((d, i) => <FileTile key={d.title + i} label={d.title} kind={d.kind} tag={d.agent} onOpen={d.path ? () => window.open(`/api/runs/${runId}/artifact?path=${encodeURIComponent(d.path!)}&raw=1`, "_blank") : undefined} />)}
          </div>
        ) : <div style={{ border: `1px dashed ${T.borderDefault}`, borderRadius: T.rLg, padding: "20px", textAlign: "center", font: `400 12.5px/1.4 ${T.sans}`, color: T.tertiary }}>The factory hasn’t produced documents yet.</div>}
      </div>
    </div>
  );
}
