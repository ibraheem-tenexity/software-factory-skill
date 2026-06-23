// design.tsx — Tenexity design system tokens, data, icons, and primitives for the
// Software Factory onboarding. Faithful 1:1 port of the design's shared.jsx
// (brand #1A7BFF, Hanken Grotesk / Georgia / JetBrains Mono, single-bubble conversation).
// JSX→TSX: window globals replaced with ES module exports; props typed; styles kept verbatim.
import React from "react";

export const T = {
  bg: "#FAFAFA", raised: "#FFFFFF", sunken: "#F4F4F5", ink: "#060709",
  fg: "#18181B", secondary: "#52525B", tertiary: "#8A8A92",
  borderSubtle: "#E7E7E9", borderDefault: "#D4D4D8",
  brand: "#1A7BFF", brandSoft: "#E8F1FF", brandDeep: "#0958C9",
  success: "#059669", successSoft: "#E4F8EF",
  warning: "#D97706", warningSoft: "#FBEFDC",
  danger: "#DC2626", dangerSoft: "#FBE3E3",
  // confidence cascade
  cExact: "#059669", cExactSoft: "#E4F8EF",
  cHigh: "#11A0B8", cHighSoft: "#E0F4F7",
  cMed: "#F2A516", cMedSoft: "#FBEFDC",
  cLow: "#DC2626", cLowSoft: "#FBE3E3",
  cNone: "#8A8A92", cNoneSoft: "#EDEDEF",
  // The design names Hanken Grotesk / Georgia / JetBrains Mono; system fallbacks keep it
  // legible offline (no CDN <link> — CSP/offline). Bundling the real woff2 is a follow-up.
  sans: "'Hanken Grotesk', ui-sans-serif, system-ui, -apple-system, sans-serif",
  display: "Georgia, 'Times New Roman', serif",
  mono: "'JetBrains Mono', ui-monospace, 'SF Mono', Menlo, monospace",
  rSm: "6px", rMd: "8px", rLg: "12px", rXl: "16px",
  shadowXs: "0 1px 2px 0 hsl(240 6% 10% / 0.04)",
  shadowSm: "0 2px 6px -2px hsl(240 6% 10% / 0.06), 0 1px 2px hsl(240 6% 10% / 0.04)",
  shadowMd: "0 8px 24px -8px hsl(240 6% 10% / 0.10), 0 2px 6px -2px hsl(240 6% 10% / 0.06)",
};

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

export function TextInput({ value, onChange, placeholder, type = "text", style, mono, onKeyDown, size = "md" }:
  { value?: string; onChange?: (v: string) => void; placeholder?: string; type?: string; style?: CSS;
    mono?: boolean; onKeyDown?: React.KeyboardEventHandler; size?: "sm" | "md" }) {
  const h = size === "sm" ? 32 : 36;
  return (
    <input type={type} value={value || ""} onChange={(e) => onChange && onChange(e.target.value)} placeholder={placeholder} onKeyDown={onKeyDown}
      style={{ width: "100%", boxSizing: "border-box", height: h, padding: "0 10px", borderRadius: T.rMd,
        border: `1px solid ${T.borderDefault}`, background: T.bg, color: T.fg,
        font: `400 13px/1 ${mono ? T.mono : T.sans}`, outline: "none", ...style }} />
  );
}

export function TextArea({ value, onChange, placeholder, rows = 4, style, onKeyDown }:
  { value?: string; onChange?: (v: string) => void; placeholder?: string; rows?: number; style?: CSS;
    onKeyDown?: React.KeyboardEventHandler }) {
  return (
    <textarea value={value || ""} onChange={(e) => onChange && onChange(e.target.value)} placeholder={placeholder} rows={rows} onKeyDown={onKeyDown}
      style={{ width: "100%", boxSizing: "border-box", padding: "10px 12px", borderRadius: T.rMd, resize: "none",
        border: `1px solid ${T.borderDefault}`, background: T.bg, color: T.fg,
        font: `400 13px/1.55 ${T.sans}`, outline: "none", ...style }} />
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

export function Dropzone({ kind, filled, onToggle, compact, files = [] }:
  { kind: "video" | "docs"; filled?: boolean; onToggle?: () => void; compact?: boolean;
    files?: { name: string; size?: string }[] }) {
  const isVideo = kind === "video";
  // The list reflects what the user ACTUALLY uploaded (passed in by the caller) — no dummy data.
  const has = files.length > 0 || !!filled;
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
              {f.size && <span style={{ font: `400 12px/1 ${T.mono}`, color: T.tertiary }}>{f.size}</span>}
              <span style={{ display: "inline-flex", alignItems: "center", gap: 4, font: `400 12px/1 ${T.sans}`, color: T.success }}>
                <Icon name="check" size={13} color={T.success} /> Uploaded
              </span>
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

export function Composer({ placeholder = "Reply…", onSend, value, onChange }:
  { placeholder?: string; onSend?: () => void; value?: string; onChange?: (v: string) => void }) {
  return (
    <div style={{ display: "flex", alignItems: "flex-end", gap: 8, border: `1px solid ${T.borderDefault}`, borderRadius: T.rLg, background: T.raised, padding: 8 }}>
      <textarea value={value || ""} onChange={(e) => onChange && onChange(e.target.value)} placeholder={placeholder} rows={1}
        onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); onSend && onSend(); } }}
        style={{ flex: 1, minWidth: 0, resize: "none", border: "none", outline: "none", background: "transparent", padding: "6px", font: `400 13px/1.4 ${T.sans}`, color: T.fg }} />
      <button title="Dictate" style={{ width: 30, height: 30, display: "grid", placeItems: "center", borderRadius: T.rMd, border: "none", background: "transparent", color: T.tertiary, cursor: "pointer" }}><Icon name="mic" size={15} /></button>
      <Btn variant="primary" size="sm" onClick={onSend} style={{ height: 30 }}><Icon name="send" size={13} color="#fff" /> Send</Btn>
    </div>
  );
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
