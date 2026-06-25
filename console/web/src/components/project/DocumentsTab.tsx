// DocumentsTab.tsx — Project view §2.5 Documents tab (design orgproject.jsx → ProjectDashboard
// docs view): all project documents as file tiles, split "Uploaded by you" + "Produced by the
// factory". Driven by tjyb5gmy's GET /api/projects/{id}/documents (PR #13); degrades to empty.
import React, { useEffect, useRef, useState } from "react";
import { api, ProjectDocuments, ProjectMaterial, ProjectArtifact } from "../../api";
import { openArtifact } from "../factory/Artifacts";
import { T, CategoryLabel, Btn, Icon } from "../onboarding/design";
import { FileTileSkel } from "../skeleton";

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

function FileTile({ label, kind, sub, tag, onOpen, scope, onScope }:
  { label: string; kind?: string; sub?: string; tag?: string; onOpen?: () => void;
    scope?: "project" | "org"; onScope?: (s: "project" | "org") => void }) {
  const k = FILE_KIND[kind || "doc"] || FILE_KIND.doc;
  const stop = (e: React.MouseEvent) => e.stopPropagation();
  return (
    <div role={onOpen ? "button" : undefined} tabIndex={onOpen ? 0 : undefined} onClick={onOpen}
      style={{ textAlign: "left", cursor: onOpen ? "pointer" : "default", background: T.raised, border: `1px solid ${T.borderSubtle}`, borderRadius: T.rLg, padding: "13px 14px", display: "flex", flexDirection: "column", gap: 10, boxShadow: T.shadowXs }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <span style={{ font: `700 9px/1 ${T.mono}`, letterSpacing: "0.05em", color: k[2], background: k[1], padding: "4px 6px", borderRadius: 4 }}>{k[0]}</span>
        {tag && <CategoryLabel style={{ fontSize: 9.5 }}>{tag}</CategoryLabel>}
      </div>
      <span style={{ font: `600 13px/1.3 ${T.sans}`, color: T.fg, wordBreak: "break-word" }}>{label}</span>
      {sub && <span style={{ font: `400 11px/1 ${T.mono}`, color: T.tertiary }}>{sub}</span>}
      {onScope && (
        <div onClick={stop} style={{ display: "flex", gap: 4, background: T.sunken, borderRadius: 9999, padding: 2 }}>
          {(["project", "org"] as const).map((s) => {
            const on = (scope || "project") === s;
            return <button key={s} onClick={() => onScope(s)} style={{ flex: 1, padding: "4px 0", borderRadius: 9999, border: "none", cursor: "pointer", font: `500 10.5px/1 ${T.sans}`, background: on ? T.raised : "transparent", color: on ? T.brandDeep : T.tertiary, boxShadow: on ? T.shadowXs : "none" }}>{s === "project" ? "Project" : "Org-wide"}</button>;
          })}
        </div>
      )}
    </div>
  );
}

export function DocumentsTab({ projectId }: { projectId: string }) {
  const [docs, setDocs] = useState<ProjectDocuments | null>(null);
  const [err, setErr] = useState("");
  const inputRef = useRef<HTMLInputElement | null>(null);

  const [loading, setLoading] = useState(true);
  const loadDocs = () => api.documents(projectId).then(setDocs).catch(() => setDocs(null));
  useEffect(() => { setLoading(true); loadDocs().finally(() => setLoading(false)); }, [projectId]);

  // Material scope toggle (project↔org-wide). PATCH /api/projects/{id}/materials/{materialId} (graceful).
  const setScope = async (materialId: string, scope: "project" | "org") => {
    try { const d = await api.setMaterialScope(projectId, materialId, scope); setDocs(d); } catch { await loadDocs(); }
  };

  // Post-promote material upload (POST /api/projects/{id}/materials NEW — graceful until live).
  const uploadMaterials = async (list: FileList | null) => {
    if (!list || !list.length) return;
    setErr("");
    try {
      for (const file of Array.from(list)) {
        const data_b64 = await new Promise<string>((resolve) => {
          const r = new FileReader();
          r.onload = () => resolve(String(r.result || "").split(",")[1] || "");
          r.onerror = () => resolve("");
          r.readAsDataURL(file);
        });
        await api.uploadMaterial(projectId, { name: file.name, content_type: file.type || undefined, data_b64 });
      }
      await loadDocs();
    } catch { setErr("Upload isn’t available yet."); }
  };

  const uploaded: ProjectMaterial[] = docs?.uploaded || [];
  const produced: ProjectArtifact[] = docs?.produced || [];
  const total = uploaded.length + produced.length;

  return (
    <div style={{ flex: 1, overflow: "auto", padding: "22px 24px 36px" }}>
      <div style={{ maxWidth: 920, margin: "0 auto" }}>
        <input ref={inputRef} type="file" multiple accept=".pdf,.doc,.docx,.xls,.xlsx,.csv,.txt,.md,video/*,image/*" style={{ display: "none" }} onChange={(e) => { uploadMaterials(e.target.files); e.target.value = ""; }} />
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 12 }}>
          <CategoryLabel>Project documents · {total}</CategoryLabel>
          <Btn variant="primary" size="sm" onClick={() => inputRef.current?.click()}><Icon name="upload" size={14} color="#fff" /> Upload material</Btn>
        </div>
        {err && <div style={{ font: `500 12px/1.4 ${T.sans}`, color: T.tertiary, marginBottom: 10 }}>{err}</div>}
        {loading && (
          <>
            <h3 style={{ font: `600 13px/1 ${T.sans}`, color: T.secondary, margin: "0 0 10px" }}>Uploaded by you</h3>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 12, marginBottom: 22 }}>
              {Array.from({ length: 4 }, (_, i) => <FileTileSkel key={i} />)}
            </div>
            <h3 style={{ font: `600 13px/1 ${T.sans}`, color: T.secondary, margin: "0 0 10px" }}>Produced by the factory</h3>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 12 }}>
              {Array.from({ length: 4 }, (_, i) => <FileTileSkel key={i} />)}
            </div>
          </>
        )}

        {!loading && (<>
          <h3 style={{ font: `600 13px/1 ${T.sans}`, color: T.secondary, margin: "0 0 10px" }}>Uploaded by you</h3>
          {uploaded.length ? (
            <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 12, marginBottom: 22 }}>
              {uploaded.map((d, i) => <FileTile key={(d.id || d.name) + i} label={d.name} kind={d.kind} sub={fmtBytes(d.size_bytes)} scope={d.scope} onScope={d.id ? (s) => setScope(d.id!, s) : undefined} />)}
            </div>
          ) : <div style={{ border: `1px dashed ${T.borderDefault}`, borderRadius: T.rLg, padding: "20px", textAlign: "center", font: `400 12.5px/1.4 ${T.sans}`, color: T.tertiary, marginBottom: 22 }}>Nothing uploaded for this project.</div>}

          <h3 style={{ font: `600 13px/1 ${T.sans}`, color: T.secondary, margin: "0 0 10px" }}>Produced by the factory</h3>
          {produced.length ? (
            <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 12 }}>
              {produced.map((d, i) => <FileTile key={d.title + i} label={d.title} kind={d.kind} tag={d.agent} onOpen={d.id ? () => openArtifact(d.id!) : d.path ? () => window.open(`/api/projects/${projectId}/artifact?path=${encodeURIComponent(d.path!)}&raw=1`, "_blank") : undefined} />)}
            </div>
          ) : <div style={{ border: `1px dashed ${T.borderDefault}`, borderRadius: T.rLg, padding: "20px", textAlign: "center", font: `400 12.5px/1.4 ${T.sans}`, color: T.tertiary }}>The factory hasn’t produced documents yet.</div>}
        </>)}
      </div>
    </div>
  );
}
