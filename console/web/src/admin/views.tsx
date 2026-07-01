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

export function Mono({ children, style }: { children: React.ReactNode; style?: React.CSSProperties }) {
  return (
    <span style={{ font: `500 11px/1 ${T.mono}`, letterSpacing: "0.04em", color: T.tertiary, ...style }}>
      {children}
    </span>
  );
}

export function ColHead({ children, style }: { children: React.ReactNode; style?: React.CSSProperties }) {
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

function UserAvatar({ name, size = 20 }: { name: string; size?: number }) {
  const letters = name
    .trim()
    .split(/\s+/)
    .slice(0, 2)
    .map((w) => w[0]?.toUpperCase())
    .join("");
  return (
    <span
      style={{
        width: size,
        height: size,
        borderRadius: 9999,
        flexShrink: 0,
        display: "grid",
        placeItems: "center",
        background: T.brandSoft,
        color: T.brandDeep,
        font: `600 ${size <= 20 ? 8 : 10}px/1 ${T.mono}`,
      }}
    >
      {letters || "?"}
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

export function AdminBtn({ children, primary, onClick, disabled }: { children: React.ReactNode; primary?: boolean; onClick?: () => void; disabled?: boolean }) {
  return (
    <button
      onClick={disabled ? undefined : onClick}
      disabled={disabled}
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 7,
        height: 36,
        padding: "0 14px",
        cursor: disabled ? "not-allowed" : "pointer",
        font: `600 11.5px/1 ${T.mono}`,
        letterSpacing: "0.05em",
        textTransform: "uppercase",
        borderRadius: T.rMd,
        border: `1px solid ${primary ? "transparent" : T.borderDefault}`,
        background: primary ? T.brand : T.raised,
        color: primary ? "#fff" : T.fg,
        opacity: disabled ? 0.5 : 1,
      }}
    >
      {children}
    </button>
  );
}

export function PageTitle({ title, sub, actions }: { title: string; sub: string; actions?: React.ReactNode }) {
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

export function AdminFilter({ children, w = 150 }: { children: React.ReactNode; w?: number }) {
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

export function FilterSelect({
  label,
  options,
  value,
  onChange,
  w = 150,
}: {
  label: string;
  options: string[];
  value: string;
  onChange: (v: string) => void;
  w?: number;
}) {
  const [open, setOpen] = React.useState(false);
  const ref = React.useRef<HTMLDivElement>(null);
  React.useEffect(() => {
    function close(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, []);
  const display = value || label;
  return (
    <div ref={ref} style={{ position: "relative", width: w, flexShrink: 0 }}>
      <div
        onClick={() => setOpen((s) => !s)}
        style={{
          display: "inline-flex",
          alignItems: "center",
          gap: 7,
          height: 36,
          padding: "0 11px",
          width: w,
          justifyContent: "space-between",
          borderRadius: T.rMd,
          border: `1px solid ${value ? T.brand : T.borderDefault}`,
          background: value ? T.brandSoft : T.raised,
          font: `500 12px/1 ${T.sans}`,
          color: value ? T.brandDeep : T.secondary,
          cursor: "pointer",
        }}
      >
        <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{display}</span>
        <Icon name="chevronDown" size={13} color={value ? T.brandDeep : T.tertiary} />
      </div>
      {open && (
        <div
          style={{
            position: "absolute",
            top: "100%",
            left: 0,
            right: 0,
            marginTop: 4,
            maxHeight: 240,
            overflow: "auto",
            zIndex: 10,
            background: T.raised,
            border: `1px solid ${T.borderDefault}`,
            borderRadius: T.rMd,
            boxShadow: T.shadowMd,
          }}
        >
          {options.map((o) => (
            <button
              key={o}
              onClick={() => {
                onChange(o === label ? "" : o);
                setOpen(false);
              }}
              style={{
                display: "block",
                width: "100%",
                textAlign: "left",
                padding: "8px 11px",
                border: "none",
                borderBottom: `1px solid ${T.borderSubtle}`,
                background: "transparent",
                cursor: "pointer",
                font: `400 12.5px/1 ${T.sans}`,
                color: o === display ? T.brandDeep : T.fg,
              }}
            >
              {o}
            </button>
          ))}
        </div>
      )}
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
        title="Organizations"
        sub="Customers and their portfolios of factory projects."
        actions={
          <AdminBtn primary onClick={onNew}>
            + New organization
          </AdminBtn>
        }
      />
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
          <ColHead>Organization</ColHead>
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

export function AdminProjectsView({ query, onOpenProject }: { query: string; onOpenProject?: (id: string) => void }) {
  const [clientFilter, setClientFilter] = React.useState("");
  const [factoryFilter, setFactoryFilter] = React.useState("");
  const [statusFilter, setStatusFilter] = React.useState("");
  const [modeFilter, setModeFilter] = React.useState("");
  const [ownerFilter, setOwnerFilter] = React.useState("");
  const { data } = useAdminFetch(() => api.adminProjects("all"));
  const allProjects = React.useMemo(() => data?.projects ?? [], [data]);

  const clientOptions = React.useMemo(
    () => ["All organizations", ...Array.from(new Set(allProjects.map((p) => p.client).filter(Boolean))).sort()],
    [allProjects]
  );
  const factoryOptions = React.useMemo(
    () => ["All factories", ...Array.from(new Set(allProjects.map((p) => p.factory).filter(Boolean))).sort()],
    [allProjects]
  );
  const statusOptions = React.useMemo(
    () => ["All statuses", ...Array.from(new Set(allProjects.map((p) => p.phase).filter(Boolean))).sort()],
    [allProjects]
  );
  const modeOptions = ["All modes", "Real", "Demo/FAKE"];
  const ownerOptions = React.useMemo(
    () => ["All users", ...Array.from(new Set(allProjects.map((p) => p.owner || p.created_by).filter((v): v is string => Boolean(v)))).sort()],
    [allProjects]
  );

  const filtered = React.useMemo(() => {
    const q = query.trim().toLowerCase();
    return allProjects.filter((p) => {
      if (
        q &&
        !(
          p.name.toLowerCase().includes(q) ||
          p.client.toLowerCase().includes(q) ||
          p.factory.toLowerCase().includes(q) ||
          p.phase.toLowerCase().includes(q)
        )
      )
        return false;
      if (clientFilter && p.client !== clientFilter) return false;
      if (factoryFilter && p.factory !== factoryFilter) return false;
      if (statusFilter && p.phase !== statusFilter) return false;
      if (ownerFilter && (p.owner || p.created_by || "") !== ownerFilter) return false;
      if (modeFilter === "Real" && p.is_demo) return false;
      if (modeFilter === "Demo/FAKE" && !p.is_demo) return false;
      return true;
    });
  }, [allProjects, query, clientFilter, factoryFilter, statusFilter, ownerFilter, modeFilter]);

  return (
    <>
      <PageTitle
        title="Projects"
        sub="Every project across every organization and factory pipeline."
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
          <span style={{ font: `400 12.5px/1 ${T.sans}`, color: T.tertiary }}>Search name, organization, factory…</span>
        </div>
        <FilterSelect label="All organizations" options={clientOptions} value={clientFilter} onChange={setClientFilter} />
        <FilterSelect label="All factories" options={factoryOptions} value={factoryFilter} onChange={setFactoryFilter} />
        <FilterSelect label="All statuses" options={statusOptions} value={statusFilter} onChange={setStatusFilter} w={130} />
        <FilterSelect label="All users" options={ownerOptions} value={ownerFilter} onChange={setOwnerFilter} w={150} />
        <FilterSelect label="All modes" options={modeOptions} value={modeFilter} onChange={setModeFilter} w={130} />
      </div>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 12 }}>
        <ColHead>Active filters</ColHead>
        <Mono>
          {filtered.length} of {allProjects.length}
        </Mono>
      </div>
      <div style={{ border: `1px solid ${T.borderSubtle}`, borderRadius: T.rLg, overflow: "hidden", background: T.raised }}>
        <div
          style={{
            display: "grid",
              gridTemplateColumns: "minmax(0,1.5fr) minmax(0,1.1fr) 130px 92px 64px minmax(0,1fr) 110px 110px",
            gap: 12,
            padding: "11px 18px",
            borderBottom: `1px solid ${T.borderSubtle}`,
            background: T.sunken,
          }}
        >
          <ColHead>Project</ColHead>
          <ColHead>Organization</ColHead>
          <ColHead>Factory</ColHead>
          <ColHead>Phase</ColHead>
          <ColHead>Tasks</ColHead>
          <ColHead>Owner</ColHead>
          <ColHead style={{ textAlign: "right" }}>Created</ColHead>
          <ColHead style={{ textAlign: "right" }}>Last activity</ColHead>
        </div>
        {filtered.map((p, i) => (
          <div
            key={p.project_id}
            onClick={() => onOpenProject?.(p.project_id)}
            style={{
              background: T.raised,
              borderTop: i ? `1px solid ${T.borderSubtle}` : "none",
              display: "grid",
          gridTemplateColumns: "minmax(0,1.5fr) minmax(0,1.1fr) 130px 92px 64px minmax(0,1fr) 110px 110px",
              gap: 12,
              padding: "13px 18px",
              alignItems: "center",
              cursor: onOpenProject ? "pointer" : "default",
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
            <span
              style={{
                display: "flex",
                alignItems: "center",
                gap: 8,
                minWidth: 0,
              }}
              title={p.owner || p.created_by}
            >
              {(p.owner || p.created_by) ? <UserAvatar name={p.owner || p.created_by!} /> : null}
              <span
                style={{
                  font: `400 12.5px/1.3 ${T.sans}`,
                  color: T.secondary,
                  whiteSpace: "nowrap",
                  overflow: "hidden",
                  textOverflow: "ellipsis",
                }}
              >
                {p.owner || p.created_by || "—"}
              </span>
            </span>
            <Mono style={{ textAlign: "right", fontSize: 11 }}>{fmtRel(p.created_at)}</Mono>
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
  const isLive = !!a.kind;
  const title = a.name || a.role;
  const kindLabel = a.kind ? a.kind.replace("_", " ") : "";
  return (
    <button
      onClick={() => onOpen(a)}
      style={{
        textAlign: "left",
        cursor: "pointer",
        background: T.raised,
        border: `1px solid ${a.callsign === "ORCHESTRATOR.MAIN" || isLive ? T.brand : T.borderSubtle}`,
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
          <span style={{ font: `600 15px/1.2 ${T.sans}`, color: T.brandDeep }}>{title}</span>
          {!isLive && <span style={{ width: 7, height: 7, borderRadius: "50%", background: a.on ? T.success : T.borderDefault }} />}
          {isLive && (
            <span
              style={{
                font: `600 8px/1 ${T.mono}`,
                letterSpacing: "0.06em",
                textTransform: "uppercase",
                color: T.brandDeep,
                background: T.brandSoft,
                padding: "2px 5px",
                borderRadius: 3,
              }}
            >
              {kindLabel}
            </span>
          )}
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
      {!isLive && (
        <div>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 5 }}>
            <ColHead style={{ fontSize: 9.5 }}>Autonomy / Success</ColHead>
            <Mono style={{ fontSize: 11, color: T.fg }}>{a.success}%</Mono>
          </div>
          <MiniBar pct={a.success ?? 0} />
        </div>
      )}
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
        {!isLive && (
          <>
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
          </>
        )}
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
        (a.name ?? "").toLowerCase().includes(q) ||
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
          <AdminBtn primary onClick={onNew}>
            + New agent
          </AdminBtn>
        }
      />
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
  onRefresh,
  onSyncAgents,
}: {
  query: string;
  onNew: () => void;
  onEdit: (t: AdminTool) => void;
  onDelete: (t: AdminTool) => void;
  onRefresh?: () => void;
  onSyncAgents?: () => void;
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
  const [syncState, setSyncState] = React.useState<{ busy: boolean; notice?: string; error?: string }>({ busy: false });
  const syncAgents = () => {
    setSyncState({ busy: true });
    api
      .adminSyncAgents()
      .then((res) => {
        setSyncState({ busy: false, notice: `Synced ${res.synced} agent${res.synced === 1 ? "" : "s"}` });
        onSyncAgents?.();
      })
      .catch((err) => setSyncState({ busy: false, error: err.message || "Agent sync failed" }));
  };
  const setStatus = (t: AdminTool, status: AdminTool["status"]) => {
    api.adminUpdateTool(t.name, { status }).then(onRefresh).catch(() => {});
  };
  return (
    <>
      <PageTitle
        title="Tool & MCP Registry"
        sub="Every tool, MCP server, and connector available to the factory’s agents."
        actions={
          <>
            <AdminBtn disabled={syncState.busy} onClick={syncAgents}>
              {syncState.busy ? "Syncing…" : `${String.fromCharCode(8644)} Sync registry`}
            </AdminBtn>
            <AdminBtn primary onClick={onNew}>
              + Register tool
            </AdminBtn>
          </>
        }
      />
      {syncState.notice && <Mono style={{ color: T.success, marginBottom: 10 }}>{syncState.notice}</Mono>}
      {syncState.error && <Mono style={{ color: T.danger, marginBottom: 10 }}>{syncState.error}</Mono>}
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
                  <button
                    onClick={() => setStatus(t, "available")}
                    style={{
                      font: `600 10.5px/1 ${T.mono}`,
                      color: T.success,
                      background: "none",
                      border: "none",
                      cursor: "pointer",
                    }}
                  >
                    live →
                  </button>
                ) : (
                  <button
                    onClick={() => setStatus(t, "connected")}
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

export function AdminOverview({ onNav, query, onOpenProject }: { onNav: (id: string) => void; query: string; onOpenProject?: (id: string) => void }) {
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
              key={p.project_id}
              onClick={() => onOpenProject?.(p.project_id)}
              style={{ display: "flex", alignItems: "center", gap: 10, padding: "11px 16px", borderTop: i ? `1px solid ${T.borderSubtle}` : "none", cursor: onOpenProject ? "pointer" : "default" }}
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

function Placeholder({ label }: { label: string }) {
  return (
    <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: "100%" }}>
      <div
        style={{
          textAlign: "center",
          maxWidth: 420,
          padding: "32px 36px",
          borderRadius: T.rLg,
          border: `1px dashed ${T.borderDefault}`,
          background: T.raised,
        }}
      >
        <Mono style={{ fontSize: 11, display: "block", marginBottom: 10, letterSpacing: "0.12em" }}>{label.toUpperCase()}</Mono>
        <p style={{ margin: 0, font: `400 14px/1.5 ${T.sans}`, color: T.tertiary }}>
          Module surface — out of scope for this prototype.
        </p>
      </div>
    </div>
  );
}

export function AdminFactories() {
  return <Placeholder label="Factories" />;
}

export function AdminSettings() {
  return <Placeholder label="Settings" />;
}

export function AdminSymphony() {
  return (
    <div style={{ maxWidth: 520 }}>
      <PageTitle title="Symphony" sub="Multi-agent orchestration and swarm coordination." />
      <div
        style={{
          padding: "20px 22px",
          borderRadius: T.rLg,
          border: `1px dashed ${T.borderDefault}`,
          background: T.raised,
        }}
      >
        <Mono style={{ fontSize: 11, display: "block", marginBottom: 10, letterSpacing: "0.12em" }}>COMING SOON</Mono>
        <p style={{ margin: 0, font: `400 14px/1.5 ${T.sans}`, color: T.tertiary }}>
          Symphony is not deployed yet. This screen will remain empty until the backend ships the
          supporting tables and API.
        </p>
      </div>
    </div>
  );
}
