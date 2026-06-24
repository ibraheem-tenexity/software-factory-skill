import React from "react";
import { T } from "./tokens";
import { AdminBtn, ColHead, Mono } from "./views";
import { Icon, StatusPill } from "./primitives";
import { api } from "../api";
import type { AdminSow } from "../api";

const SOW_STATUSES = ["Template", "Draft", "In review", "Sent", "Signed"];

const TEMPLATE_BODY = `# Statement of Work

## Project Overview

[Describe the engagement: who, what, and why.]

## Scope of Work

[List the specific work to be performed.]

## Deliverables

-
-

## Timeline

| Milestone | Date |
|-----------|------|
| Kickoff   |      |
| Delivery  |      |

## Commercial Terms

**Total Value:** $0

Payment terms: Net 30.

## Acceptance Criteria

[Describe what constitutes successful completion.]
`;

function statusTone(status: string): "success" | "warning" | "neutral" | "danger" {
  if (status === "Signed") return "success";
  if (status === "Sent") return "neutral";
  if (status === "In review") return "neutral";
  if (status === "Draft") return "warning";
  return "neutral";
}

// ── Inline markdown preview (admin-token flavour) ─────────────────────────────

function inlineRender(text: string): React.ReactNode {
  const parts = text.split(/(\*\*[^*]+\*\*|`[^`]+`|_[^_]+_)/g);
  return parts.map((p, i) => {
    if (p.startsWith("**") && p.endsWith("**")) return <strong key={i}>{p.slice(2, -2)}</strong>;
    if (p.startsWith("`") && p.endsWith("`")) return <code key={i} style={{ font: `500 12px/1 ${T.mono}`, background: T.sunken, padding: "1px 4px", borderRadius: 3 }}>{p.slice(1, -1)}</code>;
    if (p.startsWith("_") && p.endsWith("_")) return <em key={i}>{p.slice(1, -1)}</em>;
    return p;
  });
}

function MarkdownPreview({ content }: { content: string }) {
  const lines = content.split("\n");
  const blocks: React.ReactNode[] = [];
  let i = 0;
  let key = 0;

  while (i < lines.length) {
    const line = lines[i];

    if (line.startsWith("```")) {
      const lang = line.slice(3).trim();
      const codeLines: string[] = [];
      i++;
      while (i < lines.length && !lines[i].startsWith("```")) { codeLines.push(lines[i]); i++; }
      blocks.push(
        <pre key={key++} style={{ margin: "12px 0", padding: "10px 12px", borderRadius: T.rMd, background: T.sunken, overflowX: "auto", font: `400 12px/1.6 ${T.mono}`, color: T.fg }}>
          {lang && <span style={{ display: "block", font: `600 9.5px/1 ${T.mono}`, color: T.tertiary, marginBottom: 6, letterSpacing: "0.08em", textTransform: "uppercase" }}>{lang}</span>}
          {codeLines.join("\n")}
        </pre>
      );
      i++; continue;
    }

    const hm = line.match(/^(#{1,3})\s+(.+)/);
    if (hm) {
      const level = hm[1].length;
      const sizes = ["", "18px", "15px", "13px"];
      const weights = ["", "700", "600", "600"];
      blocks.push(
        <div key={key++} style={{ margin: `${level === 1 ? 20 : 14}px 0 6px`, font: `${weights[level]} ${sizes[level]}/1.3 ${T.display}`, color: T.fg }}>
          {inlineRender(hm[2].trim())}
        </div>
      );
      i++; continue;
    }

    if (/^[-*_]{3,}$/.test(line.trim())) {
      blocks.push(<hr key={key++} style={{ margin: "14px 0", border: "none", borderTop: `1px solid ${T.borderSubtle}` }} />);
      i++; continue;
    }

    if (/^\|.+\|/.test(line)) {
      const rows: string[][] = [];
      while (i < lines.length && /^\|/.test(lines[i])) {
        const cells = lines[i].split("|").slice(1, -1).map(c => c.trim());
        if (!cells.every(c => /^[-:]+$/.test(c))) rows.push(cells);
        i++;
      }
      blocks.push(
        <div key={key++} style={{ margin: "10px 0", overflowX: "auto" }}>
          <table style={{ borderCollapse: "collapse", width: "100%", font: `400 12.5px/1.5 ${T.sans}` }}>
            {rows.map((row, ri) => (
              <tr key={ri} style={{ borderBottom: `1px solid ${T.borderSubtle}` }}>
                {row.map((cell, ci) => (
                  ri === 0
                    ? <th key={ci} style={{ padding: "5px 10px", textAlign: "left", font: `600 11px/1 ${T.mono}`, letterSpacing: "0.04em", color: T.tertiary, background: T.sunken }}>{cell}</th>
                    : <td key={ci} style={{ padding: "5px 10px", color: T.secondary }}>{inlineRender(cell)}</td>
                ))}
              </tr>
            ))}
          </table>
        </div>
      );
      continue;
    }

    if (/^[-*]\s/.test(line)) {
      const items: string[] = [];
      while (i < lines.length && /^[-*]\s/.test(lines[i])) { items.push(lines[i].replace(/^[-*]\s/, "")); i++; }
      blocks.push(
        <ul key={key++} style={{ margin: "6px 0", paddingLeft: 18, display: "flex", flexDirection: "column", gap: 3 }}>
          {items.map((it, ii) => <li key={ii} style={{ font: `400 13px/1.5 ${T.sans}`, color: T.fg }}>{inlineRender(it)}</li>)}
        </ul>
      );
      continue;
    }

    if (!line.trim()) { i++; continue; }

    const para: string[] = [];
    while (i < lines.length && lines[i].trim() && !lines[i].startsWith("#") && !lines[i].startsWith("```") && !/^[-*]\s/.test(lines[i]) && !/^[-*_]{3,}$/.test(lines[i].trim()) && !/^\|/.test(lines[i])) {
      para.push(lines[i]); i++;
    }
    if (para.length) {
      blocks.push(<p key={key++} style={{ margin: "6px 0", font: `400 13px/1.6 ${T.sans}`, color: T.secondary }}>{inlineRender(para.join(" "))}</p>);
    } else { i++; }
  }

  return <div>{blocks}</div>;
}

// ── MetaField ─────────────────────────────────────────────────────────────────

function MetaField({ label, value, onChange, placeholder }: { label: string; value: string; onChange: (v: string) => void; placeholder?: string }) {
  return (
    <div>
      <label style={{ display: "block", font: `500 11.5px/1 ${T.sans}`, color: T.tertiary, marginBottom: 4 }}>{label}</label>
      <input
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        style={{ width: "100%", boxSizing: "border-box", height: 32, padding: "0 9px", borderRadius: T.rMd, border: `1px solid ${T.borderDefault}`, background: T.raised, font: `400 12.5px/1 ${T.sans}`, color: T.fg, outline: "none" }}
      />
    </div>
  );
}

// ── SowManagement ─────────────────────────────────────────────────────────────

export function SowManagement() {
  const [sows, setSows] = React.useState<AdminSow[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [selected, setSelected] = React.useState<AdminSow | null>(null);
  const [isNew, setIsNew] = React.useState(false);

  // Editor fields
  const [title, setTitle] = React.useState("");
  const [org, setOrg] = React.useState("");
  const [project, setProject] = React.useState("");
  const [value, setValue] = React.useState("");
  const [file, setFile] = React.useState("");
  const [status, setStatus] = React.useState("Draft");
  const [body, setBody] = React.useState("");
  const [mode, setMode] = React.useState<"write" | "split" | "preview">("split");
  const [saving, setSaving] = React.useState(false);
  const [dirty, setDirty] = React.useState(false);

  const loadList = React.useCallback(() => {
    api.adminSowList()
      .then((r) => setSows(r.sows))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  React.useEffect(() => { loadList(); }, [loadList]);

  const populate = (sow: AdminSow) => {
    setTitle(sow.title);
    setOrg(sow.org || "");
    setProject(sow.project || "");
    setValue(sow.value || "");
    setFile(sow.file || "");
    setStatus(sow.status);
    setBody(sow.body || "");
    setDirty(false);
  };

  const selectSow = (sow: AdminSow) => {
    setSelected(sow);
    setIsNew(false);
    populate(sow);
  };

  const startNew = () => {
    setSelected(null);
    setIsNew(true);
    setTitle("New Statement of Work");
    setOrg("");
    setProject("");
    setValue("");
    setFile("");
    setStatus("Draft");
    setBody(TEMPLATE_BODY);
    setDirty(false);
  };

  const save = async () => {
    setSaving(true);
    try {
      const payload = { title: title.trim() || "Untitled", org: org || undefined, project: project || undefined, value: value || undefined, file: file || undefined, status, body };
      if (isNew) {
        const row = await api.adminSowCreate(payload);
        setSows((prev) => [row, ...prev]);
        setSelected(row);
        setIsNew(false);
      } else if (selected) {
        const row = await api.adminSowUpdate(selected.id, payload);
        setSows((prev) => prev.map((s) => s.id === row.id ? row : s));
        setSelected(row);
      }
      setDirty(false);
    } catch {
      alert("Failed to save SOW.");
    } finally {
      setSaving(false);
    }
  };

  const openInViewer = () => {
    if (!selected) return;
    window.open(`/ArtifactViewer.html?sow=${selected.id}`, "_blank");
  };

  const hasEditor = isNew || selected !== null;

  return (
    <div style={{ display: "flex", gap: 0, border: `1px solid ${T.borderSubtle}`, borderRadius: T.rMd, overflow: "hidden", background: T.raised }}>
      {/* Left panel — list */}
      <div
        style={{
          width: 280,
          flexShrink: 0,
          borderRight: `1px solid ${T.borderSubtle}`,
          display: "flex",
          flexDirection: "column",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "14px 16px 10px", borderBottom: `1px solid ${T.borderSubtle}` }}>
          <span style={{ font: `600 13.5px/1 ${T.sans}`, color: T.fg }}>Statements of Work</span>
          <AdminBtn onClick={startNew}>
            <Icon name="plus" size={13} /> New SOW
          </AdminBtn>
        </div>
        <div style={{ maxHeight: 600, overflowY: "auto" }}>
          {loading && <div style={{ padding: "20px 16px" }}><Mono style={{ color: T.tertiary }}>Loading…</Mono></div>}
          {!loading && sows.length === 0 && (
            <div style={{ padding: "32px 16px", textAlign: "center" }}>
              <Mono style={{ fontSize: 12, color: T.tertiary }}>No SOWs yet. Create one to get started.</Mono>
            </div>
          )}
          {sows.map((sow) => {
            const on = selected?.id === sow.id && !isNew;
            return (
              <button
                key={sow.id}
                onClick={() => selectSow(sow)}
                style={{
                  display: "block",
                  width: "100%",
                  textAlign: "left",
                  padding: "11px 16px",
                  border: "none",
                  borderLeft: `2px solid ${on ? T.brand : "transparent"}`,
                  background: on ? T.brandSoft : "transparent",
                  cursor: "pointer",
                  borderBottom: `1px solid ${T.borderSubtle}`,
                }}
              >
                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8, marginBottom: 5 }}>
                  <span style={{ font: `${on ? 600 : 500} 13px/1.2 ${T.sans}`, color: on ? T.brandDeep : T.fg, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", flex: 1 }}>
                    {sow.title}
                  </span>
                  <StatusPill tone={statusTone(sow.status)} dot={sow.status !== "Template"}>{sow.status}</StatusPill>
                </div>
                <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                  {sow.org && <Mono style={{ fontSize: 10.5, color: T.tertiary, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{sow.org}</Mono>}
                  <Mono style={{ fontSize: 10, color: T.tertiary, marginLeft: "auto" }}>v{sow.version}</Mono>
                </div>
              </button>
            );
          })}
        </div>
      </div>

      {/* Right panel — editor */}
      {hasEditor ? (
        <div style={{ flex: 1, minWidth: 0, display: "flex", flexDirection: "column", overflow: "hidden" }}>
          {/* Title row */}
          <div style={{ padding: "14px 22px 12px", borderBottom: `1px solid ${T.borderSubtle}`, flexShrink: 0 }}>
            <input
              value={title}
              onChange={(e) => { setTitle(e.target.value); setDirty(true); }}
              placeholder="SOW title"
              style={{
                width: "100%",
                boxSizing: "border-box",
                border: "none",
                outline: "none",
                background: "transparent",
                font: `600 18px/1.3 ${T.display}`,
                color: T.fg,
                padding: 0,
              }}
            />
          </div>

          {/* Metadata row */}
          <div style={{ padding: "12px 22px", borderBottom: `1px solid ${T.borderSubtle}`, flexShrink: 0, display: "grid", gridTemplateColumns: "repeat(4, 1fr) 140px", gap: 10 }}>
            <MetaField label="Organization" value={org} onChange={(v) => { setOrg(v); setDirty(true); }} placeholder="Acme Corp" />
            <MetaField label="Project" value={project} onChange={(v) => { setProject(v); setDirty(true); }} placeholder="project-id" />
            <MetaField label="Value" value={value} onChange={(v) => { setValue(v); setDirty(true); }} placeholder="$0" />
            <MetaField label="File" value={file} onChange={(v) => { setFile(v); setDirty(true); }} placeholder="sow-v1.pdf" />
            <div>
              <label style={{ display: "block", font: `500 11.5px/1 ${T.sans}`, color: T.tertiary, marginBottom: 4 }}>Status</label>
              <select
                value={status}
                onChange={(e) => { setStatus(e.target.value); setDirty(true); }}
                style={{ width: "100%", height: 32, padding: "0 8px", borderRadius: T.rMd, border: `1px solid ${T.borderDefault}`, background: T.raised, font: `500 12.5px/1 ${T.sans}`, color: T.fg, outline: "none", appearance: "none" }}
              >
                {SOW_STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
              </select>
            </div>
          </div>

          {/* Mode toggle + body */}
          <div style={{ display: "flex", flexDirection: "column" }}>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "8px 22px", borderBottom: `1px solid ${T.borderSubtle}` }}>
              <div style={{ display: "inline-flex", padding: 2, borderRadius: T.rMd, background: T.sunken, border: `1px solid ${T.borderSubtle}` }}>
                {(["write", "split", "preview"] as const).map((m) => (
                  <button
                    key={m}
                    onClick={() => setMode(m)}
                    style={{
                      font: `600 10.5px/1 ${T.mono}`,
                      letterSpacing: "0.05em",
                      padding: "5px 9px",
                      borderRadius: 5,
                      cursor: "pointer",
                      border: "none",
                      background: mode === m ? T.fg : "transparent",
                      color: mode === m ? "#fff" : T.tertiary,
                      textTransform: "uppercase",
                    }}
                  >
                    {m}
                  </button>
                ))}
              </div>
            </div>

            <div style={{ display: "flex", minHeight: 360, height: 420 }}>
              {/* Write pane */}
              {(mode === "write" || mode === "split") && (
                <textarea
                  value={body}
                  onChange={(e) => { setBody(e.target.value); setDirty(true); }}
                  placeholder="Write SOW in Markdown…"
                  style={{
                    flex: 1,
                    minWidth: 0,
                    resize: "none",
                    border: "none",
                    outline: "none",
                    padding: "16px 22px",
                    font: `400 13px/1.7 ${T.mono}`,
                    color: T.fg,
                    background: T.bg,
                    borderRight: mode === "split" ? `1px solid ${T.borderSubtle}` : "none",
                    overflowY: "auto",
                  }}
                />
              )}
              {/* Preview pane */}
              {(mode === "preview" || mode === "split") && (
                <div
                  style={{
                    flex: 1,
                    minWidth: 0,
                    overflowY: "auto",
                    padding: "16px 22px",
                    background: T.raised,
                  }}
                >
                  {body.trim()
                    ? <MarkdownPreview content={body} />
                    : <Mono style={{ color: T.tertiary, fontSize: 12 }}>Nothing to preview yet.</Mono>
                  }
                </div>
              )}
            </div>
          </div>

          {/* Footer */}
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "11px 22px", borderTop: `1px solid ${T.borderSubtle}`, flexShrink: 0 }}>
            <ColHead style={{ color: dirty ? T.warning : T.tertiary }}>
              {isNew ? "Unsaved · new SOW" : dirty ? "Unsaved changes" : selected ? `SOW #${selected.id}` : ""}
            </ColHead>
            <div style={{ display: "flex", gap: 8 }}>
              {!isNew && selected && (
                <AdminBtn onClick={openInViewer}>
                  <Icon name="external" size={13} /> Open in viewer ↗
                </AdminBtn>
              )}
              <AdminBtn primary onClick={save} disabled={saving || (!dirty && !isNew)}>
                {saving ? "Saving…" : "Save"}
              </AdminBtn>
            </div>
          </div>
        </div>
      ) : (
        <div style={{ flex: 1, display: "grid", placeItems: "center" }}>
          <div style={{ textAlign: "center" }}>
            <Mono style={{ fontSize: 12, color: T.tertiary, display: "block", marginBottom: 12 }}>Select a SOW to edit or create a new one.</Mono>
            <AdminBtn primary onClick={startNew}><Icon name="plus" size={13} /> New SOW</AdminBtn>
          </div>
        </div>
      )}
    </div>
  );
}
