// markdown.tsx — the shared full block-level Markdown renderer (SOF-17). Extracted from
// viewer/ArtifactViewer.tsx's MarkdownBody, which onboarding/design.tsx's `Markdown` (non-inline
// mode) now also delegates to, so the ArtifactViewer and the project brief render off one engine
// (no drift). Extended while extracting: the original only handled h1-h3, fenced code, hr, and
// unordered lists — it did NOT actually support GFM tables, blockquotes, h4-h6, ordered lists, or
// inline links, despite SOF-17 requiring all of those. No external markdown dep; kept dependency-free
// on purpose (matches the original's own design constraint).
import React, { useMemo } from "react";
import { T } from "./theme";

export type TocEntry = { level: number; text: string; id: string };

export function slugify(text: string): string {
  return text.toLowerCase().replace(/[^\w\s-]/g, "").replace(/\s+/g, "-");
}

// Top-level TOC entries only (h1-h3) — deeper headings would make a page TOC noisy.
export function extractToc(md: string): TocEntry[] {
  return md.split("\n").flatMap((line) => {
    const m = line.match(/^(#{1,3})\s+(.+)/);
    if (!m) return [];
    return [{ level: m[1].length, text: m[2].trim(), id: slugify(m[2].trim()) }];
  });
}

function inlineRender(text: string): React.ReactNode {
  const parts = text.split(/(\*\*[^*]+\*\*|`[^`]+`|_[^_]+_|\[[^\]]+\]\([^)]+\))/g);
  return parts.map((p, pi) => {
    if (p.startsWith("**") && p.endsWith("**")) return <strong key={pi}>{p.slice(2, -2)}</strong>;
    if (p.startsWith("`") && p.endsWith("`")) return <code key={pi} style={{ font: `500 12px/1 ${T.mono}`, background: T.sunken, padding: "1px 4px", borderRadius: 3 }}>{p.slice(1, -1)}</code>;
    if (p.startsWith("_") && p.endsWith("_")) return <em key={pi}>{p.slice(1, -1)}</em>;
    const link = p.match(/^\[([^\]]+)\]\(([^)]+)\)$/);
    if (link) return <a key={pi} href={link[2]} target="_blank" rel="noreferrer" style={{ color: T.brandDeep, textDecoration: "underline" }}>{link[1]}</a>;
    return p;
  });
}

// A GFM table's separator row: |---|:--:|--:| etc. — dashes with optional leading/trailing colons.
const TABLE_SEP_RE = /^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$/;

function splitRow(line: string): string[] {
  let l = line.trim();
  if (l.startsWith("|")) l = l.slice(1);
  if (l.endsWith("|")) l = l.slice(0, -1);
  return l.split("|").map((c) => c.trim());
}

// showToc: the "On this page" sidebar only makes sense for a full-document viewer (ArtifactViewer);
// it defaults off so an embedded block (e.g. the project brief's GOAL field) doesn't grow a
// two-column layout for a few paragraphs.
export function MarkdownBody({ content, showToc = false }: { content: string; showToc?: boolean }) {
  const toc = useMemo(() => extractToc(content), [content]);
  const lines = content.split("\n");
  const blocks: React.ReactNode[] = [];
  let i = 0;
  let key = 0;

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

    // Heading (h1-h6)
    const hm = line.match(/^(#{1,6})\s+(.+)/);
    if (hm) {
      const level = hm[1].length;
      const text = hm[2].trim();
      const id = slugify(text);
      const sizes = ["", "22px", "18px", "15px", "14px", "13px", "12.5px"];
      const weights = ["", "700", "600", "600", "600", "600", "600"];
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

    // GFM table: a "| … |" header row immediately followed by a "|---|---|" separator row.
    if (line.includes("|") && lines[i + 1] !== undefined && TABLE_SEP_RE.test(lines[i + 1])) {
      const header = splitRow(line);
      i += 2;
      const rows: string[][] = [];
      while (i < lines.length && lines[i].includes("|") && lines[i].trim()) { rows.push(splitRow(lines[i])); i++; }
      blocks.push(
        <div key={key++} style={{ margin: "10px 0", overflowX: "auto" }}>
          <table style={{ borderCollapse: "collapse", width: "100%", font: `400 13px/1.5 ${T.sans}` }}>
            <thead>
              <tr>{header.map((h, hi) => <th key={hi} style={{ textAlign: "left", padding: "6px 10px", borderBottom: `2px solid ${T.borderDefault}`, font: `600 12.5px/1.3 ${T.sans}`, color: T.fg }}>{inlineRender(h)}</th>)}</tr>
            </thead>
            <tbody>
              {rows.map((r, ri) => (
                <tr key={ri}>{r.map((c, ci) => <td key={ci} style={{ padding: "6px 10px", borderBottom: `1px solid ${T.borderSubtle}`, color: T.secondary, verticalAlign: "top" }}>{inlineRender(c)}</td>)}</tr>
              ))}
            </tbody>
          </table>
        </div>
      );
      continue;
    }

    // Blockquote
    if (/^\s*>\s?/.test(line)) {
      const quoteLines: string[] = [];
      while (i < lines.length && /^\s*>\s?/.test(lines[i])) { quoteLines.push(lines[i].replace(/^\s*>\s?/, "")); i++; }
      blocks.push(
        <blockquote key={key++} style={{ margin: "10px 0", padding: "2px 14px", borderLeft: `3px solid ${T.borderDefault}`, color: T.secondary, font: `400 13.5px/1.6 ${T.sans}` }}>
          {inlineRender(quoteLines.join(" "))}
        </blockquote>
      );
      continue;
    }

    // Ordered list
    if (/^\s*\d+[.)]\s+/.test(line)) {
      const items: string[] = [];
      while (i < lines.length && /^\s*\d+[.)]\s+/.test(lines[i])) { items.push(lines[i].replace(/^\s*\d+[.)]\s+/, "")); i++; }
      blocks.push(
        <ol key={key++} style={{ margin: "8px 0", paddingLeft: 20, display: "flex", flexDirection: "column", gap: 4 }}>
          {items.map((it, ii) => <li key={ii} style={{ font: `400 13.5px/1.5 ${T.sans}`, color: T.fg }}>{inlineRender(it)}</li>)}
        </ol>
      );
      continue;
    }

    // Unordered list
    if (/^\s*[-*]\s/.test(line)) {
      const items: string[] = [];
      while (i < lines.length && /^\s*[-*]\s/.test(lines[i])) { items.push(lines[i].replace(/^\s*[-*]\s/, "")); i++; }
      blocks.push(
        <ul key={key++} style={{ margin: "8px 0", paddingLeft: 20, display: "flex", flexDirection: "column", gap: 4 }}>
          {items.map((it, ii) => <li key={ii} style={{ font: `400 13.5px/1.5 ${T.sans}`, color: T.fg }}>{inlineRender(it)}</li>)}
        </ul>
      );
      continue;
    }

    // Blank line
    if (!line.trim()) { i++; continue; }

    // Paragraph — collect until the next recognized block type.
    const para: string[] = [];
    while (i < lines.length && lines[i].trim()
      && !lines[i].startsWith("#") && !lines[i].startsWith("```")
      && !/^\s*[-*]\s/.test(lines[i]) && !/^\s*\d+[.)]\s+/.test(lines[i])
      && !/^\s*>\s?/.test(lines[i]) && !/^[-*_]{3,}$/.test(lines[i].trim())
      && !(lines[i].includes("|") && lines[i + 1] !== undefined && TABLE_SEP_RE.test(lines[i + 1]))) {
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

  if (!showToc) return <div style={{ minHeight: 0 }}>{blocks}</div>;

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
