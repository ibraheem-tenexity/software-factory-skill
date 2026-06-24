// ArtifactViewer.tsx — standalone new-tab artifact viewer.
// Entry: ArtifactViewer.html?doc=<artifact_id>
// Fetches GET /api/artifacts/{id} for the main artifact, then
// GET /api/projects/{project_id}/overview to populate the left rail.
import { useEffect, useMemo, useState } from "react";
import { api, ProjectArtifact } from "../api";
import { T, Icon } from "../components/onboarding/design";

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
    json: "JSON", csv: "CSV", image: "Image", fig: "Design" };
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

// ── Simple Markdown → React renderer (no external deps) ────────────────────

type TocEntry = { level: number; text: string; id: string };

function slugify(text: string): string {
  return text.toLowerCase().replace(/[^\w\s-]/g, "").replace(/\s+/g, "-");
}

function extractToc(md: string): TocEntry[] {
  return md.split("\n").flatMap((line) => {
    const m = line.match(/^(#{1,3})\s+(.+)/);
    if (!m) return [];
    return [{ level: m[1].length, text: m[2].trim(), id: slugify(m[2].trim()) }];
  });
}

function MarkdownBody({ content }: { content: string }) {
  const toc = useMemo(() => extractToc(content), [content]);
  const lines = content.split("\n");
  const blocks: React.ReactNode[] = [];
  let i = 0;
  let key = 0;

  function inlineRender(text: string): React.ReactNode {
    const parts = text.split(/(\*\*[^*]+\*\*|`[^`]+`|_[^_]+_)/g);
    return parts.map((p, pi) => {
      if (p.startsWith("**") && p.endsWith("**")) return <strong key={pi}>{p.slice(2, -2)}</strong>;
      if (p.startsWith("`") && p.endsWith("`")) return <code key={pi} style={{ font: `500 12px/1 ${T.mono}`, background: T.sunken, padding: "1px 4px", borderRadius: 3 }}>{p.slice(1, -1)}</code>;
      if (p.startsWith("_") && p.endsWith("_")) return <em key={pi}>{p.slice(1, -1)}</em>;
      return p;
    });
  }

  while (i < lines.length) {
    const line = lines[i];

    // Code block
    if (line.startsWith("```")) {
      const lang = line.slice(3).trim();
      const codeLines: string[] = [];
      i++;
      while (i < lines.length && !lines[i].startsWith("```")) { codeLines.push(lines[i]); i++; }
      blocks.push(
        <pre key={key++} style={{ margin: "14px 0", padding: "12px 14px", borderRadius: T.rMd, background: T.sunken, overflowX: "auto", font: `400 12.5px/1.6 ${T.mono}`, color: T.fg }}>
          {lang && <span style={{ display: "block", font: `600 10px/1 ${T.mono}`, color: T.tertiary, marginBottom: 8, letterSpacing: "0.08em", textTransform: "uppercase" }}>{lang}</span>}
          {codeLines.join("\n")}
        </pre>
      );
      i++; continue;
    }

    // Heading
    const hm = line.match(/^(#{1,3})\s+(.+)/);
    if (hm) {
      const level = hm[1].length;
      const text = hm[2].trim();
      const id = slugify(text);
      const sizes = ["", "22px", "18px", "15px"];
      const weights = ["", "700", "600", "600"];
      blocks.push(
        <div key={key++} id={id} style={{ margin: `${level === 1 ? 24 : 18}px 0 8px`, font: `${weights[level]} ${sizes[level]}/1.3 ${T.display}`, letterSpacing: "-0.01em", color: T.fg }}>
          {inlineRender(text)}
        </div>
      );
      i++; continue;
    }

    // Horizontal rule
    if (/^[-*_]{3,}$/.test(line.trim())) {
      blocks.push(<hr key={key++} style={{ margin: "18px 0", border: "none", borderTop: `1px solid ${T.borderSubtle}` }} />);
      i++; continue;
    }

    // List item
    if (/^[-*]\s/.test(line)) {
      const items: string[] = [];
      while (i < lines.length && /^[-*]\s/.test(lines[i])) { items.push(lines[i].replace(/^[-*]\s/, "")); i++; }
      blocks.push(
        <ul key={key++} style={{ margin: "8px 0", paddingLeft: 20, display: "flex", flexDirection: "column", gap: 4 }}>
          {items.map((it, ii) => <li key={ii} style={{ font: `400 13.5px/1.5 ${T.sans}`, color: T.fg }}>{inlineRender(it)}</li>)}
        </ul>
      );
      continue;
    }

    // Blank line
    if (!line.trim()) { i++; continue; }

    // Paragraph
    const para: string[] = [];
    while (i < lines.length && lines[i].trim() && !lines[i].startsWith("#") && !lines[i].startsWith("```") && !/^[-*]\s/.test(lines[i]) && !/^[-*_]{3,}$/.test(lines[i].trim())) {
      para.push(lines[i]); i++;
    }
    if (para.length) {
      blocks.push(
        <p key={key++} style={{ margin: "8px 0", font: `400 13.5px/1.6 ${T.sans}`, color: T.secondary }}>
          {inlineRender(para.join(" "))}
        </p>
      );
    } else { i++; }
  }

  return (
    <div style={{ display: "flex", gap: 32, minHeight: 0 }}>
      <div style={{ flex: 1, minWidth: 0 }}>{blocks}</div>
      {toc.length > 2 && (
        <div style={{ width: 180, flexShrink: 0 }}>
          <div style={{ position: "sticky", top: 0 }}>
            <span style={{ display: "block", font: `600 10px/1 ${T.mono}`, letterSpacing: "0.1em", textTransform: "uppercase", color: T.tertiary, marginBottom: 10 }}>On this page</span>
            {toc.map((h) => (
              <a key={h.id} href={`#${h.id}`}
                style={{ display: "block", padding: `3px 0 3px ${(h.level - 1) * 10}px`, font: `${h.level === 1 ? 500 : 400} 12px/1.4 ${T.sans}`, color: T.secondary, textDecoration: "none" }}
                onMouseEnter={(e) => (e.currentTarget.style.color = T.fg)}
                onMouseLeave={(e) => (e.currentTarget.style.color = T.secondary)}>
                {h.text}
              </a>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// ── Content renderer ─────────────────────────────────────────────────────────

function ContentBody({ artifact }: { artifact: ArtifactDetail }) {
  const { kind, path, content } = artifact;

  if (content === null) {
    return (
      <div style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", flex: 1, gap: 14, color: T.tertiary }}>
        <Icon name="file" size={36} color={T.tertiary} />
        <span style={{ font: `400 13.5px/1.5 ${T.sans}` }}>Binary file or content too large to preview.</span>
        {path && (
          <a href={path.startsWith("http") ? path : `/api/projects/${artifact.project_id}/artifact?path=${encodeURIComponent(path)}`}
            download target="_blank" rel="noreferrer"
            style={{ display: "inline-flex", alignItems: "center", gap: 6, padding: "8px 14px", borderRadius: T.rMd,
              border: `1px solid ${T.borderDefault}`, background: T.raised, font: `500 13px/1 ${T.sans}`, color: T.fg, textDecoration: "none" }}>
            <Icon name="external" size={14} color={T.secondary} /> Download / Open
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
        <MarkdownBody content={content} />
      </div>
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
    if (!docId) { setError("No doc= or sow= parameter in URL."); return; }
    api.getArtifact(docId)
      .then((a) => {
        setArtifact(a as ArtifactDetail);
        // Load project documents for the left rail (produced artifacts list)
        api.documents(a.project_id)
          .then((d) => setRailItems(d.produced || []))
          .catch(() => {});
      })
      .catch((e) => setError(String(e)));
  }, [docId, sowId]);

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
    return (
      <div style={{ height: "100vh", display: "grid", placeItems: "center", background: T.bg, fontFamily: T.sans }}>
        <span style={{ font: `400 13.5px/1.5 ${T.sans}`, color: T.danger }}>{error}</span>
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
          {activePath && (
            <a href={activePath.startsWith("http") ? activePath : `/api/projects/${artifact.project_id}/artifact?path=${encodeURIComponent(activePath)}`}
              download={!activePath.startsWith("http")} target="_blank" rel="noreferrer"
              style={{ display: "inline-flex", alignItems: "center", gap: 5, padding: "6px 11px", borderRadius: T.rMd,
                border: `1px solid ${T.borderSubtle}`, background: T.raised, cursor: "pointer",
                font: `500 12.5px/1 ${T.sans}`, color: T.fg, textDecoration: "none" }}>
              <Icon name="external" size={13} color={T.secondary} /> Download
            </a>
          )}
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
