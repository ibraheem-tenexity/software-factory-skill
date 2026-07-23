// FactoryOutputsPeer.tsx — the in-shell Factory Outputs workspace (SOF-245).
//
// A dedicated peer in the Project Console that projects the REAL factory-produced artifacts,
// grouped by the pipeline stage that produced them, and reads them inline (no modal / no new tab)
// through the ONE shared artifact-body renderer (viewer/ArtifactBody). It reuses the project
// documents projection (GET /api/projects/{id}/documents → `produced`), which is project-authorized
// and already excludes user uploads, org documents, context/interview inputs and the Product Brief.
//
// This is a self-contained component with a thin mount in ProjectView; SOF-239's unified shell
// owns the peer-view container and relocates the mount at rebase — all Outputs logic stays here.
//
// #441 (SOF-78) dependency: grouping keys off the artifact's nullable `stage` field. Until #441's
// stage metadata lands in the produced DTO every row reads stage=undefined and falls into the
// honest "Other factory outputs" bucket — never a guessed stage. After #441 merges ahead of this,
// rows carry their real producing stage and group under Research / Design / Build & Ship.
import { useEffect, useMemo, useRef, useState } from "react";
import { api, ProjectArtifact, ApiError } from "../../api";
import { T, Icon, CategoryLabel } from "../onboarding/design";
import { ArtifactBody, kindLabel, badgeTone, fmtDate } from "../../viewer/ArtifactBody";
import { openArtifact, artifactKind } from "../factory/Artifacts";
import { STAGES } from "../factory/pipeline";
import { setDisplayContext } from "../factory/displayContext";

// Stage number → customer-readable title, mirrored from the real pipeline model (pipeline.ts).
const STAGE_TITLE: Record<number, string> = Object.fromEntries(STAGES.map((s) => [s.stage, s.title]));
const OTHER_LABEL = "Other factory outputs";

// The kind the shared renderer/label dispatch on: prefer the stored kind, else derive from path.
function kindOf(a: ProjectArtifact): string {
  return a.kind || (a.path ? artifactKind(a.path) : "doc");
}

// Group produced artifacts by their real producing stage. Known stages (1/2/3) render in pipeline
// order; rows with a null/undefined/unknown stage collect under "Other factory outputs" — an
// honest bucket, never a plausible-looking guess (SOF-245 AC).
type OutputGroup = { key: string; title: string; items: ProjectArtifact[] };
function groupByStage(produced: ProjectArtifact[]): OutputGroup[] {
  const known: OutputGroup[] = STAGES.map((s) => ({ key: `stage-${s.stage}`, title: `Stage ${s.stage} · ${s.title}`, items: [] }));
  const byStage: Record<number, OutputGroup> = {};
  STAGES.forEach((s, i) => { byStage[s.stage] = known[i]; });
  const other: OutputGroup = { key: "other", title: OTHER_LABEL, items: [] };
  for (const a of produced) {
    const g = (a.stage != null && byStage[a.stage]) ? byStage[a.stage] : other;
    g.items.push(a);
  }
  return [...known.filter((g) => g.items.length), ...(other.items.length ? [other] : [])];
}

function stageLabelFor(a: ProjectArtifact): string {
  return a.stage != null && STAGE_TITLE[a.stage] ? STAGE_TITLE[a.stage] : OTHER_LABEL;
}

function setOutputParam(id: number | null) {
  const p = new URLSearchParams(location.search);
  if (id == null) p.delete("output"); else p.set("output", String(id));
  history.replaceState(null, "", "?" + p.toString());
}

export function FactoryOutputsPeer({ projectId }: { projectId: string }) {
  const [produced, setProduced] = useState<ProjectArtifact[] | null>(null);
  const [loadErr, setLoadErr] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<number | null>(() => {
    const raw = new URLSearchParams(location.search).get("output");
    const n = raw ? Number(raw) : NaN;
    return Number.isFinite(n) ? n : null;
  });
  const [content, setContent] = useState<string | null>(null);
  const [contentLoading, setContentLoading] = useState(false);
  const contentReq = useRef(0);

  // Load the project's produced-artifact projection.
  useEffect(() => {
    let live = true;
    setProduced(null);
    setLoadErr(null);
    api.documents(projectId)
      .then((d) => { if (live) setProduced(d.produced || []); })
      .catch((e) => {
        if (!live) return;
        const detail = (e as ApiError)?.detail;
        setLoadErr(typeof detail === "string" && detail ? detail : "the factory outputs projection could not be loaded.");
        setProduced([]);
      });
    return () => { live = false; };
  }, [projectId]);

  const groups = useMemo(() => groupByStage(produced || []), [produced]);
  const selected = useMemo(
    () => (produced || []).find((a) => a.id != null && a.id === selectedId) || null,
    [produced, selectedId],
  );

  // Once outputs load, honour a deep-linked ?output=<id> that no longer exists by clearing it,
  // so the peer never shows a stale "selected" state for an artifact that isn't in the projection.
  useEffect(() => {
    if (produced && selectedId != null && !selected) { setSelectedId(null); setOutputParam(null); }
  }, [produced, selectedId, selected]);

  // Load the selected artifact's content by path. An http path (repo / live app / external link)
  // and a path-less row are not fetchable — pass content=null so the shared renderer shows its
  // honest external-link / unavailable framing rather than a spinner that never resolves.
  useEffect(() => {
    if (!selected) { setContent(null); setContentLoading(false); return; }
    const req = ++contentReq.current;
    const path = selected.path || "";
    if (!path || path.startsWith("http")) { setContent(null); setContentLoading(false); return; }
    setContentLoading(true);
    api.artifact(projectId, path)
      .then((r) => { if (req === contentReq.current) setContent(r.content ?? null); })
      .catch(() => { if (req === contentReq.current) setContent(null); })
      .finally(() => { if (req === contentReq.current) setContentLoading(false); });
  }, [selected, projectId]);

  // Publish the current selection as ephemeral Concierge display context (SOF-245 AC). Cleared on
  // deselect and on unmount so it never leaks onto the Overview/Files surfaces or a later turn.
  useEffect(() => {
    if (!selected) { setDisplayContext(null); return; }
    const stageLabel = stageLabelFor(selected);
    const kLabel = kindLabel(kindOf(selected), selected.path || "");
    const title = selected.title || selected.path?.split("/").pop() || "factory output";
    const staged = stageLabel === OTHER_LABEL
      ? "its producing stage isn’t recorded"
      : `produced in the ${stageLabel} stage`;
    setDisplayContext({
      projectId, artifactId: selected.id, title, stageLabel, kindLabel: kLabel,
      summary: `The customer is viewing the factory output “${title}” (${kLabel}), ${staged}.`,
    });
    return () => setDisplayContext(null);
  }, [selected, projectId]);

  const select = (a: ProjectArtifact) => {
    if (a.id == null) return;
    setSelectedId(a.id);
    setOutputParam(a.id);
  };

  const total = produced?.length ?? 0;

  return (
    <div style={{ flex: 1, minHeight: 0, display: "flex", background: T.bg }}>
      {/* ── left rail: outputs grouped by producing stage ── */}
      <aside style={{ width: 268, flexShrink: 0, borderRight: `1px solid ${T.borderSubtle}`, background: T.raised,
        display: "flex", flexDirection: "column", overflowY: "auto" }}>
        <div style={{ padding: "16px 16px 10px", borderBottom: `1px solid ${T.borderSubtle}` }}>
          <CategoryLabel>Factory outputs{produced ? ` · ${total}` : ""}</CategoryLabel>
          <p style={{ margin: "6px 0 0", font: `400 11.5px/1.5 ${T.sans}`, color: T.tertiary }}>
            What the factory produced, grouped by the pipeline stage that made it.
          </p>
        </div>

        {produced === null ? (
          <div style={{ padding: "14px 16px", font: `400 12.5px/1.5 ${T.sans}`, color: T.tertiary }}>Loading factory outputs…</div>
        ) : loadErr ? (
          <div style={{ padding: "14px 16px", font: `400 12.5px/1.5 ${T.sans}`, color: T.danger }}>Couldn’t load factory outputs — {loadErr}</div>
        ) : total === 0 ? (
          <div style={{ padding: "14px 16px", font: `400 12.5px/1.5 ${T.sans}`, color: T.tertiary }}>
            The factory hasn’t produced any outputs for this project yet. Each output appears here as its pipeline stage completes.
          </div>
        ) : (
          groups.map((g) => (
            <div key={g.key} style={{ paddingBottom: 6 }}>
              <div style={{ padding: "10px 16px 4px", font: `600 10px/1 ${T.mono}`, letterSpacing: "0.08em",
                textTransform: "uppercase", color: g.key === "other" ? T.tertiary : T.secondary }}>
                {g.title}
              </div>
              {g.items.map((a, i) => {
                const active = a.id != null && a.id === selectedId;
                const label = a.title || a.path?.split("/").pop() || "Artifact";
                return (
                  <button key={`${a.id ?? a.path ?? label}-${i}`} onClick={() => select(a)} disabled={a.id == null} title={a.path || label}
                    style={{ display: "flex", alignItems: "center", gap: 8, width: "100%", textAlign: "left",
                      padding: "7px 16px", border: "none", cursor: a.id == null ? "default" : "pointer",
                      background: active ? T.brandSoft : "transparent",
                      borderLeft: active ? `2px solid ${T.brand}` : "2px solid transparent",
                      opacity: a.id == null ? 0.55 : 1 }}>
                    <Icon name="file" size={13} color={active ? T.brandDeep : T.tertiary} />
                    <span style={{ flex: 1, minWidth: 0, font: `${active ? 600 : 400} 12.5px/1.35 ${T.sans}`,
                      color: active ? T.brandDeep : T.fg, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                      {label}
                    </span>
                    {a.agent && <span style={{ font: `400 10px/1 ${T.mono}`, color: T.tertiary, flexShrink: 0 }}>{a.agent}</span>}
                  </button>
                );
              })}
            </div>
          ))
        )}
      </aside>

      {/* ── content: header + inline typed body ── */}
      {!selected ? (
        <div style={{ flex: 1, display: "grid", placeItems: "center", padding: 24 }}>
          <span style={{ font: `400 13.5px/1.6 ${T.sans}`, color: T.tertiary, textAlign: "center", maxWidth: 420 }}>
            {produced === null
              ? "Loading factory outputs…"
              : total === 0
                ? "No factory output to read yet — the pipeline hasn’t produced one for this project."
                : "Select a factory output on the left to read it here."}
          </span>
        </div>
      ) : (
        <div style={{ flex: 1, minWidth: 0, display: "flex", flexDirection: "column", minHeight: 0 }}>
          <ContentHeader artifact={selected} onOpenStandalone={() => selected.id != null && openArtifact(selected.id)} />
          {contentLoading
            ? <div style={{ flex: 1, display: "grid", placeItems: "center" }}><span style={{ font: `400 13px/1 ${T.sans}`, color: T.tertiary }}>Loading…</span></div>
            : <ArtifactBody data={{ kind: kindOf(selected), path: selected.path || "", content, project_id: projectId, title: selected.title }} />}
        </div>
      )}
    </div>
  );
}

// The reader header: kind badge · title · producing stage · agent · timestamp · Open in new tab
// (the standalone Artifact Viewer, same artifact id — the retained deep link).
function ContentHeader({ artifact, onOpenStandalone }: { artifact: ProjectArtifact; onOpenStandalone: () => void }) {
  const kind = kindOf(artifact);
  const { bg, color } = badgeTone(kind);
  const title = artifact.title || artifact.path?.split("/").pop() || "Artifact";
  const stageLabel = stageLabelFor(artifact);
  return (
    <header style={{ display: "flex", alignItems: "center", gap: 12, padding: "12px 20px",
      background: T.raised, borderBottom: `1px solid ${T.borderSubtle}`, flexShrink: 0 }}>
      <span style={{ padding: "3px 8px", borderRadius: 4, background: bg, font: `600 10px/1 ${T.mono}`,
        letterSpacing: "0.07em", textTransform: "uppercase", color, flexShrink: 0 }}>
        {kindLabel(kind, artifact.path || "")}
      </span>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ font: `600 13.5px/1.25 ${T.sans}`, color: T.fg, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }} title={artifact.path || title}>{title}</div>
        <div style={{ font: `400 11px/1.3 ${T.sans}`, color: T.tertiary, marginTop: 2 }}>
          {stageLabel}{artifact.agent ? ` · produced by ${artifact.agent}` : ""}{artifact.ts ? ` · ${fmtDate(artifact.ts)}` : ""}
        </div>
      </div>
      {artifact.id != null && (
        <button onClick={onOpenStandalone} title="Open in the standalone Artifact Viewer (new tab)"
          style={{ display: "inline-flex", alignItems: "center", gap: 5, padding: "6px 11px", borderRadius: T.rMd,
            border: `1px solid ${T.borderSubtle}`, background: T.raised, cursor: "pointer",
            font: `500 12.5px/1 ${T.sans}`, color: T.fg, flexShrink: 0 }}>
          <Icon name="external" size={13} color={T.secondary} /> Open in new tab
        </button>
      )}
    </header>
  );
}
