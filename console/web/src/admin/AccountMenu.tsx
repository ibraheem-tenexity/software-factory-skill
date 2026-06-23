import React from "react";
import { T } from "./tokens";
import { Icon } from "./primitives";
import { api } from "../api";
import { useAdminFetch } from "./hooks";

function initials(name: string): string {
  const p = name.trim().split(/\s+/);
  if (p.length === 1) return p[0].slice(0, 2).toUpperCase();
  return (p[0][0] + p[p.length - 1][0]).toUpperCase();
}

function Avatar({ name, size = 26 }: { name: string; size?: number }) {
  return (
    <span
      style={{
        width: size,
        height: size,
        flexShrink: 0,
        borderRadius: 9999,
        display: "grid",
        placeItems: "center",
        background: T.brandSoft,
        color: T.brandDeep,
        font: `600 ${size <= 26 ? 9 : 11}px/1 ${T.mono}`,
      }}
    >
      {initials(name)}
    </span>
  );
}

const LogoutIcon = ({ size = 14 }: { size?: number }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={T.danger} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ flexShrink: 0 }}>
    <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
    <path d="M16 17l5-5-5-5" />
    <path d="M21 12H9" />
  </svg>
);

export function AccountMenu() {
  const [open, setOpen] = React.useState(false);
  const [signingOut, setSigningOut] = React.useState(false);
  const ref = React.useRef<HTMLSpanElement>(null);
  const { data: me } = useAdminFetch(() => api.me());

  React.useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open]);

  const displayName = me?.name?.trim() || me?.email || "User";
  const isStaff = me?.is_staff ?? true; // OS portal is staff-gated; default true avoids flash

  const signOut = async () => {
    setSigningOut(true);
    try {
      await api.logout();
    } catch {
      // proceed to redirect even if logout fails
    }
    window.location.href = "/";
  };

  const item = (label: string, color: string, onClick: () => void, icon: React.ReactNode, disabled = false) => (
    <button
      key={label}
      onClick={disabled ? undefined : () => { setOpen(false); onClick(); }}
      disabled={disabled}
      style={{
        display: "flex",
        alignItems: "center",
        gap: 9,
        width: "100%",
        textAlign: "left",
        padding: "8px 10px",
        borderRadius: 6,
        border: "none",
        background: "transparent",
        cursor: disabled ? "not-allowed" : "pointer",
        font: `500 12.5px/1 ${T.sans}`,
        color: disabled ? T.tertiary : color,
        opacity: disabled ? 0.6 : 1,
      }}
      onMouseEnter={(e) => { if (!disabled) e.currentTarget.style.background = T.sunken; }}
      onMouseLeave={(e) => { e.currentTarget.style.background = "transparent"; }}
    >
      {icon}
      {label}
    </button>
  );

  return (
    <span ref={ref} style={{ position: "relative" }}>
      <button
        onClick={() => setOpen((o) => !o)}
        title="Account"
        aria-label="Account menu"
        style={{
          display: "flex",
          alignItems: "center",
          gap: 8,
          height: 34,
          padding: "0 6px 0 7px",
          borderRadius: 9999,
          cursor: "pointer",
          border: `1px solid ${open ? T.borderDefault : "transparent"}`,
          background: open ? T.sunken : "transparent",
        }}
      >
        <Avatar name={displayName} size={26} />
        <Icon name="chevronDown" size={13} color={T.tertiary} />
      </button>
      {open && (
        <div
          style={{
            position: "absolute",
            right: 0,
            top: 40,
            zIndex: 80,
            width: 248,
            padding: 5,
            borderRadius: T.rLg,
            background: T.raised,
            border: `1px solid ${T.borderSubtle}`,
            boxShadow: T.shadowMd,
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: 10, padding: "9px 10px 11px" }}>
            <Avatar name={displayName} size={36} />
            <span style={{ minWidth: 0 }}>
              <span style={{ display: "flex", alignItems: "center", gap: 6 }}>
                <span
                  style={{
                    font: `600 13.5px/1.2 ${T.sans}`,
                    color: T.fg,
                    whiteSpace: "nowrap",
                    overflow: "hidden",
                    textOverflow: "ellipsis",
                  }}
                >
                  {displayName}
                </span>
                {isStaff && (
                  <span
                    style={{
                      font: `600 8px/1 ${T.mono}`,
                      letterSpacing: "0.06em",
                      color: "#7a3ea8",
                      background: "#f3e9fb",
                      padding: "2px 4px",
                      borderRadius: 3,
                      flexShrink: 0,
                    }}
                  >
                    OPERATOR
                  </span>
                )}
              </span>
              <span
                style={{
                  font: `500 11px/1 ${T.mono}`,
                  letterSpacing: "0.04em",
                  color: T.tertiary,
                  display: "block",
                  marginTop: 2,
                  whiteSpace: "nowrap",
                  overflow: "hidden",
                  textOverflow: "ellipsis",
                }}
              >
                {me?.email || "—"}
              </span>
            </span>
          </div>
          <div style={{ height: 1, background: T.borderSubtle, margin: "2px 0 4px" }} />
          {item(
            "Account settings",
            T.fg,
            () => {},
            <Icon name="settings" size={14} color={T.tertiary} />,
            true
          )}
          {item(
            "Switch to console",
            T.fg,
            () => { window.location.href = "/"; },
            <Icon name="arrowLeft" size={14} color={T.secondary} />
          )}
          <div style={{ height: 1, background: T.borderSubtle, margin: "4px 0" }} />
          {item(
            signingOut ? "Signing out…" : "Sign out",
            T.danger,
            signOut,
            <LogoutIcon />
          )}
        </div>
      )}
    </span>
  );
}
