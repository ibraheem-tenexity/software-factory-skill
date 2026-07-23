// ArtifactViewer.tsx — standalone new-tab artifact viewer.
// Entry: ArtifactViewer.html?doc=<artifact_id> (project artifact; fetches GET /api/artifacts/{id},
// then GET /api/projects/{project_id}/overview for the left rail) — or ?blob=<blob_id>&name=<filename>
// (an org-scope KB blob, e.g. codebase-discovery's generated docs).
// generated docs; fetches GET /api/org/docs/{id}/content, no rail).
import { useEffect, useState } from "react";
import { api, ApiError, ProjectArtifact } from "../api";
import { T, Icon } from "../components/onboarding/design";
import { ArtifactBody, kindLabel, badgeTone, fmtDate } from "./ArtifactBody";

// ── Types ────────────────────────────────────────────────────────────────────

type ArtifactDetail = {
  id: number;
  project_id: string;
  title: string | null;
  kind: string;
  path: string;
  content: string | null;  // null = binary / too-large
  updated: number;
  agent: string | null;
};

// The typed body renderer + its kind/label/date helpers now live in the shared ArtifactBody
// module (SOF-245) so the standalone viewer, the in-shell Factory Outputs reader, and the Factory
// Console preview all render off one implementation.

// ── Main viewer ───────────────────────────────────────────────────────────────

export function ArtifactViewer() {
  const params = new URLSearchParams(location.search);
  const docId = params.get("doc");
  const blobId = params.get("blob");
  const blobName = params.get("name") || "";

  const [artifact, setArtifact] = useState<ArtifactDetail | null>(null);
  const [railItems, setRailItems] = useState<ProjectArtifact[]>([]);
  const [search, setSearch] = useState("");
  const [error, setError] = useState<string | null>(null);

  // Override: when user clicks a rail item, load its content by path
  const [override, setOverride] = useState<{ item: ProjectArtifact; content: string | null } | null>(null);
  const [overrideLoading, setOverrideLoading] = useState(false);

  useEffect(() => {
    if (blobId) {
      // Org-scope KB blob mode (e.g. codebase-discovery's generated docs) — a different
      // table/id-space from `artifacts`, no project rail to load, a synthesized ArtifactDetail, same shape as project artifacts.
      api.orgDocContent(Number(blobId))
        .then((r) => {
          setArtifact({
            id: Number(blobId),
            project_id: `org-doc-${blobId}`,
            title: blobName || null,
            kind: "md",
            path: blobName || `org-doc-${blobId}.md`,
            content: r.content ?? null,
            updated: 0,
            agent: null,
          });
        })
        .catch((e) => {
          const detail = (e as ApiError)?.detail;
          setError(typeof detail === "string" && detail ? detail : "This artifact couldn't be loaded.");
        });
      return;
    }
    if (!docId) { setError("No doc= or blob= parameter in URL."); return; }
    api.getArtifact(docId)
      .then((a) => {
        setArtifact(a as ArtifactDetail);
        // Load project documents for the left rail (produced artifacts list)
        api.documents(a.project_id)
          .then((d) => setRailItems(d.produced || []))
          .catch(() => {});
      })
      .catch((e) => {
        // SOF-191: a bare "path → 500" is not an honest reason a viewer should show a person —
        // surface the server's parsed `detail` when the API sent one, otherwise say plainly that
        // the artifact couldn't be loaded rather than leak the raw fetch error shape.
        const detail = (e as ApiError)?.detail;
        setError(typeof detail === "string" && detail ? detail : "This artifact couldn't be loaded.");
      });
  }, [docId, blobId, blobName]);

  const displayArtifact = artifact
    ? (override
      ? { ...artifact, title: override.item.title || artifact.title, path: override.item.path || artifact.path, content: override.content, kind: override.item.kind || artifact.kind, agent: override.item.agent || artifact.agent }
      : artifact)
    : null;

  const filteredRail = railItems.filter((r) =>
    !search || (r.title || r.path || "").toLowerCase().includes(search.toLowerCase())
  );

  const copyContent = () => {
    if (displayArtifact?.content) navigator.clipboard.writeText(displayArtifact.content).catch(() => {});
  };

  // Blob mode has no `/api/projects/{project_id}/artifact?path=` to download from (there's no
  // project) — the download route's own response is `{content}` JSON, not raw bytes, so a plain
  // `<a href>` to it would save a JSON-wrapped file under the right name but the wrong content.
  // The content is already in hand (fetched once at load), so build the real file client-side.
  const downloadBlobContent = () => {
    if (!displayArtifact?.content) return;
    const blob = new Blob([displayArtifact.content], { type: "text/plain" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = displayArtifact.path.split("/").pop() || "artifact.txt";
    a.click();
    URL.revokeObjectURL(url);
  };

  const selectRailItem = async (item: ProjectArtifact) => {
    if (!artifact) return;
    if (!item.path) { setOverride({ item, content: null }); return; }
    setOverrideLoading(true);
    try {
      const r = await api.artifact(artifact.project_id, item.path);
      setOverride({ item, content: r.content ?? null });
    } catch {
      setOverride({ item, content: null });
    } finally {
      setOverrideLoading(false);
    }
  };

  if (error) {
    // Same honest-unavailable framing ContentBody uses for a stored-but-gone artifact (SOF-139) —
    // a fetch failure isn't a different kind of "not available" from the user's point of view.
    return (
      <div style={{ height: "100vh", display: "flex", flexDirection: "column", alignItems: "center",
        justifyContent: "center", gap: 14, background: T.bg, fontFamily: T.sans, color: T.tertiary }}>
        <Icon name="file" size={36} color={T.tertiary} />
        <span style={{ font: `400 13.5px/1.5 ${T.sans}`, textAlign: "center", maxWidth: 380 }}>
          Unavailable: {error}
        </span>
      </div>
    );
  }

  if (!artifact) {
    return (
      <div style={{ height: "100vh", display: "grid", placeItems: "center", background: T.bg, fontFamily: T.sans }}>
        <span style={{ font: `400 13.5px/1 ${T.sans}`, color: T.tertiary }}>Loading…</span>
      </div>
    );
  }

  const activeKind = displayArtifact?.kind || artifact.kind;
  const activePath = displayArtifact?.path || artifact.path;
  const activeTitle = displayArtifact?.title || artifact.title || activePath.split("/").pop() || "Artifact";
  const activeUpdated = artifact.updated;
  const { bg: badgeBg, color: badgeColor } = badgeTone(activeKind);

  return (
    <div style={{ height: "100vh", display: "flex", flexDirection: "column", background: T.bg, fontFamily: T.sans, color: T.fg }}>

      {/* topbar */}
      <header style={{ display: "flex", alignItems: "center", gap: 12, padding: "11px 20px", background: T.raised, borderBottom: `1px solid ${T.borderSubtle}`, flexShrink: 0 }}>
        {/* breadcrumb */}
        <div style={{ display: "flex", alignItems: "center", gap: 6, flex: 1, minWidth: 0 }}>
          <span style={{ font: `400 12.5px/1 ${T.mono}`, color: T.tertiary, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
            {artifact.project_id}
          </span>
          <Icon name="chevronDown" size={12} color={T.tertiary} />
          <span style={{ font: `600 13px/1 ${T.sans}`, color: T.fg, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{activeTitle}</span>
        </div>

        {/* kind badge */}
        <span style={{ padding: "3px 8px", borderRadius: 4, background: badgeBg, font: `600 10px/1 ${T.mono}`, letterSpacing: "0.07em", textTransform: "uppercase", color: badgeColor, flexShrink: 0 }}>
          {kindLabel(activeKind, activePath)}
        </span>

        {/* updated */}
        <span style={{ font: `400 11.5px/1 ${T.sans}`, color: T.tertiary, flexShrink: 0 }}>Updated {fmtDate(activeUpdated)}</span>

        {/* actions */}
        <div style={{ display: "flex", gap: 6, flexShrink: 0 }}>
          {displayArtifact?.content && (
            <button onClick={copyContent}
              style={{ display: "inline-flex", alignItems: "center", gap: 5, padding: "6px 11px", borderRadius: T.rMd,
                border: `1px solid ${T.borderSubtle}`, background: T.raised, cursor: "pointer",
                font: `500 12.5px/1 ${T.sans}`, color: T.fg }}>
              <Icon name="file" size={13} color={T.secondary} /> Copy
            </button>
          )}
          {activePath && (blobId ? (
            <button onClick={downloadBlobContent}
              style={{ display: "inline-flex", alignItems: "center", gap: 5, padding: "6px 11px", borderRadius: T.rMd,
                border: `1px solid ${T.borderSubtle}`, background: T.raised, cursor: "pointer",
                font: `500 12.5px/1 ${T.sans}`, color: T.fg }}>
              <Icon name="external" size={13} color={T.secondary} /> Download
            </button>
          ) : (
            <a href={activePath.startsWith("http") ? activePath : `/api/projects/${artifact.project_id}/artifact?path=${encodeURIComponent(activePath)}`}
              download={!activePath.startsWith("http")} target="_blank" rel="noreferrer"
              style={{ display: "inline-flex", alignItems: "center", gap: 5, padding: "6px 11px", borderRadius: T.rMd,
                border: `1px solid ${T.borderSubtle}`, background: T.raised, cursor: "pointer",
                font: `500 12.5px/1 ${T.sans}`, color: T.fg, textDecoration: "none" }}>
              <Icon name="external" size={13} color={T.secondary} /> Download
            </a>
          ))}
        </div>
      </header>

      {/* body: left rail + content */}
      <div style={{ flex: 1, minHeight: 0, display: "flex" }}>

        {/* left rail */}
        <aside style={{ width: 240, flexShrink: 0, borderRight: `1px solid ${T.borderSubtle}`, background: T.raised, display: "flex", flexDirection: "column", overflowY: "auto" }}>
          <div style={{ padding: "12px 12px 8px" }}>
            <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search artifacts…"
              style={{ width: "100%", boxSizing: "border-box", height: 30, padding: "0 9px", borderRadius: T.rSm,
                border: `1px solid ${T.borderDefault}`, background: T.bg, color: T.fg,
                font: `400 12.5px/1 ${T.sans}`, outline: "none" }} />
          </div>

          {/* project group header */}
          <div style={{ padding: "6px 12px 4px", font: `500 10px/1 ${T.mono}`, letterSpacing: "0.1em", textTransform: "uppercase", color: T.tertiary }}>
            {artifact.project_id.replace("project-", "").slice(0, 8)}
          </div>

          {filteredRail.length === 0
            ? <div style={{ padding: "8px 12px", font: `400 12px/1.4 ${T.sans}`, color: T.tertiary }}>{railItems.length === 0 ? "No artifacts in project." : "No results."}</div>
            : filteredRail.map((item, i) => {
              const isActive = !override
                ? item.path === artifact.path
                : item.path === override.item.path;
              return (
                <button key={i} onClick={() => selectRailItem(item)}
                  style={{ display: "flex", alignItems: "center", gap: 8, width: "100%", textAlign: "left",
                    padding: "7px 12px", border: "none", cursor: "pointer",
                    background: isActive ? T.brandSoft : "transparent",
                    borderLeft: isActive ? `2px solid ${T.brand}` : "2px solid transparent" }}>
                  <Icon name="file" size={13} color={isActive ? T.brandDeep : T.tertiary} />
                  <span style={{ font: `${isActive ? 600 : 400} 12.5px/1.3 ${T.sans}`, color: isActive ? T.brandDeep : T.fg, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                    {item.title || item.path?.split("/").pop() || "Artifact"}
                  </span>
                </button>
              );
            })
          }
        </aside>

        {/* content area */}
        {overrideLoading
          ? <div style={{ flex: 1, display: "grid", placeItems: "center" }}><span style={{ font: `400 13px/1 ${T.sans}`, color: T.tertiary }}>Loading…</span></div>
          : displayArtifact && <ArtifactBody data={displayArtifact as ArtifactDetail} />
        }
      </div>
    </div>
  );
}
