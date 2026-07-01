// Cross-tenant conversation history (SOF-34/T1.5) — Tenexity OS, staff-only. Sessions roll-up with
// filters + cursor pagination; click a session to drill into its full transcript.
import React from "react";
import { T } from "./tokens";
import { Icon, Btn } from "./primitives";
import { Skel, SkelPill } from "../components/skeleton";
import { api } from "../api";
import type { AdminConversationSession, AdminConversationMessage } from "../api";
import { ColHead, Mono, PageTitle, FilterSelect } from "./views";
import { useAdminFetch } from "./hooks";

const ROW_COLS = "minmax(0,1.3fr) minmax(0,1fr) minmax(0,1fr) 90px 110px 130px";

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
  width: "min(720px, 100%)",
  maxHeight: "82vh",
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
  flexShrink: 0,
};

const dateInputStyle: React.CSSProperties = {
  height: 36,
  padding: "0 10px",
  borderRadius: T.rMd,
  border: `1px solid ${T.borderDefault}`,
  background: T.raised,
  font: `500 12px/1 ${T.sans}`,
  color: T.secondary,
};

function fmtTs(iso?: string): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return String(iso);
  return d.toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

function ConversationRowSkel({ first = false }: { first?: boolean }) {
  return (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: ROW_COLS,
        gap: 12,
        padding: "13px 18px",
        alignItems: "center",
        borderTop: first ? "none" : `1px solid ${T.borderSubtle}`,
      }}
    >
      <Skel w="70%" h={12} />
      <Skel w="60%" h={12} />
      <Skel w="55%" h={12} />
      <SkelPill w={40} h={18} />
      <Skel w="70%" h={12} />
      <Skel w="70%" h={12} />
    </div>
  );
}

function EmptyState() {
  return (
    <div style={{ padding: "40px 18px", textAlign: "center" }}>
      <Mono style={{ fontSize: 12, color: T.tertiary }}>No conversations match these filters.</Mono>
    </div>
  );
}

function CloseBtn({ onClick }: { onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      style={{ width: 28, height: 28, display: "grid", placeItems: "center", borderRadius: T.rMd, border: "none", background: "transparent", color: T.tertiary, cursor: "pointer" }}
    >
      <Icon name="x" size={16} />
    </button>
  );
}

function MessageRowSkel({ first = false }: { first?: boolean }) {
  return (
    <div style={{ padding: "12px 0", borderTop: first ? "none" : `1px solid ${T.borderSubtle}` }}>
      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 8 }}>
        <Skel w={60} h={10} />
        <Skel w={120} h={10} />
      </div>
      <Skel w="90%" h={12} />
    </div>
  );
}

function MessageRow({ m, first }: { m: AdminConversationMessage; first: boolean }) {
  const meta = [m.provider, m.model].filter(Boolean).join(" · ");
  return (
    <div style={{ padding: "12px 0", borderTop: first ? "none" : `1px solid ${T.borderSubtle}` }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", gap: 10 }}>
        <ColHead>{m.role}</ColHead>
        <Mono style={{ textAlign: "right" }}>
          {meta}{meta && m.cost_usd ? " · " : ""}{m.cost_usd ? `$${m.cost_usd.toFixed(4)}` : ""}
        </Mono>
      </div>
      <p style={{ margin: "6px 0 0", font: `400 13px/1.55 ${T.sans}`, color: T.fg, whiteSpace: "pre-wrap" }}>
        {m.input || <span style={{ color: T.tertiary }}>—</span>}
      </p>
    </div>
  );
}

function TranscriptModal({ sessionId, onClose }: { sessionId: string; onClose: () => void }) {
  const [messages, setMessages] = React.useState<AdminConversationMessage[] | null>(null);
  const [loading, setLoading] = React.useState(true);

  React.useEffect(() => {
    let active = true;
    setLoading(true);
    api.adminConversationTranscript(sessionId)
      .then((r) => { if (active) { setMessages(r.messages); setLoading(false); } })
      .catch(() => { if (active) { setMessages([]); setLoading(false); } });
    return () => { active = false; };
  }, [sessionId]);

  return (
    <div style={overlay} onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div style={modalCard}>
        <div style={modalHeader}>
          <div>
            <h2 style={{ font: `400 18px/1.2 ${T.display}`, color: T.fg, margin: 0 }}>Transcript</h2>
            <Mono style={{ display: "block", marginTop: 4 }}>{sessionId}</Mono>
          </div>
          <CloseBtn onClick={onClose} />
        </div>
        <div style={{ padding: "4px 20px 18px", overflowY: "auto", flex: 1 }}>
          {loading && Array.from({ length: 4 }, (_, i) => <MessageRowSkel key={i} first={i === 0} />)}
          {!loading && messages?.length === 0 && (
            <div style={{ padding: "24px 0", textAlign: "center" }}>
              <Mono style={{ fontSize: 12, color: T.tertiary }}>No messages in this session.</Mono>
            </div>
          )}
          {!loading && messages?.map((m, i) => <MessageRow key={m.id} m={m} first={i === 0} />)}
        </div>
      </div>
    </div>
  );
}

export function AdminConversations() {
  const [orgFilter, setOrgFilter] = React.useState("");
  const [projectFilter, setProjectFilter] = React.useState("");
  const [userFilter, setUserFilter] = React.useState("");
  const [roleFilter, setRoleFilter] = React.useState("");
  const [dateFrom, setDateFrom] = React.useState("");
  const [dateTo, setDateTo] = React.useState("");
  const [sessions, setSessions] = React.useState<AdminConversationSession[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [loadingMore, setLoadingMore] = React.useState(false);
  const [nextCursor, setNextCursor] = React.useState<string | null>(null);
  const [openSession, setOpenSession] = React.useState<string | null>(null);

  const { data: clientsData } = useAdminFetch(() => api.adminClients());
  const { data: projectsData } = useAdminFetch(() => api.adminProjects("all"));
  const { data: accessData } = useAdminFetch(() => api.adminAccess());

  const orgIdByName = React.useMemo(
    () => Object.fromEntries((clientsData?.clients ?? []).map((c) => [c.name, c.org_id])),
    [clientsData]
  );
  const projectIdByName = React.useMemo(
    () => Object.fromEntries((projectsData?.projects ?? []).map((p) => [p.name, p.project_id])),
    [projectsData]
  );
  const userIdByEmail = React.useMemo(
    () => Object.fromEntries((accessData?.users ?? []).map((u) => [u.email, u.id])),
    [accessData]
  );

  const orgOptions = React.useMemo(() => ["All organizations", ...Object.keys(orgIdByName).sort()], [orgIdByName]);
  const projectOptions = React.useMemo(() => ["All projects", ...Object.keys(projectIdByName).sort()], [projectIdByName]);
  const userOptions = React.useMemo(() => ["All users", ...Object.keys(userIdByEmail).sort()], [userIdByEmail]);
  const roleOptions = ["All roles", "user", "agent", "tool", "system"];

  const buildFilter = React.useCallback(
    (cursor?: string) => ({
      org_id: orgFilter ? orgIdByName[orgFilter] : undefined,
      project_id: projectFilter ? projectIdByName[projectFilter] : undefined,
      user_id: userFilter ? userIdByEmail[userFilter] : undefined,
      role: roleFilter || undefined,
      date_from: dateFrom || undefined,
      date_to: dateTo || undefined,
      cursor,
      limit: 50,
    }),
    [orgFilter, projectFilter, userFilter, roleFilter, dateFrom, dateTo, orgIdByName, projectIdByName, userIdByEmail]
  );

  React.useEffect(() => {
    let active = true;
    setLoading(true);
    api.adminConversations(buildFilter())
      .then((r) => { if (active) { setSessions(r.sessions); setNextCursor(r.next_cursor); setLoading(false); } })
      .catch(() => { if (active) { setSessions([]); setNextCursor(null); setLoading(false); } });
    return () => { active = false; };
  }, [buildFilter]);

  const loadMore = () => {
    if (!nextCursor) return;
    setLoadingMore(true);
    api.adminConversations(buildFilter(nextCursor))
      .then((r) => { setSessions((prev) => [...prev, ...r.sessions]); setNextCursor(r.next_cursor); })
      .catch(() => {})
      .finally(() => setLoadingMore(false));
  };

  return (
    <>
      <PageTitle title="Conversations" sub="Every Concierge conversation across every organization, project, and user." />
      <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 14, flexWrap: "wrap" }}>
        <FilterSelect label="All organizations" options={orgOptions} value={orgFilter} onChange={setOrgFilter} />
        <FilterSelect label="All projects" options={projectOptions} value={projectFilter} onChange={setProjectFilter} w={170} />
        <FilterSelect label="All users" options={userOptions} value={userFilter} onChange={setUserFilter} w={190} />
        <FilterSelect label="All roles" options={roleOptions} value={roleFilter} onChange={setRoleFilter} w={120} />
        <input type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} style={dateInputStyle} />
        <Mono>to</Mono>
        <input type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)} style={dateInputStyle} />
      </div>
      <div style={{ border: `1px solid ${T.borderSubtle}`, borderRadius: T.rLg, overflow: "hidden", background: T.raised }}>
        <div style={{ display: "grid", gridTemplateColumns: ROW_COLS, gap: 12, padding: "11px 18px", borderBottom: `1px solid ${T.borderSubtle}`, background: T.sunken }}>
          <ColHead>Session</ColHead>
          <ColHead>Organization</ColHead>
          <ColHead>User</ColHead>
          <ColHead>Turns</ColHead>
          <ColHead style={{ textAlign: "right" }}>Cost</ColHead>
          <ColHead style={{ textAlign: "right" }}>Last activity</ColHead>
        </div>
        {loading && Array.from({ length: 6 }, (_, i) => <ConversationRowSkel key={i} first={i === 0} />)}
        {!loading && sessions.length === 0 && <EmptyState />}
        {!loading && sessions.map((s, i) => (
          <div
            key={s.session_id}
            onClick={() => setOpenSession(s.session_id)}
            style={{
              display: "grid",
              gridTemplateColumns: ROW_COLS,
              gap: 12,
              padding: "13px 18px",
              alignItems: "center",
              borderTop: i ? `1px solid ${T.borderSubtle}` : "none",
              cursor: "pointer",
            }}
          >
            <span style={{ font: `500 12.5px/1.3 ${T.mono}`, color: T.fg, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
              {s.project_name || s.session_id}
            </span>
            <span style={{ font: `400 12.5px/1.3 ${T.sans}`, color: T.secondary }}>{s.org_name || "—"}</span>
            <span style={{ font: `400 12.5px/1.3 ${T.sans}`, color: T.secondary }}>{s.user_email || "—"}</span>
            <Mono>{s.turn_count}</Mono>
            <Mono style={{ textAlign: "right" }}>${s.total_cost.toFixed(4)}</Mono>
            <Mono style={{ textAlign: "right" }}>{fmtTs(s.last_activity)}</Mono>
          </div>
        ))}
      </div>
      {!loading && nextCursor && (
        <div style={{ display: "flex", justifyContent: "center", marginTop: 14 }}>
          <Btn onClick={loadMore} disabled={loadingMore}>{loadingMore ? "Loading…" : "Load more"}</Btn>
        </div>
      )}
      {openSession && <TranscriptModal sessionId={openSession} onClose={() => setOpenSession(null)} />}
    </>
  );
}
