// design.tsx — Tenexity design system tokens, data, icons, and primitives for the
// Software Factory onboarding. Faithful 1:1 port of the design's shared.jsx
// (brand #1A7BFF, Hanken Grotesk / Georgia / JetBrains Mono, single-bubble conversation).
// JSX→TSX: window globals replaced with ES module exports; props typed; styles kept verbatim.
import React from "react";
import { Spinner } from "../skeleton";
// SOF-11: T used to be a byte-for-byte duplicate of admin/tokens.ts; both now share one source.
import { T } from "../../theme";
import { api } from "../../api";
// SOF-17: the full block-level renderer (headings/tables/code/blockquotes/lists), shared with
// the standalone ArtifactViewer so the two never drift.
import { MarkdownBody } from "../../markdown";
export { T };

type CSS = React.CSSProperties;

// ---------- icons (lucide-style, 24-grid stroke) ----------
const PATHS: Record<string, string> = {
  upload: "M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4 M17 8l-5-5-5 5 M12 3v12",
  check: "M20 6L9 17l-5-5",
  plus: "M12 5v14 M5 12h14",
  arrowRight: "M5 12h14 M12 5l7 7-7 7",
  arrowLeft: "M19 12H5 M12 19l-7-7 7-7",
  x: "M18 6L6 18 M6 6l12 12",
  mic: "M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z M19 10v2a7 7 0 0 1-14 0v-2 M12 19v4",
  paperclip: "M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48",
  chevronRight: "M9 18l6-6-6-6",
  chevronDown: "M6 9l6 6 6-6",
  dots: "M12 13a1 1 0 1 0 0-2 1 1 0 0 0 0 2z M19 13a1 1 0 1 0 0-2 1 1 0 0 0 0 2z M5 13a1 1 0 1 0 0-2 1 1 0 0 0 0 2z",
  play: "M5 3l14 9-14 9V3z",
  pause: "M6 4h4v16H6z M14 4h4v16h-4z",
  link: "M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71 M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71",
  video: "M23 7l-7 5 7 5V7z M14 5H3a2 2 0 0 0-2 2v10a2 2 0 0 0 2 2h11a2 2 0 0 0 2-2V7a2 2 0 0 0-2-2z",
  file: "M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z M14 2v6h6",
  building: "M3 21h18 M5 21V7l8-4v18 M19 21V11l-6-3",
  layers: "M12 2L2 7l10 5 10-5-10-5z M2 17l10 5 10-5 M2 12l10 5 10-5",
  bot: "M12 8V4H8 M4 8h16a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2v-8a2 2 0 0 1 2-2z M2 14h2 M20 14h2 M15 13v2 M9 13v2",
  search: "M11 19a8 8 0 1 0 0-16 8 8 0 0 0 0 16z M21 21l-4.35-4.35",
  send: "M22 2L11 13 M22 2l-7 20-4-9-9-4 20-7z",
  // factory-console additions
  kanban: "M5 3h4v18H5z M15 3h4v10h-4z",
  tree: "M5 3a2 2 0 1 0 0 4 2 2 0 0 0 0-4z M19 17a2 2 0 1 0 0 4 2 2 0 0 0 0-4z M19 7a2 2 0 1 0 0 4 2 2 0 0 0 0-4z M5 7v10 M5 12h9a3 3 0 0 0 3-3V9 M5 17h9a3 3 0 0 1 3 3v-1",
  map: "M12 2a7 7 0 0 0-7 7c0 5 7 13 7 13s7-8 7-13a7 7 0 0 0-7-7z M12 11a2 2 0 1 0 0-4 2 2 0 0 0 0 4z",
  refresh: "M23 4v6h-6 M1 20v-6h6 M3.51 9a9 9 0 0 1 14.85-3.36L23 10 M1 14l4.64 4.36A9 9 0 0 0 20.49 15",
  external: "M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6 M15 3h6v6 M10 14L21 3",
  github: "M9 19c-5 1.5-5-2.5-7-3m14 6v-3.87a3.37 3.37 0 0 0-.94-2.61c3.14-.35 6.44-1.54 6.44-7A5.44 5.44 0 0 0 20 4.77 5.07 5.07 0 0 0 19.91 1S18.73.65 16 2.48a13.38 13.38 0 0 0-7 0C6.27.65 5.09 1 5.09 1A5.07 5.07 0 0 0 5 4.77a5.44 5.44 0 0 0-1.5 3.78c0 5.42 3.3 6.61 6.44 7A3.37 3.37 0 0 0 9 18.13V22",
  lock: "M5 11h14a2 2 0 0 1 2 2v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-7a2 2 0 0 1 2-2z M7 11V7a5 5 0 0 1 10 0v4",
  flask: "M9 2v6l-5 9a2 2 0 0 0 2 3h12a2 2 0 0 0 2-3l-5-9V2 M7 2h10 M6.5 14h11",
  database: "M12 2c4.42 0 8 1.34 8 3s-3.58 3-8 3-8-1.34-8-3 3.58-3 8-3z M4 5v6c0 1.66 3.58 3 8 3s8-1.34 8-3V5 M4 11v6c0 1.66 3.58 3 8 3s8-1.34 8-3v-6",
  zap: "M13 2L3 14h9l-1 8 10-12h-9l1-8z",
  pencil: "M12 20h9 M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z",
};

export function Icon({ name, size = 16, color = "currentColor", strokeWidth = 2, style }:
  { name: string; size?: number; color?: string; strokeWidth?: number; style?: CSS }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color}
      strokeWidth={strokeWidth} strokeLinecap="round" strokeLinejoin="round" style={{ flexShrink: 0, ...style }}>
      {PATHS[name].split(" M").map((seg, i) => <path key={i} d={i === 0 ? seg : "M" + seg} />)}
    </svg>
  );
}

export function Sparkle({ size = 11, color = "currentColor", style }:
  { size?: number; color?: string; style?: CSS }) {
  return (
    <svg width={size} height={size} viewBox="0 0 12 12" fill={color} aria-hidden="true" style={{ flexShrink: 0, ...style }}>
      <path d="M6 0 L7 5 L12 6 L7 7 L6 12 L5 7 L0 6 L5 5 Z" />
    </svg>
  );
}

// ---------- data (aligned to tenexity catalog domain) ----------
export type Industry = { id: string; label: string; hint: string };
export const INDUSTRIES: Industry[] = [
  { id: "eng", label: "Engineering & Design", hint: "Design firms, consultancies" },
  { id: "mfg", label: "Parts Manufacturing", hint: "Machined & fabricated parts" },
  { id: "dist", label: "Industrial Distribution", hint: "MRO, multi-line distributors" },
  { id: "pipe", label: "Pipe, Valves & Fittings", hint: "PVF, flanges, couplings" },
  { id: "elec", label: "Electrical Supply", hint: "Components, wholesale" },
  { id: "fab", label: "Fabrication & Machining", hint: "Job shops, CNC" },
  { id: "ithw", label: "IT Hardware Distribution", hint: "Networking, devices, VARs" },
  { id: "whse", label: "Wholesale & Supply Chain", hint: "Logistics, 3PL" },
];
export const SIZES = ["1–10", "11–50", "51–200", "201–1,000", "1,000+"];
export const REVENUE = ["< $1M", "$1M–$10M", "$10M–$50M", "$50M–$250M", "$250M+"];
export const ROLES = ["Owner / Exec", "Operations", "Engineering", "IT / Systems", "Sales / Procurement"];
export type IntegrationItem = { id: string; label: string; kind: string };
export const INTEGRATIONS: IntegrationItem[] = [
  { id: "epicor", label: "Epicor", kind: "ERP" },
  { id: "sap", label: "SAP", kind: "ERP" },
  { id: "netsuite", label: "NetSuite", kind: "ERP" },
  { id: "qb", label: "QuickBooks", kind: "Accounting" },
  { id: "sf", label: "Salesforce", kind: "CRM" },
  { id: "site", label: "Existing website", kind: "Web" },
];

// ---------- primitives ----------
export function CategoryLabel({ children, tone = "tertiary", style }:
  { children: React.ReactNode; tone?: "brand" | "tertiary"; style?: CSS }) {
  return <span style={{ font: `500 11px/1 ${T.sans}`, letterSpacing: "0.12em", textTransform: "uppercase",
    color: tone === "brand" ? T.brand : T.tertiary, display: "inline-block", ...style }}>{children}</span>;
}

export function SectionDivider({ label, sub, icon }:
  { label: string; sub?: string; icon?: string }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 12, margin: "6px 0 2px" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, flexShrink: 0 }}>
        {icon && <span style={{ width: 22, height: 22, borderRadius: 6, display: "grid", placeItems: "center", background: T.sunken, border: `1px solid ${T.borderSubtle}`, color: T.secondary }}>
          <Icon name={icon} size={13} color={T.secondary} /></span>}
        <CategoryLabel style={{ color: T.fg }}>{label}</CategoryLabel>
        {sub && <span style={{ font: `400 12px/1 ${T.sans}`, color: T.tertiary }}>{sub}</span>}
      </div>
      <span style={{ flex: 1, height: 1, background: T.borderSubtle }} />
    </div>
  );
}

export function Btn({ children, variant = "secondary", size = "md", onClick, disabled, style, full, title }:
  { children: React.ReactNode; variant?: "primary" | "secondary" | "ghost" | "danger";
    size?: "sm" | "md" | "lg"; onClick?: () => void; disabled?: boolean; style?: CSS;
    full?: boolean; title?: string }) {
  const sizes = { sm: { h: 32, px: 10, fs: 13 }, md: { h: 36, px: 12, fs: 13 }, lg: { h: 40, px: 16, fs: 14 } }[size];
  const variants = {
    primary: { background: T.brand, color: "#fff", border: "1px solid transparent" },
    secondary: { background: T.raised, color: T.fg, border: `1px solid ${T.borderDefault}` },
    ghost: { background: "transparent", color: T.secondary, border: "1px solid transparent" },
    danger: { background: T.danger, color: "#fff", border: "1px solid transparent" },
  }[variant];
  return (
    <button onClick={disabled ? undefined : onClick} title={title} data-variant={variant} disabled={disabled}
      style={{ height: sizes.h, padding: `0 ${sizes.px}px`, font: `500 ${sizes.fs}px/1 ${T.sans}`, borderRadius: T.rMd,
        cursor: disabled ? "not-allowed" : "pointer", opacity: disabled ? 0.5 : 1, transition: "background .18s, border-color .18s, color .18s",
        display: "inline-flex", alignItems: "center", justifyContent: "center", gap: 6, whiteSpace: "nowrap", width: full ? "100%" : "auto",
        ...variants, ...style }}>
      {children}
    </button>
  );
}

// Dictation (SOF-14's DictateButton) is wired into every text field here, matching the design's
// shared.jsx TextInput/TextArea ("Shared across every text field") — previously only the
// Concierge Composer had it, leaving the rest of the onboarding form silent.
export function TextInput({ value, onChange, placeholder, type = "text", style, mono, onKeyDown, size = "md", noMic }:
  { value?: string; onChange?: (v: string) => void; placeholder?: string; type?: string; style?: CSS;
    mono?: boolean; onKeyDown?: React.KeyboardEventHandler; size?: "sm" | "md"; noMic?: boolean }) {
  const h = size === "sm" ? 32 : 36;
  const showMic = !noMic && MIC_SUPPORTED && type !== "password";
  const input = (
    <input type={type} value={value || ""} onChange={(e) => onChange && onChange(e.target.value)} placeholder={placeholder} onKeyDown={onKeyDown}
      style={{ width: "100%", boxSizing: "border-box", height: h, padding: "0 10px", borderRadius: T.rMd,
        border: `1px solid ${T.borderDefault}`, background: T.bg, color: T.fg,
        font: `400 13px/1 ${mono ? T.mono : T.sans}`, outline: "none", ...style, ...(showMic ? { paddingRight: h - 4 } : null) }} />
  );
  if (!showMic) return input;
  return (
    <div style={{ position: "relative", width: "100%" }}>
      {input}
      <span style={{ position: "absolute", right: 2, top: 0, height: h, display: "flex", alignItems: "center" }}>
        <DictateButton value={value} onChange={onChange} />
      </span>
    </div>
  );
}

export function TextArea({ value, onChange, placeholder, rows = 4, style, onKeyDown, noMic }:
  { value?: string; onChange?: (v: string) => void; placeholder?: string; rows?: number; style?: CSS;
    onKeyDown?: React.KeyboardEventHandler; noMic?: boolean }) {
  const showMic = !noMic && MIC_SUPPORTED;
  const ta = (
    <textarea value={value || ""} onChange={(e) => onChange && onChange(e.target.value)} placeholder={placeholder} rows={rows} onKeyDown={onKeyDown}
      style={{ width: "100%", boxSizing: "border-box", padding: "10px 12px", borderRadius: T.rMd, resize: "none",
        border: `1px solid ${T.borderDefault}`, background: T.bg, color: T.fg,
        font: `400 13px/1.55 ${T.sans}`, outline: "none", ...style, ...(showMic ? { paddingRight: 38 } : null) }} />
  );
  if (!showMic) return ta;
  return (
    <div style={{ position: "relative", width: "100%" }}>
      {ta}
      <span style={{ position: "absolute", right: 6, top: 7 }}>
        <DictateButton value={value} onChange={onChange} />
      </span>
    </div>
  );
}

export function Field({ label, optional, hint, children, style }:
  { label?: string; optional?: boolean; hint?: string; children: React.ReactNode; style?: CSS }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 6, ...style }}>
      {(label || optional) && (
        <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", gap: 8 }}>
          {label && <label style={{ font: `500 13px/1.2 ${T.sans}`, color: T.fg }}>{label}</label>}
          {optional && <CategoryLabel style={{ fontSize: 10 }}>Optional</CategoryLabel>}
        </div>
      )}
      {children}
      {hint && <p style={{ margin: 0, font: `400 12px/1.4 ${T.sans}`, color: T.tertiary }}>{hint}</p>}
    </div>
  );
}

export function Chip({ children, selected, onClick }:
  { children: React.ReactNode; selected?: boolean; onClick?: () => void }) {
  return (
    <button onClick={onClick} style={{ font: `500 13px/1 ${T.sans}`, padding: "8px 13px", borderRadius: 9999, cursor: "pointer",
      border: `1px solid ${selected ? T.brand : T.borderSubtle}`, background: selected ? T.brandSoft : T.sunken,
      color: selected ? T.brandDeep : T.secondary, transition: "all .12s" }}>{children}</button>
  );
}

export function Chips({ options, value, onChange, multi }:
  { options: string[]; value?: string | string[]; onChange?: (v: any) => void; multi?: boolean }) {
  const isOn = (o: string) => multi ? ((value as string[]) || []).includes(o) : value === o;
  const toggle = (o: string) => {
    if (!onChange) return;
    if (multi) { const s = (value as string[]) || []; onChange(isOn(o) ? s.filter((x) => x !== o) : [...s, o]); }
    else onChange(o);
  };
  return <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>{options.map((o) => <Chip key={o} selected={isOn(o)} onClick={() => toggle(o)}>{o}</Chip>)}</div>;
}

// Pill-track segmented control (two-option toggle). Options may be disabled — a disabled option
// renders greyed with a "SOON" tag and is not selectable (used to gate not-yet-wired backend paths).
export function Segmented({ value, onChange, options }:
  { value: string; onChange?: (v: string) => void;
    options: { id: string; label: string; disabled?: boolean }[] }) {
  return (
    <div style={{ display: "inline-flex", padding: 3, gap: 2, background: T.sunken, borderRadius: 9999, border: `1px solid ${T.borderSubtle}` }}>
      {options.map((o) => {
        const on = value === o.id;
        return (
          <button key={o.id} disabled={o.disabled} onClick={() => !o.disabled && onChange && onChange(o.id)}
            style={{ font: `500 12.5px/1 ${T.sans}`, padding: "7px 13px", borderRadius: 9999,
              cursor: o.disabled ? "not-allowed" : "pointer", border: "none",
              background: on ? T.raised : "transparent", color: on ? T.fg : o.disabled ? T.tertiary : T.secondary,
              opacity: o.disabled ? 0.55 : 1, display: "inline-flex", alignItems: "center", gap: 5,
              boxShadow: on ? T.shadowXs : "none" }}>
            {o.label}
            {o.disabled && <span style={{ font: `700 8px/1 ${T.mono}`, color: T.tertiary, background: T.raised, padding: "2px 4px", borderRadius: 3 }}>SOON</span>}
          </button>
        );
      })}
    </div>
  );
}

export function IndustryTile({ item, selected, onClick, compact }:
  { item: Industry; selected?: boolean; onClick?: () => void; compact?: boolean }) {
  return (
    <button onClick={onClick} style={{ textAlign: "left", cursor: "pointer", background: selected ? T.brandSoft : T.raised,
      border: `1px solid ${selected ? T.brand : T.borderDefault}`, borderRadius: T.rLg, padding: compact ? "11px 13px" : "14px 15px",
      transition: "all .12s", display: "flex", flexDirection: "column", gap: 4, boxShadow: selected ? "none" : T.shadowXs }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <Icon name="building" size={15} color={selected ? T.brandDeep : T.tertiary} />
        <span style={{ font: `600 ${compact ? 13 : 14}px/1.2 ${T.sans}`, color: selected ? T.brandDeep : T.fg }}>{item.label}</span>
      </div>
      {!compact && <span style={{ font: `400 12px/1.3 ${T.sans}`, color: T.tertiary, paddingLeft: 23 }}>{item.hint}</span>}
    </button>
  );
}

// SOF-49: real per-file ingestion progress (T3.2's SSE stream), once the transport upload
// itself finishes. `ingestStage`/`ingestPct` absent (or `ingestStatus` "ready"/undefined) falls
// back to today's plain "Uploaded" checkmark — SF_MEMORY off, or the event just hasn't arrived
// yet, both degrade to the exact prior behavior, never a stuck/broken-looking row.
export const INGEST_STAGE_LABEL: Record<string, string> = {
  parsing: "Parsing", chunking: "Chunking", embedding: "Embedding", summarizing: "Summarizing",
};

export function Dropzone({ kind, filled, onToggle, compact, files = [] }:
  { kind: "video" | "docs"; filled?: boolean; onToggle?: () => void; compact?: boolean;
    files?: { name: string; size?: string; uploading?: boolean; ingestStage?: string;
      ingestPct?: number; ingestStatus?: "running" | "ready" | "failed" }[] }) {
  const isVideo = kind === "video";
  // The list reflects what the user ACTUALLY uploaded (passed in by the caller) — no dummy data.
  const has = files.length > 0 || !!filled;
  const reduceMotion = typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
      <button onClick={onToggle} style={{ width: "100%", boxSizing: "border-box", cursor: "pointer",
        display: "flex", alignItems: "center", justifyContent: "center", gap: 12, textAlign: "center",
        border: `2px dashed ${has ? T.brand : T.borderDefault}`, borderRadius: T.rLg,
        background: has ? T.brandSoft : T.sunken, padding: compact ? "10px 14px" : "22px 16px", transition: "all .14s" }}>
        <Icon name={isVideo ? "video" : "upload"} size={20} color={has ? T.brand : T.tertiary} />
        <div style={{ display: "flex", flexDirection: "column", alignItems: "center" }}>
          <span style={{ font: `500 14px/1.3 ${T.sans}`, color: T.fg }}>
            {has ? (isVideo ? "Replace recording" : "Add more files") : (isVideo ? "Record or drop a process walkthrough" : "Drag files here or click to browse")}
          </span>
          <span style={{ marginTop: 2, font: `400 12px/1.3 ${T.sans}`, color: T.tertiary }}>
            {isVideo ? "screen recording · mp4, mov — up to 500 MB" : "SOPs, price lists, specs — pdf, xlsx, docx up to 25 MB"}
          </span>
        </div>
      </button>
      {files.length > 0 && (
        <div style={{ border: `1px solid ${T.borderSubtle}`, borderRadius: T.rLg, background: T.raised, overflow: "hidden" }}>
          {files.map((f, i, arr) => (
            <div key={f.name + i} style={{ display: "flex", alignItems: "center", gap: 12, padding: "9px 12px", borderBottom: i < arr.length - 1 ? `1px solid ${T.borderSubtle}` : "none" }}>
              <span style={{ display: "grid", placeItems: "center", width: 30, height: 30, borderRadius: 6, border: `1px solid ${T.borderSubtle}`, background: T.sunken }}>
                <Icon name={isVideo ? "video" : "file"} size={14} color={T.tertiary} />
              </span>
              <span style={{ flex: 1, minWidth: 0, font: `500 13px/1.2 ${T.sans}`, color: T.fg, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{f.name}</span>
              {f.size && !f.uploading && <span style={{ font: `400 12px/1 ${T.mono}`, color: T.tertiary }}>{f.size}</span>}
              {f.uploading ? (
                <span style={{ display: "inline-flex", alignItems: "center", gap: 4, font: `400 12px/1 ${T.sans}`, color: T.tertiary }}>
                  {!reduceMotion && <Spinner size={13} color={T.tertiary} />}Uploading…
                </span>
              ) : f.ingestStatus === "failed" ? (
                <span style={{ display: "inline-flex", alignItems: "center", gap: 4, font: `400 12px/1 ${T.sans}`, color: T.danger }}>
                  <Icon name="x" size={13} color={T.danger} /> Processing failed
                </span>
              ) : f.ingestStatus === "running" ? (
                <span style={{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: 3, minWidth: 90 }}>
                  <span style={{ font: `400 11px/1 ${T.mono}`, color: T.tertiary }}>
                    {INGEST_STAGE_LABEL[f.ingestStage || ""] || "Processing"}{typeof f.ingestPct === "number" ? ` · ${f.ingestPct}%` : ""}
                  </span>
                  <span style={{ width: 70, height: 3, borderRadius: 2, background: T.sunken, overflow: "hidden" }}>
                    <span style={{ display: "block", height: "100%", width: `${f.ingestPct ?? 0}%`, background: T.brand, transition: "width .3s ease" }} />
                  </span>
                </span>
              ) : (
                <span style={{ display: "inline-flex", alignItems: "center", gap: 4, font: `400 12px/1 ${T.sans}`, color: T.success }}>
                  <Icon name="check" size={13} color={T.success} /> Uploaded
                </span>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export function IntegrationRow({ item, connected, onToggle }:
  { item: IntegrationItem; connected?: boolean; onToggle?: () => void }) {
  return (
    <button onClick={onToggle} style={{ width: "100%", boxSizing: "border-box", display: "flex", alignItems: "center", gap: 12, cursor: "pointer",
      padding: "10px 13px", borderRadius: T.rMd, border: `1px solid ${connected ? T.brand : T.borderDefault}`,
      background: connected ? T.brandSoft : T.raised, transition: "all .12s", textAlign: "left" }}>
      <span style={{ width: 30, height: 30, borderRadius: 7, flexShrink: 0, display: "grid", placeItems: "center",
        background: connected ? T.brand : T.sunken, color: connected ? "#fff" : T.secondary, font: `700 11px/1 ${T.mono}` }}>
        {item.label.slice(0, 2).toUpperCase()}
      </span>
      <span style={{ flex: 1 }}>
        <span style={{ display: "block", font: `600 13px/1.2 ${T.sans}`, color: T.fg }}>{item.label}</span>
        <CategoryLabel style={{ fontSize: 10, marginTop: 2 }}>{item.kind}</CategoryLabel>
      </span>
      <span style={{ display: "inline-flex", alignItems: "center", gap: 5, font: `500 12px/1 ${T.sans}`, color: connected ? T.success : T.brandDeep }}>
        {connected ? <><Icon name="check" size={13} color={T.success} /> Linked</> : <><Icon name="link" size={13} color={T.brandDeep} /> Link</>}
      </span>
    </button>
  );
}

export function StatusPill({ tone = "neutral", children, dot = true }:
  { tone?: "neutral" | "success" | "warning" | "danger" | "info" | "brand"; children: React.ReactNode; dot?: boolean }) {
  const tones = {
    neutral: [T.sunken, T.secondary], success: [T.successSoft, T.success], warning: [T.warningSoft, T.warning],
    danger: [T.dangerSoft, T.danger], info: [T.brandSoft, T.brandDeep], brand: [T.brandSoft, T.brandDeep],
  }[tone];
  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: 6, padding: "3px 9px", borderRadius: 9999,
      font: `500 11px/1.3 ${T.sans}`, background: tones[0], color: tones[1] }}>
      {dot && <span style={{ width: 6, height: 6, borderRadius: "50%", background: "currentColor" }} />}{children}
    </span>
  );
}

// ConfidencePill — the confidence cascade (exact→high→med→low→none) rendered as a soft pill.
// Matches the design's signature: band + optional numeric score (shared.jsx ConfidencePill).
export function ConfidencePill({ band, score }:
  { band: "exact" | "high" | "med" | "low" | "none"; score?: number }) {
  const map = {
    exact: [T.cExactSoft, T.cExact, "exact"], high: [T.cHighSoft, T.cHigh, "high"],
    med: [T.cMedSoft, T.cMed, "medium"], low: [T.cLowSoft, T.cLow, "low"], none: [T.cNoneSoft, T.cNone, "—"],
  }[band];
  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: 5, padding: "2px 8px", borderRadius: 9999,
      font: `500 11px/1.3 ${T.sans}`, background: map[0] as string, color: map[1] as string }}>
      <span style={{ width: 6, height: 6, borderRadius: "50%", background: "currentColor" }} />
      {map[2]}{score != null ? ` ${score}` : ""}
    </span>
  );
}

export function Avatar({ name, size = 28, tone }:
  { name: string; size?: number; tone?: "neutral" | "brand" | "success" | "warning" }) {
  const tones: Record<string, [string, string]> = {
    neutral: [T.sunken, T.secondary], brand: [T.brandSoft, T.brandDeep], success: [T.successSoft, T.success], warning: [T.warningSoft, T.warning],
  };
  const order = ["neutral", "brand", "success", "warning"];
  let h = 0; for (let i = 0; i < name.length; i++) h = (h * 31 + name.charCodeAt(i)) >>> 0;
  const t = tones[tone || order[h % 4]];
  const parts = name.trim().split(/\s+/);
  const init = parts.length === 1 ? parts[0].slice(0, 2).toUpperCase() : (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
  return <span title={name} style={{ width: size, height: size, borderRadius: "50%", display: "inline-grid", placeItems: "center",
    background: t[0], color: t[1], font: `600 ${Math.round(size * 0.38)}px/1 ${T.sans}`, flexShrink: 0 }}>{init}</span>;
}

// Conversation item — ONE bubble shape, identified by avatar+name, never alignment.
export function Message({ who, persona, text, anim, badge }:
  { who: "agent" | "user"; persona?: string; text: string; anim?: boolean; badge?: string }) {
  const isAgent = who === "agent";
  return (
    <article style={{ display: "flex", gap: 10, animation: anim ? "sfRise .35s var(--ease-out, ease) both" : "none" }}>
      {isAgent ? (
        <span style={{ marginTop: 1, width: 28, height: 28, flexShrink: 0, borderRadius: "50%", display: "grid", placeItems: "center",
          background: T.brandSoft, color: T.brand, boxShadow: `inset 0 0 0 1px ${T.brand}33` }}><Sparkle size={13} color={T.brand} /></span>
      ) : <Avatar name="You" size={28} />}
      <div style={{ flex: 1, minWidth: 0, display: "flex", flexDirection: "column", gap: 6,
        border: `1px solid ${isAgent ? T.brand + "33" : T.borderSubtle}`, background: isAgent ? T.brandSoft + "4d" : T.raised,
        borderRadius: T.rLg, padding: "10px 13px" }}>
        <header style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <span style={{ font: `600 13px/1 ${T.sans}`, color: T.fg }}>{isAgent ? (persona || "Concierge") : "You"}</span>
          {isAgent && <span style={{ font: `500 10px/1 ${T.sans}`, letterSpacing: "0.08em", textTransform: "uppercase",
            background: T.brandSoft, color: T.brandDeep, padding: "3px 6px", borderRadius: 4 }}>{badge || "Concierge"}</span>}
        </header>
        <p style={{ margin: 0, font: `400 13.5px/1.5 ${T.sans}`, color: isAgent ? T.secondary : T.fg }}>{text}</p>
      </div>
    </article>
  );
}

// Reads a recorded Blob as base64 (no "data:...;base64," prefix — the backend wants raw bytes).
function blobToBase64(blob: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onloadend = () => resolve(((reader.result as string) || "").split(",")[1] || "");
    reader.onerror = reject;
    reader.readAsDataURL(blob);
  });
}

// Dictate (SOF-14): mic -> MediaRecorder -> POST /api/transcribe (OpenRouter Whisper Large v3,
// server-side key) -> transcript appends to the draft. No dead click: hidden where getUserMedia
// isn't available; a denied/failed permission just cancels back to idle, no crash.
const MIC_SUPPORTED = typeof navigator !== "undefined" && !!navigator.mediaDevices?.getUserMedia;

export function DictateButton({ value, onChange, disabled }:
  { value?: string; onChange?: (v: string) => void; disabled?: boolean }) {
  const [recording, setRecording] = React.useState(false);
  const [transcribing, setTranscribing] = React.useState(false);
  const recorderRef = React.useRef<MediaRecorder | null>(null);
  const chunksRef = React.useRef<Blob[]>([]);

  if (!MIC_SUPPORTED) return null;

  const startRecording = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mimeType = typeof MediaRecorder.isTypeSupported === "function" && MediaRecorder.isTypeSupported("audio/webm")
        ? "audio/webm" : "";
      const recorder = mimeType ? new MediaRecorder(stream, { mimeType }) : new MediaRecorder(stream);
      chunksRef.current = [];
      recorder.ondataavailable = (e) => { if (e.data.size) chunksRef.current.push(e.data); };
      recorder.onstop = async () => {
        stream.getTracks().forEach((t) => t.stop());
        const blob = new Blob(chunksRef.current, { type: recorder.mimeType || "audio/webm" });
        const format = (recorder.mimeType || "audio/webm").split("/")[1]?.split(";")[0] || "webm";
        setTranscribing(true);
        try {
          const b64 = await blobToBase64(blob);
          const { text } = await api.transcribe(b64, format);
          if (text && onChange) onChange(value ? `${value} ${text}` : text);
        } catch {
          // transcription failed (network/upstream) — draft is untouched, user can retype or retry
        }
        setTranscribing(false);
      };
      recorderRef.current = recorder;
      recorder.start();
      setRecording(true);
    } catch {
      setRecording(false);   // permission denied / no device — stay idle, no crash
    }
  };

  const stopRecording = () => {
    recorderRef.current?.stop();
    setRecording(false);
  };

  if (transcribing) {
    return (
      <span title="Transcribing…" style={{ width: 30, height: 30, display: "grid", placeItems: "center" }}>
        <Spinner size={15} color={T.tertiary} />
      </span>
    );
  }

  return (
    <button title={recording ? "Stop dictating" : "Dictate"} disabled={disabled}
      onClick={recording ? stopRecording : startRecording}
      style={{ width: 30, height: 30, display: "grid", placeItems: "center", borderRadius: T.rMd, border: "none",
        background: recording ? T.dangerSoft : "transparent", color: recording ? T.danger : T.tertiary, cursor: "pointer",
        animation: recording ? "sfPulse 1.4s ease-in-out infinite" : "none" }}>
      <Icon name="mic" size={15} />
    </button>
  );
}

export function Composer({ placeholder = "Reply…", onSend, value, onChange, loading }:
  { placeholder?: string; onSend?: () => void; value?: string; onChange?: (v: string) => void; loading?: boolean }) {
  return (
    <div style={{ display: "flex", alignItems: "flex-end", gap: 8, border: `1px solid ${T.borderDefault}`, borderRadius: T.rLg, background: T.raised, padding: 8, opacity: loading ? 0.75 : 1 }}>
      <textarea value={value || ""} onChange={(e) => !loading && onChange && onChange(e.target.value)} placeholder={loading ? "Working…" : placeholder} rows={1}
        readOnly={loading}
        onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); !loading && onSend && onSend(); } }}
        style={{ flex: 1, minWidth: 0, resize: "none", border: "none", outline: "none", background: "transparent", padding: "6px", font: `400 13px/1.4 ${T.sans}`, color: T.fg }} />
      <DictateButton value={value} onChange={onChange} disabled={loading} />
      <Btn variant="primary" size="sm" onClick={loading ? undefined : onSend} disabled={loading} style={{ height: 30 }}>{loading ? "Working…" : <><Icon name="send" size={13} color="#fff" /> Send</>}</Btn>
    </div>
  );
}

// Up-to-4 single-select answers for a Concierge question. Clicking a choice submits it as the
// user's reply (via onPick). Disabled once answered / while a turn is in flight.
//
// SOF-40: this is the OLD `{message, choices, done}` contract's renderer — kept as-is, still the
// live call site's shape until the backend swap to ConciergeTurn/suggested_responses lands (see
// SuggestedResponseList below, which is the NEW contract's renderer, built standalone and not
// yet wired into OnboardingScreen.tsx pending that swap).
export function ChoiceList({ options, onPick, disabled }:
  { options: string[]; onPick: (o: string) => void; disabled?: boolean }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
      {options.slice(0, 4).map((o) => (
        <button key={o} onClick={() => { if (!disabled) onPick(o); }} disabled={disabled}
          style={{ display: "flex", alignItems: "center", gap: 10, width: "100%", boxSizing: "border-box", textAlign: "left",
            cursor: disabled ? "default" : "pointer", padding: "9px 11px", borderRadius: T.rMd, font: `500 13px/1.3 ${T.sans}`,
            border: `1px solid ${T.borderDefault}`, background: T.raised, color: T.fg, opacity: disabled ? 0.55 : 1, transition: "all .12s" }}>
          <span style={{ width: 16, height: 16, flexShrink: 0, borderRadius: "50%", border: `1.5px solid ${T.borderDefault}` }} />
          <span style={{ flex: 1 }}>{o}</span>
        </button>
      ))}
    </div>
  );
}

export type SuggestedResponseOption = { response: string; type: "single select" | "multi select" };

// SOF-40: renders a ConciergeTurn's `suggested_responses` — the NEW contract. A turn's list is
// treated as one homogeneous "question" (rendered by the FIRST item's `type`); the schema allows
// a per-item type, but mixing radio-submits-immediately with checkbox-then-confirm within one
// list has no coherent UI, so a single turn is expected to use one mode throughout. `onSubmit`
// always receives an array — one item for a single-select click, the ticked set (in list order)
// for multi-select's Confirm. No 4-item cap here (unlike the old ChoiceList) — the new contract's
// spec doesn't state one; flag if product wants one added.
export function SuggestedResponseList({ options, onSubmit, disabled }:
  { options: SuggestedResponseOption[]; onSubmit: (values: string[]) => void; disabled?: boolean }) {
  const isMulti = options[0]?.type === "multi select";
  const [picked, setPicked] = React.useState<Set<string>>(new Set());

  if (!options.length) return null;

  if (!isMulti) {
    return (
      <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
        {options.map((o) => (
          <button key={o.response} onClick={() => { if (!disabled) onSubmit([o.response]); }} disabled={disabled}
            style={{ display: "flex", alignItems: "center", gap: 10, width: "100%", boxSizing: "border-box", textAlign: "left",
              cursor: disabled ? "default" : "pointer", padding: "9px 11px", borderRadius: T.rMd, font: `500 13px/1.3 ${T.sans}`,
              border: `1px solid ${T.borderDefault}`, background: T.raised, color: T.fg, opacity: disabled ? 0.55 : 1, transition: "all .12s" }}>
            <span style={{ width: 16, height: 16, flexShrink: 0, borderRadius: "50%", border: `1.5px solid ${T.borderDefault}` }} />
            <span style={{ flex: 1 }}>{o.response}</span>
          </button>
        ))}
      </div>
    );
  }

  const toggle = (response: string) => setPicked((prev) => {
    const next = new Set(prev);
    if (next.has(response)) next.delete(response); else next.add(response);
    return next;
  });

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
      {options.map((o) => {
        const checked = picked.has(o.response);
        return (
          <button key={o.response} onClick={() => { if (!disabled) toggle(o.response); }} disabled={disabled}
            style={{ display: "flex", alignItems: "center", gap: 10, width: "100%", boxSizing: "border-box", textAlign: "left",
              cursor: disabled ? "default" : "pointer", padding: "9px 11px", borderRadius: T.rMd, font: `500 13px/1.3 ${T.sans}`,
              border: `1px solid ${checked ? T.brand : T.borderDefault}`, background: T.raised, color: T.fg,
              opacity: disabled ? 0.55 : 1, transition: "all .12s" }}>
            <span style={{ width: 16, height: 16, flexShrink: 0, borderRadius: 4, border: `1.5px solid ${checked ? T.brand : T.borderDefault}`,
              background: checked ? T.brand : "transparent", display: "grid", placeItems: "center" }}>
              {checked && <Icon name="check" size={11} color="#fff" />}
            </span>
            <span style={{ flex: 1 }}>{o.response}</span>
          </button>
        );
      })}
      <Btn variant="primary" size="sm" disabled={disabled || picked.size === 0}
        onClick={() => onSubmit(options.filter((o) => picked.has(o.response)).map((o) => o.response))}>
        Confirm
      </Btn>
    </div>
  );
}

export function OrgImportPicker({ docs = [] }:
  { docs?: { id: string; name: string }[] }) {
  const [open, setOpen] = React.useState(false);
  const [picks, setPicks] = React.useState<string[]>([]);
  if (!docs.length) return null;
  const toggle = (id: string) => setPicks((p) => p.includes(id) ? p.filter((x) => x !== id) : [...p, id]);
  return (
    <div style={{ border: `1px solid ${T.borderDefault}`, borderRadius: T.rLg, overflow: "hidden", background: T.raised }}>
      <button onClick={() => setOpen((o) => !o)}
        style={{ width: "100%", display: "flex", alignItems: "center", gap: 10, padding: "11px 14px", background: "transparent", border: "none", cursor: "pointer", textAlign: "left" }}>
        <Icon name="building" size={15} color={T.secondary} />
        <span style={{ flex: 1, font: `500 13px/1.2 ${T.sans}`, color: T.fg }}>Import from organization</span>
        <CategoryLabel style={{ marginRight: 4 }}>{picks.length ? `${picks.length} selected` : `${docs.length} available`}</CategoryLabel>
        <Icon name={open ? "chevronDown" : "chevronRight"} size={14} color={T.tertiary} />
      </button>
      {open && (
        <div style={{ borderTop: `1px solid ${T.borderSubtle}` }}>
          {docs.map((d) => {
            const on = picks.includes(d.id);
            return (
              <button key={d.id} onClick={() => toggle(d.id)}
                style={{ width: "100%", display: "flex", alignItems: "center", gap: 10, padding: "9px 14px",
                  background: on ? T.brandSoft : "transparent", border: "none", borderBottom: `1px solid ${T.borderSubtle}`, cursor: "pointer", textAlign: "left" }}>
                <span style={{ width: 16, height: 16, flexShrink: 0, borderRadius: 4, display: "grid", placeItems: "center",
                  background: on ? T.brand : "transparent", border: `1.5px solid ${on ? T.brand : T.borderDefault}` }}>
                  {on && <Icon name="check" size={10} color="#fff" />}
                </span>
                <Icon name="file" size={14} color={T.tertiary} />
                <span style={{ flex: 1, minWidth: 0, font: `500 13px/1.2 ${T.sans}`, color: T.fg, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{d.name}</span>
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}

// ---------- inline markdown ----------
// Lightweight renderer for short free-text fields (e.g. the project summary/description shown on the
// dashboard card). Renders **bold**, *italic* / _italic_, `code`, [links](url), and "- " / "1." lists.
// With no markdown tokens it renders the text verbatim, so plain prose is unaffected. This is a
// faithful TSX port of the design's shared.jsx `Markdown`, plus an `inline` mode used by the dashboard
// snippet: it flattens to ONE line (block markers stripped per line, newlines → spaces) inside a
// <span>, so a parent with nowrap+ellipsis still truncates cleanly and no raw `**`/`- ` ever shows.
// Distinct from the heavier full-document MarkdownBody/MarkdownPreview (artifact/SOW renderers).
const MD_INLINE_RE = /(\*\*[^*]+\*\*|\*[^*]+\*|_[^_]+_|`[^`]+`|\[[^\]]+\]\([^)]+\))/g;

export function looksLikeMarkdown(s: unknown): boolean {
  // SOF-17: a brief made ONLY of headings/a table/a blockquote (no bold/list mixed in) must
  // still be detected — otherwise it falls through to the plain-text fallback below and none
  // of it renders as markdown at all.
  return typeof s === "string" &&
    /(\*\*[^*]+\*\*|\*[^*]+\*|_[^_]+_|`[^`]+`|\[[^\]]+\]\([^)]+\)|^\s*[-*]\s+|^\s*\d+[.)]\s+|^\s{0,3}#{1,6}\s+|^\s*>\s?|^```|^\s*\|.*\|\s*$)/m.test(s);
}

function renderInlineMd(text: string, key: string): React.ReactNode[] {
  const out: React.ReactNode[] = [];
  text.split(MD_INLINE_RE).forEach((tok, n) => {
    if (!tok) return;
    const k = `${key}-${n}`;
    if (/^\*\*[^*]+\*\*$/.test(tok)) out.push(<strong key={k} style={{ fontWeight: 600, color: T.fg }}>{tok.slice(2, -2)}</strong>);
    else if (/^\*[^*]+\*$/.test(tok)) out.push(<em key={k}>{tok.slice(1, -1)}</em>);
    else if (/^_[^_]+_$/.test(tok)) out.push(<em key={k}>{tok.slice(1, -1)}</em>);
    else if (/^`[^`]+`$/.test(tok)) out.push(<code key={k} style={{ font: `400 0.92em/1.4 ${T.mono}`, background: T.sunken, border: `1px solid ${T.borderSubtle}`, borderRadius: 4, padding: "1px 5px" }}>{tok.slice(1, -1)}</code>);
    else {
      const m = tok.match(/^\[([^\]]+)\]\(([^)]+)\)$/);
      if (m) out.push(<a key={k} href={m[2]} style={{ color: T.brandDeep, textDecoration: "underline" }}>{m[1]}</a>);
      else out.push(<React.Fragment key={k}>{tok}</React.Fragment>);
    }
  });
  return out;
}

export function Markdown({ children, style, inline }:
  { children?: string; style?: CSS; inline?: boolean }) {
  const text = typeof children === "string" ? children : "";
  // Inline (single-line) mode: strip per-line block markers, collapse to one line, render emphasis
  // only — inside a <span> so a parent's nowrap+ellipsis truncation still applies.
  if (inline) {
    const flat = text
      .replace(/^[ \t]*(?:#{1,6}\s+|[-*+]\s+|\d+[.)]\s+)/gm, "")
      .replace(/\s*\n+\s*/g, " ")
      .trim();
    return <span style={style}>{renderInlineMd(flat, "i")}</span>;
  }
  if (!looksLikeMarkdown(text)) return <p style={{ margin: 0, ...style }}>{text}</p>;
  // SOF-17: full block-level rendering (headings, GFM tables, fenced code, blockquotes,
  // ordered/unordered lists, hr) — the same engine as the standalone ArtifactViewer, so the
  // project brief and the artifact viewer never drift apart.
  return <div style={style}><MarkdownBody content={text} /></div>;
}

export function Wordmark({ size = 19 }: { size?: number }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 9 }}>
      <span style={{ width: 24, height: 24, borderRadius: 6, background: T.brand, display: "grid", placeItems: "center", flexShrink: 0 }}>
        <Icon name="layers" size={14} color="#fff" strokeWidth={2.2} />
      </span>
      <span style={{ font: `700 ${size}px/1 ${T.display}`, letterSpacing: "-0.015em", color: T.fg }}>Software Factory</span>
    </div>
  );
}
