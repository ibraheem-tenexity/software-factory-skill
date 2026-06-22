import React from "react";
import { T } from "./tokens";
import { Icon } from "./primitives";
import { api } from "../api";
import type { AdminAgent, AdminClient, AdminTool } from "../api";
import { AdminClients, AdminProjectsView, AdminAgents, AdminTools, AdminOverview } from "./views";
import { InviteModal, AgentPromptPanel, ClientModal, AgentModal, ToolModal, ConfirmDelete } from "./modals";

const NAV_PATHS: Record<string, string> = {
  overview: "M3 3h7v7H3z M14 3h7v7h-7z M14 14h7v7h-7z M3 14h7v7H3z",
  clients:
    "M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2 M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8z M23 21v-2a4 4 0 0 0-3-3.87 M16 3.13a4 4 0 0 1 0 7.75",
  projects: "M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z",
  newproject: "M12 5v14 M5 12h14",
  agents:
    "M12 8V4H8 M4 8h16a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2v-8a2 2 0 0 1 2-2z M2 14h2 M20 14h2 M15 13v2 M9 13v2",
  tools: "M14.7 6.3a4 4 0 0 0 5 5l-9 9a2 2 0 0 1-3-3l9-9a4 4 0 0 0-2-2z",
  factories: "M2 20h20 M4 20V8l5 4V8l5 4V8l5 4v8",
  symphony: "M6 3v12 M18 9a3 3 0 1 0 0 6 3 3 0 0 0 0-6z M6 21a3 3 0 1 0 0-6 3 3 0 0 0 0 6z M18 9V3l-9 2",
  settings:
    "M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6z M19.4 15a1.6 1.6 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.6 1.6 0 0 0-2.7 1.1V21a2 2 0 1 1-4 0v-.1A1.6 1.6 0 0 0 6.6 19l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.6 1.6 0 0 0-1.1-2.7H2a2 2 0 1 1 0-4h.1A1.6 1.6 0 0 0 3.2 6.6l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.6 1.6 0 0 0 2.7-1.1V2a2 2 0 1 1 4 0v.1a1.6 1.6 0 0 0 2.7 1.1l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.6 1.6 0 0 0-.3 1.8",
};

function NavIcon({ name, size = 17, color = "currentColor" }: { name: keyof typeof NAV_PATHS; size?: number; color?: string }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke={color}
      strokeWidth={1.8}
      strokeLinecap="round"
      strokeLinejoin="round"
      style={{ flexShrink: 0 }}
    >
      {NAV_PATHS[name].split(" M").map((s, i) => (
        <path key={i} d={i === 0 ? s : `M${s}`} />
      ))}
    </svg>
  );
}

export function AdminPortal() {
  const [view, setView] = React.useState<string>("clients");
  const [agent, setAgent] = React.useState<AdminAgent | null>(null);
  const [agentModal, setAgentModal] = React.useState<AdminAgent | null | "new">(null);
  const [clientModal, setClientModal] = React.useState<AdminClient | null | "new">(null);
  const [toolModal, setToolModal] = React.useState<AdminTool | null | "new">(null);
  const [deleteTarget, setDeleteTarget] = React.useState<{ kind: "client" | "agent" | "tool"; item: AdminClient | AdminAgent | AdminTool } | null>(null);
  const [invite, setInvite] = React.useState(false);
  const [query, setQuery] = React.useState("");
  const [agentVersion, setAgentVersion] = React.useState(0);
  const [clientVersion, setClientVersion] = React.useState(0);
  const [toolVersion, setToolVersion] = React.useState(0);
  const searchRef = React.useRef<HTMLInputElement>(null);

  React.useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        searchRef.current?.focus();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const NAV = [
    { id: "overview", label: "Overview", icon: "overview" },
    { id: "clients", label: "Clients", icon: "clients" },
    { id: "projects", label: "Projects", icon: "projects" },
    { id: "newproject", label: "New Project", icon: "newproject" },
    { id: "agents", label: "Agents", icon: "agents" },
    { id: "tools", label: "Tools", icon: "tools" },
    { id: "factories", label: "Factories", icon: "factories" },
    { id: "settings", label: "Settings", icon: "settings" },
  ] as const;

  const pulse = [
    ["AGENTS_ACTIVE", "—"],
    ["TASKS_RUNNING", "—"],
    ["AVG_FRICTION", "—"],
    ["TODAY_BURN", "—"],
    ["PROJECTS", "—"],
  ];

  const handleDelete = () => {
    if (!deleteTarget) return;
    const { kind, item } = deleteTarget;
    let p: Promise<any>;
    if (kind === "client") p = api.adminDeleteClient((item as AdminClient).org_id);
    else if (kind === "agent") p = api.adminDeleteAgent((item as AdminAgent).callsign);
    else p = api.adminDeleteTool((item as AdminTool).name);
    p.then(() => {
      if (kind === "agent") setAgentVersion((v) => v + 1);
      if (kind === "client") setClientVersion((v) => v + 1);
      if (kind === "tool") setToolVersion((v) => v + 1);
      setDeleteTarget(null);
    }).catch(() => setDeleteTarget(null));
  };

  return (
    <>
      <style>{`
        html, body, #root { height: 100%; margin: 0; }
        body { font-family: ${T.sans}; background: ${T.bg}; color: ${T.fg}; font-size: 14px; -webkit-font-smoothing: antialiased; }
        @keyframes sfRise { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: none; } }
      `}</style>
      <div style={{ height: "100%", position: "relative", display: "flex", background: T.bg, fontFamily: T.sans }}>
        {/* sidebar */}
        <div
          style={{
            width: 210,
            flexShrink: 0,
            borderRight: `1px solid ${T.borderSubtle}`,
            background: T.raised,
            display: "flex",
            flexDirection: "column",
            padding: "18px 14px",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "0 8px 18px" }}>
            <span style={{ font: `700 18px/1 ${T.display}`, letterSpacing: "-0.01em", color: T.fg }}>Tenexity</span>
            <span
              style={{
                font: `600 9px/1 ${T.mono}`,
                letterSpacing: "0.1em",
                color: T.brandDeep,
                background: T.brandSoft,
                padding: "3px 5px",
                borderRadius: 3,
              }}
            >
              OS
            </span>
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 1 }}>
            {NAV.map((n) => {
              const on = view === n.id;
              return (
                <button
                  key={n.id}
                  onClick={() => setView(n.id)}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: 11,
                    padding: "9px 10px",
                    borderRadius: T.rMd,
                    width: "100%",
                    cursor: "pointer",
                    background: on ? T.brandSoft : "transparent",
                    border: "none",
                    textAlign: "left",
                    color: on ? T.brandDeep : T.secondary,
                    font: `${on ? 600 : 500} 13px/1 ${T.sans}`,
                  }}
                >
                  <NavIcon name={n.icon as keyof typeof NAV_PATHS} size={16} color={on ? T.brandDeep : T.tertiary} />
                  {n.label}
                </button>
              );
            })}
          </div>
          <div
            style={{
              marginTop: "auto",
              padding: 10,
              borderRadius: T.rMd,
              border: `1px solid ${T.borderSubtle}`,
              background: T.bg,
            }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: 7 }}>
              <span style={{ width: 6, height: 6, borderRadius: "50%", background: T.success }} />
              <span style={{ font: `500 10.5px/1 ${T.mono}`, letterSpacing: "0.04em", color: T.success }}>LINEAR · PHI</span>
            </div>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginTop: 6 }}>
              <span style={{ font: `500 10px/1 ${T.mono}`, letterSpacing: "0.04em", color: T.tertiary }}>Sys Status</span>
              <span style={{ font: `500 10px/1 ${T.mono}`, letterSpacing: "0.04em", color: T.success }}>Nominal</span>
            </div>
          </div>
        </div>

        {/* main */}
        <div style={{ flex: 1, minWidth: 0, display: "flex", flexDirection: "column" }}>
          {/* pulse bar */}
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: 26,
              padding: "12px 26px",
              borderBottom: `1px solid ${T.borderSubtle}`,
              background: T.raised,
              flexShrink: 0,
              flexWrap: "wrap",
            }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <span style={{ font: `600 10.5px/1 ${T.mono}`, letterSpacing: "0.08em", textTransform: "uppercase", color: T.tertiary }}>
                Factory Pulse
              </span>
              <span style={{ width: 7, height: 7, borderRadius: "50%", background: T.success }} />
            </div>
            {pulse.map(([k, v]) => (
              <span key={k} style={{ display: "inline-flex", alignItems: "baseline", gap: 6 }}>
                <span style={{ font: `500 11px/1 ${T.mono}`, letterSpacing: "0.04em", color: T.tertiary }}>{k}:</span>
                <span style={{ font: `600 12px/1 ${T.mono}`, color: T.fg }}>{v}</span>
              </span>
            ))}
          </div>
          {/* search row */}
          <div
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              gap: 12,
              padding: "14px 26px 0",
              flexShrink: 0,
            }}
          >
            <div
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: 8,
                height: 34,
                padding: "0 11px",
                borderRadius: T.rMd,
                border: `1px solid ${T.borderDefault}`,
                background: T.raised,
                width: 260,
              }}
            >
              <Icon name="search" size={14} color={T.tertiary} />
              <input
                ref={searchRef}
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Search…"
                style={{
                  flex: 1,
                  border: "none",
                  background: "transparent",
                  outline: "none",
                  font: `400 12.5px/1 ${T.sans}`,
                  color: T.fg,
                }}
              />
              <span
                style={{
                  font: `500 10px/1 ${T.mono}`,
                  color: T.tertiary,
                  border: `1px solid ${T.borderSubtle}`,
                  borderRadius: 4,
                  padding: "2px 4px",
                }}
              >
                ⌘K
              </span>
            </div>
            <button
              onClick={() => setInvite(true)}
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
                border: "1px solid transparent",
                background: T.brand,
                color: "#fff",
              }}
            >
              <Icon name="plus" size={14} color="#fff" /> Provide access
            </button>
          </div>
          {/* content */}
          <div style={{ flex: 1, overflow: "auto", padding: "20px 26px 36px" }}>
            {view === "overview" && <AdminOverview onNav={setView} query={query} />}
            {view === "clients" && (
              <AdminClients query={query} onNew={() => setClientModal("new")} onEdit={(c) => setClientModal(c)} onDelete={(c) => setDeleteTarget({ kind: "client", item: c })} />
            )}
            {(view === "projects" || view === "newproject") && <AdminProjectsView query={query} />}
            {view === "agents" && (
              <AdminAgents
                key={agentVersion}
                onOpen={setAgent}
                onNew={() => setAgentModal("new")}
                onEdit={(a) => setAgentModal(a)}
                onDelete={(a) => setDeleteTarget({ kind: "agent", item: a })}
                query={query}
              />
            )}
            {view === "tools" && (
              <AdminTools
                key={toolVersion}
                query={query}
                onNew={() => setToolModal("new")}
                onEdit={(t) => setToolModal(t)}
                onDelete={(t) => setDeleteTarget({ kind: "tool", item: t })}
                onRefresh={() => setToolVersion((v) => v + 1)}
              />
            )}
            {(view === "factories" || view === "settings") && (
              <div style={{ display: "grid", placeItems: "center", height: 320 }}>
                <div style={{ textAlign: "center" }}>
                  <span style={{ font: `500 12px/1 ${T.mono}`, letterSpacing: "0.08em", textTransform: "uppercase", color: T.tertiary, display: "block", marginBottom: 6 }}>
                    {view}
                  </span>
                  <span style={{ font: `400 14px/1.5 ${T.sans}`, color: T.tertiary }}>Module surface — out of scope for this prototype.</span>
                </div>
              </div>
            )}
          </div>
        </div>
        {agent && <AgentPromptPanel agent={agent} onClose={() => setAgent(null)} onSaved={() => setAgentVersion((v) => v + 1)} />}
        {invite && <InviteModal onClose={() => setInvite(false)} />}
        {agentModal && (
          <AgentModal
            agent={agentModal === "new" ? undefined : agentModal}
            onClose={() => setAgentModal(null)}
            onSaved={() => setAgentVersion((v) => v + 1)}
          />
        )}
        {clientModal && (
          <ClientModal
            client={clientModal === "new" ? undefined : clientModal}
            onClose={() => setClientModal(null)}
            onSaved={() => setClientVersion((v) => v + 1)}
          />
        )}
        {toolModal && (
          <ToolModal
            tool={toolModal === "new" ? undefined : toolModal}
            onClose={() => setToolModal(null)}
            onSaved={() => setToolVersion((v) => v + 1)}
          />
        )}
        {deleteTarget && (
          <ConfirmDelete
            title={`Delete ${deleteTarget.kind}`}
            detail={`Remove ${deleteTarget.kind === "client" ? (deleteTarget.item as AdminClient).name : deleteTarget.kind === "agent" ? (deleteTarget.item as AdminAgent).callsign : (deleteTarget.item as AdminTool).name}?`}
            onConfirm={handleDelete}
            onClose={() => setDeleteTarget(null)}
          />
        )}
      </div>
    </>
  );
}
