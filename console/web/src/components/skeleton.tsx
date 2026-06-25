// skeleton.tsx — Shared loading skeleton primitives.
// Rule: shapes mirror the exact size/layout of real content so nothing pops in.
import React from "react";
import { T } from "./onboarding/design";

// Inject keyframes once per page (idempotent by id).
if (typeof document !== "undefined" && !document.getElementById("sf-skel")) {
  const s = document.createElement("style");
  s.id = "sf-skel";
  // The Tenexity loading signature: a single moving-gradient shimmer sweep under
  // every skeleton (not an opacity pulse). `.on-dark` is the dark-surface variant;
  // reduced-motion degrades to a gentle opacity pulse with no sweep.
  s.textContent =
    ".sf-skel{position:relative;overflow:hidden;background:#E7E7EA}" +
    ".sf-skel.on-dark{background:#26262b}" +
    ".sf-skel::after{content:'';position:absolute;inset:0;transform:translateX(-100%);background:linear-gradient(90deg,transparent,rgba(255,255,255,.55),transparent);animation:sfShimmer 1.5s ease-in-out infinite}" +
    ".sf-skel.on-dark::after{background:linear-gradient(90deg,transparent,rgba(255,255,255,.08),transparent)}" +
    "@keyframes sfShimmer{100%{transform:translateX(100%)}}" +
    "@keyframes sf-spin{to{transform:rotate(360deg)}}" +
    "@media(prefers-reduced-motion:reduce){.sf-skel{animation:sfSkelPulse 1.6s ease-in-out infinite}.sf-skel::after{display:none}.sf-spin{animation-duration:0s!important}@keyframes sfSkelPulse{0%,100%{opacity:.5}50%{opacity:.85}}}";
  document.head.appendChild(s);
}

type CSS = React.CSSProperties;

// ── Primitives ─────────────────────────────────────────────────────────────────
// Base shimmer block. The `.sf-skel` class (injected above) supplies the
// background + the moving-gradient shimmer sweep; `dark` switches to the
// on-dark surface treatment for skeletons placed over dark backgrounds.

export function Skel({ w = "100%", h = 12, r, dark, style }: { w?: string | number; h?: number; r?: number | string; dark?: boolean; style?: CSS }) {
  return <span className={dark ? "sf-skel on-dark" : "sf-skel"} style={{ display: "block", width: w, height: h, borderRadius: r ?? 4, ...style }} />;
}

export function SkelLine({ w = "70%", h = 12, dark }: { w?: string | number; h?: number; dark?: boolean }) {
  return <Skel w={w} h={h} dark={dark} />;
}

export function SkelCircle({ size = 28, dark }: { size?: number; dark?: boolean }) {
  return <Skel w={size} h={size} r="50%" dark={dark} />;
}

export function SkelPill({ w = 64, h = 22, dark }: { w?: number; h?: number; dark?: boolean }) {
  return <Skel w={w} h={h} r={9999} dark={dark} />;
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

// DocumentsTab / OrgAdmin: file / document tile (mirrors FileTile)
export function FileTileSkel() {
  return (
    <div style={{ background: T.raised, border: `1px solid ${T.borderSubtle}`, borderRadius: T.rLg, boxShadow: T.shadowXs, padding: "13px 14px", display: "flex", flexDirection: "column", gap: 12 }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <Skel w={30} h={16} r={4} />
        <Skel w={48} h={8} />
      </div>
      <Skel w="80%" h={13} />
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <Skel w={44} h={9} />
        <Skel w={52} h={9} />
      </div>
    </div>
  );
}

// FactoryConsole: kanban ticket card (build board). `dark` for the dark board surface.
export function KanbanCardSkel({ dark = false }: { dark?: boolean }) {
  const surface: CSS = dark
    ? { background: "#1f1f23", border: "1px solid #2e2e34" }
    : { background: T.raised, border: `1px solid ${T.borderSubtle}`, boxShadow: T.shadowXs };
  return (
    <div style={{ ...surface, borderRadius: T.rLg, padding: "12px 13px", display: "flex", flexDirection: "column", gap: 10 }}>
      <div style={{ display: "flex", justifyContent: "space-between" }}>
        <Skel w={48} h={9} dark={dark} />
        <Skel w={28} h={16} r={4} dark={dark} />
      </div>
      <Skel w="85%" h={12} dark={dark} />
      <div style={{ display: "flex", alignItems: "center", gap: 7 }}>
        <SkelCircle size={20} dark={dark} />
        <Skel w={52} h={26} r={9999} dark={dark} />
      </div>
    </div>
  );
}

// FactoryConsole / Concierge: chat message bubble. `dark` for dark rails.
export function MessageSkel({ dark = false }: { dark?: boolean }) {
  const surface: CSS = dark
    ? { background: "#1f1f23", border: "1px solid #2e2e34" }
    : { background: T.raised, border: `1px solid ${T.borderSubtle}` };
  return (
    <div style={{ display: "flex", gap: 9 }}>
      <SkelCircle size={26} dark={dark} />
      <div style={{ flex: 1, padding: "11px 13px", borderRadius: T.rLg, ...surface, display: "flex", flexDirection: "column", gap: 7 }}>
        <Skel w="90%" h={11} dark={dark} />
        <Skel w="70%" h={11} dark={dark} />
      </div>
    </div>
  );
}
