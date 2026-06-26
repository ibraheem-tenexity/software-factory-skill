// AccountMenu.tsx — the canonical customer-app account menu (DRY: one component used by every
// customer top bar — Dashboard, Org Admin, Project view, Factory console). Faithful to the design's
// admin.jsx AccountMenu, wired to REAL data:
//   - header user = GET /api/me (name + email + role; is_internal gates the staff item)
//   - "Switch to Tenexity OS" → /admin, ONLY for internal/staff (me.is_internal === true)
//   - "Sign out" → POST /api/auth/logout → redirect "/" (SPA re-checks /api/me → login)
//   - "Account settings" is intentionally OMITTED (no backing screen yet — no dead button)
// Opens on click, closes on click-outside (mousedown). FE-only; name/is_internal/logout
// graceful-degrade until the backend ships them (name→email fallback, staff item hidden, logout
// redirects regardless).
import React, { useEffect, useRef, useState } from "react";
import { api } from "../api";
import { useMe } from "./MeContext";
import { T, Icon, Avatar } from "./onboarding/design";

const LogoutIcon = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke={T.danger} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" /><path d="M16 17l5-5-5-5" /><path d="M21 12H9" />
  </svg>
);

function MenuItem({ label, color, icon, onClick }: { label: string; color: string; icon: React.ReactNode; onClick: () => void }) {
  return (
    <button onClick={onClick} style={{ display: "flex", alignItems: "center", gap: 9, width: "100%", textAlign: "left", padding: "8px 10px", borderRadius: 6, border: "none", background: "transparent", cursor: "pointer", font: `500 12.5px/1 ${T.sans}`, color }}
      onMouseEnter={(e) => (e.currentTarget.style.background = T.sunken)} onMouseLeave={(e) => (e.currentTarget.style.background = "transparent")}>
      {icon}{label}
    </button>
  );
}

export function AccountMenu({ size = 28 }: { size?: number }) {
  const [open, setOpen] = useState(false);
  const me = useMe();
  const ref = useRef<HTMLSpanElement | null>(null);

  useEffect(() => {
    if (!open) return;
    const h = (e: MouseEvent) => { if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false); };
    document.addEventListener("mousedown", h);
    return () => document.removeEventListener("mousedown", h);
  }, [open]);

  const name = me?.name || me?.email || "You";
  const email = me?.email || "";
  const role = (me?.role || "").toUpperCase();
  // Staff-only "Switch to Tenexity OS": require a real signed-in staff account. The `email` guard
  // keeps it hidden in local/dev auth-off mode (where the backend returns is_internal:true for the
  // anonymous operator) while staying correct in prod (real staff always have an email).
  const isInternal = me?.is_internal === true && !!me?.email;

  const signOut = async () => { setOpen(false); await api.logout(); window.location.href = "/"; };
  const switchToOS = () => { window.location.href = "/admin"; };

  return (
    <span ref={ref} style={{ position: "relative" }}>
      <button onClick={() => setOpen((o) => !o)} title="Account" aria-label="Account menu"
        style={{ display: "flex", alignItems: "center", gap: 8, height: size + 6, padding: "0 6px 0 7px", borderRadius: 9999, cursor: "pointer",
          border: `1px solid ${open ? T.borderDefault : "transparent"}`, background: open ? T.sunken : "transparent" }}>
        <Avatar name={name} size={size} tone="brand" />
        <Icon name="chevronDown" size={13} color={T.tertiary} />
      </button>
      {open && (
        <div style={{ position: "absolute", right: 0, top: size + 12, zIndex: 80, width: 248, padding: 5, borderRadius: T.rLg, background: T.raised, border: `1px solid ${T.borderSubtle}`, boxShadow: T.shadowMd }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10, padding: "9px 10px 11px" }}>
            <Avatar name={name} size={36} tone="brand" />
            <span style={{ minWidth: 0 }}>
              <span style={{ display: "flex", alignItems: "center", gap: 6 }}>
                <span style={{ font: `600 13.5px/1.2 ${T.sans}`, color: T.fg, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{name}</span>
                {role && <span style={{ font: `600 8px/1 ${T.mono}`, letterSpacing: "0.06em", color: T.brandDeep, background: T.brandSoft, padding: "2px 4px", borderRadius: 3, flexShrink: 0 }}>{role}</span>}
              </span>
              {email && <span style={{ font: `400 10.5px/1.3 ${T.mono}`, color: T.tertiary, display: "block", marginTop: 2, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{email}</span>}
            </span>
          </div>
          <div style={{ height: 1, background: T.borderSubtle, margin: "2px 0 4px" }} />
          {isInternal && <MenuItem label="Switch to Tenexity OS" color={T.fg} icon={<Icon name="layers" size={14} color={T.secondary} />} onClick={switchToOS} />}
          {isInternal && <div style={{ height: 1, background: T.borderSubtle, margin: "4px 0" }} />}
          <MenuItem label="Sign out" color={T.danger} icon={<LogoutIcon />} onClick={signOut} />
        </div>
      )}
    </span>
  );
}
