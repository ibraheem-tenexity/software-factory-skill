// ArtifactBody.tsx — the ONE authoritative typed artifact-body renderer (SOF-245).
//
// Extracted from ArtifactViewer.tsx's ContentBody so every artifact reader renders off a single
// implementation: the standalone Artifact Viewer (viewer/ArtifactViewer.tsx), the in-shell Factory
// Outputs reader (components/project/FactoryOutputsPeer.tsx), and the Factory Console preview modal
// (components/factory/Artifacts.tsx → DocViewer). No second Markdown parser or artifact registry —
// Markdown routes through the shared MarkdownBody (markdown.tsx, SOF-17); the kind/extension
// dispatch below is the shared registry.
import { T, Icon } from "../components/onboarding/design";
import { MarkdownBody } from "../markdown";

// The minimal fields the renderer needs. Real callers pass a superset (ArtifactViewer's
// ArtifactDetail, the Outputs peer's selection, the DocViewer's doc) — structural typing keeps
// them all on this one path without a wrapper.
export type ArtifactBodyData = {
  kind: string;
  path: string;
  content: string | null; // null = binary / too-large / external link / stored-but-gone
  project_id: string;
  title?: string | null;
};

// ── Kind classification (shared registry) ─────────────────────────────────────

export function extOf(path: string): string {
  return path.split(".").pop()?.toLowerCase() || "";
}
export function isMd(kind: string, path: string): boolean {
  return kind === "md" || ["md", "mdx"].includes(extOf(path));
}
export function isSvg(kind: string, path: string): boolean {
  return kind === "svg" || extOf(path) === "svg";
}
export function isImage(kind: string, path: string): boolean {
  return kind === "image" || ["png", "jpg", "jpeg", "gif", "webp"].includes(extOf(path));
}
export function isCode(kind: string, path: string): boolean {
  return ["code", "json", "csv", "repo"].includes(kind) || ["js", "ts", "tsx", "jsx", "py", "json", "csv", "sh", "yml", "yaml", "txt"].includes(extOf(path));
}
export function isHtml(kind: string, path: string): boolean {
  return kind === "mockup" || extOf(path) === "html";
}

export function kindLabel(kind: string, path: string): string {
  const ext = extOf(path);
  const MAP: Record<string, string> = { deploy: "Deploy", repo: "Repo", "demo-creds": "Creds",
    context: "Context", md: "Markdown", svg: "SVG", code: "Code",
    json: "JSON", csv: "CSV", image: "Image", fig: "Design", mockup: "Mockup", "flow-map": "Flow Map",
    "decision-log": "Decision Log", link: "Link" };
  return MAP[kind] || MAP[ext] || kind || "File";
}

export function badgeTone(kind: string): { bg: string; color: string } {
  if (kind === "deploy" || kind === "repo") return { bg: T.successSoft, color: T.success };
  if (kind === "md") return { bg: T.brandSoft, color: T.brandDeep };
  return { bg: T.sunken, color: T.secondary };
}

export function fmtDate(epoch?: number): string {
  if (!epoch) return "—";
  return new Date(epoch * 1000).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
}

// ── The renderer ───────────────────────────────────────────────────────────────

export function ArtifactBody({ data }: { data: ArtifactBodyData }) {
  const { kind, path, content } = data;

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
    const src = path.startsWith("http") ? path : `/api/projects/${data.project_id}/artifact?path=${encodeURIComponent(path)}`;
    return (
      <div style={{ flex: 1, overflow: "auto", display: "grid", placeItems: "center", padding: 24 }}>
        <img src={src} alt={data.title || path} style={{ maxWidth: "100%", borderRadius: T.rMd, boxShadow: T.shadowMd }} />
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
      <iframe title={data.title || path} srcDoc={content} sandbox=""
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
