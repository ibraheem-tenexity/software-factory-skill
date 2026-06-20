import React from "react";
import { T } from "./tokens";
import { Icon, Sparkle, StatusPill, MetricCard } from "./primitives";
import { api } from "../api";
import type { AdminAgent, AdminProjectRow, AdminClient, AdminTool } from "../api";
import { useAdminFetch, fmtRel } from "./hooks";

const PHASE_TONE: Record<string, "info" | "warning" | "brand" | "neutral" | "success"> = {
  REVIEW: "info",
  PLANNING: "warning",
  BUILDING: "brand",
  TRIAGE: "neutral",
  INTAKE: "neutral",
  LIVE: "success",
};

function Mono({ children, style }: { children: React.ReactNode; style?: React.CSSProperties }) {
  return (
    <span style={{ font: `500 11px/1 ${T.mono}`, letterSpacing: "0.04em", color: T.tertiary, ...style }}>
      {children}
    </span>
  );
}

function ColHead({ children, style }: { children: React.ReactNode; style?: React.CSSProperties }) {
  return (
    <span
      style={{
        font: `600 10.5px/1 ${T.mono}`,
        letterSpacing: "0.08em",
        textTransform: "uppercase",
        color: T.tertiary,
        ...style,
      }}
    >
      {children}
    </span>
  );
}

function InitSquare({ t }: { t: string }) {
  return (
    <span
      style={{
        width: 28,
        height: 28,
        flexShrink: 0,
        borderRadius: 6,
        display: "grid",
        placeItems: "center",
        border: `1px solid ${T.borderSubtle}`,
        background: T.sunken,
        font: `600 10px/1 ${T.mono}`,
        color: T.secondary,
      }}
    >
      {t}
    </span>
  );
}

function PhasePill({ phase }: { phase: string }) {
  const tone = PHASE_TONE[phase] || "neutral";
  const colors: Record<string, [string, string]> = {
    info: [T.brandSoft, T.brandDeep],
    warning: [T.warningSoft, T.warning],
    brand: [T.brandSoft, T.brandDeep],
    neutral: [T.sunken, T.secondary],
    success: [T.successSoft, T.success],
  };
  const [bg, fg] = colors[tone];
  return (
    <span
      style={{
        font: `600 10px/1 ${T.mono}`,
        letterSpacing: "0.06em",
        color: fg,
        background: bg,
        border: `1px solid ${fg}22`,
        padding: "4px 7px",
        borderRadius: 4,
      }}
    >
      {phase}
    </span>
  );
}

function AdminBtn({ children, primary, onClick }: { children: React.ReactNode; primary?: boolean; onClick?: () => void }) {
  return (
    <button
      onClick={onClick}
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
        border: `1px solid ${primary ? "transparent" : T.borderDefault}`,
        background: primary ? T.brand : T.raised,
        color: primary ? "#fff" : T.fg,
      }}
    >
      {children}
    </button>
  );
}

function PageTitle({ title, sub, actions }: { title: string; sub: string; actions?: React.ReactNode }) {
  return (
    <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 16, marginBottom: 22 }}>
      <div>
        <h1 style={{ font: `400 30px/1.1 ${T.display}`, letterSpacing: "-0.01em", color: T.fg, margin: 0 }}>{title}</h1>
        <p style={{ font: `400 13px/1.5 ${T.mono}`, color: T.tertiary, margin: "8px 0 0" }}>{sub}</p>
      </div>
      <div style={{ display: "flex", gap: 10 }}>{actions}</div>
    </div>
  );
}

function CostDots({ n }: { n: number }) {
  return (
    <span style={{ display: "inline-flex", gap: 2 }}>
      {[0, 1, 2].map((i) => (
        <span key={i} style={{ width: 5, height: 5, borderRadius: "50%", background: i < n ? T.fg : T.borderDefault }} />
      ))}
    </span>
  );
}

function MiniBar({ pct }: { pct: number }) {
  return (
    <span style={{ display: "block", height: 4, borderRadius: 2, background: T.sunken, overflow: "hidden" }}>
      <span style={{ display: "block", height: "100%", width: `${pct}%`, background: T.success }} />
    </span>
  );
}

function AdminFilter({ children, w = 150 }: { children: React.ReactNode; w?: number }) {
  return (
    <div
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 7,
        height: 36,
        padding: "0 11px",
        width: w,
        justifyContent: "space-between",
        borderRadius: T.rMd,
        border: `1px solid ${T.borderDefault}`,
        background: T.raised,
        font: `500 12px/1 ${T.sans}`,
        color: T.secondary,
        cursor: "pointer",
      }}
    >
      {children}
      <Icon name="chevronDown" size={13} color={T.tertiary} />
    </div>
  );
}

export function AdminClients({
  query,
  onNew,
  onEdit,
  onDelete,
}: {
  query: string;
  onNew: () => void;
  onEdit: (c: AdminClient) => void;
  onDelete: (c: AdminClient) => void;
}) {
  const { data } = useAdminFetch(() => api.adminClients());
  const clients = React.useMemo(() => {
    const list = data?.clients ?? [];
    const q = query.trim().toLowerCase();
    if (!q) return list;
    return list.filter(
      (c) =>
        c.name.toLowerCase().includes(q) ||
        c.initials.toLowerCase().includes(q) ||
        c.last_activity.toLowerCase().includes(q)
    );
  }, [data, query]);
  return (
    <>
      <PageTitle
        title="Clients"
        sub="Customers and their portfolios of factory projects."
        actions={
          <>
            <AdminBtn>{String.fromCharCode(8644)} Import from Asana</AdminBtn>
            <AdminBtn primary onClick={onNew}>
              + New client
            </AdminBtn>
          </>
        }
      />
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 12,
          padding: "12px 16px",
          borderRadius: T.rLg,
          border: `1px solid ${T.warning}55`,
          background: `${T.warningSoft}66`,
          marginBottom: 20,
        }}
      >
        <span style={{ width: 7, height: 7, borderRadius: "50%", background: T.warning }} />
        <span style={{ font: `600 12px/1.3 ${T.sans}`, color: T.fg }}>
          Asana · <span style={{ color: T.warning, fontFamily: T.mono }}>ERROR</span>
        </span>
        <span
          style={{
            flex: 1,
            font: `400 11.5px/1.3 ${T.mono}`,
            color: T.tertiary,
            whiteSpace: "nowrap",
            overflow: "hidden",
            textOverflow: "ellipsis",
          }}
        >
          Asana 401: Not Authorized — reconnect to resume portfolio sync.
        </span>
        <button
          style={{
            font: `600 11px/1 ${T.mono}`,
            color: T.brandDeep,
            background: "none",
            border: "none",
            cursor: "pointer",
          }}
        >
          CONNECT →
        </button>
      </div>
      <div style={{ border: `1px solid ${T.borderSubtle}`, borderRadius: T.rLg, overflow: "hidden", background: T.raised }}>
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "minmax(0,1fr) 130px 140px 130px 130px 100px",
            gap: 16,
            padding: "11px 18px",
            borderBottom: `1px solid ${T.borderSubtle}`,
            background: T.sunken,
          }}
        >
          <ColHead>Client</ColHead>
          <ColHead>Active projects</ColHead>
          <ColHead>In-flight tickets</ColHead>
          <ColHead>Total spend</ColHead>
          <ColHead style={{ textAlign: "right" }}>Last activity</ColHead>
          <ColHead style={{ textAlign: "right" }}>Actions</ColHead>
        </div>
        {clients.map((c, i) => (
          <div
            key={c.org_id}
            style={{
              background: T.raised,
              borderTop: i ? `1px solid ${T.borderSubtle}` : "none",
              display: "grid",
              gridTemplateColumns: "minmax(0,1fr) 130px 140px 130px 130px 100px",
              gap: 16,
              padding: "14px 18px",
              alignItems: "center",
            }}
          >
            <span style={{ display: "flex", alignItems: "center", gap: 11, minWidth: 0 }}>
              <InitSquare t={c.initials} />
              <span
                style={{
                  font: `600 14px/1.2 ${T.sans}`,
                  color: T.fg,
                  whiteSpace: "nowrap",
                  overflow: "hidden",
                  textOverflow: "ellipsis",
                }}
              >
                {c.name}
              </span>
            </span>
            <Mono style={{ color: T.fg, fontSize: 13 }}>{c.projects}</Mono>
            <Mono style={{ color: T.fg, fontSize: 13 }}>{c.tickets}</Mono>
            <Mono style={{ color: T.fg, fontSize: 13 }}>{c.spend}</Mono>
            <Mono style={{ textAlign: "right" }}>{c.last_activity}</Mono>
            <span style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
              <button
                onClick={() => onEdit(c)}
                style={{
                  font: `500 11px/1 ${T.mono}`,
                  color: T.brandDeep,
                  background: "none",
                  border: "none",
                  cursor: "pointer",
                }}
              >
                Edit
              </button>
              <button
                onClick={() => onDelete(c)}
                style={{
                  font: `500 11px/1 ${T.mono}`,
                  color: T.danger,
                  background: "none",
                  border: "none",
                  cursor: "pointer",
                }}
              >
                ×
              </button>
            </span>
          </div>
        ))}
      </div>
    </>
  );
}

export function AdminProjectsView({ query }: { query: string }) {
  const [type, setType] = React.useState<"ALL PROJECTS" | "REAL" | "DEMO/FAKE">("REAL");
  const mode: "all" | "real" | "demo" =
    type === "ALL PROJECTS" ? "all" : type === "REAL" ? "real" : "demo";
  const { data } = useAdminFetch(() => api.adminProjects(mode));
  const filtered = React.useMemo(() => {
    const list = data?.projects ?? [];
    const q = query.trim().toLowerCase();
    if (!q) return list;
    return list.filter(
      (p) =>
        p.name.toLowerCase().includes(q) ||
        p.client.toLowerCase().includes(q) ||
        p.factory.toLowerCase().includes(q) ||
        p.phase.toLowerCase().includes(q)
    );
  }, [data, query]);
  const total = (data?.projects ?? []).length;
  return (
    <>
      <PageTitle
        title="Projects"
        sub="Every project across every client and factory pipeline."
        actions={<AdminBtn primary>+ New project</AdminBtn>}
      />
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
          <span style={{ font: `400 12.5px/1 ${T.sans}`, color: T.tertiary }}>Search name, client, factory…</span>
        </div>
        <AdminFilter>All clients</AdminFilter>
        <AdminFilter>All factories</AdminFilter>
        <AdminFilter w={130}>All statuses</AdminFilter>
        <AdminFilter w={130}>All modes</AdminFilter>
      </div>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 12 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <ColHead>Project type</ColHead>
          <div
            style={{
              display: "inline-flex",
              padding: 2,
              borderRadius: T.rMd,
              background: T.sunken,
              border: `1px solid ${T.borderSubtle}`,
            }}
          >
            {["ALL PROJECTS", "REAL", "DEMO/FAKE"].map((t) => (
              <button
                key={t}
                onClick={() => setType(t as typeof type)}
                style={{
                  font: `600 10.5px/1 ${T.mono}`,
                  letterSpacing: "0.05em",
                  padding: "6px 9px",
                  borderRadius: 5,
                  cursor: "pointer",
                  border: "none",
                  background: type === t ? T.fg : "transparent",
                  color: type === t ? "#fff" : T.tertiary,
                }}
              >
                {t}
              </button>
            ))}
          </div>
        </div>
        <Mono>
          {filtered.length} of {total}
        </Mono>
      </div>
      <div style={{ border: `1px solid ${T.borderSubtle}`, borderRadius: T.rLg, overflow: "hidden", background: T.raised }}>
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "minmax(0,1.5fr) minmax(0,1.1fr) 130px 92px 64px 48px 56px 110px",
            gap: 12,
            padding: "11px 18px",
            borderBottom: `1px solid ${T.borderSubtle}`,
            background: T.sunken,
          }}
        >
          <ColHead>Project</ColHead>
          <ColHead>Client</ColHead>
          <ColHead>Factory</ColHead>
          <ColHead>Phase</ColHead>
          <ColHead>Tasks</ColHead>
          <ColHead>F</ColHead>
          <ColHead>Auto</ColHead>
          <ColHead style={{ textAlign: "right" }}>Last activity</ColHead>
        </div>
        {filtered.map((p, i) => (
          <div
            key={p.run_id}
            style={{
              background: T.raised,
              borderTop: i ? `1px solid ${T.borderSubtle}` : "none",
              display: "grid",
              gridTemplateColumns: "minmax(0,1.5fr) minmax(0,1.1fr) 130px 92px 64px 48px 56px 110px",
              gap: 12,
              padding: "13px 18px",
              alignItems: "center",
            }}
          >
            <span style={{ display: "flex", alignItems: "center", gap: 8, minWidth: 0 }}>
              <span
                style={{
                  font: `600 13px/1.3 ${T.sans}`,
                  color: T.fg,
                  whiteSpace: "nowrap",
                  overflow: "hidden",
                  textOverflow: "ellipsis",
                }}
              >
                {p.name}
              </span>
              <span
                style={{
                  font: `600 8.5px/1 ${T.mono}`,
                  letterSpacing: "0.06em",
                  color: T.brandDeep,
                  background: T.brandSoft,
                  padding: "3px 4px",
                  borderRadius: 3,
                  flexShrink: 0,
                }}
              >
                WORKSPACE
              </span>
            </span>
            <span
              style={{
                font: `400 12.5px/1.3 ${T.sans}`,
                color: T.secondary,
                whiteSpace: "nowrap",
                overflow: "hidden",
                textOverflow: "ellipsis",
              }}
            >
              {p.client}
            </span>
            <Mono style={{ fontSize: 11.5 }}>{p.factory}</Mono>
            <PhasePill phase={p.phase} />
            <Mono style={{ color: T.fg, fontSize: 12 }}>
              {p.tasks_done ?? 0}/{p.tasks_total ?? 0}
            </Mono>
            <Mono style={{ color: T.fg, fontSize: 12 }}>—</Mono>
            <Mono style={{ color: T.fg, fontSize: 12 }}>—</Mono>
            <Mono style={{ textAlign: "right", fontSize: 11 }}>{fmtRel(p.updated)}</Mono>
          </div>
        ))}
      </div>
    </>
  );
}

function AgentCard({
  a,
  onOpen,
  onEdit,
  onDelete,
}: {
  a: AdminAgent;
  onOpen: (a: AdminAgent) => void;
  onEdit: (a: AdminAgent) => void;
  onDelete: (a: AdminAgent) => void;
}) {
  return (
    <button
      onClick={() => onOpen(a)}
      style={{
        textAlign: "left",
        cursor: "pointer",
        background: T.raised,
        border: `1px solid ${a.callsign === "ORCHESTRATOR.MAIN" ? T.brand : T.borderSubtle}`,
        borderRadius: T.rLg,
        padding: "16px 17px",
        display: "flex",
        flexDirection: "column",
        gap: 11,
        boxShadow: T.shadowXs,
      }}
    >
      <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 8 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <span style={{ font: `600 15px/1.2 ${T.sans}`, color: T.brandDeep }}>{a.role}</span>
          <span style={{ width: 7, height: 7, borderRadius: "50%", background: a.on ? T.success : T.borderDefault }} />
        </div>
        <span
          style={{
            font: `600 9.5px/1 ${T.mono}`,
            letterSpacing: "0.04em",
            color: T.secondary,
            background: T.sunken,
            border: `1px solid ${T.borderSubtle}`,
            padding: "4px 5px",
            borderRadius: 4,
          }}
        >
          {a.callsign}
        </span>
      </div>
      <p style={{ margin: 0, font: `400 13px/1.4 ${T.sans}`, color: T.secondary, minHeight: 36 }}>{a.desc}</p>
      <Mono style={{ fontSize: 10.5 }}>CALLSIGN · {a.sign}</Mono>
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          borderTop: `1px solid ${T.borderSubtle}`,
          paddingTop: 10,
        }}
      >
        <Mono style={{ fontSize: 11, color: T.secondary }}>Model: {a.model}</Mono>
        <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
          <Mono style={{ fontSize: 11 }}>Cost:</Mono>
          <CostDots n={a.cost_tier} />
        </span>
      </div>
      <div>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 5 }}>
          <ColHead style={{ fontSize: 9.5 }}>Autonomy / Success</ColHead>
          <Mono style={{ fontSize: 11, color: T.fg }}>{a.success}%</Mono>
        </div>
        <MiniBar pct={a.success} />
      </div>
      <div
        style={{
          display: "flex",
          gap: 8,
          justifyContent: "flex-end",
          paddingTop: 8,
          borderTop: `1px solid ${T.borderSubtle}`,
        }}
        onClick={(e) => e.stopPropagation()}
      >
        <button
          onClick={() => onEdit(a)}
          style={{ font: `500 11px/1 ${T.mono}`, color: T.brandDeep, background: "none", border: "none", cursor: "pointer" }}
        >
          Edit
        </button>
        <button
          onClick={() => onDelete(a)}
          style={{ font: `500 11px/1 ${T.mono}`, color: T.danger, background: "none", border: "none", cursor: "pointer" }}
        >
          ×
        </button>
      </div>
    </button>
  );
}

export function AdminAgents({
  onOpen,
  onNew,
  onEdit,
  onDelete,
  query,
}: {
  onOpen: (a: AdminAgent) => void;
  onNew: () => void;
  onEdit: (a: AdminAgent) => void;
  onDelete: (a: AdminAgent) => void;
  query: string;
}) {
  const { data } = useAdminFetch(() => api.adminAgents());
  const filtered = React.useMemo(() => {
    const list = data?.agents ?? [];
    const q = query.trim().toLowerCase();
    if (!q) return list;
    return list.filter(
      (a) =>
        a.role.toLowerCase().includes(q) ||
        a.callsign.toLowerCase().includes(q) ||
        a.sign.toLowerCase().includes(q) ||
        a.desc.toLowerCase().includes(q) ||
        a.model.toLowerCase().includes(q)
    );
  }, [data, query]);
  return (
    <>
      <PageTitle
        title="Agent Roster"
        sub="Active autonomous workforce. Click a card to monitor or edit its prompt."
        actions={
          <>
            <AdminBtn>{String.fromCharCode(8997)} Configure repo</AdminBtn>
            <AdminBtn primary onClick={onNew}>
              + New agent
            </AdminBtn>
          </>
        }
      />
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 14,
          padding: "12px 16px",
          borderRadius: T.rLg,
          border: `1px solid ${T.warning}55`,
          background: `${T.warningSoft}55`,
          marginBottom: 20,
          flexWrap: "wrap",
        }}
      >
        <span
          style={{
            font: `600 10px/1 ${T.mono}`,
            letterSpacing: "0.06em",
            color: T.warning,
            background: T.warningSoft,
            border: `1px solid ${T.warning}55`,
            padding: "4px 7px",
            borderRadius: 4,
          }}
        >
          {String.fromCharCode(9888)} DRIFT DETECTED · 1
        </span>
        <Mono style={{ fontSize: 11.5 }}>
          pinned <b style={{ color: T.fg }}>0.0.0</b> · current <b style={{ color: T.fg }}>0.1.0</b> (Δ 1 minor)
        </Mono>
        <Mono style={{ flex: 1, fontSize: 11.5, color: T.danger }}>
          [MISSING] .tenexity/lockfile.json — repo never synced with tenexity standards
        </Mono>
        <Mono style={{ fontSize: 11 }}>ok 0 · missing 1 · modified 0 · outdated 0</Mono>
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 14 }}>
        {filtered.map((a) => (
          <AgentCard key={a.callsign} a={a} onOpen={onOpen} onEdit={onEdit} onDelete={onDelete} />
        ))}
      </div>
    </>
  );
}

export function AdminTools({
  query,
  onNew,
  onEdit,
  onDelete,
}: {
  query: string;
  onNew: () => void;
  onEdit: (t: AdminTool) => void;
  onDelete: (t: AdminTool) => void;
}) {
  const { data } = useAdminFetch(() => api.adminTools());
  const TYPE_C: Record<string, [string, string]> = {
    MCP: [T.brandSoft, T.brandDeep],
    API: [T.cHighSoft, T.cHigh],
    native: [T.successSoft, T.success],
    HTTP: ["#f3e9fb", "#7a3ea8"],
  };
  const filtered = React.useMemo(() => {
    const list = data?.tools ?? [];
    const q = query.trim().toLowerCase();
    if (!q) return list;
    return list.filter(
      (t) =>
        t.name.toLowerCase().includes(q) ||
        t.type.toLowerCase().includes(q) ||
        t.provider.toLowerCase().includes(q) ||
        t.scope.toLowerCase().includes(q) ||
        t.auth.toLowerCase().includes(q)
    );
  }, [data, query]);
  const all = data?.tools ?? [];
  return (
    <>
      <PageTitle
        title="Tool & MCP Registry"
        sub="Every tool, MCP server, and connector available to the factory’s agents."
        actions={
          <>
            <AdminBtn>{String.fromCharCode(8644)} Sync registry</AdminBtn>
            <AdminBtn primary onClick={onNew}>
              + Register tool
            </AdminBtn>
          </>
        }
      />
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 12, marginBottom: 20 }}>
        <MetricCard label="Registered" value={all.length} hint="across all factories" accent />
        <MetricCard label="Connected" value={all.filter((t) => t.status === "connected").length} hint="live & authenticated" />
        <MetricCard label="MCP servers" value={all.filter((t) => t.type === "MCP").length} hint="model context protocol" />
        <MetricCard label="Available" value={all.filter((t) => t.status === "available").length} hint="ready to connect" />
      </div>
      <div style={{ border: `1px solid ${T.borderSubtle}`, borderRadius: T.rLg, overflow: "hidden", background: T.raised }}>
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "minmax(0,1fr) 80px minmax(0,0.9fr) minmax(0,1fr) 120px 70px 90px 100px",
            gap: 12,
            padding: "11px 18px",
            borderBottom: `1px solid ${T.borderSubtle}`,
            background: T.sunken,
          }}
        >
          <ColHead>Tool / Server</ColHead>
          <ColHead>Type</ColHead>
          <ColHead>Provider</ColHead>
          <ColHead>Scope</ColHead>
          <ColHead>Auth</ColHead>
          <ColHead>Used by</ColHead>
          <ColHead style={{ textAlign: "right" }}>Status</ColHead>
          <ColHead style={{ textAlign: "right" }}>Actions</ColHead>
        </div>
        {filtered.map((t, i) => {
          const tc = TYPE_C[t.type] || TYPE_C.native;
          const connected = t.status === "connected";
          const idVal = t.name;
          return (
            <div
              key={t.name}
              style={{
                display: "grid",
                gridTemplateColumns: "minmax(0,1fr) 80px minmax(0,0.9fr) minmax(0,1fr) 120px 70px 90px 100px",
                gap: 12,
                padding: "13px 18px",
                alignItems: "center",
                borderTop: i ? `1px solid ${T.borderSubtle}` : "none",
              }}
            >
              <span style={{ display: "flex", alignItems: "center", gap: 10, minWidth: 0 }}>
                <span
                  style={{
                    width: 26,
                    height: 26,
                    flexShrink: 0,
                    borderRadius: 6,
                    display: "grid",
                    placeItems: "center",
                    background: T.sunken,
                    border: `1px solid ${T.borderSubtle}`,
                    font: `700 9px/1 ${T.mono}`,
                    color: T.secondary,
                  }}
                >
                  {t.name.slice(0, 2).toUpperCase()}
                </span>
                <span
                  style={{
                    font: `600 13px/1.2 ${T.sans}`,
                    color: T.fg,
                    whiteSpace: "nowrap",
                    overflow: "hidden",
                    textOverflow: "ellipsis",
                  }}
                >
                  {t.name}
                </span>
              </span>
              <span
                style={{
                  font: `600 9.5px/1 ${T.mono}`,
                  letterSpacing: "0.04em",
                  color: tc[1],
                  background: tc[0],
                  padding: "4px 5px",
                  borderRadius: 4,
                  justifySelf: "start",
                }}
              >
                {t.type}
              </span>
              <span
                style={{
                  font: `400 12.5px/1.3 ${T.sans}`,
                  color: T.secondary,
                  whiteSpace: "nowrap",
                  overflow: "hidden",
                  textOverflow: "ellipsis",
                }}
              >
                {t.provider}
              </span>
              <Mono style={{ fontSize: 11.5, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{t.scope}</Mono>
              <Mono style={{ fontSize: 11 }}>{t.auth}</Mono>
              <Mono style={{ fontSize: 12, color: t.used ? T.fg : T.tertiary }}>{t.used ? `${t.used} agents` : "—"}</Mono>
              <span style={{ justifySelf: "end" }}>
                {connected ? (
                  <StatusPill tone="success">live</StatusPill>
                ) : (
                  <button
                    onClick={() => onEdit({ ...t, status: "connected" })}
                    style={{
                      font: `600 10.5px/1 ${T.mono}`,
                      color: T.brandDeep,
                      background: "none",
                      border: "none",
                      cursor: "pointer",
                    }}
                  >
                    CONNECT →
                  </button>
                )}
              </span>
              <span style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
                <button
                  onClick={() => onEdit(t)}
                  style={{ font: `500 11px/1 ${T.mono}`, color: T.brandDeep, background: "none", border: "none", cursor: "pointer" }}
                >
                  Edit
                </button>
                <button
                  onClick={() => onDelete(t)}
                  style={{ font: `500 11px/1 ${T.mono}`, color: T.danger, background: "none", border: "none", cursor: "pointer" }}
                >
                  ×
                </button>
              </span>
            </div>
          );
        })}
      </div>
    </>
  );
}

export function AdminOverview({ onNav, query }: { onNav: (id: string) => void; query: string }) {
  const { data } = useAdminFetch(() => api.adminOverview());
  const pulse = data?.pulse ?? {};
  const active = pulse.agents_active ?? 0;
  const totalAgents = pulse.agents_total ?? 0;
  const agentsText = totalAgents ? `${active} / ${totalAgents}` : `${active}`;
  const filteredProjects = React.useMemo(() => {
    const list = data?.active_projects ?? [];
    const q = query.trim().toLowerCase();
    if (!q) return list;
    return list.filter(
      (p) =>
        p.name.toLowerCase().includes(q) ||
        p.client.toLowerCase().includes(q) ||
        p.phase.toLowerCase().includes(q)
    );
  }, [data, query]);
  const filteredAgents = React.useMemo(() => {
    const list = data?.agents ?? [];
    const q = query.trim().toLowerCase();
    if (!q) return list;
    return list.filter(
      (a) =>
        a.role.toLowerCase().includes(q) ||
        a.callsign.toLowerCase().includes(q) ||
        a.sign.toLowerCase().includes(q)
    );
  }, [data, query]);
  return (
    <>
      <PageTitle
        title="Factory Overview"
        sub="Platform-wide pulse across every tenant, project, and agent."
        actions={
          <AdminBtn primary onClick={() => onNav("projects")}>
            View all projects
          </AdminBtn>
        }
      />
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 12, marginBottom: 18 }}>
        <MetricCard label="Tenants" value={pulse.tenants ?? 0} hint="active organizations" accent />
        <MetricCard label="Projects" value={pulse.projects ?? 0} hint="across all factories" />
        <MetricCard label="Agents active" value={agentsText} hint="autonomous workforce" />
        <MetricCard label="Today burn" value={pulse.today_burn ?? "$0.00"} hint={pulse.avg_friction ? `avg friction ${pulse.avg_friction}` : "avg friction not tracked"} />
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "1.3fr 1fr", gap: 14 }}>
        <div style={{ border: `1px solid ${T.borderSubtle}`, borderRadius: T.rLg, background: T.raised, overflow: "hidden" }}>
          <div
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              padding: "11px 16px",
              borderBottom: `1px solid ${T.borderSubtle}`,
              background: T.sunken,
            }}
          >
            <ColHead>Most active projects</ColHead>
            <button
              onClick={() => onNav("projects")}
              style={{
                font: `600 10.5px/1 ${T.mono}`,
                color: T.brandDeep,
                background: "none",
                border: "none",
                cursor: "pointer",
              }}
            >
              ALL →
            </button>
          </div>
          {filteredProjects.slice(0, 6).map((p, i) => (
            <div
              key={p.run_id}
              style={{ display: "flex", alignItems: "center", gap: 10, padding: "11px 16px", borderTop: i ? `1px solid ${T.borderSubtle}` : "none" }}
            >
              <span
                style={{
                  flex: 1,
                  font: `500 13px/1.2 ${T.sans}`,
                  color: T.fg,
                  whiteSpace: "nowrap",
                  overflow: "hidden",
                  textOverflow: "ellipsis",
                }}
              >
                {p.name}
              </span>
              <PhasePill phase={p.phase} />
              <Mono style={{ fontSize: 10.5, width: 80, textAlign: "right" }}>{fmtRel(p.updated)}</Mono>
            </div>
          ))}
        </div>
        <div style={{ border: `1px solid ${T.borderSubtle}`, borderRadius: T.rLg, background: T.raised, overflow: "hidden" }}>
          <div
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              padding: "11px 16px",
              borderBottom: `1px solid ${T.borderSubtle}`,
              background: T.sunken,
            }}
          >
            <ColHead>Agent workforce</ColHead>
            <button
              onClick={() => onNav("agents")}
              style={{
                font: `600 10.5px/1 ${T.mono}`,
                color: T.brandDeep,
                background: "none",
                border: "none",
                cursor: "pointer",
              }}
            >
              ROSTER →
            </button>
          </div>
          {filteredAgents.slice(0, 6).map((a, i) => (
            <div
              key={a.callsign}
              style={{ display: "flex", alignItems: "center", gap: 10, padding: "11px 16px", borderTop: i ? `1px solid ${T.borderSubtle}` : "none" }}
            >
              <span style={{ width: 7, height: 7, borderRadius: "50%", background: a.on ? T.success : T.borderDefault }} />
              <span style={{ flex: 1, font: `500 13px/1.2 ${T.sans}`, color: T.fg }}>{a.role}</span>
              <Mono style={{ fontSize: 10.5 }}>{a.success}%</Mono>
            </div>
          ))}
        </div>
      </div>
    </>
  );
}
