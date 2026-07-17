import React from "react";
import { T } from "./tokens";
import { Icon, Sparkle, StatusPill, MetricCard, TextInput } from "./primitives";
import { api } from "../api";
import type { AdminAccessUser, AdminClient, Me } from "../api";
import { useAdminFetch, fmtRel } from "./hooks";
import { PageTitle, Mono, ColHead, AdminBtn } from "./views";

const GRID = "minmax(0,2fr) minmax(0,1.4fr) 100px 120px 130px 96px 40px";

type Audience = "ALL" | "CUSTOMERS" | "INTERNAL";

function isInternal(u: AdminAccessUser): boolean {
  return u.is_internal ?? u.type === "Tenexity";
}

function displayRole(u: AdminAccessUser): string {
  const r = u.role || "";
  return r ? r.charAt(0).toUpperCase() + r.slice(1) : "—";
}

function displayName(u: AdminAccessUser): string {
  if (u.name?.trim()) return u.name.trim();
  return u.email;
}

function initials(name: string): string {
  const p = name.trim().split(/\s+/);
  if (p.length === 1) return p[0].slice(0, 2).toUpperCase();
  return (p[0][0] + p[p.length - 1][0]).toUpperCase();
}

function Avatar({ name, size = 30, internal }: { name: string; size?: number; internal?: boolean }) {
  const bg = internal ? "#f3e9fb" : T.sunken;
  const color = internal ? "#7a3ea8" : T.secondary;
  return (
    <span
      style={{
        width: size,
        height: size,
        flexShrink: 0,
        borderRadius: 6,
        display: "grid",
        placeItems: "center",
        background: bg,
        color: color,
        font: `600 ${size <= 30 ? 10 : 12}px/1 ${T.mono}`,
      }}
    >
      {initials(name)}
    </span>
  );
}

function RoleBadge({ role }: { role: string }) {
  const [bg, color] = role === "Admin" ? [T.brandSoft, T.brandDeep] : [T.sunken, T.secondary];
  return (
    <span
      style={{
        font: `600 9.5px/1 ${T.mono}`,
        letterSpacing: "0.05em",
        textTransform: "uppercase",
        color,
        background: bg,
        border: `1px solid ${color}22`,
        padding: "4px 6px",
        borderRadius: 4,
        justifySelf: "start",
      }}
    >
      {role}
    </span>
  );
}

const SIGNIN_METHODS: Record<string, { label: string; short: string; mark: string; tone: [string, string]; enabled: boolean }> = {
  google: { label: "Google", short: "Google", mark: "G", tone: [T.brandSoft, T.brandDeep], enabled: true },
  microsoft: { label: "Microsoft", short: "Microsoft", mark: "MS", tone: ["#E0F4F7", "#11A0B8"], enabled: false },
  password: { label: "Email & password", short: "Email · pass", mark: "@", tone: [T.sunken, T.secondary], enabled: true },
  sso: { label: "Organization SSO", short: "SSO", mark: "SSO", tone: ["#f3e9fb", "#7a3ea8"], enabled: false },
};
const METHOD_ORDER = ["google", "microsoft", "password", "sso"];

function MethodBadge({ method }: { method?: string }) {
  const m = SIGNIN_METHODS[method || "google"];
  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: 7, minWidth: 0 }}>
      <span
        style={{
          width: 22,
          height: 22,
          flexShrink: 0,
          borderRadius: 5,
          display: "grid",
          placeItems: "center",
          background: m.tone[0],
          color: m.tone[1],
          font: `700 8.5px/1 ${T.mono}`,
        }}
      >
        {m.mark}
      </span>
      <Mono style={{ fontSize: 11, color: T.secondary, whiteSpace: "nowrap" }}>{m.short}</Mono>
    </span>
  );
}

function userMethod(u: AdminAccessUser): string {
  return u.sign_in_method || u.method || "";
}

function StatusCell({ status }: { status: string }) {
  const map: Record<string, ["success" | "warning" | "danger" | "neutral", string]> = {
    active: ["success", "active"],
    invited: ["warning", "invited"],
    disabled: ["neutral", "disabled"],
  };
  const [tone, label] = map[status] || ["neutral", status];
  return <StatusPill tone={tone} dot={status !== "disabled"}>{label}</StatusPill>;
}

function SelectField({ value, onChange, options, w }: { value: string; onChange: (v: string) => void; options: string[]; w?: number | string }) {
  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        height: 36,
        borderRadius: T.rMd,
        border: `1px solid ${T.borderDefault}`,
        background: T.raised,
        position: "relative",
        width: w || "100%",
      }}
    >
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        style={{
          appearance: "none",
          WebkitAppearance: "none",
          width: "100%",
          height: "100%",
          border: "none",
          background: "transparent",
          outline: "none",
          padding: "0 28px 0 11px",
          font: `500 12.5px/1 ${T.sans}`,
          color: T.fg,
          cursor: "pointer",
        }}
      >
        {options.map((o) => (
          <option key={o} value={o}>
            {o}
          </option>
        ))}
      </select>
      <Icon name="chevronDown" size={14} color={T.tertiary} style={{ position: "absolute", right: 9, pointerEvents: "none" }} />
    </div>
  );
}

function useUsersAndClients() {
  const usersQ = useAdminFetch(() => api.adminAccess());
  const clientsQ = useAdminFetch(() => api.adminClients());
  const refresh = React.useCallback(() => {
    usersQ.refetch();
    clientsQ.refetch();
  }, [usersQ, clientsQ]);
  const users = usersQ.data?.users ?? [];
  const clients = clientsQ.data?.clients ?? [];
  return { users, clients, loading: usersQ.loading, refresh };
}

function AddUserModal({ onClose, onCreated }: { onClose: () => void; onCreated: () => void }) {
  const [email, setEmail] = React.useState("");
  const [name, setName] = React.useState("");
  const [designation, setDesignation] = React.useState("");
  const [audience, setAudience] = React.useState<"org" | "tenexity">("org");
  const [orgName, setOrgName] = React.useState("");
  const [role, setRole] = React.useState<"Admin" | "Member">("Admin");
  const [method, setMethod] = React.useState<"google" | "password">("google");
  const [password, setPassword] = React.useState("");
  const [loading, setLoading] = React.useState(false);
  const [createdLink, setCreatedLink] = React.useState<string | null>(null);
  // SOF-195: mirror OrgAdminScreen's SOF-140 pattern — the user row is the success signal
  // regardless of email; only speak up when invite_email_sent comes back false.
  const [emailFailed, setEmailFailed] = React.useState(false);
  const [invitedNoLink, setInvitedNoLink] = React.useState(false);
  const { clients } = useUsersAndClients();
  const valid = /^\S+@\S+\.\S+$/.test(email);
  const isTenexity = audience === "tenexity";

  React.useEffect(() => {
    if (clients.length && !orgName) setOrgName(clients[0].name);
  }, [clients, orgName]);

  const submit = async () => {
    if (!valid) return;
    if (!isTenexity && !orgName.trim()) return;
    if (method === "password" && password.length < 6) return;
    setLoading(true);
    try {
      const body: Parameters<typeof api.adminInvite>[0] = {
        email,
        access_type: isTenexity ? "tenexity" : "org",
        org_name: isTenexity ? undefined : orgName,
        name: name.trim() || undefined,
        designation: designation.trim() || undefined,
        method,
        ...(method === "password" ? { password } : {}),
        ...(isTenexity ? {} : { role: role.toLowerCase() as "admin" | "member" }),
      };
      const d = await api.adminInvite(body);
      setEmailFailed(d.invite_email_sent === false);
      if (method === "password") {
        try {
          const r = await api.adminResendInvite(email);
          setCreatedLink(r.link);
        } catch {
          onCreated();
        }
      } else if (d.invite_email_sent === false) {
        // Don't silently close on a failed email — the admin needs to know to tell the
        // invitee out-of-band, same as OrgAdminScreen's inviteMember notice.
        setInvitedNoLink(true);
      } else {
        onCreated();
      }
    } catch {
      alert("Failed to invite user.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div
      onClick={onClose}
      style={{
        position: "absolute",
        inset: 0,
        zIndex: 70,
        background: "rgba(9,12,18,0.45)",
        display: "grid",
        placeItems: "center",
        padding: 28,
      }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          width: "min(560px, 100%)",
          maxHeight: "100%",
          background: T.raised,
          borderRadius: T.rXl,
          boxShadow: T.shadowMd,
          display: "flex",
          flexDirection: "column",
          overflow: "hidden",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "16px 20px", borderBottom: `1px solid ${T.borderSubtle}` }}>
          <div>
            <h2 style={{ font: `400 19px/1.2 ${T.display}`, color: T.fg, margin: 0 }}>Add user</h2>
            <Mono style={{ fontSize: 11, marginTop: 4, display: "block" }}>One record in the master users table</Mono>
          </div>
          <button
            onClick={onClose}
            title="Close"
            style={{ width: 28, height: 28, display: "grid", placeItems: "center", borderRadius: T.rMd, border: "none", background: "transparent", color: T.tertiary, cursor: "pointer" }}
          >
            <Icon name="x" size={16} />
          </button>
        </div>

        <div style={{ padding: "18px 20px", display: "flex", flexDirection: "column", gap: 14, overflow: "auto" }}>
          <div>
            <ColHead style={{ display: "block", marginBottom: 7 }}>Belongs to</ColHead>
            <div style={{ display: "inline-flex", padding: 2, borderRadius: T.rMd, background: T.sunken, border: `1px solid ${T.borderSubtle}` }}>
              {[
                ["org", "An organization"],
                ["tenexity", "Tenexity · internal"],
              ].map(([id, label]) => (
                <button
                  key={id}
                  onClick={() => setAudience(id as "org" | "tenexity")}
                  style={{
                    font: `600 11px/1 ${T.mono}`,
                    letterSpacing: "0.03em",
                    padding: "7px 12px",
                    borderRadius: 5,
                    cursor: "pointer",
                    border: "none",
                    background: audience === id ? T.fg : "transparent",
                    color: audience === id ? "#fff" : T.tertiary,
                  }}
                >
                  {label}
                </button>
              ))}
            </div>
          </div>

          <div style={{ display: "flex", gap: 10 }}>
            <div style={{ flex: 1 }}>
              <label style={{ display: "block", font: `500 13px/1.2 ${T.sans}`, color: T.fg, marginBottom: 6 }}>Email address</label>
              <TextInput type="email" value={email} onChange={setEmail} placeholder="person@company.com" mono />
            </div>
            <div style={{ flex: 1 }}>
              <label style={{ display: "block", font: `500 13px/1.2 ${T.sans}`, color: T.fg, marginBottom: 6 }}>Full name <Mono style={{ color: T.tertiary }}>Optional</Mono></label>
              <TextInput value={name} onChange={setName} placeholder="Jordan Rivera" />
            </div>
          </div>

          <div style={{ display: "flex", gap: 10 }}>
            <div style={{ flex: 1 }}>
              <label style={{ display: "block", font: `500 13px/1.2 ${T.sans}`, color: T.fg, marginBottom: 6 }}>{isTenexity ? "Workspace" : "Organization"}</label>
              {isTenexity ? (
                <div
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: 8,
                    height: 36,
                    padding: "0 11px",
                    borderRadius: T.rMd,
                    border: `1px solid ${T.borderDefault}`,
                    background: T.sunken,
                  }}
                >
                  <Sparkle size={11} color="#7a3ea8" />
                  <span style={{ font: `500 12.5px/1 ${T.sans}`, color: T.fg }}>Tenexity (cross-tenant access)</span>
                </div>
              ) : (
                <SelectField value={orgName} onChange={setOrgName} options={clients.length ? ["Select organization", ...clients.map((c) => c.name)] : ["Select organization"]} />
              )}
            </div>
            <div style={{ width: 150, flexShrink: 0 }}>
              <label style={{ display: "block", font: `500 13px/1.2 ${T.sans}`, color: T.fg, marginBottom: 6 }}>Role</label>
              {isTenexity ? (
                <div
                  style={{
                    display: "flex",
                    alignItems: "center",
                    height: 36,
                    padding: "0 11px",
                    borderRadius: T.rMd,
                    border: `1px solid ${T.borderSubtle}`,
                    background: T.sunken,
                    font: `500 12.5px/1 ${T.sans}`,
                    color: T.secondary,
                  }}
                >
                  Operator
                </div>
              ) : (
                <SelectField value={role} onChange={(v) => setRole(v as "Admin" | "Member")} options={["Admin", "Member"]} />
              )}
            </div>
          </div>

          <div>
            <label style={{ display: "block", font: `500 13px/1.2 ${T.sans}`, color: T.fg, marginBottom: 6 }}>Sign-in method</label>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 8 }}>
              {METHOD_ORDER.map((m) => {
                const meta = SIGNIN_METHODS[m];
                const on = method === (m as typeof method);
                return (
                  <button
                    key={m}
                    disabled={!meta.enabled}
                    onClick={() => meta.enabled && setMethod(m as "google" | "password")}
                    title={meta.enabled ? meta.label : `${meta.label} · coming soon`}
                    style={{
                      display: "flex",
                      flexDirection: "column",
                      alignItems: "center",
                      gap: 7,
                      padding: "12px 6px",
                      borderRadius: T.rMd,
                      cursor: meta.enabled ? "pointer" : "not-allowed",
                      border: `1px solid ${on ? T.brand : T.borderDefault}`,
                      background: on ? T.brandSoft : T.raised,
                      opacity: meta.enabled ? 1 : 0.45,
                    }}
                  >
                    <span
                      style={{
                        width: 26,
                        height: 26,
                        borderRadius: 6,
                        display: "grid",
                        placeItems: "center",
                        background: meta.tone[0],
                        color: meta.tone[1],
                        font: `700 9px/1 ${T.mono}`,
                      }}
                    >
                      {meta.mark}
                    </span>
                    <span style={{ font: `500 11px/1.1 ${T.sans}`, color: on ? T.brandDeep : T.secondary, textAlign: "center" }}>{meta.label}</span>
                  </button>
                );
              })}
            </div>
          </div>

          {method === "password" && (
            <div>
              <label style={{ display: "block", font: `500 13px/1.2 ${T.sans}`, color: T.fg, marginBottom: 6 }}>
                Initial password <Mono style={{ color: T.tertiary }}>Required for Email &amp; password</Mono>
              </label>
              <div style={{ display: "flex", gap: 8 }}>
                <TextInput value={password} onChange={setPassword} placeholder="Temporary password (6+ chars)" mono style={{ flex: 1 }} />
                <AdminBtn onClick={() => setPassword(Math.random().toString(36).slice(2, 10) + "A1")}>Generate</AdminBtn>
              </div>
            </div>
          )}

          <div>
            <label style={{ display: "block", font: `500 13px/1.2 ${T.sans}`, color: T.fg, marginBottom: 6 }}>
              Designation <Mono style={{ color: T.tertiary }}>Optional</Mono>
            </label>
            <TextInput value={designation} onChange={setDesignation} placeholder="e.g. Operations Manager" />
          </div>
        </div>

        {createdLink && (
          <div style={{ padding: "14px 20px", borderTop: `1px solid ${T.borderSubtle}`, background: T.sunken }}>
            <ColHead style={{ display: "block", marginBottom: 8 }}>User created — share this sign-in link</ColHead>
            {emailFailed && (
              <Mono style={{ display: "block", marginBottom: 8, color: T.danger }}>
                The invite email couldn't be sent — share this link with them directly.
              </Mono>
            )}
            <div style={{ display: "flex", gap: 8 }}>
              <div
                style={{
                  flex: 1,
                  display: "flex",
                  alignItems: "center",
                  height: 36,
                  padding: "0 11px",
                  borderRadius: T.rMd,
                  border: `1px solid ${T.borderSubtle}`,
                  background: T.raised,
                  overflow: "hidden",
                }}
              >
                <Mono style={{ fontSize: 11, color: T.secondary, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{createdLink}</Mono>
              </div>
              <AdminBtn onClick={() => navigator.clipboard.writeText(createdLink!)}>Copy</AdminBtn>
              <AdminBtn primary onClick={() => { onCreated(); }}>Done</AdminBtn>
            </div>
          </div>
        )}
        {invitedNoLink && (
          <div style={{ padding: "14px 20px", borderTop: `1px solid ${T.borderSubtle}`, background: T.sunken }}>
            <Mono style={{ display: "block", marginBottom: 10, color: T.danger }}>
              User invited, but the invite email couldn't be sent — tell them to sign in with this
              email address at the console.
            </Mono>
            <div style={{ display: "flex", justifyContent: "flex-end" }}>
              <AdminBtn primary onClick={() => { onCreated(); }}>Done</AdminBtn>
            </div>
          </div>
        )}
        {!createdLink && !invitedNoLink && (
          <div style={{ display: "flex", alignItems: "center", justifyContent: "flex-end", gap: 9, padding: "13px 20px", borderTop: `1px solid ${T.borderSubtle}`, background: T.sunken }}>
            <AdminBtn onClick={onClose}>Cancel</AdminBtn>
            <AdminBtn
              primary
              onClick={submit}
              disabled={!valid || (!isTenexity && !orgName) || (method === "password" && password.length < 6) || loading}
            >
              {loading ? "Sending…" : method === "password" ? "Create user" : "Send invite"}
            </AdminBtn>
          </div>
        )}
      </div>
    </div>
  );
}

function UserDrawer({ user, currentUserEmail, onClose, onChanged }: { user: AdminAccessUser; currentUserEmail?: string; onClose: () => void; onChanged: () => void }) {
  const [role, setRole] = React.useState(displayRole(user));
  const [internal, setInternal] = React.useState(isInternal(user));
  const [saving, setSaving] = React.useState(false);
  const [inviteLink, setInviteLink] = React.useState<string | null>(null);
  const [resending, setResending] = React.useState(false);

  const resendInvite = async () => {
    setResending(true);
    try {
      const r = await api.adminResendInvite(user.email);
      setInviteLink(r.link);
    } catch {
      alert("Failed to get invite link.");
    } finally {
      setResending(false);
    }
  };

  const patchRole = async () => {
    const apiRole = role.toLowerCase();
    const removingOwnStaff =
      user.email === currentUserEmail &&
      isInternal(user) &&
      (!internal || apiRole !== "admin");
    if (removingOwnStaff) {
      alert("You cannot remove your own staff admin access from this UI.");
      return;
    }
    setSaving(true);
    try {
      await api.adminUpdateAccess(user.email, { role: apiRole, is_internal: internal });
      onChanged();
      onClose();
    } catch (e) {
      const msg = (e as Error).message || "";
      if (msg.includes("409")) {
        alert("Cannot update role: this would leave the organization without a staff admin, or you cannot demote this session.");
      } else {
        alert("Failed to update user.");
      }
    } finally {
      setSaving(false);
    }
  };

  const setStatus = async (status: "active" | "disabled") => {
    try {
      await api.adminUpdateAccess(user.email, { status });
      onChanged();
      onClose();
    } catch {
      alert(`Failed to ${status === "active" ? "enable" : "disable"} user.`);
    }
  };

  const remove = async () => {
    if (!confirm(`Remove ${user.email}?`)) return;
    try {
      await api.adminDeleteAccess(user.email);
      onChanged();
      onClose();
    } catch {
      alert("Failed to remove user.");
    }
  };

  const methodLabel = userMethod(user) ? SIGNIN_METHODS[userMethod(user)]?.label || userMethod(user) : "—";

  return (
    <div
      onClick={onClose}
      style={{
        position: "absolute",
        inset: 0,
        zIndex: 65,
        background: "rgba(9,12,18,0.45)",
        display: "flex",
        justifyContent: "flex-end",
      }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{ width: "min(480px, 100%)", height: "100%", background: T.raised, boxShadow: T.shadowMd, display: "flex", flexDirection: "column" }}
      >
        <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", padding: "18px 20px", borderBottom: `1px solid ${T.borderSubtle}` }}>
          <div style={{ display: "flex", gap: 12, minWidth: 0 }}>
            <Avatar name={displayName(user)} size={42} internal={internal} />
            <div style={{ minWidth: 0 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <span style={{ font: `600 16px/1.2 ${T.sans}`, color: T.fg }}>{displayName(user)}</span>
                <StatusCell status={user.status} />
              </div>
              <Mono style={{ fontSize: 11.5, color: T.secondary, marginTop: 3, display: "block" }}>{user.email}</Mono>
            </div>
          </div>
          <button
            onClick={onClose}
            title="Close"
            style={{ width: 28, height: 28, flexShrink: 0, display: "grid", placeItems: "center", borderRadius: T.rMd, border: "none", background: "transparent", color: T.tertiary, cursor: "pointer" }}
          >
            <Icon name="x" size={16} />
          </button>
        </div>

        <div style={{ flex: 1, overflow: "auto", padding: "18px 20px", display: "flex", flexDirection: "column", gap: 16 }}>
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "1fr 1fr",
              gap: 1,
              background: T.borderSubtle,
              border: `1px solid ${T.borderSubtle}`,
              borderRadius: T.rMd,
              overflow: "hidden",
            }}
          >
            {[
              ["Organization", user.org || "—"],
              ["Joined", user.created_at ? String(user.created_at) : "—"],
              ["Last active", user.last_active ? fmtRel(user.last_active as number) : "—"],
              ["Invited by", user.invited_by || "—"],
            ].map(([k, v]) => (
              <div key={k} style={{ background: T.raised, padding: "11px 13px" }}>
                <ColHead style={{ display: "block", marginBottom: 4 }}>{k}</ColHead>
                <span style={{ font: `500 12.5px/1.3 ${T.sans}`, color: T.fg, wordBreak: "break-word" }}>{v}</span>
              </div>
            ))}
          </div>

          <div>
            <label style={{ font: `500 13px/1.2 ${T.sans}`, color: T.fg, display: "block", marginBottom: 6 }}>Role</label>
            <SelectField value={role} onChange={setRole} options={["Admin", "Member"]} />
            <label
              style={{
                display: "flex",
                alignItems: "center",
                gap: 8,
                marginTop: 10,
                font: `500 12.5px/1 ${T.sans}`,
                color: T.fg,
                cursor: "pointer",
              }}
            >
              <input
                type="checkbox"
                checked={internal}
                onChange={(e) => {
                  const next = e.target.checked;
                  setInternal(next);
                  if (next) setRole("Admin");
                }}
                style={{ cursor: "pointer" }}
              />
              Tenexity internal staff
            </label>
          </div>

          <div>
            <label style={{ font: `500 13px/1.2 ${T.sans}`, color: T.fg, display: "block", marginBottom: 6 }}>Sign-in method</label>
            <div
              style={{
                display: "flex",
                alignItems: "center",
                height: 36,
                padding: "0 11px",
                borderRadius: T.rMd,
                border: `1px solid ${T.borderSubtle}`,
                background: T.sunken,
                font: `500 12.5px/1 ${T.sans}`,
                color: T.secondary,
              }}
            >
              {methodLabel}
            </div>
          </div>

          <div>
            <label style={{ font: `500 13px/1.2 ${T.sans}`, color: T.fg, display: "block", marginBottom: 6 }}>Designation</label>
            <div
              style={{
                display: "flex",
                alignItems: "center",
                height: 36,
                padding: "0 11px",
                borderRadius: T.rMd,
                border: `1px solid ${T.borderSubtle}`,
                background: T.sunken,
                font: `500 12.5px/1 ${T.sans}`,
                color: T.secondary,
              }}
            >
              {user.designation || "—"}
            </div>
          </div>

          {user.status === "invited" && (
            <div>
              <label style={{ font: `500 13px/1.2 ${T.sans}`, color: T.fg, display: "block", marginBottom: 6 }}>Invite link</label>
              {inviteLink ? (
                <div style={{ display: "flex", gap: 8 }}>
                  <div
                    style={{
                      flex: 1,
                      display: "flex",
                      alignItems: "center",
                      height: 36,
                      padding: "0 11px",
                      borderRadius: T.rMd,
                      border: `1px solid ${T.borderSubtle}`,
                      background: T.sunken,
                      overflow: "hidden",
                    }}
                  >
                    <Mono style={{ fontSize: 11, color: T.secondary, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{inviteLink}</Mono>
                  </div>
                  <AdminBtn onClick={() => navigator.clipboard.writeText(inviteLink)}>Copy</AdminBtn>
                </div>
              ) : (
                <AdminBtn onClick={resendInvite} disabled={resending}>{resending ? "Fetching…" : "Get invite link"}</AdminBtn>
              )}
            </div>
          )}

          <div style={{ marginTop: 6, paddingTop: 14, borderTop: `1px solid ${T.borderSubtle}` }}>
            <ColHead style={{ display: "block", marginBottom: 10, color: T.danger }}>Danger zone</ColHead>
            <div style={{ display: "flex", gap: 9, flexWrap: "wrap" }}>
              {user.status === "active" && (
                <AdminBtn onClick={() => setStatus("disabled")}>
                  <Icon name="x" size={13} color={T.warning} /> Disable sign-in
                </AdminBtn>
              )}
              {user.status === "disabled" && (
                <AdminBtn onClick={() => setStatus("active")}>
                  <Icon name="check" size={13} color={T.success} /> Re-enable
                </AdminBtn>
              )}
              <button
                onClick={remove}
                style={{
                  display: "inline-flex",
                  alignItems: "center",
                  gap: 7,
                  height: 36,
                  padding: "0 14px",
                  cursor: "pointer",
                  font: `600 11.5px/1 ${T.mono}`,
                  letterSpacing: "0.05em",
                  textTransform: "uppercase",
                  borderRadius: T.rMd,
                  border: `1px solid ${T.danger}55`,
                  background: T.dangerSoft,
                  color: T.danger,
                }}
              >
                Remove user
              </button>
            </div>
          </div>
        </div>

        <div style={{ display: "flex", alignItems: "center", justifyContent: "flex-end", gap: 9, padding: "13px 20px", borderTop: `1px solid ${T.borderSubtle}` }}>
          <AdminBtn onClick={onClose}>Cancel</AdminBtn>
          <AdminBtn primary onClick={patchRole} disabled={saving || (role === displayRole(user) && internal === isInternal(user))}>
            {saving ? "Saving…" : "Save changes"}
          </AdminBtn>
        </div>
      </div>
    </div>
  );
}

function RowMenu({ user, sessionStaff, onAct }: { user: AdminAccessUser; sessionStaff?: boolean; onAct: (id: string, user: AdminAccessUser) => void }) {
  const [open, setOpen] = React.useState(false);
  const ref = React.useRef<HTMLSpanElement>(null);
  React.useEffect(() => {
    if (!open) return;
    const h = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", h);
    return () => document.removeEventListener("mousedown", h);
  }, [open]);
  const items = [
    user.status === "invited" && ["resend", "Resend invite", T.fg],
    user.status === "active" && ["disable", "Disable sign-in", T.warning],
    user.status === "disabled" && ["enable", "Re-enable", T.success],
    sessionStaff && !isInternal(user) && ["make-tenexity-admin", "Make Tenexity admin", T.brandDeep],
    ["edit", "Edit user", T.fg],
    ["remove", "Remove user", T.danger],
  ].filter(Boolean) as [string, string, string][];
  return (
    <span ref={ref} style={{ position: "relative", justifySelf: "end" }}>
      <button
        onClick={(e) => {
          e.stopPropagation();
          setOpen((o) => !o);
        }}
        title="Actions"
        style={{ width: 28, height: 28, display: "grid", placeItems: "center", borderRadius: T.rMd, border: "none", background: open ? T.sunken : "transparent", color: T.tertiary, cursor: "pointer" }}
      >
        <Icon name="dots" size={16} />
      </button>
      {open && (
        <div
          style={{
            position: "absolute",
            right: 0,
            top: 32,
            zIndex: 30,
            minWidth: 180,
            padding: 5,
            borderRadius: T.rLg,
            background: T.raised,
            border: `1px solid ${T.borderSubtle}`,
            boxShadow: T.shadowMd,
          }}
        >
          {items.map(([id, label, color]) => (
            <button
              key={id}
              onClick={(e) => {
                e.stopPropagation();
                setOpen(false);
                onAct(id, user);
              }}
              style={{
                display: "block",
                width: "100%",
                textAlign: "left",
                padding: "8px 10px",
                borderRadius: 6,
                border: "none",
                background: "transparent",
                cursor: "pointer",
                font: `500 12.5px/1 ${T.sans}`,
                color,
              }}
              onMouseEnter={(e) => (e.currentTarget.style.background = T.sunken)}
              onMouseLeave={(e) => (e.currentTarget.style.background = "transparent")}
            >
              {label}
            </button>
          ))}
        </div>
      )}
    </span>
  );
}

export function UsersManagement() {
  const { users, clients, loading: usersLoading, refresh } = useUsersAndClients();
  const [add, setAdd] = React.useState(false);
  const [drawer, setDrawer] = React.useState<AdminAccessUser | null>(null);
  const [me, setMe] = React.useState<Me | null>(null);

  React.useEffect(() => {
    api.me().then(setMe).catch(() => setMe(null));
  }, []);

  const sessionStaff = me?.role === "admin" && me?.is_internal === true;
  const [audience, setAudience] = React.useState<Audience>("ALL");
  const [fOrg, setFOrg] = React.useState("All organizations");
  const [fRole, setFRole] = React.useState("All roles");
  const [fStatus, setFStatus] = React.useState("All statuses");
  const [q, setQ] = React.useState("");

  const orgNames = React.useMemo(
    () => ["All organizations", ...clients.map((c) => c.name), "Tenexity"],
    [clients]
  );

  const filtered = React.useMemo(() => {
    const query = q.trim().toLowerCase();
    return users.filter((u) => {
      const internal = isInternal(u);
      if (audience === "CUSTOMERS" && internal) return false;
      if (audience === "INTERNAL" && !internal) return false;
      if (fOrg !== "All organizations" && u.org !== fOrg) return false;
      if (fRole !== "All roles" && displayRole(u) !== fRole) return false;
      if (fStatus !== "All statuses" && u.status !== fStatus.toLowerCase()) return false;
      if (query && !(displayName(u) + " " + u.email + " " + (u.org || "")).toLowerCase().includes(query)) return false;
      return true;
    });
  }, [users, audience, fOrg, fRole, fStatus, q]);

  const counts = React.useMemo(() => {
    const total = users.length;
    const active = users.filter((u) => u.status === "active").length;
    const invited = users.filter((u) => u.status === "invited").length;
    const disabled = users.filter((u) => u.status === "disabled").length;
    return { total, active, invited, disabled };
  }, [users]);

  const act = async (id: string, user: AdminAccessUser) => {
    if (id === "remove") {
      if (!confirm(`Remove ${user.email}?`)) return;
      try {
        await api.adminDeleteAccess(user.email);
        refresh();
      } catch {
        alert("Failed to remove user.");
      }
    } else if (id === "disable") {
      try {
        await api.adminUpdateAccess(user.email, { status: "disabled" });
        refresh();
      } catch {
        alert("Failed to disable user.");
      }
    } else if (id === "enable") {
      try {
        await api.adminUpdateAccess(user.email, { status: "active" });
        refresh();
      } catch {
        alert("Failed to enable user.");
      }
    } else if (id === "resend" || id === "edit") {
      setDrawer(user);
    } else if (id === "make-tenexity-admin") {
      try {
        await api.adminUpdateAccess(user.email, { role: "admin", is_internal: true });
        refresh();
      } catch (e) {
        const msg = (e as Error).message || "";
        if (msg.includes("409")) {
          alert("Cannot promote user: this would conflict with staff-admin rules.");
        } else {
          alert("Failed to promote user.");
        }
      }
    }
  };

  return (
    <>
      <PageTitle
        title="Users"
        sub="The master users table — everyone allowed to sign in, across every organization and internal Tenexity staff."
        actions={
          <AdminBtn primary onClick={() => setAdd(true)}>
            <Icon name="plus" size={14} color="#fff" /> Add user
          </AdminBtn>
        }
      />

      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 12, marginBottom: 20 }}>
        <MetricCard label="Total users" value={counts.total} hint="across all organizations" accent />
        <MetricCard label="Active" value={counts.active} hint="signed in at least once" />
        <MetricCard label="Pending invites" value={counts.invited} hint="awaiting first sign-in" />
        <MetricCard label="Disabled" value={counts.disabled} hint="sign-in revoked" />
      </div>

      <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 14, flexWrap: "wrap" }}>
        <div
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: 8,
            height: 36,
            padding: "0 11px",
            borderRadius: T.rMd,
            border: `1px solid ${T.borderDefault}`,
            background: T.raised,
            flex: 1,
            minWidth: 200,
          }}
        >
          <Icon name="search" size={14} color={T.tertiary} />
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Search name, email, organization…"
            style={{ flex: 1, border: "none", outline: "none", background: "transparent", font: `400 12.5px/1 ${T.sans}`, color: T.fg }}
          />
        </div>
        <div style={{ width: 170 }}>
          <SelectField value={fOrg} onChange={setFOrg} options={orgNames} />
        </div>
        <div style={{ width: 130 }}>
          <SelectField value={fRole} onChange={setFRole} options={["All roles", "Admin", "Member", "Operator"]} />
        </div>
        <div style={{ width: 130 }}>
          <SelectField value={fStatus} onChange={setFStatus} options={["All statuses", "Active", "Invited", "Disabled"]} />
        </div>
      </div>

      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 12 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <ColHead>Audience</ColHead>
          <div style={{ display: "inline-flex", padding: 2, borderRadius: T.rMd, background: T.sunken, border: `1px solid ${T.borderSubtle}` }}>
            {(["ALL", "CUSTOMERS", "INTERNAL"] as Audience[]).map((t) => (
              <button
                key={t}
                onClick={() => setAudience(t)}
                style={{
                  font: `600 10.5px/1 ${T.mono}`,
                  letterSpacing: "0.05em",
                  padding: "6px 9px",
                  borderRadius: 5,
                  cursor: "pointer",
                  border: "none",
                  background: audience === t ? T.fg : "transparent",
                  color: audience === t ? "#fff" : T.tertiary,
                }}
              >
                {t}
              </button>
            ))}
          </div>
        </div>
        <Mono>
          {filtered.length} of {users.length}
        </Mono>
      </div>

      <div style={{ border: `1px solid ${T.borderSubtle}`, borderRadius: T.rLg, overflow: "visible", background: T.raised }}>
        <div
          style={{
            display: "grid",
            gridTemplateColumns: GRID,
            gap: 12,
            padding: "11px 18px",
            borderBottom: `1px solid ${T.borderSubtle}`,
            background: T.sunken,
            borderRadius: `${T.rLg} ${T.rLg} 0 0`,
          }}
        >
          <ColHead>User</ColHead>
          <ColHead>Organization</ColHead>
          <ColHead>Role</ColHead>
          <ColHead>Sign-in method</ColHead>
          <ColHead>Status</ColHead>
          <ColHead>Last active</ColHead>
          <ColHead>&nbsp;</ColHead>
        </div>
        {filtered.map((u, i) => (
          <div
            key={u.email}
            onClick={() => setDrawer(u)}
            style={{
              cursor: "pointer",
              display: "grid",
              gridTemplateColumns: GRID,
              gap: 12,
              padding: "13px 18px",
              alignItems: "center",
              borderTop: i ? `1px solid ${T.borderSubtle}` : "none",
            }}
            onMouseEnter={(e) => (e.currentTarget.style.background = T.sunken)}
            onMouseLeave={(e) => (e.currentTarget.style.background = T.raised)}
          >
            <span style={{ display: "flex", alignItems: "center", gap: 11, minWidth: 0 }}>
              <Avatar name={displayName(u)} size={30} internal={isInternal(u)} />
              <span style={{ minWidth: 0 }}>
                <span style={{ display: "flex", alignItems: "center", gap: 7 }}>
                  <span
                    style={{
                      font: `600 13.5px/1.2 ${T.sans}`,
                      color: T.fg,
                      whiteSpace: "nowrap",
                      overflow: "hidden",
                      textOverflow: "ellipsis",
                    }}
                  >
                    {displayName(u)}
                  </span>
                  {isInternal(u) && (
                    <span
                      style={{
                        font: `600 8px/1 ${T.mono}`,
                        letterSpacing: "0.06em",
                        color: "#7a3ea8",
                        background: "#f3e9fb",
                        padding: "2px 4px",
                        borderRadius: 3,
                      }}
                    >
                      STAFF
                    </span>
                  )}
                </span>
                <Mono style={{ fontSize: 10.5, color: T.tertiary, display: "block", marginTop: 2, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{u.email}</Mono>
              </span>
            </span>
            <span style={{ font: `400 12.5px/1.3 ${T.sans}`, color: T.secondary, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{u.org || "—"}</span>
            <RoleBadge role={displayRole(u)} />
            <MethodBadge method={userMethod(u)} />
            <span>
              <StatusCell status={u.status} />
            </span>
            <Mono style={{ fontSize: 10.5, whiteSpace: "nowrap" }}>{u.last_active ? fmtRel(u.last_active as number) : "—"}</Mono>
            <RowMenu user={u} sessionStaff={sessionStaff} onAct={act} />
          </div>
        ))}
        {!usersLoading && filtered.length === 0 && (
          <div style={{ padding: "44px 18px", textAlign: "center" }}>
            <Mono style={{ fontSize: 12, color: T.tertiary }}>No users match these filters.</Mono>
          </div>
        )}
      </div>

      {add && <AddUserModal onClose={() => setAdd(false)} onCreated={refresh} />}
      {drawer && <UserDrawer user={drawer} currentUserEmail={me?.email} onClose={() => setDrawer(null)} onChanged={refresh} />}
    </>
  );
}
