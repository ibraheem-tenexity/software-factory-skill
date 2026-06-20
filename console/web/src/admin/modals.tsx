import React from "react";
import { T } from "./tokens";
import { Icon, Sparkle, StatusPill, Field, TextInput, Btn } from "./primitives";
import { api } from "../api";
import type { AdminAgent, AdminTool, AdminClient, AdminAccessUser } from "../api";
import { useAdminFetch, fmtRel } from "./hooks";

const overlay: React.CSSProperties = {
  position: "absolute",
  inset: 0,
  zIndex: 60,
  background: "rgba(9,12,18,0.45)",
  display: "grid",
  placeItems: "center",
  padding: 28,
  animation: "sfRise .18s ease both",
};

const modalCard: React.CSSProperties = {
  width: "min(620px, 100%)",
  maxHeight: "100%",
  background: T.raised,
  borderRadius: T.rXl,
  boxShadow: T.shadowMd,
  display: "flex",
  flexDirection: "column",
  overflow: "hidden",
};

const modalHeader: React.CSSProperties = {
  display: "flex",
  alignItems: "center",
  justifyContent: "space-between",
  padding: "16px 20px",
  borderBottom: `1px solid ${T.borderSubtle}`,
};

const Mono = ({ children, style }: { children: React.ReactNode; style?: React.CSSProperties }) => (
  <span style={{ font: `500 11px/1 ${T.mono}`, letterSpacing: "0.04em", color: T.tertiary, ...style }}>{children}</span>
);

function CloseBtn({ onClick }: { onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      style={{
        width: 28,
        height: 28,
        display: "grid",
        placeItems: "center",
        borderRadius: T.rMd,
        border: "none",
        background: "transparent",
        color: T.tertiary,
        cursor: "pointer",
      }}
    >
      <Icon name="x" size={16} />
    </button>
  );
}

export function ConfirmDelete({
  title,
  detail,
  onConfirm,
  onClose,
}: {
  title: string;
  detail: string;
  onConfirm: () => void;
  onClose: () => void;
}) {
  return (
    <div style={overlay}>
      <div style={modalCard}>
        <div style={modalHeader}>
          <h2 style={{ font: `400 19px/1.2 ${T.display}`, color: T.fg, margin: 0 }}>{title}</h2>
          <CloseBtn onClick={onClose} />
        </div>
        <div style={{ padding: 18, display: "flex", flexDirection: "column", gap: 14 }}>
          <p style={{ margin: 0, font: `400 13px/1.5 ${T.sans}`, color: T.secondary }}>{detail}</p>
          <div style={{ display: "flex", gap: 10, justifyContent: "flex-end" }}>
            <Btn onClick={onClose}>Cancel</Btn>
            <Btn variant="danger" onClick={onConfirm}>
              Delete
            </Btn>
          </div>
        </div>
      </div>
    </div>
  );
}

export function AgentPromptPanel({ agent, onClose, onSaved }: { agent: AdminAgent; onClose: () => void; onSaved?: () => void }) {
  const { data: detail } = useAdminFetch(() => api.adminAgent(agent.callsign));
  const [prompt, setPrompt] = React.useState(agent.prompt || "");
  const [tab, setTab] = React.useState<"prompt" | "tools" | "activity">("prompt");
  const [saving, setSaving] = React.useState(false);
  const [appliedNote, setAppliedNote] = React.useState<string | null>(null);
  React.useEffect(() => {
    if (detail?.prompt) setPrompt(detail.prompt);
  }, [detail?.prompt]);
  const dirty = prompt !== (detail?.prompt || agent.prompt || "");
  const active = detail ?? agent;
  const save = () => {
    setSaving(true);
    api
      .adminPatchAgentPrompt(agent.callsign, prompt)
      .then((res) => {
        setSaving(false);
        setAppliedNote(res.applied ? "saved & applied" : "saved — not yet applied to live agents");
        onSaved?.();
      })
      .catch(() => setSaving(false));
  };
  return (
    <div
      onClick={onClose}
      style={{
        position: "absolute",
        inset: 0,
        zIndex: 60,
        background: "rgba(9,12,18,0.45)",
        display: "flex",
        justifyContent: "flex-end",
        animation: "sfRise .18s ease both",
      }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          width: "min(560px, 100%)",
          height: "100%",
          background: T.raised,
          boxShadow: T.shadowMd,
          display: "flex",
          flexDirection: "column",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "16px 20px", borderBottom: `1px solid ${T.borderSubtle}` }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <span style={{ font: `600 16px/1.2 ${T.sans}`, color: T.fg }}>{active.role}</span>
            <span style={{ width: 7, height: 7, borderRadius: "50%", background: active.on ? T.success : T.borderDefault }} />
            <span
              style={{
                font: `600 9.5px/1 ${T.mono}`,
                color: T.secondary,
                background: T.sunken,
                border: `1px solid ${T.borderSubtle}`,
                padding: "4px 5px",
                borderRadius: 4,
              }}
            >
              {active.callsign}
            </span>
          </div>
          <CloseBtn onClick={onClose} />
        </div>
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(3, 1fr)",
            gap: 1,
            background: T.borderSubtle,
            borderBottom: `1px solid ${T.borderSubtle}`,
          }}
        >
          {[
            ["Model", active.model],
            ["Callsign", active.sign],
            ["Success", `${active.success}%`],
          ].map(([k, v]) => (
            <div key={k} style={{ background: T.raised, padding: "11px 16px" }}>
              <Mono style={{ display: "block", marginBottom: 4 }}>{k}</Mono>
              <Mono style={{ color: T.fg, fontSize: 12.5 }}>{v}</Mono>
            </div>
          ))}
        </div>
        <div style={{ display: "flex", gap: 2, padding: "8px 16px 0" }}>
          {[
            { id: "prompt", l: "System prompt" },
            { id: "tools", l: "Tools" },
            { id: "activity", l: "Activity" },
          ].map((t) => {
            const on = tab === (t.id as typeof tab);
            return (
              <button
                key={t.id}
                onClick={() => setTab(t.id as typeof tab)}
                style={{
                  position: "relative",
                  padding: "9px 12px",
                  background: "none",
                  border: "none",
                  cursor: "pointer",
                  font: `${on ? 600 : 500} 12.5px/1 ${T.sans}`,
                  color: on ? T.fg : T.tertiary,
                }}
              >
                {t.l}
                {on && <span style={{ position: "absolute", left: 8, right: 8, bottom: -1, height: 2, background: T.brand }} />}
              </button>
            );
          })}
        </div>
        <div style={{ flex: 1, overflow: "auto", padding: "16px 20px" }}>
          {tab === "prompt" && (
            <>
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 8 }}>
                <Mono>System prompt</Mono>
                <button
                  style={{
                    display: "inline-flex",
                    alignItems: "center",
                    gap: 5,
                    font: `500 11px/1 ${T.sans}`,
                    color: T.brandDeep,
                    background: "none",
                    border: "none",
                    cursor: "pointer",
                  }}
                >
                  <Sparkle size={10} color={T.brandDeep} /> Suggest improvements
                </button>
              </div>
              <textarea
                value={prompt}
                onChange={(e) => setPrompt(e.target.value)}
                style={{
                  width: "100%",
                  boxSizing: "border-box",
                  minHeight: 280,
                  padding: "13px 15px",
                  borderRadius: T.rMd,
                  resize: "vertical",
                  border: `1px solid ${T.borderDefault}`,
                  background: T.bg,
                  color: T.fg,
                  font: `400 13px/1.65 ${T.mono}`,
                  outline: "none",
                }}
              />
              <Mono style={{ fontSize: 10.5, marginTop: 8, display: "block" }}>
                {prompt.length} chars{detail?.prompt_version ? ` · version ${detail.prompt_version}` : ""}
                {appliedNote ? ` · ${appliedNote}` : ""}
              </Mono>
            </>
          )}
          {tab === "tools" && (
            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              <Mono style={{ marginBottom: 2, display: "block" }}>Tools available to {active.sign}</Mono>
              {(detail?.tools ?? []).map((t) => (
                <div
                  key={t.name}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: 10,
                    padding: "10px 12px",
                    borderRadius: T.rMd,
                    border: `1px solid ${T.borderSubtle}`,
                    background: T.bg,
                  }}
                >
                  <span
                    style={{
                      font: `600 9px/1 ${T.mono}`,
                      color: T.brandDeep,
                      background: T.brandSoft,
                      padding: "3px 5px",
                      borderRadius: 3,
                    }}
                  >
                    {t.type || "MCP"}
                  </span>
                  <span style={{ flex: 1, font: `500 13px/1.2 ${T.sans}`, color: T.fg }}>{t.name}</span>
                  <Mono style={{ fontSize: 10.5 }}>{t.scope}</Mono>
                </div>
              ))}
              {(detail?.tools ?? []).length === 0 && <Mono>No tools listed.</Mono>}
            </div>
          )}
          {tab === "activity" && (
            <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              {(detail?.activity ?? []).map((r, i, arr) => (
                <div
                  key={i}
                  style={{
                    display: "flex",
                    gap: 10,
                    paddingBottom: 10,
                    borderBottom: i < arr.length - 1 ? `1px solid ${T.borderSubtle}` : "none",
                  }}
                >
                  <span style={{ marginTop: 5, width: 6, height: 6, borderRadius: "50%", background: T.brand, flexShrink: 0 }} />
                  <span style={{ flex: 1, font: `400 13px/1.4 ${T.sans}`, color: T.secondary }}>{r.text}</span>
                  <Mono style={{ fontSize: 10.5 }}>{fmtRel(r.ts)}</Mono>
                </div>
              ))}
              {(detail?.activity ?? []).length === 0 && <Mono>No recent activity.</Mono>}
            </div>
          )}
        </div>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "13px 20px", borderTop: `1px solid ${T.borderSubtle}` }}>
          <span style={{ display: "inline-flex", alignItems: "center", gap: 7 }}>
            <span style={{ width: 7, height: 7, borderRadius: "50%", background: active.on ? T.success : T.borderDefault }} />
            <Mono style={{ fontSize: 11.5 }}>{active.on ? "active" : "idle"}</Mono>
          </span>
          <div style={{ display: "flex", gap: 9 }}>
            <Btn onClick={onClose}>Cancel</Btn>
            <Btn variant="primary" onClick={save} disabled={!dirty || saving}>
              {saving ? "Saving…" : dirty ? "Save prompt" : "Saved"}
            </Btn>
          </div>
        </div>
      </div>
    </div>
  );
}

export function ClientModal({
  client,
  onClose,
  onSaved,
}: {
  client?: AdminClient;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [name, setName] = React.useState(client?.name ?? "");
  const [initials, setInitials] = React.useState(client?.initials ?? "");
  const [projects, setProjects] = React.useState(String(client?.projects ?? 0));
  const [tickets, setTickets] = React.useState(String(client?.tickets ?? 0));
  const [spend, setSpend] = React.useState(client?.spend ?? "$0.00");
  const [last, setLast] = React.useState(client?.last_activity ?? "");
  const [busy, setBusy] = React.useState(false);
  const save = () => {
    const body = {
      name,
      initials: initials || name.slice(0, 2).toUpperCase(),
      projects: Number(projects) || 0,
      tickets: Number(tickets) || 0,
      spend,
      last_activity: last,
    };
    setBusy(true);
    const p = client
      ? api.adminUpdateClient(client.org_id, body)
      : api.adminCreateClient(body as any);
    p.then(() => {
      setBusy(false);
      onSaved();
      onClose();
    }).catch(() => setBusy(false));
  };
  return (
    <div style={overlay}>
      <div style={modalCard}>
        <div style={modalHeader}>
          <h2 style={{ font: `400 19px/1.2 ${T.display}`, color: T.fg, margin: 0 }}>{client ? "Edit client" : "New client"}</h2>
          <CloseBtn onClick={onClose} />
        </div>
        <div style={{ padding: "18px 20px", display: "flex", flexDirection: "column", gap: 14, overflow: "auto" }}>
          <Field label="Organization name">
            <TextInput value={name} onChange={setName} placeholder="Acme Industrial Supply" />
          </Field>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
            <Field label="Initials">
              <TextInput value={initials} onChange={setInitials} placeholder="AC" />
            </Field>
            <Field label="Total spend">
              <TextInput value={spend} onChange={setSpend} placeholder="$0.00" />
            </Field>
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
            <Field label="Active projects">
              <TextInput type="number" value={projects} onChange={setProjects} />
            </Field>
            <Field label="In-flight tickets">
              <TextInput type="number" value={tickets} onChange={setTickets} />
            </Field>
          </div>
          <Field label="Last activity">
            <TextInput value={last} onChange={setLast} placeholder="—" />
          </Field>
          <div style={{ display: "flex", justifyContent: "flex-end", gap: 10, marginTop: 4 }}>
            <Btn onClick={onClose}>Cancel</Btn>
            <Btn variant="primary" onClick={save} disabled={!name || busy}>
              {busy ? "Saving…" : client ? "Save" : "Create"}
            </Btn>
          </div>
        </div>
      </div>
    </div>
  );
}

export function AgentModal({
  agent,
  onClose,
  onSaved,
}: {
  agent?: AdminAgent;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [callsign, setCallsign] = React.useState(agent?.callsign ?? "");
  const [sign, setSign] = React.useState(agent?.sign ?? "");
  const [role, setRole] = React.useState(agent?.role ?? "");
  const [desc, setDesc] = React.useState(agent?.desc ?? "");
  const [model, setModel] = React.useState(agent?.model ?? "");
  const [cost, setCost] = React.useState(String(agent?.cost_tier ?? 2));
  const [success, setSuccess] = React.useState(String(agent?.success ?? 90));
  const [on, setOn] = React.useState(agent?.on ?? true);
  const [busy, setBusy] = React.useState(false);
  const save = () => {
    const body: any = {
      callsign,
      sign,
      role,
      desc,
      model,
      cost_tier: Number(cost) || 2,
      success: Number(success) || 90,
      on,
    };
    setBusy(true);
    const p = agent ? api.adminUpdateAgent(agent.callsign, body) : api.adminCreateAgent(body);
    p.then(() => {
      setBusy(false);
      onSaved();
      onClose();
    }).catch(() => setBusy(false));
  };
  return (
    <div style={overlay}>
      <div style={modalCard}>
        <div style={modalHeader}>
          <h2 style={{ font: `400 19px/1.2 ${T.display}`, color: T.fg, margin: 0 }}>{agent ? "Edit agent" : "New agent"}</h2>
          <CloseBtn onClick={onClose} />
        </div>
        <div style={{ padding: "18px 20px", display: "flex", flexDirection: "column", gap: 14, overflow: "auto" }}>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
            <Field label="Callsign">
              <TextInput value={callsign} onChange={setCallsign} placeholder="AGENT.ROLE" disabled={!!agent} />
            </Field>
            <Field label="Sign / codename">
              <TextInput value={sign} onChange={setSign} placeholder="CODENAME" />
            </Field>
          </div>
          <Field label="Role / display name">
            <TextInput value={role} onChange={setRole} placeholder="e.g. Design Lead" />
          </Field>
          <Field label="Description">
            <TextInput value={desc} onChange={setDesc} placeholder="Short responsibility summary" />
          </Field>
          <div style={{ display: "grid", gridTemplateColumns: "2fr 1fr 1fr", gap: 12 }}>
            <Field label="Model">
              <TextInput value={model} onChange={setModel} placeholder="claude-sonnet-4" />
            </Field>
            <Field label="Cost tier (1-3)">
              <TextInput type="number" value={cost} onChange={setCost} />
            </Field>
            <Field label="Success %">
              <TextInput type="number" value={success} onChange={setSuccess} />
            </Field>
          </div>
          <label style={{ display: "flex", alignItems: "center", gap: 8, font: `500 13px/1 ${T.sans}`, color: T.fg }}>
            <input type="checkbox" checked={on} onChange={(e) => setOn(e.target.checked)} />
            Active
          </label>
          <div style={{ display: "flex", justifyContent: "flex-end", gap: 10, marginTop: 4 }}>
            <Btn onClick={onClose}>Cancel</Btn>
            <Btn variant="primary" onClick={save} disabled={!callsign || !role || busy}>
              {busy ? "Saving…" : agent ? "Save" : "Create"}
            </Btn>
          </div>
        </div>
      </div>
    </div>
  );
}

export function ToolModal({
  tool,
  onClose,
  onSaved,
}: {
  tool?: AdminTool;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [name, setName] = React.useState(tool?.name ?? "");
  const [type, setType] = React.useState<AdminTool["type"]>(tool?.type ?? "MCP");
  const [provider, setProvider] = React.useState(tool?.provider ?? "");
  const [scope, setScope] = React.useState(tool?.scope ?? "");
  const [auth, setAuth] = React.useState(tool?.auth ?? "");
  const [status, setStatus] = React.useState(tool?.status ?? "available");
  const [busy, setBusy] = React.useState(false);
  const save = () => {
    const body: any = { name, type, provider, scope, auth, status };
    setBusy(true);
    const p = tool ? api.adminUpdateTool(tool.name, body) : api.adminCreateTool(body);
    p.then(() => {
      setBusy(false);
      onSaved();
      onClose();
    }).catch(() => setBusy(false));
  };
  return (
    <div style={overlay}>
      <div style={modalCard}>
        <div style={modalHeader}>
          <h2 style={{ font: `400 19px/1.2 ${T.display}`, color: T.fg, margin: 0 }}>{tool ? "Edit tool" : "Register tool"}</h2>
          <CloseBtn onClick={onClose} />
        </div>
        <div style={{ padding: "18px 20px", display: "flex", flexDirection: "column", gap: 14, overflow: "auto" }}>
          <Field label="Tool / server name">
            <TextInput value={name} onChange={setName} placeholder="e.g. Supabase" disabled={!!tool} />
          </Field>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
            <Field label="Type">
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  height: 36,
                  borderRadius: T.rMd,
                  border: `1px solid ${T.borderDefault}`,
                  background: T.raised,
                  position: "relative",
                }}
              >
                <select
                  value={type}
                  onChange={(e) => setType(e.target.value as AdminTool["type"])}
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
                  <option>MCP</option>
                  <option>API</option>
                  <option>native</option>
                  <option>HTTP</option>
                </select>
                <Icon name="chevronDown" size={14} color={T.tertiary} style={{ position: "absolute", right: 9, pointerEvents: "none" }} />
              </div>
            </Field>
            <Field label="Status">
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  height: 36,
                  borderRadius: T.rMd,
                  border: `1px solid ${T.borderDefault}`,
                  background: T.raised,
                  position: "relative",
                }}
              >
                <select
                  value={status}
                  onChange={(e) => setStatus(e.target.value as AdminTool["status"])}
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
                  <option value="connected">connected</option>
                  <option value="available">available</option>
                </select>
                <Icon name="chevronDown" size={14} color={T.tertiary} style={{ position: "absolute", right: 9, pointerEvents: "none" }} />
              </div>
            </Field>
          </div>
          <Field label="Provider">
            <TextInput value={provider} onChange={setProvider} placeholder="Supabase" />
          </Field>
          <Field label="Scope">
            <TextInput value={scope} onChange={setScope} placeholder="postgres · auth · storage" />
          </Field>
          <Field label="Auth">
            <TextInput value={auth} onChange={setAuth} placeholder="service key" />
          </Field>
          <div style={{ display: "flex", justifyContent: "flex-end", gap: 10, marginTop: 4 }}>
            <Btn onClick={onClose}>Cancel</Btn>
            <Btn variant="primary" onClick={save} disabled={!name || !provider || busy}>
              {busy ? "Saving…" : tool ? "Save" : "Register"}
            </Btn>
          </div>
        </div>
      </div>
    </div>
  );
}

export function InviteModal({ onClose }: { onClose: () => void }) {
  const [email, setEmail] = React.useState("");
  const [type, setType] = React.useState<"org" | "tenexity">("org");
  const [orgName, setOrgName] = React.useState("");
  const { data, refetch } = useAdminFetch(() => api.adminAccess());
  const list = data?.users ?? [];
  const valid = /\S+@\S+\.\S+/.test(email);
  const send = () => {
    if (!valid) return;
    api
      .adminInvite({ email, access_type: type, org_name: type === "org" ? orgName : undefined })
      .then((res) => {
        setEmail("");
        setOrgName("");
        // reflect server response if provided, else refetch
        if (res.users) refetch();
      })
      .catch(() => {
        // Graceful: keep invite visible
      });
  };
  const revoke = (email: string) => {
    api
      .adminDeleteAccess(email)
      .then(() => refetch())
      .catch(() => {});
  };
  return (
    <div style={overlay}>
      <div style={modalCard}>
        <div style={modalHeader}>
          <div>
            <h2 style={{ font: `400 19px/1.2 ${T.display}`, color: T.fg, margin: 0 }}>Provide access</h2>
            <Mono style={{ fontSize: 11, marginTop: 4, display: "block" }}>Add a person to the sign-in allow-list</Mono>
          </div>
          <CloseBtn onClick={onClose} />
        </div>
        <div style={{ padding: "18px 20px", display: "flex", flexDirection: "column", gap: 14 }}>
          <div style={{ display: "flex", gap: 10, alignItems: "flex-end" }}>
            <Field label="Email address" style={{ flex: 1 }}>
              <TextInput type="email" value={email} onChange={setEmail} placeholder="person@company.com" mono />
            </Field>
            <Field label="Access type" style={{ width: 150, flexShrink: 0 }}>
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  height: 36,
                  borderRadius: T.rMd,
                  border: `1px solid ${T.borderDefault}`,
                  background: T.raised,
                  position: "relative",
                }}
              >
                <select
                  value={type}
                  onChange={(e) => setType(e.target.value as typeof type)}
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
                  <option value="org">New org</option>
                  <option value="tenexity">Tenexity</option>
                </select>
                <Icon name="chevronDown" size={14} color={T.tertiary} style={{ position: "absolute", right: 9, pointerEvents: "none" }} />
              </div>
            </Field>
          </div>
          {type === "org" ? (
            <Field label="Organization name" hint="They’ll be created as the admin of this new organization.">
              <TextInput value={orgName} onChange={setOrgName} placeholder="e.g. Northwind Supply Co." />
            </Field>
          ) : (
            <div
              style={{
                display: "flex",
                alignItems: "center",
                gap: 9,
                padding: "11px 13px",
                borderRadius: T.rMd,
                background: `${T.brandSoft}66`,
                border: `1px solid ${T.brand}33`,
              }}
            >
              <Sparkle size={12} color={T.brandDeep} />
              <span style={{ font: `400 12.5px/1.4 ${T.sans}`, color: T.secondary }}>
                Internal <b style={{ color: T.fg }}>Tenexity operator</b> — full access to every tenant, project, and agent.
              </span>
            </div>
          )}
          <div
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              padding: "10px 12px",
              borderRadius: T.rMd,
              background: T.sunken,
              border: `1px solid ${T.borderSubtle}`,
            }}
          >
            <Mono style={{ fontSize: 11 }}>
              {type === "org" ? "Becomes ORG ADMIN · email added to allow-list" : "Added to allow-list as OPERATOR"}
            </Mono>
            <Btn variant="primary" onClick={send} disabled={!valid}>
              Send invite
            </Btn>
          </div>
        </div>
        <div style={{ borderTop: `1px solid ${T.borderSubtle}`, overflow: "auto" }}>
          <div
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              padding: "11px 20px",
              background: T.sunken,
              borderBottom: `1px solid ${T.borderSubtle}`,
            }}
          >
            <Mono style={{ fontSize: 10.5, color: T.tertiary }}>ALLOWED SIGN-INS</Mono>
            <Mono style={{ fontSize: 10.5 }}>{list.length}</Mono>
          </div>
          {list.map((u, i) => (
            <div
              key={u.email + i}
              style={{
                display: "grid",
                gridTemplateColumns: "minmax(0,1fr) 130px 90px 80px 60px",
                gap: 10,
                alignItems: "center",
                padding: "11px 20px",
                borderTop: i ? `1px solid ${T.borderSubtle}` : "none",
              }}
            >
              <span
                style={{
                  font: `500 12.5px/1.2 ${T.mono}`,
                  color: T.fg,
                  whiteSpace: "nowrap",
                  overflow: "hidden",
                  textOverflow: "ellipsis",
                }}
              >
                {u.email}
              </span>
              <span
                style={{
                  font: `400 12px/1.2 ${T.sans}`,
                  color: T.secondary,
                  whiteSpace: "nowrap",
                  overflow: "hidden",
                  textOverflow: "ellipsis",
                }}
              >
                {u.org}
              </span>
              <span
                style={{
                  font: `600 9.5px/1 ${T.mono}`,
                  letterSpacing: "0.04em",
                  color: u.type === "Tenexity" ? "#7a3ea8" : T.brandDeep,
                  background: u.type === "Tenexity" ? "#f3e9fb" : T.brandSoft,
                  padding: "4px 6px",
                  borderRadius: 4,
                  justifySelf: "start",
                }}
              >
                {u.role}
              </span>
              <span style={{ justifySelf: "end" }}>
                <StatusPill tone={u.status === "active" ? "success" : "warning"} dot={u.status === "active"}>
                  {u.status}
                </StatusPill>
              </span>
              <button
                onClick={() => revoke(u.email)}
                style={{ justifySelf: "end", font: `500 11px/1 ${T.mono}`, color: T.danger, background: "none", border: "none", cursor: "pointer" }}
              >
                Revoke
              </button>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
