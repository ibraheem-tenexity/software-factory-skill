import React from "react";
import { T } from "./tokens";

const PATHS: Record<string, string> = {
  upload: "M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4 M17 8l-5-5-5 5 M12 3v12",
  check: "M20 6L9 17l-5-5",
  plus: "M12 5v14 M5 12h14",
  arrowRight: "M5 12h14 M12 5l7 7-7 7",
  arrowLeft: "M19 12H5 M12 19l-7-7 7-7",
  x: "M18 6L6 18 M6 6l12 12",
  mic: "M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z M19 10v2a7 7 0 0 1-14 0v-2 M12 19v4",
  paperclip:
    "M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48",
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
  settings:
    "M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6z M19.4 15a1.6 1.6 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.6 1.6 0 0 0-2.7 1.1V21a2 2 0 1 1-4 0v-.1A1.6 1.6 0 0 0 6.6 19l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.6 1.6 0 0 0-1.1-2.7H2a2 2 0 1 1 0-4h.1A1.6 1.6 0 0 0 3.2 6.6l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.6 1.6 0 0 0 2.7-1.1V2a2 2 0 1 1 4 0v.1a1.6 1.6 0 0 0 2.7 1.1l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.6 1.6 0 0 0-.3 1.8",
};

export function Icon({
  name,
  size = 16,
  color = "currentColor",
  strokeWidth = 2,
  style,
}: {
  name: keyof typeof PATHS;
  size?: number;
  color?: string;
  strokeWidth?: number;
  style?: React.CSSProperties;
}) {
  const p = PATHS[name] || "";
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke={color}
      strokeWidth={strokeWidth}
      strokeLinecap="round"
      strokeLinejoin="round"
      style={{ flexShrink: 0, ...style }}
    >
      {p.split(" M").map((seg, i) => (
        <path key={i} d={i === 0 ? seg : `M${seg}`} />
      ))}
    </svg>
  );
}

export function Sparkle({ size = 11, color = "currentColor", style }: { size?: number; color?: string; style?: React.CSSProperties }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 12 12"
      fill={color}
      aria-hidden="true"
      style={{ flexShrink: 0, ...style }}
    >
      <path d="M6 0 L7 5 L12 6 L7 7 L6 12 L5 7 L0 6 L5 5 Z" />
    </svg>
  );
}

export function CategoryLabel({ children, tone = "tertiary", style }: { children: React.ReactNode; tone?: "tertiary" | "brand"; style?: React.CSSProperties }) {
  return (
    <span
      style={{
        font: `500 11px/1 ${T.sans}`,
        letterSpacing: "0.12em",
        textTransform: "uppercase",
        color: tone === "brand" ? T.brand : T.tertiary,
        display: "inline-block",
        ...style,
      }}
    >
      {children}
    </span>
  );
}

export function Btn({
  children,
  variant = "secondary",
  size = "md",
  onClick,
  disabled,
  style,
  title,
}: {
  children: React.ReactNode;
  variant?: "primary" | "secondary" | "ghost" | "danger";
  size?: "sm" | "md" | "lg";
  onClick?: () => void;
  disabled?: boolean;
  style?: React.CSSProperties;
  title?: string;
}) {
  const sizes = {
    sm: { h: 32, px: 10, fs: 13 },
    md: { h: 36, px: 12, fs: 13 },
    lg: { h: 40, px: 16, fs: 14 },
  }[size];
  const variants = {
    primary: { background: T.brand, color: "#fff", border: "1px solid transparent" },
    secondary: { background: T.raised, color: T.fg, border: `1px solid ${T.borderDefault}` },
    ghost: { background: "transparent", color: T.secondary, border: "1px solid transparent" },
    danger: { background: T.danger, color: "#fff", border: "1px solid transparent" },
  }[variant];
  return (
    <button
      onClick={disabled ? undefined : onClick}
      title={title}
      data-variant={variant}
      disabled={disabled}
      style={{
        height: sizes.h,
        padding: `0 ${sizes.px}px`,
        font: `500 ${sizes.fs}px/1 ${T.sans}`,
        borderRadius: T.rMd,
        cursor: disabled ? "not-allowed" : "pointer",
        opacity: disabled ? 0.5 : 1,
        transition: "background .18s, border-color .18s, color .18s",
        display: "inline-flex",
        alignItems: "center",
        justifyContent: "center",
        gap: 6,
        whiteSpace: "nowrap",
        width: "auto",
        ...variants,
        ...style,
      }}
    >
      {children}
    </button>
  );
}

export function TextInput({
  value,
  onChange,
  placeholder,
  type = "text",
  style,
  mono,
  onKeyDown,
  size = "md",
  disabled,
}: {
  value?: string;
  onChange?: (value: string) => void;
  placeholder?: string;
  type?: string;
  style?: React.CSSProperties;
  mono?: boolean;
  onKeyDown?: (e: React.KeyboardEvent) => void;
  size?: "sm" | "md";
  disabled?: boolean;
}) {
  const h = size === "sm" ? 32 : 36;
  return (
    <input
      type={type}
      value={value || ""}
      disabled={disabled}
      onChange={(e) => onChange?.(e.target.value)}
      placeholder={placeholder}
      onKeyDown={onKeyDown}
      style={{
        width: "100%",
        boxSizing: "border-box",
        height: h,
        padding: "0 10px",
        borderRadius: T.rMd,
        border: `1px solid ${T.borderDefault}`,
        background: T.bg,
        color: T.fg,
        font: `400 13px/1 ${mono ? T.mono : T.sans}`,
        outline: "none",
        opacity: disabled ? 0.6 : 1,
        ...style,
      }}
    />
  );
}

export function Field({
  label,
  optional,
  hint,
  children,
  style,
}: {
  label?: string;
  optional?: boolean;
  hint?: string;
  children: React.ReactNode;
  style?: React.CSSProperties;
}) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 6, ...style }}>
      {(label || optional) && (
        <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", gap: 8 }}>
          {label && (
            <label style={{ font: `500 13px/1.2 ${T.sans}`, color: T.fg }}>{label}</label>
          )}
          {optional && <CategoryLabel style={{ fontSize: 10 }}>Optional</CategoryLabel>}
        </div>
      )}
      {children}
      {hint && (
        <p style={{ margin: 0, font: `400 12px/1.4 ${T.sans}`, color: T.tertiary }}>{hint}</p>
      )}
    </div>
  );
}

export function StatusPill({
  tone = "neutral",
  children,
  dot = true,
}: {
  tone?: "neutral" | "success" | "warning" | "danger" | "info" | "brand";
  children: React.ReactNode;
  dot?: boolean;
}) {
  const tones: Record<string, [string, string]> = {
    neutral: [T.sunken, T.secondary],
    success: [T.successSoft, T.success],
    warning: [T.warningSoft, T.warning],
    danger: [T.dangerSoft, T.danger],
    info: [T.brandSoft, T.brandDeep],
    brand: [T.brandSoft, T.brandDeep],
  };
  const [bg, color] = tones[tone];
  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 6,
        padding: "3px 9px",
        borderRadius: 9999,
        font: `500 11px/1.3 ${T.sans}`,
        background: bg,
        color: color,
      }}
    >
      {dot && <span style={{ width: 6, height: 6, borderRadius: "50%", background: "currentColor" }} />}
      {children}
    </span>
  );
}

export function MetricCard({
  label,
  value,
  hint,
  accent,
}: {
  label: string;
  value: React.ReactNode;
  hint: string;
  accent?: boolean;
}) {
  return (
    <div
      style={{
        border: `1px solid ${accent ? `${T.brand}33` : T.borderSubtle}`,
        borderRadius: T.rLg,
        background: accent ? `${T.brandSoft}40` : T.raised,
        padding: "14px 16px",
        boxShadow: T.shadowXs,
      }}
    >
      <CategoryLabel style={{ fontSize: 10 }}>{label}</CategoryLabel>
      <div
        style={{
          font: `400 22px/1.1 ${T.display}`,
          letterSpacing: "-0.01em",
          color: accent ? T.brandDeep : T.fg,
          marginTop: 6,
        }}
      >
        {value}
      </div>
      <div style={{ font: `400 11px/1.3 ${T.mono}`, color: T.tertiary, marginTop: 4 }}>{hint}</div>
    </div>
  );
}
