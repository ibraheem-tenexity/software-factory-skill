// DocumentsTab.tsx — Project view §2.5 Documents tab (design orgproject.jsx → ProjectDashboard
// docs view): all project documents as file tiles, split "Uploaded by you" + "Produced by the
// factory". Driven by tjyb5gmy's GET /api/projects/{id}/documents (PR #13); degrades to empty.
import React, { useEffect, useRef, useState } from "react";
import { api, ProjectDocuments, ProjectMaterial, ProjectArtifact } from "../../api";
import { openArtifact } from "../factory/Artifacts";
import { T, CategoryLabel, Btn, Icon, StatusPill } from "../onboarding/design";
import { FileTileSkel } from "../skeleton";

// SOF-91: a document with no visible status looked identical whether it was never ingested,
// still processing, or had genuinely failed — the only signal was a blank summary line. Map the
// real summary_status (undefined = no doc_summary row at all yet) to an explicit, distinct badge.
const INGEST_STATUS: Record<string, { tone: "success" | "warning" | "danger" | "neutral"; label: string }> = {
  ready: { tone: "success", label: "Ingested" },
  pending: { tone: "warning", label: "Processing…" },
  failed: { tone: "danger", label: "Failed to ingest" },
};

const FILE_KIND: Record<string, [string, string, string]> = {
  pdf: ["PDF", "#fbe3e3", "#c0392f"], xlsx: ["XLS", "#e4f8ef", "#1f8a5b"], csv: ["CSV", "#e4f8ef", "#1f8a5b"],
  doc: ["DOC", "#e8f1ff", "#1A7BFF"], md: ["MD", "#e8f1ff", "#1A7BFF"], svg: ["SVG", "#f3e9fb", "#7a3ea8"],
  video: ["MP4", "#f3e9fb", "#7a3ea8"], img: ["IMG", "#fbefdc", "#b06f12"], mockup: ["HTML", "#f3e9fb", "#7a3ea8"],
};
function fmtBytes(n?: number): string {
  if (!n) return "";
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${Math.round(n / 1024)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}

function FileTile({ label, kind, sub, used, tag, onOpen, scope, onScope, summary, summaryStatus, summarizing, onSummarize }:
  { label: string; kind?: string; sub?: string; used?: string; tag?: string; onOpen?: () => void;
    scope?: "project" | "org"; onScope?: (s: "project" | "org") => void;
    summary?: string; summaryStatus?: "pending" | "ready" | "failed"; summarizing?: boolean; onSummarize?: () => void }) {
  const k = FILE_KIND[kind || "doc"] || FILE_KIND.doc;
  const stop = (e: React.MouseEvent) => e.stopPropagation();
  // Design (orgproject.jsx FileTile) renders a real <button> with the sf-artchip hover class —
  // native keyboard handling (Enter/Space) for free, not a div+tabIndex+onKeyDown reimplementation.
  const Tile = onOpen ? "button" : "div";
  // Hover is JS-state-driven, not the sf-artchip CSS class (index.css) — this tile's border/
  // box-shadow are already set INLINE below, and inline styles always beat a stylesheet
  // selector's border-color/box-shadow regardless of specificity, so .sf-artchip:hover could
  // never actually win (confirmed live: only `transform`, which has no inline counterpart,
  // was ever applying). Every other interactive element in this codebase is inline-driven the
  // same way, so this matches the established convention rather than fighting the cascade.
  const [hovered, setHovered] = useState(false);
  const hoverActive = !!onOpen && hovered;
  return (
    <Tile onClick={onOpen} onMouseEnter={() => setHovered(true)} onMouseLeave={() => setHovered(false)}
      className={onOpen ? "sf-artchip" : undefined}
      style={{ textAlign: "left", cursor: onOpen ? "pointer" : "default", background: T.raised,
        border: `1px solid ${hoverActive ? T.brand : T.borderSubtle}`, borderRadius: T.rLg, padding: "13px 14px",
        display: "flex", flexDirection: "column", gap: 10,
        boxShadow: hoverActive ? T.shadowMd : T.shadowXs,
        transform: hoverActive ? "translateY(-1px)" : "none",
        transition: "border-color .12s, transform .12s, box-shadow .12s",
        width: "100%", font: "inherit" }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <span style={{ font: `700 9px/1 ${T.mono}`, letterSpacing: "0.05em", color: k[2], background: k[1], padding: "4px 6px", borderRadius: 4 }}>{k[0]}</span>
        {tag && <CategoryLabel style={{ fontSize: 9.5 }}>{tag}</CategoryLabel>}
      </div>
      <span style={{ font: `600 13px/1.3 ${T.sans}`, color: T.fg, wordBreak: "break-word" }}>{label}</span>
      {onSummarize && (
        <StatusPill tone={(summaryStatus && INGEST_STATUS[summaryStatus]?.tone) || "neutral"}>
          {(summaryStatus && INGEST_STATUS[summaryStatus]?.label) || "Not yet ingested"}
        </StatusPill>
      )}
      {(sub || used) && (
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", font: `400 11px/1 ${T.mono}`, color: T.tertiary }}>
          <span>{sub}</span>{used && <span>{used}</span>}
        </div>
      )}
      {summary && (
        <span style={{ font: `400 11.5px/1.4 ${T.sans}`, color: T.secondary, display: "-webkit-box",
          WebkitLineClamp: 2, WebkitBoxOrient: "vertical", overflow: "hidden" }}>{summary}</span>
      )}
      {onSummarize && (
        <button onClick={(e) => { stop(e); onSummarize(); }} disabled={summarizing}
          style={{ alignSelf: "flex-start", padding: "3px 8px", borderRadius: 9999, border: `1px solid ${T.borderDefault}`,
            background: "transparent", color: summarizing ? T.tertiary : T.brandDeep, cursor: summarizing ? "default" : "pointer",
            font: `500 10.5px/1 ${T.sans}` }}>
          {summarizing ? "Summarizing…" : summaryStatus === "failed" ? "Retry ingestion" : summary ? "Regenerate" : "Auto-summarize"}
        </button>
      )}
      {onScope && (
        <div onClick={stop} style={{ display: "flex", gap: 4, background: T.sunken, borderRadius: 9999, padding: 2 }}>
          {(["project", "org"] as const).map((s) => {
            const on = (scope || "project") === s;
            return <button key={s} onClick={() => onScope(s)} style={{ flex: 1, padding: "4px 0", borderRadius: 9999, border: "none", cursor: "pointer", font: `500 10.5px/1 ${T.sans}`, background: on ? T.raised : "transparent", color: on ? T.brandDeep : T.tertiary, boxShadow: on ? T.shadowXs : "none" }}>{s === "project" ? "Project" : "Org-wide"}</button>;
          })}
        </div>
      )}
    </Tile>
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

  // Auto-summarize / Regenerate (SOF-36/T3.3). One in flight at a time per tile — summarizingId
  // gates just that tile's button, the rest of the grid stays interactive.
  const [summarizingId, setSummarizingId] = useState<string | null>(null);
  const [summarizeErr, setSummarizeErr] = useState("");
  const summarize = async (materialId: string) => {
    setSummarizingId(materialId);
    setSummarizeErr("");
    try {
      const d = await api.summarizeDocument(projectId, materialId);
      setDocs(d);
    } catch {
      setSummarizeErr("Summarize isn’t available right now.");
    } finally {
      setSummarizingId(null);
    }
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
  // Org knowledge base surfaced on this tab (design #32 / PRD §2.5b) — where a doc toggled
  // project→org lands, with a toggle back to project so it never disappears.
  const org: ProjectMaterial[] = docs?.org || [];
  const total = uploaded.length + produced.length + org.length;

  return (
    <div style={{ flex: 1, overflow: "auto", padding: "22px 24px 36px" }}>
      <div style={{ maxWidth: 920, margin: "0 auto" }}>
        <input ref={inputRef} type="file" multiple accept=".pdf,.doc,.docx,.xls,.xlsx,.csv,.txt,.md,video/*,image/*" style={{ display: "none" }} onChange={(e) => { uploadMaterials(e.target.files); e.target.value = ""; }} />
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 12 }}>
          <CategoryLabel>Project documents · {total}</CategoryLabel>
          <Btn variant="primary" size="sm" onClick={() => inputRef.current?.click()}><Icon name="upload" size={14} color="#fff" /> Upload material</Btn>
        </div>
        {err && <div style={{ font: `500 12px/1.4 ${T.sans}`, color: T.danger, marginBottom: 10 }}>{err}</div>}
        {summarizeErr && <div style={{ font: `500 12px/1.4 ${T.sans}`, color: T.danger, marginBottom: 10 }}>{summarizeErr}</div>}
        {loading && (
          <>
            <h3 style={{ font: `600 13px/1 ${T.sans}`, color: T.secondary, margin: "0 0 10px" }}>Uploaded by you</h3>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 12, marginBottom: 22 }}>
              {Array.from({ length: 4 }, (_, i) => <FileTileSkel key={i} />)}
            </div>
            <h3 style={{ font: `600 13px/1 ${T.sans}`, color: T.secondary, margin: "0 0 10px" }}>From your organization</h3>
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
              {uploaded.map((d, i) => <FileTile key={(d.id || d.name) + i} label={d.name} kind={d.kind} sub={fmtBytes(d.size_bytes)} scope={d.scope} onScope={d.id ? (s) => setScope(d.id!, s) : undefined} summary={d.summary} summaryStatus={d.summary_status} summarizing={!!d.id && summarizingId === d.id} onSummarize={d.id ? () => summarize(d.id!) : undefined} />)}
            </div>
          ) : <div style={{ border: `1px dashed ${T.borderDefault}`, borderRadius: T.rLg, padding: "20px", textAlign: "center", font: `400 12.5px/1.4 ${T.sans}`, color: T.tertiary, marginBottom: 22 }}>Nothing uploaded for this project.</div>}

          <div style={{ display: "flex", alignItems: "baseline", gap: 8, margin: "0 0 10px" }}>
            <h3 style={{ font: `600 13px/1 ${T.sans}`, color: T.secondary, margin: 0 }}>From your organization</h3>
            <span style={{ font: `400 11.5px/1 ${T.sans}`, color: T.tertiary }}>· knowledge base · reused across projects</span>
          </div>
          {org.length ? (
            <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 12, marginBottom: 22 }}>
              {org.map((d, i) => <FileTile key={(d.id || d.name) + i} label={d.name} kind={d.kind} sub={fmtBytes(d.size_bytes)} tag={d.tag} used={d.used_count ? `${d.used_count} project${d.used_count > 1 ? "s" : ""}` : undefined} scope="org" onScope={d.id ? (s) => setScope(d.id!, s) : undefined} />)}
            </div>
          ) : <div style={{ border: `1px dashed ${T.borderDefault}`, borderRadius: T.rLg, padding: "20px", textAlign: "center", font: `400 12.5px/1.4 ${T.sans}`, color: T.tertiary, marginBottom: 22 }}>Your organization’s knowledge base is empty. Toggle a document to “Org-wide” to share it across every project.</div>}

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
