// FilesPeer.tsx — §2.5d Files: a hierarchical source-material browser (SOF-255), built on SOF-253's
// Files API (#448). Virtual combined "Files" root → per-scope (project/org) persisted roots → nested
// directories → files. Factory outputs and the Product Brief never appear here (they are their own
// Project Console peers). Directory summaries are generated (SOF-254) and READ-ONLY; their state
// (Summarizing / Ready / Needs refresh / Failed) is shown truthfully — a stale or absent summary is
// never presented as fresh.
//
// This is a self-contained peer with a THIN mount into ProjectView. SOF-239's shell (#447) relocates
// it into the Files peer line at the cascade rebase; the shared Concierge context wiring is that
// shell's job. `onSelect` exposes the selected directory/file so the shell can pass it to the
// Concierge as display context. Phase-1 retrieval stays flat semantic search (SOF-237 owns any
// directory-scoped behavior) — nothing here claims a subtree boundary.
import React, { useEffect, useMemo, useRef, useState } from "react";
import {
  api, ApiError, FilesTree, FilesDirectory, FilesFile, FilesRecent, DirScope, SummaryStatus,
} from "../../api";
import { openProjectFile } from "../factory/Artifacts";
import { T, Icon, Btn, StatusPill, CategoryLabel } from "../onboarding/design";
import { MarkdownBody } from "../../markdown";
import { Spinner, Skel } from "../skeleton";

// ── Selection surfaced to the shell → Concierge (display context only) ──────────
export type FilesSelection =
  | { type: "directory"; id: string; name: string; scope: DirScope; summary_status: SummaryStatus | null }
  | { type: "file"; id: number; name: string; scope: DirScope };

// ── File typing: kind → typed icon + swatch. Falls back to extension / content-type ─────
type Visual = { label: string; icon: string; bg: string; fg: string };
const KIND_VISUAL: Record<string, Visual> = {
  pdf: { label: "PDF", icon: "file", bg: "#fbe3e3", fg: "#c0392f" },
  spreadsheet: { label: "SHEET", icon: "database", bg: "#e4f8ef", fg: "#1f8a5b" },
  document: { label: "DOC", icon: "file", bg: "#e8f1ff", fg: "#1A7BFF" },
  markdown: { label: "MD", icon: "file", bg: "#e8f1ff", fg: "#1A7BFF" },
  image: { label: "IMG", icon: "file", bg: "#fbefdc", fg: "#b06f12" },
  video: { label: "VIDEO", icon: "video", bg: "#f3e9fb", fg: "#7a3ea8" },
  other: { label: "FILE", icon: "file", bg: "#ececed", fg: "#555" },
};
const EXT_KIND: Record<string, string> = {
  pdf: "pdf", xls: "spreadsheet", xlsx: "spreadsheet", csv: "spreadsheet",
  doc: "document", docx: "document", txt: "document", rtf: "document",
  md: "markdown", mdx: "markdown",
  png: "image", jpg: "image", jpeg: "image", gif: "image", webp: "image", svg: "image",
  mp4: "video", mov: "video", webm: "video", avi: "video", mkv: "video",
};
function visualFor(f: { name: string; kind: string | null; content_type: string | null }): Visual {
  const byKind = f.kind && KIND_VISUAL[f.kind];
  if (byKind) return byKind;
  const ext = f.name.split(".").pop()?.toLowerCase() || "";
  const k = EXT_KIND[ext];
  if (k && KIND_VISUAL[k]) return KIND_VISUAL[k];
  const ct = f.content_type || "";
  if (ct.startsWith("image/")) return KIND_VISUAL.image;
  if (ct.startsWith("video/")) return KIND_VISUAL.video;
  if (ct.includes("pdf")) return KIND_VISUAL.pdf;
  return KIND_VISUAL.other;
}

function fmtBytes(n: number | null): string {
  if (n == null) return "";
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${Math.round(n / 1024)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}
function fmtDate(epoch: number | null): string {
  if (!epoch) return "—";
  return new Date(epoch * 1000).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
}
function scopeLabel(s: DirScope): string {
  return s === "org" ? "Org-wide" : "Project";
}

// Honest summary-status mapping. `null` = no summary generated yet (never a fabricated one).
const SUMMARY_STATUS: Record<SummaryStatus, { tone: "success" | "warning" | "danger" | "info"; label: string }> = {
  summarizing: { tone: "info", label: "Summarizing…" },
  ready: { tone: "success", label: "Ready" },
  needs_refresh: { tone: "warning", label: "Needs refresh" },
  failed: { tone: "danger", label: "Failed" },
};
function SummaryStatusPill({ status }: { status: SummaryStatus | null }) {
  if (!status) return <StatusPill tone="neutral">No summary yet</StatusPill>;
  const s = SUMMARY_STATUS[status];
  return (
    <StatusPill tone={s.tone} dot={status !== "summarizing"}>
      {status === "summarizing" && <Spinner size={11} color={T.brandDeep} />}
      {s.label}
    </StatusPill>
  );
}

// Map the API's real reason (409/400/404/403 → `.detail`) to inline copy. Never guesses.
function errText(e: unknown, fallback: string): string {
  const detail = (e as ApiError)?.detail;
  if (typeof detail === "string" && detail) return detail;
  return fallback;
}

// ── Main component ───────────────────────────────────────────────────────────
export function FilesPeer({ projectId, onSelect }: { projectId: string; onSelect?: (sel: FilesSelection | null) => void }) {
  const [tree, setTree] = useState<FilesTree | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadErr, setLoadErr] = useState("");
  // cwd: null = the virtual combined Files root; otherwise a real directory id (root or nested).
  const [cwd, setCwd] = useState<string | null>(null);
  const [selectedFileId, setSelectedFileId] = useState<number | null>(null);
  const [search, setSearch] = useState("");
  const [actionErr, setActionErr] = useState("");
  const [creating, setCreating] = useState(false);
  const [newName, setNewName] = useState("");
  const [busy, setBusy] = useState(false);
  const [movingId, setMovingId] = useState<number | null>(null);
  const uploadRef = useRef<HTMLInputElement | null>(null);

  const load = () => api.files(projectId).then(setTree);
  useEffect(() => {
    setLoading(true);
    setLoadErr("");
    load().catch((e) => setLoadErr(errText(e, "Couldn't load files."))).finally(() => setLoading(false));
  }, [projectId]);

  // Indexes over the flat tree payload.
  const dirById = useMemo(() => {
    const m = new Map<string, FilesDirectory>();
    if (tree) for (const d of [...tree.roots, ...tree.directories]) m.set(d.id, d);
    return m;
  }, [tree]);

  const currentDir = cwd ? dirById.get(cwd) || null : null;
  // Root of the scope the cwd lives in (for "file with directory_id:null sits at its scope root").
  const childDirs = (dirId: string): FilesDirectory[] =>
    (tree ? [...tree.roots, ...tree.directories] : []).filter((d) => d.parent_id === dirId);
  const filesInDir = (dir: FilesDirectory): FilesFile[] => {
    if (!tree) return [];
    const inDir = tree.files.filter((f) => f.directory_id === dir.id);
    // A rootless blob (directory_id:null) is presented at the persisted root of its own scope.
    const rootless = dir.parent_id === null
      ? tree.files.filter((f) => f.directory_id === null && f.scope === dir.scope)
      : [];
    return [...inDir, ...rootless];
  };

  const selectedFile = useMemo(
    () => (tree && selectedFileId != null ? tree.files.find((f) => f.id === selectedFileId) || null : null),
    [tree, selectedFileId],
  );

  // Surface selection to the shell (display context only — Phase-1 retrieval stays flat).
  useEffect(() => {
    if (!onSelect) return;
    if (selectedFile) onSelect({ type: "file", id: selectedFile.id, name: selectedFile.name, scope: selectedFile.scope });
    else if (currentDir) onSelect({ type: "directory", id: currentDir.id, name: currentDir.name, scope: currentDir.scope, summary_status: currentDir.summary_status });
    else onSelect(null);
  }, [selectedFileId, cwd, tree]); // eslint-disable-line react-hooks/exhaustive-deps

  // Breadcrumb path: virtual root → … → cwd.
  const breadcrumb = useMemo(() => {
    const chain: FilesDirectory[] = [];
    let d = currentDir;
    while (d) { chain.unshift(d); d = d.parent_id ? dirById.get(d.parent_id) || null : null; }
    return chain;
  }, [currentDir, dirById]);

  const goto = (dirId: string | null) => { setCwd(dirId); setSelectedFileId(null); setSearch(""); setCreating(false); setActionErr(""); };

  // ── Mutations. Every one returns the fresh tree; we re-render from server truth. ──
  const doCreateDir = async () => {
    const name = newName.trim();
    if (!name || !cwd) return;
    setBusy(true); setActionErr("");
    try { setTree(await api.createDirectory(projectId, { parent_id: cwd, name })); setNewName(""); setCreating(false); }
    catch (e) { setActionErr(errText(e, "Couldn't create that folder.")); }
    finally { setBusy(false); }
  };

  const doUpload = async (list: FileList | null) => {
    if (!list || !list.length || !cwd) return;
    setBusy(true); setActionErr("");
    try {
      let latest: FilesTree | null = null;
      for (const file of Array.from(list)) {
        const data_b64 = await new Promise<string>((resolve) => {
          const r = new FileReader();
          r.onload = () => resolve(String(r.result || "").split(",")[1] || "");
          r.onerror = () => resolve("");
          r.readAsDataURL(file);
        });
        latest = await api.uploadFile(projectId, { name: file.name, content_type: file.type || undefined, data_b64, directory_id: cwd });
      }
      if (latest) setTree(latest);
    } catch (e) { setActionErr(errText(e, "Upload isn't available right now.")); }
    finally { setBusy(false); }
  };

  const doMove = async (file: FilesFile, target: FilesDirectory) => {
    setBusy(true); setActionErr(""); setMovingId(null);
    try {
      // Cross-scope reassignment reuses the scope change; same-scope is a plain directory_id move.
      const body = target.scope === file.scope
        ? { directory_id: target.id }
        : { directory_id: target.id, scope: target.scope };
      setTree(await api.moveFile(projectId, file.id, body));
    } catch (e) { setActionErr(errText(e, "Couldn't move that file.")); }
    finally { setBusy(false); }
  };

  const doDelete = async (file: FilesFile) => {
    if (!confirm(`Delete "${file.name}"? This removes it from your source material.`)) return;
    setBusy(true); setActionErr("");
    try { setTree(await api.deleteFile(projectId, file.id)); if (selectedFileId === file.id) setSelectedFileId(null); }
    catch (e) { setActionErr(errText(e, "Couldn't delete that file.")); }
    finally { setBusy(false); }
  };

  // Navigate to a file's real scoped directory and select it (recent-file links → real membership).
  const revealFile = (id: number, directory_id: string | null, scope: DirScope) => {
    let dest = directory_id;
    if (!dest && tree) dest = tree.roots.find((r) => r.scope === scope)?.id || null;
    setCwd(dest); setSearch(""); setSelectedFileId(id); setCreating(false); setActionErr("");
  };

  // ── Render ──────────────────────────────────────────────────────────────────
  if (loading) return <Loading />;
  if (loadErr || !tree) {
    return (
      <div style={{ flex: 1, display: "grid", placeItems: "center", padding: 24 }}>
        <div style={{ textAlign: "center", color: T.tertiary, maxWidth: 380 }}>
          <Icon name="file" size={34} color={T.tertiary} />
          <p style={{ font: `400 13.5px/1.5 ${T.sans}`, marginTop: 12 }}>{loadErr || "Files are unavailable right now."}</p>
        </div>
      </div>
    );
  }

  const atRoot = cwd === null;
  const q = search.trim().toLowerCase();
  const matches = (name: string, summary?: string | null) =>
    !q || name.toLowerCase().includes(q) || (!!summary && summary.toLowerCase().includes(q));

  return (
    <div style={{ flex: 1, overflow: "auto", padding: "20px 24px 40px" }}>
      <div style={{ maxWidth: 980, margin: "0 auto" }}>
        {/* header: breadcrumbs + search + actions (actions hidden at the virtual root) */}
        <div style={{ display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap", marginBottom: 14 }}>
          <nav aria-label="Breadcrumb" style={{ display: "flex", alignItems: "center", gap: 4, flex: 1, minWidth: 0, flexWrap: "wrap" }}>
            <BreadcrumbButton label="Files" icon="layers" active={atRoot} onClick={() => goto(null)} />
            {breadcrumb.map((d, i) => (
              <React.Fragment key={d.id}>
                <Icon name="chevronRight" size={13} color={T.tertiary} />
                <BreadcrumbButton label={d.name} active={i === breadcrumb.length - 1} onClick={() => goto(d.id)} />
              </React.Fragment>
            ))}
          </nav>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <div style={{ position: "relative" }}>
              <span style={{ position: "absolute", left: 9, top: 0, height: 32, display: "flex", alignItems: "center", pointerEvents: "none" }}>
                <Icon name="search" size={14} color={T.tertiary} />
              </span>
              <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search names & summaries…" aria-label="Search files"
                style={{ height: 32, width: 220, boxSizing: "border-box", padding: "0 10px 0 30px", borderRadius: T.rMd, border: `1px solid ${T.borderDefault}`, background: T.bg, color: T.fg, font: `400 12.5px/1 ${T.sans}`, outline: "none" }} />
            </div>
            {!atRoot && (
              <>
                <Btn size="sm" variant="secondary" onClick={() => { setCreating((v) => !v); setNewName(""); setActionErr(""); }}>
                  <Icon name="plus" size={13} color={T.secondary} /> New folder
                </Btn>
                <Btn size="sm" variant="primary" onClick={() => uploadRef.current?.click()}>
                  <Icon name="upload" size={13} color="#fff" /> Add file
                </Btn>
                <input ref={uploadRef} type="file" multiple style={{ display: "none" }}
                  onChange={(e) => { doUpload(e.target.files); e.target.value = ""; }} />
              </>
            )}
          </div>
        </div>

        {creating && !atRoot && (
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 12 }}>
            <input autoFocus value={newName} onChange={(e) => setNewName(e.target.value)} placeholder="Folder name"
              onKeyDown={(e) => { if (e.key === "Enter") doCreateDir(); if (e.key === "Escape") setCreating(false); }}
              style={{ height: 32, width: 240, boxSizing: "border-box", padding: "0 10px", borderRadius: T.rMd, border: `1px solid ${T.borderDefault}`, background: T.bg, color: T.fg, font: `400 12.5px/1 ${T.sans}`, outline: "none" }} />
            <Btn size="sm" variant="primary" onClick={doCreateDir} disabled={busy || !newName.trim()}>Create</Btn>
            <Btn size="sm" variant="ghost" onClick={() => setCreating(false)}>Cancel</Btn>
          </div>
        )}
        {actionErr && <div style={{ font: `500 12px/1.4 ${T.sans}`, color: T.danger, marginBottom: 12 }}>{actionErr}</div>}

        {atRoot
          ? <VirtualRoot tree={tree} onOpenDir={goto} onRevealFile={revealFile} matches={matches} />
          : (
            <div style={{ display: "grid", gridTemplateColumns: selectedFile ? "minmax(0,1fr) 320px" : "minmax(0,1fr)", gap: 18, alignItems: "start" }}>
              <div style={{ minWidth: 0 }}>
                {currentDir && <DirSummary dir={currentDir} />}
                <DirListing
                  dirs={childDirs(cwd!).filter((d) => matches(d.name, d.summary_md))}
                  files={filesInDir(currentDir!).filter((f) => matches(f.name, f.summary))}
                  selectedFileId={selectedFileId}
                  onOpenDir={goto}
                  onSelectFile={(id) => setSelectedFileId((cur) => (cur === id ? null : id))}
                  searching={!!q}
                />
              </div>
              {selectedFile && (
                <FileDetails
                  file={selectedFile}
                  directories={[...tree.roots, ...tree.directories]}
                  moving={movingId === selectedFile.id}
                  onStartMove={() => setMovingId(selectedFile.id)}
                  onCancelMove={() => setMovingId(null)}
                  onMove={(target) => doMove(selectedFile, target)}
                  onDelete={() => doDelete(selectedFile)}
                  onOpen={() => openProjectFile(projectId, selectedFile.id, selectedFile.name)}
                  onClose={() => setSelectedFileId(null)}
                  busy={busy}
                />
              )}
            </div>
          )}
      </div>
    </div>
  );
}

// ── Virtual combined root: scoped-root cards + recent files. No mutation controls. ──
function VirtualRoot({ tree, onOpenDir, onRevealFile, matches }: {
  tree: FilesTree; onOpenDir: (id: string) => void;
  onRevealFile: (id: number, dirId: string | null, scope: DirScope) => void;
  matches: (name: string, summary?: string | null) => boolean;
}) {
  const roots = tree.roots.filter((r) => matches(r.name, r.summary_md));
  const recent = tree.recent.filter((r) => matches(r.name));
  return (
    <>
      <CategoryLabel>Source material · project & organization roots</CategoryLabel>
      {roots.length ? (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))", gap: 12, margin: "10px 0 26px" }}>
          {roots.map((r) => <RootCard key={r.id} dir={r} onOpen={() => onOpenDir(r.id)} />)}
        </div>
      ) : (
        <div style={{ ...emptyBox, margin: "10px 0 26px" }}>
          No source roots yet. Project and organization roots appear here once material exists.
        </div>
      )}

      <CategoryLabel>Recently added</CategoryLabel>
      {recent.length ? (
        <div style={{ marginTop: 10, border: `1px solid ${T.borderSubtle}`, borderRadius: T.rLg, overflow: "hidden", background: T.raised }}>
          {recent.map((r, i) => <RecentRow key={r.id} row={r} first={i === 0} onOpen={() => onRevealFile(r.id, r.directory_id, r.scope)} />)}
        </div>
      ) : (
        <div style={{ ...emptyBox, marginTop: 10 }}>No files added yet.</div>
      )}
    </>
  );
}

function RootCard({ dir, onOpen }: { dir: FilesDirectory; onOpen: () => void }) {
  const [hover, setHover] = useState(false);
  return (
    <button onClick={onOpen} onMouseEnter={() => setHover(true)} onMouseLeave={() => setHover(false)}
      style={{ textAlign: "left", cursor: "pointer", background: T.raised, border: `1px solid ${hover ? T.brand : T.borderSubtle}`, borderRadius: T.rLg, padding: "14px 15px", display: "flex", flexDirection: "column", gap: 9, boxShadow: hover ? T.shadowMd : T.shadowXs, transition: "border-color .12s, box-shadow .12s", font: "inherit", width: "100%" }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8 }}>
        <span style={{ display: "inline-flex", alignItems: "center", gap: 8, minWidth: 0 }}>
          <FolderGlyph />
          <span style={{ font: `600 14px/1.2 ${T.sans}`, color: T.fg, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{dir.name}</span>
        </span>
        <StatusPill tone={dir.scope === "org" ? "brand" : "neutral"} dot={false}>{scopeLabel(dir.scope)}</StatusPill>
      </div>
      <div style={{ font: `400 11.5px/1 ${T.mono}`, color: T.tertiary }}>
        {dir.child_dir_count} folder{dir.child_dir_count === 1 ? "" : "s"} · {dir.member_file_count} file{dir.member_file_count === 1 ? "" : "s"}
      </div>
      <SummaryPreview dir={dir} />
    </button>
  );
}

function RecentRow({ row, first, onOpen }: { row: FilesRecent; first: boolean; onOpen: () => void }) {
  const v = visualFor({ name: row.name, kind: null, content_type: null });
  return (
    <button onClick={onOpen}
      style={{ display: "flex", alignItems: "center", gap: 11, width: "100%", textAlign: "left", padding: "10px 14px", border: "none", borderTop: first ? "none" : `1px solid ${T.borderSubtle}`, background: "transparent", cursor: "pointer", font: "inherit" }}>
      <FileGlyph v={v} size={26} />
      <span style={{ flex: 1, minWidth: 0, font: `500 13px/1.3 ${T.sans}`, color: T.fg, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{row.name}</span>
      <StatusPill tone={row.scope === "org" ? "brand" : "neutral"} dot={false}>{scopeLabel(row.scope)}</StatusPill>
      <span style={{ font: `400 11px/1 ${T.mono}`, color: T.tertiary, flexShrink: 0 }}>{fmtDate(row.created_at)}</span>
    </button>
  );
}

// ── Directory summary panel (read-only, honest state). ──
function DirSummary({ dir }: { dir: FilesDirectory }) {
  const empty = dir.child_dir_count === 0 && dir.member_file_count === 0;
  const stale = dir.summary_status === "needs_refresh";
  const failed = dir.summary_status === "failed";
  return (
    <div style={{ border: `1px solid ${T.borderSubtle}`, borderRadius: T.rLg, background: T.raised, padding: "14px 16px", marginBottom: 16 }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 10, marginBottom: 8 }}>
        <CategoryLabel>Directory summary</CategoryLabel>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          {dir.last_successful_summary_at != null && (
            <span style={{ font: `400 11px/1 ${T.mono}`, color: T.tertiary }}>Last refreshed {fmtDate(dir.last_successful_summary_at)}</span>
          )}
          <SummaryStatusPill status={dir.summary_status} />
        </div>
      </div>
      {empty ? (
        <p style={{ font: `400 12.5px/1.5 ${T.sans}`, color: T.tertiary, margin: 0 }}>This folder contains no indexed material yet.</p>
      ) : dir.summary_md ? (
        <>
          {(stale || failed) && (
            <p style={{ font: `500 11.5px/1.4 ${T.sans}`, color: failed ? T.danger : T.warning, margin: "0 0 8px" }}>
              {failed
                ? "Summary generation failed — the text below is the last successful version and may be out of date."
                : "Contents changed since this summary was generated — it may be out of date while it refreshes."}
            </p>
          )}
          <div style={{ font: `400 12.5px/1.55 ${T.sans}`, color: T.secondary }}>
            <MarkdownBody content={dir.summary_md} />
          </div>
        </>
      ) : (
        <p style={{ font: `400 12.5px/1.5 ${T.sans}`, color: T.tertiary, margin: 0 }}>
          {dir.summary_status === "summarizing" ? "A summary is being generated for this directory." : "No summary has been generated for this directory yet."}
        </p>
      )}
    </div>
  );
}

// Short summary preview line for cards/folders (2-line clamp).
function SummaryPreview({ dir }: { dir: FilesDirectory }) {
  if (dir.child_dir_count === 0 && dir.member_file_count === 0)
    return <span style={{ font: `400 11.5px/1.4 ${T.sans}`, color: T.tertiary }}>No indexed material yet.</span>;
  if (!dir.summary_md)
    return (
      <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
        <SummaryStatusPill status={dir.summary_status} />
      </span>
    );
  return (
    <span style={{ font: `400 11.5px/1.45 ${T.sans}`, color: T.secondary, display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical", overflow: "hidden" }}>
      {dir.summary_md.replace(/[#*`>_\-]/g, "").trim().slice(0, 180)}
    </span>
  );
}

// ── Directory listing: child folders + member files. Empty & failed rows stay visible. ──
function DirListing({ dirs, files, selectedFileId, onOpenDir, onSelectFile, searching }: {
  dirs: FilesDirectory[]; files: FilesFile[]; selectedFileId: number | null;
  onOpenDir: (id: string) => void; onSelectFile: (id: number) => void; searching: boolean;
}) {
  if (!dirs.length && !files.length) {
    return (
      <div style={emptyBox}>
        {searching ? "No files or folders match your search." : "This folder contains no indexed material yet."}
      </div>
    );
  }
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>
      {dirs.length > 0 && (
        <div>
          <CategoryLabel>Folders</CategoryLabel>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(240px, 1fr))", gap: 10, marginTop: 10 }}>
            {dirs.map((d) => <FolderCard key={d.id} dir={d} onOpen={() => onOpenDir(d.id)} />)}
          </div>
        </div>
      )}
      {files.length > 0 && (
        <div>
          <CategoryLabel>Files</CategoryLabel>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(220px, 1fr))", gap: 10, marginTop: 10 }}>
            {files.map((f) => <FileCard key={f.id} file={f} selected={selectedFileId === f.id} onSelect={() => onSelectFile(f.id)} />)}
          </div>
        </div>
      )}
    </div>
  );
}

function FolderCard({ dir, onOpen }: { dir: FilesDirectory; onOpen: () => void }) {
  const [hover, setHover] = useState(false);
  return (
    <button onClick={onOpen} onMouseEnter={() => setHover(true)} onMouseLeave={() => setHover(false)}
      style={{ textAlign: "left", cursor: "pointer", background: T.raised, border: `1px solid ${hover ? T.brand : T.borderSubtle}`, borderRadius: T.rLg, padding: "12px 13px", display: "flex", flexDirection: "column", gap: 8, boxShadow: hover ? T.shadowSm : T.shadowXs, transition: "border-color .12s", font: "inherit", width: "100%" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 9, minWidth: 0 }}>
        <FolderGlyph />
        <span style={{ font: `600 13px/1.2 ${T.sans}`, color: T.fg, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{dir.name}</span>
      </div>
      <div style={{ font: `400 11px/1 ${T.mono}`, color: T.tertiary }}>
        {dir.member_file_count} file{dir.member_file_count === 1 ? "" : "s"}{dir.child_dir_count ? ` · ${dir.child_dir_count} folder${dir.child_dir_count === 1 ? "" : "s"}` : ""}
      </div>
      <SummaryPreview dir={dir} />
    </button>
  );
}

function FileCard({ file, selected, onSelect }: { file: FilesFile; selected: boolean; onSelect: () => void }) {
  const v = visualFor(file);
  const failed = file.ingest_status === "failed";
  return (
    <button onClick={onSelect} aria-pressed={selected}
      style={{ textAlign: "left", cursor: "pointer", background: selected ? T.brandSoft : T.raised, border: `1px solid ${selected ? T.brand : T.borderSubtle}`, borderRadius: T.rLg, padding: "12px 13px", display: "flex", flexDirection: "column", gap: 9, boxShadow: T.shadowXs, transition: "border-color .12s, background .12s", font: "inherit", width: "100%" }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8 }}>
        <FileGlyph v={v} size={30} />
        {failed && <StatusPill tone="danger" dot={false}>Failed to ingest</StatusPill>}
        {!failed && file.ingest_status === "pending" && <StatusPill tone="warning" dot={false}>Processing…</StatusPill>}
      </div>
      <span style={{ font: `600 12.5px/1.35 ${T.sans}`, color: T.fg, wordBreak: "break-word", display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical", overflow: "hidden" }}>{file.name}</span>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", font: `400 10.5px/1 ${T.mono}`, color: T.tertiary }}>
        <span>{fmtBytes(file.size_bytes) || v.label}</span>
        <span>{fmtDate(file.created_at)}</span>
      </div>
    </button>
  );
}

// ── File details / summary panel (source-file actions only — never artifact-only actions). ──
function FileDetails({ file, directories, moving, onStartMove, onCancelMove, onMove, onDelete, onOpen, onClose, busy }: {
  file: FilesFile; directories: FilesDirectory[]; moving: boolean;
  onStartMove: () => void; onCancelMove: () => void; onMove: (target: FilesDirectory) => void;
  onDelete: () => void; onOpen: () => void; onClose: () => void; busy: boolean;
}) {
  const v = visualFor(file);
  return (
    <aside style={{ border: `1px solid ${T.borderSubtle}`, borderRadius: T.rLg, background: T.raised, padding: "16px", position: "sticky", top: 0, display: "flex", flexDirection: "column", gap: 12 }}>
      <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 10 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10, minWidth: 0 }}>
          <FileGlyph v={v} size={34} />
          <span style={{ font: `600 13.5px/1.35 ${T.sans}`, color: T.fg, wordBreak: "break-word" }}>{file.name}</span>
        </div>
        <button onClick={onClose} title="Close details" style={{ width: 26, height: 26, display: "grid", placeItems: "center", border: "none", borderRadius: T.rMd, background: "transparent", cursor: "pointer", color: T.tertiary, flexShrink: 0 }}><Icon name="x" size={14} /></button>
      </div>

      <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
        <StatusPill tone={file.scope === "org" ? "brand" : "neutral"} dot={false}>{scopeLabel(file.scope)}</StatusPill>
        {file.ingest_status === "failed"
          ? <StatusPill tone="danger" dot={false}>Failed to ingest</StatusPill>
          : file.ingest_status === "pending"
            ? <StatusPill tone="warning" dot={false}>Processing…</StatusPill>
            : file.ingest_status === "ready" && <StatusPill tone="success" dot={false}>Ingested</StatusPill>}
      </div>

      <dl style={{ margin: 0, display: "grid", gridTemplateColumns: "auto 1fr", gap: "4px 12px", font: `400 11.5px/1.4 ${T.sans}` }}>
        <dt style={{ color: T.tertiary }}>Type</dt><dd style={{ margin: 0, color: T.secondary }}>{v.label}{file.tag ? ` · ${file.tag}` : ""}</dd>
        {file.size_bytes != null && (<><dt style={{ color: T.tertiary }}>Size</dt><dd style={{ margin: 0, color: T.secondary }}>{fmtBytes(file.size_bytes)}</dd></>)}
        <dt style={{ color: T.tertiary }}>Added</dt><dd style={{ margin: 0, color: T.secondary }}>{fmtDate(file.created_at)}</dd>
        <dt style={{ color: T.tertiary }}>Blob id</dt><dd style={{ margin: 0, color: T.secondary, font: `400 11px/1.4 ${T.mono}` }}>{file.id}</dd>
      </dl>

      <div>
        <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6 }}>
          <CategoryLabel>Summary</CategoryLabel>
          <SummaryStatusPill status={file.summary_status} />
        </div>
        {file.summary
          ? <p style={{ font: `400 12px/1.5 ${T.sans}`, color: T.secondary, margin: 0 }}>{file.summary}</p>
          : <p style={{ font: `400 12px/1.5 ${T.sans}`, color: T.tertiary, margin: 0 }}>{file.ingest_status === "failed" ? "This file failed to ingest, so no summary is available." : "No summary generated yet."}</p>}
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: 8, borderTop: `1px solid ${T.borderSubtle}`, paddingTop: 12 }}>
        <Btn size="sm" variant="secondary" full onClick={onOpen}>
          <Icon name="external" size={13} color={T.secondary} /> Open in viewer
        </Btn>
        {moving ? (
          <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            <label style={{ font: `400 11px/1 ${T.mono}`, color: T.tertiary }}>Move / assign to</label>
            <select autoFocus defaultValue="" disabled={busy}
              onChange={(e) => { const d = directories.find((x) => x.id === e.target.value); if (d) onMove(d); }}
              style={{ height: 32, borderRadius: T.rMd, border: `1px solid ${T.borderDefault}`, background: T.bg, color: T.fg, font: `400 12.5px/1 ${T.sans}`, padding: "0 8px" }}>
              <option value="" disabled>Choose a folder…</option>
              {(["project", "org"] as DirScope[]).map((sc) => {
                const group = directories.filter((d) => d.scope === sc);
                if (!group.length) return null;
                return (
                  <optgroup key={sc} label={scopeLabel(sc)}>
                    {group.map((d) => (
                      <option key={d.id} value={d.id} disabled={d.id === file.directory_id}>
                        {d.parent_id === null ? `${d.name} (root)` : d.name}{d.scope !== file.scope ? " — changes scope" : ""}
                      </option>
                    ))}
                  </optgroup>
                );
              })}
            </select>
            <Btn size="sm" variant="ghost" onClick={onCancelMove}>Cancel</Btn>
          </div>
        ) : (
          <Btn size="sm" variant="secondary" full onClick={onStartMove} disabled={busy}>
            <Icon name="tree" size={13} color={T.secondary} /> Move / assign
          </Btn>
        )}
        <Btn size="sm" variant="ghost" full onClick={onDelete} disabled={busy} style={{ color: T.danger }}>
          <Icon name="x" size={13} color={T.danger} /> Delete file
        </Btn>
      </div>
    </aside>
  );
}

// ── Small primitives ──────────────────────────────────────────────────────────
function BreadcrumbButton({ label, icon, active, onClick }: { label: string; icon?: string; active: boolean; onClick: () => void }) {
  return (
    <button onClick={onClick} disabled={active}
      style={{ display: "inline-flex", alignItems: "center", gap: 5, padding: "4px 7px", border: "none", borderRadius: T.rMd, background: "transparent", cursor: active ? "default" : "pointer", font: `${active ? 600 : 500} 13px/1 ${T.sans}`, color: active ? T.fg : T.brandDeep, maxWidth: 200, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
      {icon && <Icon name={icon} size={13} color={active ? T.fg : T.brandDeep} />}{label}
    </button>
  );
}

function FolderGlyph() {
  return (
    <span style={{ width: 30, height: 24, flexShrink: 0, display: "grid", placeItems: "center", background: "#eef2ff", borderRadius: 5 }}>
      <svg width={17} height={17} viewBox="0 0 24 24" fill="none" stroke="#1A7BFF" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round">
        <path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7z" />
      </svg>
    </span>
  );
}

function FileGlyph({ v, size }: { v: Visual; size: number }) {
  return (
    <span style={{ width: size, height: size, flexShrink: 0, display: "grid", placeItems: "center", background: v.bg, borderRadius: 6, position: "relative" }}>
      <Icon name={v.icon} size={Math.round(size * 0.5)} color={v.fg} />
      <span style={{ position: "absolute", bottom: -6, left: "50%", transform: "translateX(-50%)", font: `700 7px/1 ${T.mono}`, letterSpacing: "0.04em", color: v.fg, background: v.bg, padding: "1px 3px", borderRadius: 3, whiteSpace: "nowrap" }}>{v.label}</span>
    </span>
  );
}

const emptyBox: React.CSSProperties = {
  border: `1px dashed ${T.borderDefault}`, borderRadius: 12, padding: "22px", textAlign: "center",
  font: `400 12.5px/1.5 ${T.sans}`, color: T.tertiary,
};

function Loading() {
  return (
    <div style={{ flex: 1, overflow: "auto", padding: "20px 24px" }}>
      <div style={{ maxWidth: 980, margin: "0 auto" }}>
        <Skel w={180} h={14} style={{ marginBottom: 16 }} />
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))", gap: 12 }}>
          {Array.from({ length: 4 }, (_, i) => (
            <div key={i} style={{ border: `1px solid ${T.borderSubtle}`, borderRadius: T.rLg, padding: "14px 15px", background: T.raised, display: "flex", flexDirection: "column", gap: 10 }}>
              <Skel w="60%" h={14} /><Skel w="40%" h={10} /><Skel w="90%" h={10} />
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
