// ProcessingScreen.tsx — Step 2 of the Intake→Processing→Interview→Handoff flow (PRD §2.4a
// "Step 2 — ProcessingScreen"). Shows real per-file ingest progress over the SOF-49/T3.2 SSE
// channel and calls onDone() once every attached file reaches a terminal status. If the draft
// has no attached files at all, there is nothing to process — call onDone() immediately.
import React, { useEffect, useRef, useState } from "react";
import { api } from "../../api";
import { T, Icon, CategoryLabel, Wordmark } from "./design";

type FileRow = { blobId: number; name: string; pct: number; stage: string; status: "running" | "ready" | "failed" };

export function ProcessingScreen({ draftId, projectName, onDone }: { draftId: string; projectName: string; onDone: () => void }) {
  const [files, setFiles] = useState<FileRow[]>([]);
  const [loaded, setLoaded] = useState(false);
  const firedDoneRef = useRef(false);

  // Seed the file list from the draft's attached materials so we know how many rows to wait for
  // even before the first SSE frame arrives for each one.
  useEffect(() => {
    let live = true;
    api.documents(draftId).then((docs) => {
      if (!live) return;
      const rows: FileRow[] = (docs.uploaded || [])
        .filter((d) => d.id != null)
        .map((d) => ({ blobId: Number(d.id), name: d.name, pct: 0, stage: "queued", status: "running" as const }));
      setFiles(rows);
      setLoaded(true);
    }).catch(() => setLoaded(true));
    return () => { live = false; };
  }, [draftId]);

  useEffect(() => {
    const es = new EventSource(`/api/projects/${draftId}/ingest/stream`);
    es.onmessage = (ev) => {
      let data: { blob_id: number; doc_name?: string; stage: string; pct: number; status: string };
      try { data = JSON.parse(ev.data); } catch { return; }
      setFiles((rows) => {
        const known = rows.some((r) => r.blobId === data.blob_id);
        return known
          ? rows.map((r) => r.blobId === data.blob_id
              ? { ...r, stage: data.stage, pct: data.pct, status: (data.status === "ready" || data.status === "failed") ? data.status : "running" }
              : r)
          : [...rows, { blobId: data.blob_id, name: data.doc_name || "file", pct: data.pct,
              stage: data.stage, status: (data.status === "ready" || data.status === "failed") ? data.status : "running" }];
      });
    };
    return () => es.close();
  }, [draftId]);

  const allDone = loaded && files.every((f) => f.status !== "running");
  useEffect(() => {
    if (!allDone || firedDoneRef.current) return;
    firedDoneRef.current = true;
    const t = setTimeout(onDone, files.length ? 900 : 0);
    return () => clearTimeout(t);
  }, [allDone, files.length, onDone]);

  const totalPct = files.length ? Math.round(files.reduce((s, f) => s + (f.status === "running" ? f.pct : 100), 0) / files.length) : 100;
  const active = files.find((f) => f.status === "running");

  return (
    <div style={{ height: "100%", display: "flex", flexDirection: "column", background: T.bg, fontFamily: T.sans }}>
      <div style={{ display: "flex", alignItems: "center", gap: 10, padding: "14px 24px", background: T.raised, borderBottom: `1px solid ${T.borderSubtle}`, flexShrink: 0 }}>
        <Wordmark /><span style={{ color: T.tertiary }}>/</span>
        <span style={{ font: `600 13px/1.2 ${T.sans}`, color: T.fg }}>{projectName || "Untitled project"}</span>
        <span style={{ marginLeft: "auto", display: "inline-flex", alignItems: "center", gap: 6, padding: "5px 10px", borderRadius: 9999, background: T.brandSoft, font: `600 11px/1 ${T.sans}`, color: T.brandDeep }}>
          <span style={{ display: "inline-flex", animation: "sfSpin 1s linear infinite" }}><Icon name="refresh" size={12} color={T.brandDeep} /></span> Processing
        </span>
      </div>

      <div style={{ flex: 1, overflow: "auto", padding: "40px 32px" }}>
        <div style={{ maxWidth: 640, margin: "0 auto" }}>
          <CategoryLabel tone="brand" style={{ marginBottom: 9 }}>Step 2 of 3 · Processing your materials</CategoryLabel>
          <h1 style={{ font: `700 26px/1.2 ${T.display}`, letterSpacing: "-0.02em", color: T.fg, margin: 0 }}>Reading what you gave us</h1>
          <p style={{ font: `400 14px/1.5 ${T.sans}`, color: T.secondary, margin: "8px 0 24px" }}>
            Large files can take a moment — we'll move to the interview the instant this finishes.
          </p>

          <div style={{ marginBottom: 8, display: "flex", justifyContent: "space-between", font: `500 12px/1 ${T.mono}`, color: T.secondary }}>
            <span>{active ? active.name : (files.length ? "Finishing up" : "Nothing to process")}</span>
            <span>{totalPct}%</span>
          </div>
          <div style={{ height: 8, borderRadius: 5, background: T.sunken, overflow: "hidden" }}>
            <div style={{ height: "100%", width: `${totalPct}%`, borderRadius: 5, background: allDone ? T.success : T.brand, transition: "width 300ms ease" }} />
          </div>

          {files.length > 0 && (
            <div style={{ marginTop: 20, borderRadius: T.rLg, background: T.ink, padding: "14px 16px", display: "flex", flexDirection: "column", gap: 6 }}>
              {files.map((f) => (
                <div key={f.blobId} style={{ display: "flex", alignItems: "center", gap: 8, font: `400 12px/1.5 ${T.mono}`, color: f.status === "running" ? "#fff" : "rgba(255,255,255,0.55)" }}>
                  {f.status === "failed"
                    ? <Icon name="x" size={12} color="#F87171" />
                    : f.status === "ready"
                      ? <Icon name="check" size={12} color={T.success} />
                      : <span style={{ display: "inline-flex", animation: "sfSpin 1s linear infinite" }}><Icon name="refresh" size={12} color="#fff" /></span>}
                  <span>{f.name} — {f.status === "running" ? f.stage : f.status}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
