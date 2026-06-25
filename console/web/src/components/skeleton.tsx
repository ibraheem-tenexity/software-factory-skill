// skeleton.tsx — Shared loading skeleton primitives.
// Rule: shapes mirror the exact size/layout of real content so nothing pops in.
import React from "react";
import { T } from "./onboarding/design";

// Inject keyframes once per page (idempotent by id).
if (typeof document !== "undefined" && !document.getElementById("sf-skel")) {
  const s = document.createElement("style");
  s.id = "sf-skel";
  s.textContent = "@keyframes sf-pulse{0%,100%{opacity:1}50%{opacity:.45}}@keyframes sf-spin{to{transform:rotate(360deg)}}";
  document.head.appendChild(s);
}

type CSS = React.CSSProperties;
const PULSE: CSS = { animation: "sf-pulse 1.6s ease-in-out infinite" };

// ── Primitives ─────────────────────────────────────────────────────────────────

export function Skel({ w = "100%", h = 12, r, style }: { w?: string | number; h?: number; r?: number | string; style?: CSS }) {
  return <span style={{ display: "block", width: w, height: h, borderRadius: r ?? 4, background: T.borderSubtle, ...PULSE, ...style }} />;
}

export function SkelLine({ w = "70%", h = 12 }: { w?: string | number; h?: number }) {
  return <Skel w={w} h={h} />;
}

export function SkelCircle({ size = 28 }: { size?: number }) {
  return <Skel w={size} h={size} r="50%" />;
}

export function SkelPill({ w = 64, h = 22 }: { w?: number; h?: number }) {
  return <Skel w={w} h={h} r={9999} />;
}

export function Spinner({ size = 16, color }: { size?: number; color?: string }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color || T.tertiary}
      strokeWidth={2} strokeLinecap="round" style={{ animation: "sf-spin 0.8s linear infinite", flexShrink: 0 }}>
      <circle cx="12" cy="12" r="9" strokeOpacity={0.2} />
      <path d="M12 3a9 9 0 0 1 9 9" />
    </svg>
  );
}

// ── Composite skeletons — mirror exact shape/size of real content ───────────────

// Dashboard: 4-column metric strip
export function MetricCardSkel() {
  return (
    <div style={{ background: T.raised, border: `1px solid ${T.borderSubtle}`, borderRadius: T.rLg, padding: "14px 16px", boxShadow: T.shadowXs, display: "flex", flexDirection: "column", gap: 8 }}>
      <Skel w={80} h={10} />
      <Skel w={56} h={26} />
      <Skel w={110} h={10} />
    </div>
  );
}

// Dashboard: project row in the "In progress" / "Deployed" list
export function ProjectRowSkel({ first = false }: { first?: boolean }) {
  return (
    <div style={{ padding: "16px 18px", display: "grid", gridTemplateColumns: "minmax(0,1fr) 132px 150px 96px 28px", alignItems: "center", gap: 16, borderTop: first ? "none" : `1px solid ${T.borderSubtle}`, background: T.raised }}>
      <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
        <Skel w="50%" h={14} />
        <Skel w="30%" h={10} />
      </div>
      <Skel w={80} h={6} r={4} />
      <div style={{ display: "flex", gap: -4 }}>
        <SkelCircle size={20} />
      </div>
      <SkelPill w={60} h={22} />
      <SkelCircle size={28} />
    </div>
  );
}

// OverviewTab: panel body placeholder (used inside each Panel while data loads)
export function PanelBodySkel({ rows = 3 }: { rows?: number }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
      {Array.from({ length: rows }, (_, i) => <Skel key={i} w={i % 2 === 0 ? "80%" : "60%"} h={12} />)}
    </div>
  );
}

// OrgAdminScreen: team member list rows
export function ListRowSkel({ rows = 3 }: { rows?: number }) {
  return (
    <>
      {Array.from({ length: rows }, (_, i) => (
        <div key={i} style={{ display: "flex", alignItems: "center", gap: 12, padding: "10px 0", borderTop: i === 0 ? "none" : `1px solid ${T.borderSubtle}` }}>
          <SkelCircle size={32} />
          <div style={{ flex: 1, display: "flex", flexDirection: "column", gap: 5 }}>
            <Skel w="40%" h={12} />
            <Skel w="55%" h={10} />
          </div>
          <SkelPill w={56} h={20} />
        </div>
      ))}
    </>
  );
}

// admin/users.tsx: users table rows
export function TableRowSkel({ rows = 5 }: { rows?: number }) {
  return (
    <>
      {Array.from({ length: rows }, (_, i) => (
        <div key={i} style={{ display: "flex", alignItems: "center", gap: 12, padding: "10px 16px", borderBottom: `1px solid ${T.borderSubtle}` }}>
          <SkelCircle size={28} />
          <Skel w="18%" h={12} />
          <Skel w="22%" h={12} />
          <span style={{ flex: 1 }} />
          <SkelPill w={52} h={20} />
          <SkelPill w={52} h={20} />
        </div>
      ))}
    </>
  );
}
