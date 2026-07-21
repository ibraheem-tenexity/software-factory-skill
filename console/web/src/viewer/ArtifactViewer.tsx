// ArtifactViewer.tsx — standalone new-tab artifact viewer.
// Entry: ArtifactViewer.html?doc=<artifact_id> (project artifact; fetches GET /api/artifacts/{id},
// then GET /api/projects/{project_id}/overview for the left rail) — or ?sow=<sow_id> (Tenexity OS
// SOW) — or ?blob=<blob_id>&name=<filename> (an org-scope KB blob, e.g. codebase-discovery's
// generated docs; fetches GET /api/org/docs/{id}/content, no rail).
import { useEffect, useState } from "react";
import { api, ApiError, ProjectArtifact } from "../api";
import { T, Icon } from "../components/onboarding/design";
import { MarkdownBody } from "../markdown";

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

// ── Helpers ──────────────────────────────────────────────────────────────────

function kindLabel(kind: string, path: string): string {
  const ext = path.split(".").pop()?.toLowerCase() || "";
  const MAP: Record<string, string> = { deploy: "Deploy", repo: "Repo", "demo-creds": "Creds",
    context: "Context", md: "Markdown", sow: "SOW", svg: "SVG", code: "Code",
    json: "JSON", csv: "CSV", image: "Image", fig: "Design", mockup: "Mockup", "flow-map": "Flow Map",
    "decision-log": "Decision Log" };
  return MAP[kind] || MAP[ext] || kind || "File";
}

function badgeTone(kind: string): { bg: string; color: string } {
  if (kind === "deploy" || kind === "repo") return { bg: T.successSoft, color: T.success };
  if (kind === "md" || kind === "sow") return { bg: T.brandSoft, color: T.brandDeep };
  return { bg: T.sunken, color: T.secondary };
}

function fmtDate(epoch?: number): string {
  if (!epoch) return "—";
  return new Date(epoch * 1000).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
}

function extOf(path: string): string {
  return path.split(".").pop()?.toLowerCase() || "";
}

function isMd(kind: string, path: string): boolean {
  return kind === "md" || kind === "sow" || ["md", "mdx"].includes(extOf(path));
}
function isSvg(kind: string, path: string): boolean {
  return kind === "svg" || extOf(path) === "svg";
}
function isImage(kind: string, path: string): boolean {
  return kind === "image" || ["png", "jpg", "jpeg", "gif", "webp"].includes(extOf(path));
}
function isCode(kind: string, path: string): boolean {
  return ["code", "json", "csv", "repo"].includes(kind) || ["js", "ts", "tsx", "jsx", "py", "json", "csv", "sh", "yml", "yaml", "txt"].includes(extOf(path));
}
function isHtml(kind: string, path: string): boolean {
  return kind === "mockup" || extOf(path) === "html";
}

// ── Content renderer ─────────────────────────────────────────────────────────

function ContentBody({ artifact }: { artifact: ArtifactDetail }) {
  const { kind, path, content } = artifact;

  if (content === null) {
    // SOF-139: don't conflate "external link", "binary", and "content is gone" — and never show a
    // Download link that 404s. A URL artifact opens externally; anything else with no content is
    // honestly unavailable (its file wasn't stored and the workspace was cleaned up — SOF-138).
    const isUrl = path.startsWith("http");
    return (
      <div style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", flex: 1, gap: 14, color: T.tertiary }}>
        <Icon name="file" size={36} color={T.tertiary} />
        <span style={{ font: `400 13.5px/1.5 ${T.sans}`, textAlign: "center", maxWidth: 380 }}>
          {isUrl
            ? "This artifact is an external link."
            : "This file’s content is no longer available — it wasn’t stored and its workspace has been cleaned up."}
        </span>
        {isUrl && (
          <a href={path} target="_blank" rel="noreferrer"
            style={{ display: "inline-flex", alignItems: "center", gap: 6, padding: "8px 14px", borderRadius: T.rMd,
              border: `1px solid ${T.borderDefault}`, background: T.raised, font: `500 13px/1 ${T.sans}`, color: T.fg, textDecoration: "none" }}>
            <Icon name="external" size={14} color={T.secondary} /> Open link
          </a>
        )}
      </div>
    );
  }

  if (isSvg(kind, path)) {
    return (
      <div style={{ flex: 1, overflow: "auto", display: "grid", placeItems: "center", padding: 24 }}
        dangerouslySetInnerHTML={{ __html: content }} />
    );
  }

  if (isImage(kind, path)) {
    const src = path.startsWith("http") ? path : `/api/projects/${artifact.project_id}/artifact?path=${encodeURIComponent(path)}`;
    return (
      <div style={{ flex: 1, overflow: "auto", display: "grid", placeItems: "center", padding: 24 }}>
        <img src={src} alt={artifact.title || path} style={{ maxWidth: "100%", borderRadius: T.rMd, boxShadow: T.shadowMd }} />
      </div>
    );
  }

  if (isMd(kind, path)) {
    return (
      <div style={{ flex: 1, overflow: "auto", padding: "24px 28px" }}>
        <MarkdownBody content={content} showToc />
      </div>
    );
  }

  if (isHtml(kind, path)) {
    // SOF-99: mockups are agent-generated static HTML — sandbox with NO allow-scripts, since
    // they're meant to be static and a script (even benign) should never execute here.
    return (
      <iframe title={artifact.title || path} srcDoc={content} sandbox=""
        style={{ flex: 1, border: "none", background: "#fff" }} />
    );
  }

  // code / json / csv / plain text
  return (
    <div style={{ flex: 1, overflow: "auto", padding: "20px 24px" }}>
      <pre style={{ margin: 0, font: `400 12.5px/1.6 ${T.mono}`, color: T.fg, whiteSpace: "pre-wrap", wordBreak: "break-word" }}>
        {content}
      </pre>
    </div>
  );
}

// ── Main viewer ───────────────────────────────────────────────────────────────

export function ArtifactViewer() {
  const params = new URLSearchParams(location.search);
  const docId = params.get("doc");
  const sowId = params.get("sow");
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
    if (sowId) {
      // SOW mode: fetch from /api/admin/sow/{id} and synthesise an ArtifactDetail
      api.adminSowGet(Number(sowId))
        .then((sow) => {
          setArtifact({
            id: sow.id,
            project_id: `sow-${sow.id}`,
            title: sow.title,
            kind: "sow",
            path: `sow-${sow.id}.md`,
            content: sow.body ?? "",
            updated: typeof sow.updated_at === "number" ? sow.updated_at : 0,
            agent: null,
          });
        })
        .catch((e) => setError(String(e)));
      return;
    }
    if (blobId) {
      // Org-scope KB blob mode (e.g. codebase-discovery's generated docs) — a different
      // table/id-space from `artifacts`, no project rail to load, mirrors the sow-mode shape above.
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
    if (!docId) { setError("No doc=, sow=, or blob= parameter in URL."); return; }
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
  }, [docId, sowId, blobId, blobName]);

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
          : displayArtifact && <ContentBody artifact={displayArtifact as ArtifactDetail} />
        }
      </div>
    </div>
  );
}
