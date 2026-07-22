// ProcessingScreen.tsx — Step 2 of the Intake→Processing→Interview→Handoff flow (PRD §2.4a
// "Step 2 — ProcessingScreen"). Shows real per-file ingest progress over the SOF-49/T3.2 SSE
// channel and calls onDone() once every attached file reaches a terminal status. If the draft
// has no attached files at all, there is nothing to process — call onDone() immediately.
// SOF-72: if ingest emits no SSE events (worker died pre-first-event, connection drop, wedged
// summarize) the user gets an explicit "Continue to interview" escape hatch instead of hanging
// forever — never auto-skipped, and still-running rows keep their real backend-reported status.
import React, { useEffect, useRef, useState } from "react";
import { api } from "../../api";
import { T, Icon, CategoryLabel, Wordmark, Btn } from "./design";

type FileRow = { blobId: number; name: string; pct: number; stage: string; status: "running" | "ready" | "failed" };

// SOF-226: map a documents-endpoint row to a FileRow using its real summary_status.
function seedRow(d: { id?: string; name: string; summary_status?: "pending" | "ready" | "failed" }): FileRow {
  if (d.summary_status === "ready") return { blobId: Number(d.id), name: d.name, pct: 100, stage: "done", status: "ready" };
  if (d.summary_status === "failed") return { blobId: Number(d.id), name: d.name, pct: 100, stage: "failed", status: "failed" };
  return { blobId: Number(d.id), name: d.name, pct: 0, stage: "queued", status: "running" };
}

const STALL_MS = 20_000;

export function ProcessingScreen({ draftId, projectName, onDone }: { draftId: string; projectName: string; onDone: () => void }) {
  const [files, setFiles] = useState<FileRow[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [stalled, setStalled] = useState(false);
  const firedDoneRef = useRef(false);
  const lastEventAtRef = useRef(Date.now());

  // Seed the file list from the draft's attached materials so we know how many rows to wait for
  // even before the first SSE frame arrives for each one.
  useEffect(() => {
    let live = true;
    api.documents(draftId).then((docs) => {
      if (!live) return;
      // SOF-226: seed from the truth the response already carries — a doc whose ingestion
      // finished BEFORE this screen mounted (fast ingest, missed SSE events: the stream has no
      // replay) must render done immediately, not sit "queued" forever waiting for events that
      // already fired.
      const rows: FileRow[] = (docs.uploaded || [])
        .filter((d) => d.id != null)
        .map((d) => seedRow(d));
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
      lastEventAtRef.current = Date.now();
      setStalled(false);
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

  // SOF-72: watch for a stalled ingest — no SSE event within STALL_MS of mount, or since the
  // last event mid-run. SOF-226: before surfacing the notice, RECONCILE against the documents
  // endpoint (summary_status is authoritative) — a missed SSE event (no-replay stream) then
  // self-heals instead of stranding the user; the notice remains only for genuinely stuck docs.
  useEffect(() => {
    if (allDone) { setStalled(false); return; }
    const t = setInterval(() => {
      if (Date.now() - lastEventAtRef.current <= STALL_MS) return;
      api.documents(draftId).then((docs) => {
        const byId = new Map((docs.uploaded || []).filter((d) => d.id != null).map((d) => [Number(d.id), d.summary_status]));
        let healed = false;
        setFiles((rows) => rows.map((r) => {
          const s = byId.get(r.blobId);
          if (r.status === "running" && (s === "ready" || s === "failed")) {
            healed = true;
            return { ...r, status: s, pct: 100, stage: s === "ready" ? "done" : "failed" };
          }
          return r;
        }));
        if (healed) { lastEventAtRef.current = Date.now(); setStalled(false); }
        else setStalled(true);
      }).catch(() => setStalled(true));
    }, 2000);
    return () => clearInterval(t);
  }, [allDone, draftId]);

  const continueAnyway = () => {
    if (firedDoneRef.current) return;
    firedDoneRef.current = true;
    onDone();
  };

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

          {stalled && !allDone && (
            <div style={{ marginTop: 16, borderRadius: T.rLg, background: T.warningSoft, border: `1px solid ${T.warning}`, padding: "12px 16px", display: "flex", alignItems: "center", gap: 12 }}>
              <div style={{ flex: 1 }}>
                <div style={{ font: `600 13px/1.4 ${T.sans}`, color: T.fg }}>Processing is taking longer than expected</div>
                <div style={{ font: `400 12px/1.4 ${T.sans}`, color: T.secondary }}>
                  You can continue to the interview now — any documents still processing will keep going in the background.
                </div>
              </div>
              <Btn variant="secondary" size="sm" onClick={continueAnyway}>Continue to interview</Btn>
            </div>
          )}

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
