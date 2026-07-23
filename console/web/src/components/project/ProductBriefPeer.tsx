// ProductBriefPeer.tsx — the Product brief peer body (SOF-242 reader + SOF-243 editor), mounted
// inside the unified Project Console shell (SOF-239) at ProjectConsole's `view === "brief"` line.
//
// One document, one write path. Everything here reads and writes the CANONICAL versioned Product
// Brief through the SOF-244 API (api.productBrief / productBriefVersions / productBriefVersion /
// saveProductBrief). There is NO parallel store: a direct save POSTs a new immutable artifact
// version exactly the way the Concierge's finalize_product_brief does (newest-wins, prior versions
// retained as history — never mutated). The reader derives its contents rail from the headings that
// actually exist in the Markdown (presentation index only; no fixed section model), renders the body
// through the shared MarkdownBody engine, and surfaces the real server reason on every failure.
import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, ApiError, ProductBriefDoc, ProductBriefVersion } from "../../api";
import { T, Icon, Btn } from "../onboarding/design";
import { Spinner } from "../skeleton";
import { MarkdownBody, extractToc } from "../../markdown";
import { setDisplayContext } from "../factory/displayContext";
import { openArtifact } from "../factory/Artifacts";

// The server's actual refusal text, never a plausible-sounding guess. 409 conflict details arrive as
// { message, latest }; 400 (empty markdown) / 404 arrive as a plain string; anything else falls back
// to the thrown Error message.
function errText(e: unknown): string {
  const err = e as ApiError;
  const d = err?.detail;
  if (typeof d === "string" && d) return d;
  if (d && typeof d === "object" && typeof (d as { message?: unknown }).message === "string") {
    return (d as { message: string }).message;
  }
  return err?.message || "Something went wrong.";
}

// Factual provenance of a version — the SOF-60 origin/agent convention, not a fabricated source line.
function sourceLabel(v: { origin: string; agent: string | null }): string {
  if (v.origin === "agent") return `Created by ${v.agent === "concierge" ? "the Concierge" : v.agent || "an agent"}`;
  return "Edited directly in the console";
}

function fmtWhen(epoch?: number): string {
  if (!epoch) return "—";
  return new Date(epoch * 1000).toLocaleString("en-US",
    { month: "short", day: "numeric", year: "numeric", hour: "numeric", minute: "2-digit" });
}

export function ProductBriefPeer({ projectId }: { projectId: string }) {
  // The true newest canonical version's id (drives "is this the current version?" everywhere).
  const [latestId, setLatestId] = useState<number | null>(null);
  const [versions, setVersions] = useState<ProductBriefVersion[]>([]);
  // The version currently on screen — latest by default, or a historical one when browsing history.
  const [doc, setDoc] = useState<ProductBriefDoc | null>(null);
  const [viewingId, setViewingId] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [showHistory, setShowHistory] = useState(false);
  const [selHeading, setSelHeading] = useState<string | null>(null);

  // Editor (SOF-243)
  const [mode, setMode] = useState<"read" | "edit">("read");
  const [draft, setDraft] = useState("");
  const [baseMarkdown, setBaseMarkdown] = useState("");
  const [baseId, setBaseId] = useState<number | null>(null);
  const [saveState, setSaveState] = useState<"idle" | "saving" | "saved" | "error">("idle");
  const [saveError, setSaveError] = useState<string | null>(null);
  // A newer canonical version than the one open for editing — detected reactively (409 on save) OR
  // proactively (poll sees a Concierge revision). Never overwrites the draft; the user reconciles.
  const [newer, setNewer] = useState<ProductBriefDoc | null>(null);

  const taRef = useRef<HTMLTextAreaElement>(null);
  const bodyRef = useRef<HTMLDivElement>(null);

  const dirty = mode === "edit" && draft !== baseMarkdown;
  const onLatest = viewingId != null && viewingId === latestId;

  // Initial load (and on project change): newest version + the version list, together.
  const load = useCallback(async () => {
    setLoading(true); setLoadError(null);
    try {
      const [{ latest }, vres] = await Promise.all([
        api.productBrief(projectId),
        api.productBriefVersions(projectId),
      ]);
      setVersions(vres.versions);
      setLatestId(latest ? latest.artifact_id : null);
      setDoc(latest);
      setViewingId(latest ? latest.artifact_id : null);
    } catch (e) {
      setLoadError(errText(e));
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  useEffect(() => {
    setMode("read"); setNewer(null); setShowHistory(false); setSelHeading(null);
    load();
  }, [projectId, load]);

  // Poll for a newer canonical version (e.g. a Concierge finalize while this page is open). If we are
  // reading the latest, follow to it; if we are mid-edit with unsaved work, surface a non-destructive
  // banner instead of clobbering the draft (SOF-243 AC).
  useEffect(() => {
    let live = true;
    const h = setInterval(async () => {
      try {
        const { latest } = await api.productBrief(projectId);
        if (!live) return;
        const newId = latest ? latest.artifact_id : null;
        if (newId === latestId) return;
        api.productBriefVersions(projectId).then((r) => live && setVersions(r.versions)).catch(() => {});
        if (mode === "edit" && dirty) {
          setNewer(latest);         // reconcile on the user's terms; keep the draft
          setLatestId(newId);       // stop the banner from re-firing every tick
        } else {
          setLatestId(newId);
          if (mode === "read" && (viewingId == null || onLatest)) { setDoc(latest); setViewingId(newId); }
        }
      } catch { /* transient poll error — the next tick retries; the mounted view is unaffected */ }
    }, 8000);
    return () => { live = false; clearInterval(h); };
  }, [projectId, latestId, mode, dirty, viewingId, onLatest]);

  // Relay what the customer is looking at to the persistent Concierge (SOF-245 display-context store —
  // the SAME channel Factory outputs uses; no bespoke wiring). The selected heading rides along so
  // "explain this section" is grounded. Cleared on unmount.
  useEffect(() => {
    if (!doc) { setDisplayContext(null); return; }
    const title = doc.title || "Product brief";
    const where = mode === "edit" ? "editing the Product brief"
      : `viewing the Product brief${onLatest ? "" : " (an earlier version)"}`;
    const sect = selHeading ? ` — section “${selHeading}”` : "";
    setDisplayContext({
      projectId, artifactId: doc.artifact_id, title, stageLabel: "Product brief", kindLabel: "Product Brief",
      summary: `The customer is ${where}${sect}.`,
    });
    return () => setDisplayContext(null);
  }, [projectId, doc, mode, onLatest, selHeading]);

  const toc = useMemo(() => (doc?.markdown ? extractToc(doc.markdown) : []), [doc?.markdown]);

  const selectHeading = (id: string, text: string) => {
    setSelHeading(text);
    const el = bodyRef.current?.querySelector(`#${(window.CSS && CSS.escape) ? CSS.escape(id) : id}`);
    if (el) el.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  const openVersion = async (id: number) => {
    setShowHistory(false); setSelHeading(null);
    try {
      const d = await api.productBriefVersion(projectId, id);
      setDoc(d); setViewingId(id);
    } catch (e) { setLoadError(errText(e)); }
  };

  // ── editor actions ────────────────────────────────────────────────────────────────────
  const startEdit = () => {
    const md = doc?.markdown ?? "";
    setBaseMarkdown(md); setDraft(md); setBaseId(doc ? doc.artifact_id : null);
    setSaveState("idle"); setSaveError(null); setNewer(null); setShowHistory(false); setSelHeading(null);
    setMode("edit");
  };
  const cancelEdit = () => {
    if (dirty && !confirm("Discard your unsaved changes to the Product Brief?")) return;
    setMode("read"); setNewer(null); setSaveState("idle"); setSaveError(null);
    setDraft(""); setBaseMarkdown("");
  };
  const doSave = async () => {
    setSaveState("saving"); setSaveError(null);
    try {
      const saved = await api.saveProductBrief(projectId, draft, baseId);
      setLatestId(saved.artifact_id); setDoc(saved); setViewingId(saved.artifact_id);
      setNewer(null); setSaveState("saved");
      api.productBriefVersions(projectId).then((r) => setVersions(r.versions)).catch(() => {});
      setMode("read");
    } catch (e) {
      const err = e as ApiError;
      const d = err?.detail as { message?: string; latest?: ProductBriefDoc } | undefined;
      if (err?.status === 409 && d?.latest) { setNewer(d.latest); setSaveError(d.message || "A newer version exists."); }
      else setSaveError(errText(e));
      setSaveState("error");
    }
  };
  // Reconcile: keep MY draft, rebase it onto the newer version so the next Save appends it as the new
  // newest (append-only — the intervening version stays in history, nothing is overwritten).
  const rebaseOntoNewer = () => { if (newer) { setBaseId(newer.artifact_id); setNewer(null); setSaveError(null); setSaveState("idle"); } };
  // Reconcile the other way: throw away MY draft and load the newer version read-only.
  const discardForNewer = () => {
    if (!newer) return;
    if (dirty && !confirm("Discard your draft and load the newer version?")) return;
    setDoc(newer); setViewingId(newer.artifact_id); setLatestId(newer.artifact_id);
    setNewer(null); setMode("read"); setSaveState("idle"); setSaveError(null); setDraft(""); setBaseMarkdown("");
  };

  // textarea Markdown helpers — modify the canonical Markdown in place, never a proprietary schema.
  const surround = (before: string, after = before) => {
    const ta = taRef.current; if (!ta) return;
    const s = ta.selectionStart, e = ta.selectionEnd, sel = draft.slice(s, e);
    setDraft(draft.slice(0, s) + before + sel + after + draft.slice(e));
    requestAnimationFrame(() => { ta.focus(); ta.selectionStart = s + before.length; ta.selectionEnd = e + before.length; });
  };
  const linePrefix = (prefix: string) => {
    const ta = taRef.current; if (!ta) return;
    const s = ta.selectionStart, lineStart = draft.lastIndexOf("\n", s - 1) + 1;
    setDraft(draft.slice(0, lineStart) + prefix + draft.slice(lineStart));
    requestAnimationFrame(() => { ta.focus(); ta.selectionStart = ta.selectionEnd = s + prefix.length; });
  };
  const addSection = () => {
    const pad = draft === "" || draft.endsWith("\n\n") ? "" : draft.endsWith("\n") ? "\n" : "\n\n";
    const next = draft + pad + "## New section\n\n";
    setDraft(next);
    requestAnimationFrame(() => { const ta = taRef.current; if (ta) { ta.focus(); ta.selectionStart = ta.selectionEnd = next.length; } });
  };

  // ── render ───────────────────────────────────────────────────────────────────────────
  if (loading) {
    return <Centered><Spinner size={22} /><Note>Loading the Product Brief…</Note></Centered>;
  }
  if (loadError) {
    return (
      <Centered>
        <Icon name="x" size={22} color={T.danger} />
        <Note><strong style={{ color: T.fg }}>Couldn't load the Product Brief.</strong></Note>
        <Note>{loadError}</Note>
        <Btn variant="secondary" size="sm" onClick={load} style={{ marginTop: 6 }}><Icon name="refresh" size={13} /> Retry</Btn>
      </Centered>
    );
  }
  if (!doc && mode === "read") {
    // Honest no-brief state — never a fake example brief.
    return (
      <Centered>
        <Icon name="file" size={26} color={T.tertiary} />
        <Note><strong style={{ color: T.fg }}>No Product Brief yet.</strong></Note>
        <Note style={{ maxWidth: 420, textAlign: "center" }}>
          The Concierge hasn't created the Product Brief for this project yet. Ask it in the panel on
          the right to draft one — it will appear here as the canonical, versioned document.
        </Note>
      </Centered>
    );
  }

  if (mode === "edit") {
    return (
      <div style={{ height: "100%", display: "flex", flexDirection: "column", background: T.bg, minHeight: 0 }}>
        {/* editor header: state + actions */}
        <div style={{ flexShrink: 0, display: "flex", alignItems: "center", gap: 10, padding: "13px 24px", borderBottom: `1px solid ${T.borderSubtle}`, background: T.raised }}>
          <span style={{ font: `700 15px/1.2 ${T.display}`, color: T.fg }}>Editing Product Brief</span>
          <SaveBadge state={saveState} dirty={dirty} />
          <div style={{ flex: 1 }} />
          <Btn variant="ghost" size="sm" onClick={addSection} title="Insert a new heading + content block"><Icon name="plus" size={13} /> Add section</Btn>
          <Btn variant="ghost" size="sm" onClick={cancelEdit}>Cancel</Btn>
          <Btn variant="primary" size="sm" onClick={doSave} disabled={saveState === "saving" || !dirty || !!newer}>
            {saveState === "saving" ? <><Spinner size={13} color="#fff" /> Saving…</> : <><Icon name="check" size={13} color="#fff" /> Save version</>}
          </Btn>
        </div>

        {/* version-conflict / concierge-revision banner — keeps the draft, offers reconcile paths */}
        {newer && (
          <div role="alert" style={{ flexShrink: 0, display: "flex", alignItems: "center", flexWrap: "wrap", gap: 10, padding: "10px 24px", background: T.warningSoft, borderBottom: `1px solid ${T.warning}44` }}>
            <Icon name="refresh" size={14} color={T.warning} />
            <span style={{ font: `500 12.5px/1.4 ${T.sans}`, color: T.fg }}>
              A newer version exists ({sourceLabel(newer)}, {fmtWhen(newer.ts)}). Your draft is kept — reconcile before saving.
            </span>
            <div style={{ flex: 1 }} />
            <Btn variant="secondary" size="sm" onClick={rebaseOntoNewer} title="Save your draft as the new newest version (the intervening version stays in history)">Keep my draft as newest</Btn>
            <Btn variant="ghost" size="sm" onClick={discardForNewer}>Discard mine, load newest</Btn>
          </div>
        )}
        {saveState === "error" && !newer && (
          <div role="alert" style={{ flexShrink: 0, padding: "9px 24px", background: T.dangerSoft, borderBottom: `1px solid ${T.danger}44`, font: `500 12.5px/1.4 ${T.sans}`, color: T.danger }}>
            Save failed: {saveError}
          </div>
        )}

        {/* toolbar */}
        <div style={{ flexShrink: 0, display: "flex", alignItems: "center", gap: 4, padding: "8px 24px", borderBottom: `1px solid ${T.borderSubtle}`, background: T.raised }}>
          <Tool label="Heading" onClick={() => linePrefix("## ")}>H</Tool>
          <Tool label="Bold" onClick={() => surround("**")}><b>B</b></Tool>
          <Tool label="Italic" onClick={() => surround("_")}><i>I</i></Tool>
          <Tool label="Inline code" onClick={() => surround("`")}>{"</>"}</Tool>
          <Tool label="Link" onClick={() => surround("[", "](https://)")}><Icon name="link" size={13} /></Tool>
          <Tool label="Bulleted list" onClick={() => linePrefix("- ")}>•</Tool>
          <Tool label="Numbered list" onClick={() => linePrefix("1. ")}>1.</Tool>
        </div>

        {/* editor + live preview (both scroll independently; preview reuses the shared renderer) */}
        <div style={{ flex: 1, display: "flex", minHeight: 0 }}>
          <textarea ref={taRef} value={draft} onChange={(e) => setDraft(e.target.value)}
            aria-label="Product Brief Markdown"
            spellCheck
            style={{ flex: 1, minWidth: 0, resize: "none", border: "none", outline: "none", padding: "18px 24px",
              background: T.bg, color: T.fg, font: `400 13px/1.7 ${T.mono}` }} />
          <div style={{ flex: 1, minWidth: 0, overflowY: "auto", padding: "18px 24px", borderLeft: `1px solid ${T.borderSubtle}`, background: T.raised }}>
            <span style={{ display: "block", font: `600 10px/1 ${T.mono}`, letterSpacing: "0.1em", textTransform: "uppercase", color: T.tertiary, marginBottom: 12 }}>Preview</span>
            {draft.trim()
              ? <MarkdownBody content={draft} />
              : <Note>Nothing to preview yet — start typing on the left.</Note>}
          </div>
        </div>
      </div>
    );
  }

  // ── reader ─────────────────────────────────────────────────────────────────────────────
  const contentMissing = doc && doc.markdown == null;
  return (
    <div style={{ height: "100%", display: "flex", flexDirection: "column", background: T.bg, minHeight: 0 }}>
      {/* header band: title, version meta + source, actions */}
      <div style={{ flexShrink: 0, display: "flex", alignItems: "flex-start", gap: 12, padding: "18px 24px", borderBottom: `1px solid ${T.borderSubtle}`, background: T.raised }}>
        <div style={{ minWidth: 0, flex: 1 }}>
          <h2 style={{ margin: "0 0 4px", font: `700 18px/1.2 ${T.display}`, color: T.fg }}>{doc?.title || "Product brief"}</h2>
          <div style={{ display: "flex", alignItems: "center", flexWrap: "wrap", gap: 8, font: `400 12px/1.4 ${T.sans}`, color: T.tertiary }}>
            {onLatest
              ? <span style={{ font: `600 10.5px/1 ${T.mono}`, letterSpacing: "0.06em", textTransform: "uppercase", color: T.success }}>Current version</span>
              : <span style={{ font: `600 10.5px/1 ${T.mono}`, letterSpacing: "0.06em", textTransform: "uppercase", color: T.warning }}>Earlier version (read-only)</span>}
            {doc && <span>· {sourceLabel(doc)} · {fmtWhen(doc.ts)}</span>}
          </div>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 8, flexShrink: 0 }}>
          {!onLatest && <Btn variant="ghost" size="sm" onClick={() => { if (latestId) openVersion(latestId); }}><Icon name="arrowLeft" size={13} /> Back to current</Btn>}
          <Btn variant="secondary" size="sm" onClick={() => setShowHistory((v) => !v)} title="Version history">
            <Icon name="layers" size={13} /> History{versions.length ? ` (${versions.length})` : ""}
          </Btn>
          {doc && <Btn variant="ghost" size="sm" onClick={() => openArtifact(doc.artifact_id)} title="Open the standalone Artifact Viewer in a new tab"><Icon name="external" size={13} /> Open</Btn>}
          {onLatest && !contentMissing && <Btn variant="primary" size="sm" onClick={startEdit}><Icon name="pencil" size={13} color="#fff" /> Edit document</Btn>}
        </div>
      </div>

      {/* history panel (real versions; selecting an older one opens it read-only) */}
      {showHistory && (
        <div style={{ flexShrink: 0, maxHeight: 240, overflowY: "auto", borderBottom: `1px solid ${T.borderSubtle}`, background: T.sunken }}>
          {versions.length === 0
            ? <div style={{ padding: "14px 24px" }}><Note>No versions recorded yet.</Note></div>
            : versions.map((v) => {
              const active = v.artifact_id === viewingId;
              const isCur = v.artifact_id === latestId;
              return (
                <button key={v.artifact_id} onClick={() => openVersion(v.artifact_id)}
                  style={{ display: "flex", alignItems: "center", gap: 10, width: "100%", textAlign: "left", padding: "10px 24px", background: active ? T.brandSoft : "transparent", border: "none", borderBottom: `1px solid ${T.borderSubtle}`, cursor: "pointer" }}>
                  <Icon name="file" size={13} color={active ? T.brandDeep : T.tertiary} />
                  <span style={{ flex: 1, minWidth: 0, font: `500 12.5px/1.3 ${T.sans}`, color: T.fg }}>
                    {sourceLabel(v)} <span style={{ color: T.tertiary, fontWeight: 400 }}>· {fmtWhen(v.ts)}</span>
                  </span>
                  {isCur && <span style={{ font: `600 9.5px/1 ${T.mono}`, letterSpacing: "0.06em", textTransform: "uppercase", color: T.success }}>Current</span>}
                </button>
              );
            })}
        </div>
      )}

      {/* body: contents rail + document */}
      <div style={{ flex: 1, display: "flex", minHeight: 0 }}>
        <nav aria-label="Contents" style={{ width: 200, flexShrink: 0, overflowY: "auto", padding: "20px 12px 20px 24px", borderRight: `1px solid ${T.borderSubtle}` }}>
          <span style={{ display: "block", font: `600 10px/1 ${T.mono}`, letterSpacing: "0.1em", textTransform: "uppercase", color: T.tertiary, marginBottom: 12 }}>Contents</span>
          {toc.length === 0
            ? <Note style={{ fontSize: 11.5 }}>This brief has no Markdown headings.</Note>
            : toc.map((h, i) => (
              <button key={`${h.id}-${i}`} onClick={() => selectHeading(h.id, h.text)}
                style={{ display: "block", width: "100%", textAlign: "left", padding: `4px 0 4px ${(h.level - 1) * 12}px`, background: "none", border: "none", cursor: "pointer",
                  font: `${h.level === 1 ? 600 : 400} 12px/1.4 ${T.sans}`, color: selHeading === h.text ? T.brandDeep : T.secondary }}>
                {h.text || <em style={{ color: T.tertiary }}>(untitled heading)</em>}
              </button>
            ))}
        </nav>
        <div ref={bodyRef} style={{ flex: 1, minWidth: 0, overflowY: "auto", padding: "24px 32px" }}>
          <div style={{ maxWidth: 760 }}>
            {contentMissing
              ? <Note><strong style={{ color: T.fg }}>Content not preserved for this version.</strong> This older version predates inline content storage, so its exact Markdown is no longer recoverable. Newer versions render in full.</Note>
              : doc?.markdown
                ? <MarkdownBody content={doc.markdown} />
                : <Note>This version has no content.</Note>}
          </div>
        </div>
      </div>
    </div>
  );
}

// ── small local presentational helpers ─────────────────────────────────────────────────────
function Centered({ children }: { children: React.ReactNode }) {
  return <div style={{ flex: 1, height: "100%", display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: 10, padding: 24 }}>{children}</div>;
}
function Note({ children, style }: { children: React.ReactNode; style?: React.CSSProperties }) {
  return <p style={{ margin: 0, font: `400 13px/1.6 ${T.sans}`, color: T.secondary, ...style }}>{children}</p>;
}
function Tool({ label, onClick, children }: { label: string; onClick: () => void; children: React.ReactNode }) {
  return (
    <button onClick={onClick} title={label} aria-label={label}
      style={{ display: "grid", placeItems: "center", minWidth: 30, height: 28, padding: "0 8px", borderRadius: T.rSm, border: `1px solid ${T.borderSubtle}`, background: T.raised, color: T.secondary, cursor: "pointer", font: `500 12.5px/1 ${T.sans}` }}>
      {children}
    </button>
  );
}
function SaveBadge({ state, dirty }: { state: "idle" | "saving" | "saved" | "error"; dirty: boolean }) {
  if (state === "saving") return <Badge tone={T.brandDeep} bg={T.brandSoft}>Saving…</Badge>;
  if (state === "saved" && !dirty) return <Badge tone={T.success} bg={T.successSoft}>Saved</Badge>;
  if (state === "error") return <Badge tone={T.danger} bg={T.dangerSoft}>Save failed</Badge>;
  if (dirty) return <Badge tone={T.warning} bg={T.warningSoft}>Unsaved changes</Badge>;
  return <Badge tone={T.tertiary} bg={T.sunken}>Editing</Badge>;
}
function Badge({ tone, bg, children }: { tone: string; bg: string; children: React.ReactNode }) {
  return <span style={{ font: `600 10px/1 ${T.mono}`, letterSpacing: "0.06em", textTransform: "uppercase", color: tone, background: bg, padding: "4px 8px", borderRadius: 9999 }}>{children}</span>;
}
