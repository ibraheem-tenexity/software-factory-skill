// Dashboard.tsx — Projects dashboard (PRD §2.2), the post-login home. Faithful TSX port of the
// design's dashboard.jsx, reusing the Tenexity primitives from onboarding/design.tsx and driven
// by REAL run-registry data (/api/projects, owner-scoped) + /api/me + /api/org. Fields the prototype
// mocked are derived from real data where it exists and degrade honestly where it doesn't.
import React, { useEffect, useState } from "react";
import { api, phaseIsStale, ProjectSummary, Org } from "../api";
import { useMe } from "./MeContext";
import { T, Icon, CategoryLabel, Btn, StatusPill, Avatar, Wordmark, TextInput, Markdown } from "./onboarding/design";
import { MetricCardSkel, ProjectRowSkel } from "./skeleton";
import { AccountMenu } from "./AccountMenu";
import { toneForHaltedPhase } from "./factory/pipeline";

type StatusKey = "deployed" | "needs-input" | "draft" | "researching" | "building" | "stopped" | "crashed" | "paused";
type Tone = "success" | "warning" | "neutral" | "brand" | "info" | "danger";

// Derive the project status from real run state (never fabricated).
function statusOf(r: ProjectSummary): { key: StatusKey; label: string; tone: Tone } {
  if (r.deploy_url || r.done || r.phase === "done") return { key: "deployed", label: "Deployed", tone: "success" };
  if (r.phase === "draft") return { key: "draft", label: "Draft", tone: "neutral" };
  if (r.budget_stopped || r.held) return { key: "needs-input", label: "Needs input", tone: "warning" };
  // Shared with FactoryConsole's phaseTone() (factory/pipeline.ts) so a halted run reads the
  // same here as in the detail view — see #128, where a duplicated if-chain drifted out of sync.
  if (r.phase === "stopped") return { key: "stopped", label: "Stopped", tone: toneForHaltedPhase("stopped")! };
  if (r.phase === "crashed") return { key: "crashed", label: "Crashed", tone: toneForHaltedPhase("crashed")! };
  if (r.phase === "paused") return { key: "paused", label: "Paused", tone: toneForHaltedPhase("paused")! };
  if ((r.phase || "").toLowerCase().includes("research")) return { key: "researching", label: "Researching", tone: "brand" };
  return { key: "building", label: "Building", tone: "info" };
}

// Progress reflects the staged pipeline (stage 1→2→3); deployed = 100, draft = 0.
function pctOf(r: ProjectSummary, key: StatusKey): number {
  if (key === "deployed") return 100;
  if (key === "draft") return 0;
  const stage = Math.max(0, Math.min(3, r.stage || 0));
  return Math.round((stage / 3) * 100);
}

function barColor(key: StatusKey): string {
  if (key === "deployed") return T.success;
  if (key === "needs-input") return T.warning;
  return T.brand;
}

function relTime(epoch?: number): string {
  if (!epoch) return "—";
  const s = Math.max(0, Date.now() / 1000 - epoch);
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  return `${Math.floor(s / 86400)}d ago`;
}

function money(v?: number): string {
  return v ? `$${v.toFixed(2)}` : "—";
}

function draftLabel(projectId: string): string {
  return `Draft Project ${projectId.replace("project-", "").slice(0, 8)}`;
}

function MetricCard({ label, value, hint, accent }: { label: string; value: string; hint?: string; accent?: boolean }) {
  return (
    <div style={{ background: T.raised, border: `1px solid ${T.borderSubtle}`, borderRadius: T.rLg, padding: "14px 16px", boxShadow: T.shadowXs }}>
      <CategoryLabel>{label}</CategoryLabel>
      <div style={{ font: `700 26px/1.1 ${T.display}`, letterSpacing: "-0.02em", color: accent ? T.brandDeep : T.fg, marginTop: 8 }}>{value}</div>
      {hint && <div style={{ font: `400 11.5px/1.3 ${T.sans}`, color: T.tertiary, marginTop: 4 }}>{hint}</div>}
    </div>
  );
}

function emailToName(email: string): string {
  const local = email.split("@")[0] || email;
  return local.replace(/[._-]/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

function AgentDots({ agents, owner }: { agents: string[]; owner?: string }) {
  const hasAgents = agents.length > 0;
  if (!owner && !hasAgents) return <span style={{ font: `400 11.5px/1 ${T.sans}`, color: T.tertiary }}>—</span>;
  return (
    <div style={{ display: "flex", alignItems: "center" }}>
      {owner && (
        <span title={owner} style={{ border: `1.5px solid ${T.raised}`, borderRadius: "50%" }}>
          <Avatar name={emailToName(owner)} size={20} tone="neutral" />
        </span>
      )}
      {agents.map((a, i) => (
        <span key={a + i} style={{ marginLeft: (owner || i) ? -6 : 0, border: `1.5px solid ${T.raised}`, borderRadius: "50%" }}>
          <Avatar name={a} size={20} />
        </span>
      ))}
    </div>
  );
}

const rowMenuItem: React.CSSProperties = { display: "block", width: "100%", textAlign: "left", padding: "9px 12px", background: "none", border: "none", cursor: "pointer", font: `500 12.5px/1 ${"'Hanken Grotesk', ui-sans-serif, system-ui, sans-serif"}`, color: T.fg };

// A confirm action — kind drives the copy, button variant, and icon.
type ConfirmAction = { kind: "archive" | "delete"; project: ProjectSummary };

// archive / trash glyphs for the confirm modal. Kept local (same 24×24 stroke convention as the
// shared Icon) so #19 touches no shared design file; the design icon set has neither glyph.
const CONFIRM_ICON: Record<"archive" | "trash", string> = {
  archive: "M21 8v13H3V8 M1 3h22v5H1z M10 12h4",
  trash: "M3 6h18 M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2 M10 11v6 M14 11v6",
};
function ConfirmIcon({ name, size = 16, color = "currentColor" }: { name: "archive" | "trash"; size?: number; color?: string }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color}
      strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" style={{ flexShrink: 0 }}>
      {CONFIRM_ICON[name].split(" M").map((seg, i) => <path key={i} d={i === 0 ? seg : "M" + seg} />)}
    </svg>
  );
}

// Centered confirm overlay — replaces the browser confirm() for archive / permanent delete.
function ConfirmModal({ action, onConfirm, onCancel }:
  { action: ConfirmAction; onConfirm: () => void; onCancel: () => void }) {
  const { kind, project } = action;
  const label = project.name || draftLabel(project.project_id);
  const running = statusOf(project).key === "building" || statusOf(project).key === "researching";
  const isDelete = kind === "delete";
  const title = isDelete ? "Delete project permanently?" : "Archive project?";
  const body = isDelete
    ? `${label} and its build history will be permanently removed. This cannot be undone.`
    : `${label} will move to Archived.${running ? " Any running agents stop and the automation is paused." : ""} You can restore it anytime.`;
  return (
    <div onClick={onCancel} style={{ position: "fixed", inset: 0, zIndex: 50, background: "rgba(9,7,9,0.42)", display: "grid", placeItems: "center", padding: 24 }}>
      <div onClick={(e) => e.stopPropagation()} role="dialog" aria-modal="true"
        style={{ width: "100%", maxWidth: 420, background: T.raised, border: `1px solid ${T.borderSubtle}`, borderRadius: T.rLg, boxShadow: T.shadowMd, padding: "22px 22px 18px" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 11, marginBottom: 10 }}>
          <span style={{ display: "grid", placeItems: "center", width: 36, height: 36, borderRadius: "50%", background: isDelete ? T.dangerSoft : T.brandSoft }}>
            <ConfirmIcon name={isDelete ? "trash" : "archive"} size={17} color={isDelete ? T.danger : T.brandDeep} />
          </span>
          <h2 style={{ font: `700 17px/1.2 ${T.display}`, letterSpacing: "-0.01em", color: T.fg, margin: 0 }}>{title}</h2>
        </div>
        <p style={{ font: `400 13.5px/1.5 ${T.sans}`, color: T.secondary, margin: "0 0 18px" }}>{body}</p>
        <div style={{ display: "flex", justifyContent: "flex-end", gap: 8 }}>
          <Btn variant="ghost" onClick={onCancel}>Cancel</Btn>
          <Btn variant={isDelete ? "danger" : "primary"} onClick={onConfirm}>
            <ConfirmIcon name={isDelete ? "trash" : "archive"} size={14} color="#fff" /> {isDelete ? "Delete permanently" : "Archive project"}
          </Btn>
        </div>
      </div>
    </div>
  );
}

type RowHandlers = {
  onRename: (id: string, name: string) => void;
  onRequestArchive: (r: ProjectSummary) => void;
  onRequestDelete: (r: ProjectSummary) => void;
  onRestore: (id: string) => void;
};

function ProjectRow({ r, onClick, first, onRename, onRequestArchive, onRequestDelete, onRestore }:
  { r: ProjectSummary; onClick: () => void; first: boolean } & RowHandlers) {
  const st = statusOf(r);
  const live = st.key === "building" || st.key === "researching";
  const pct = pctOf(r, st.key);
  const archived = !!r.archived;
  // Archived rows are de-emphasized — but dim only the CONTENT, never the actions menu. CSS
  // opacity on the whole row cascades into the popover (a descendant), greying out
  // "Delete permanently" so it reads as disabled (the reported bug). Keep actions full-opacity.
  const dim = archived ? { opacity: 0.6 } : undefined;
  const [menu, setMenu] = useState(false);
  const [renaming, setRenaming] = useState(false);
  const [name, setName] = useState(r.name || "");
  const stop = (e: React.MouseEvent) => e.stopPropagation();
  return (
    <div role="button" tabIndex={0} onClick={renaming ? undefined : onClick}
      onKeyDown={(e) => { if ((e.key === "Enter" || e.key === " ") && !renaming) onClick(); }}
      style={{ width: "100%", textAlign: "left", cursor: renaming ? "default" : "pointer", background: T.raised,
        borderTop: first ? "none" : `1px solid ${T.borderSubtle}`, padding: "16px 18px", display: "grid",
        gridTemplateColumns: "minmax(0,1fr) 132px 150px 96px 28px", alignItems: "center", gap: 16, transition: "background .12s" }}
      onMouseEnter={(e) => (e.currentTarget.style.background = T.sunken)} onMouseLeave={(e) => (e.currentTarget.style.background = T.raised)}>
      <div style={{ minWidth: 0, ...dim }}>
        {renaming ? (
          <div onClick={stop} style={{ display: "flex", alignItems: "center", gap: 6 }}>
            <TextInput value={name} onChange={setName} size="sm" />
            <Btn size="sm" variant="primary" onClick={() => { onRename(r.project_id, name.trim()); setRenaming(false); }}>Save</Btn>
            <Btn size="sm" variant="ghost" onClick={() => { setRenaming(false); setName(r.name || ""); }}>Cancel</Btn>
          </div>
        ) : (
          <>
            <div style={{ display: "flex", alignItems: "center", gap: 9 }}>
              <span style={{ font: `600 14.5px/1.2 ${T.sans}`, color: r.name ? T.fg : T.tertiary, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{r.name || draftLabel(r.project_id)}</span>
              {archived
                ? <StatusPill tone="neutral">Archived</StatusPill>
                : <StatusPill tone={st.tone} dot={live}>{st.label}</StatusPill>}
            </div>
            <p style={{ margin: "5px 0 0", font: `400 12.5px/1.4 ${T.sans}`, color: T.secondary, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}><Markdown inline>{r.summary || r.description || "—"}</Markdown></p>
            {r.created_by && <p style={{ margin: "3px 0 0", font: `400 11px/1 ${T.mono}`, color: T.tertiary, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>Created by {r.created_by}{r.created_at ? ` · ${new Date(r.created_at * 1000).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" })}` : ""}</p>}
          </>
        )}
      </div>
      <div style={dim}>
        <div style={{ font: `500 11.5px/1 ${T.mono}`, color: T.secondary, marginBottom: 6 }}>{phaseIsStale(r.phase, r.stage) ? `stage ${r.stage} · starting` : (r.phase || "—")}</div>
        {st.key !== "draft" && !archived && (
          <span style={{ display: "block", width: 110, height: 5, borderRadius: 3, background: T.sunken, overflow: "hidden" }}>
            <span style={{ display: "block", height: "100%", width: pct + "%", background: barColor(st.key) }} />
          </span>
        )}
      </div>
      <div style={dim}><AgentDots agents={r.agents || []} owner={r.owner} /></div>
      <div style={{ font: `400 11.5px/1.3 ${T.sans}`, color: T.tertiary, ...dim }}>{relTime(r.updated)}<div style={{ font: `400 11px/1 ${T.mono}`, color: T.tertiary, marginTop: 3 }}>{money(r.spent_usd)}</div></div>
      <div style={{ position: "relative" }} onClick={stop}>
        <button onClick={() => setMenu((v) => !v)} title="Project actions" style={{ display: "grid", placeItems: "center", width: 28, height: 28, borderRadius: 6, border: "none", background: "transparent", cursor: "pointer", color: T.tertiary }}><Icon name="dots" size={16} color={T.tertiary} /></button>
        {menu && (
          <>
            <div onClick={() => setMenu(false)} style={{ position: "fixed", inset: 0, zIndex: 9 }} />
            <div style={{ position: "absolute", right: 0, top: 30, zIndex: 10, background: T.raised, border: `1px solid ${T.borderSubtle}`, borderRadius: T.rMd, boxShadow: T.shadowMd, overflow: "hidden", minWidth: 150 }}>
              {archived ? (
                <>
                  <button onClick={() => { setMenu(false); onRestore(r.project_id); }} style={rowMenuItem}>Restore project</button>
                  <button onClick={() => { setMenu(false); onRequestDelete(r); }} style={{ ...rowMenuItem, color: T.danger }}>Delete permanently</button>
                </>
              ) : (
                <>
                  <button onClick={() => { setMenu(false); setName(r.name || ""); setRenaming(true); }} style={rowMenuItem}>Rename</button>
                  {st.key === "draft"
                    ? <button onClick={() => { setMenu(false); onRequestArchive(r); }} style={{ ...rowMenuItem, color: T.danger }}>Discard draft</button>
                    : <button onClick={() => { setMenu(false); onRequestArchive(r); }} style={{ ...rowMenuItem, color: T.danger }}>Archive project</button>
                  }
                </>
              )}
            </div>
          </>
        )}
      </div>
    </div>
  );
}

function ProjectList({ projects, onOpen, handlers, empty }:
  { projects: ProjectSummary[]; onOpen: (id: string) => void; handlers: RowHandlers; empty: string }) {
  if (!projects.length) return <div style={{ border: `1px dashed ${T.borderDefault}`, borderRadius: T.rLg, padding: "22px", textAlign: "center", font: `400 13px/1.4 ${T.sans}`, color: T.tertiary }}>{empty}</div>;
  return (
    <div style={{ border: `1px solid ${T.borderSubtle}`, borderRadius: T.rLg, overflow: "hidden", boxShadow: T.shadowXs }}>
      {projects.map((r, i) => <ProjectRow key={r.project_id} r={r} first={i === 0} onClick={() => onOpen(r.project_id)} {...handlers} />)}
    </div>
  );
}

export function Dashboard({ onOpen, onNew, onOrg }: { onOpen: (id: string) => void; onNew: () => void; onOrg: () => void }) {
  const [projects, setProjects] = useState<ProjectSummary[]>([]);
  const me = useMe();
  const [org, setOrg] = useState<Org | null>(null);
  const [docCount, setDocCount] = useState<number | null>(null);
  const [memberCount, setMemberCount] = useState<number | null>(null);

  const [loading, setLoading] = useState(true);
  const [ownerFilter, setOwnerFilter] = useState<string>(""); // "" = all
  const [confirm, setConfirm] = useState<ConfirmAction | null>(null);
  // include_archived=true so the Archived section has rows; statusOf() never sees them (split below).
  const loadProjects = () => api.projects(true).then((d) => setProjects(d.projects || [])).catch(() => setProjects([]));
  useEffect(() => {
    setLoading(true);
    loadProjects().finally(() => setLoading(false));
    api.getOrg().then((d) => setOrg(d.org)).catch(() => setOrg(null));
    // counts for the org-preview card (Knowledge base · Team) — real org endpoints, degrade to —
    api.orgDocs().then((d) => setDocCount(d.docs?.length ?? 0)).catch(() => setDocCount(null));
    api.orgMembers().then((d) => setMemberCount(d.members?.length ?? 0)).catch(() => setMemberCount(null));
  }, []);

  // Project CRUD — refetch on success.
  const renameProject = async (id: string, name: string) => {
    if (!name) return;
    try { await api.patchProject(id, { name }); await loadProjects(); } catch { /* surface nothing — keep the row */ }
  };
  const restoreProject = async (id: string) => {
    try { await api.restoreProject(id); await loadProjects(); } catch { /* keep archived */ }
  };
  // Archive + permanent delete go through the styled ConfirmModal; this runs on confirm.
  const runConfirm = async () => {
    if (!confirm) return;
    const { kind, project } = confirm;
    setConfirm(null);
    try {
      if (kind === "delete") await api.deleteProjectPermanently(project.project_id);
      else await api.deleteProject(project.project_id);
      await loadProjects();
    } catch { /* keep the row */ }
  };

  const handlers: RowHandlers = {
    onRename: renameProject,
    onRequestArchive: (r) => setConfirm({ kind: "archive", project: r }),
    onRequestDelete: (r) => setConfirm({ kind: "delete", project: r }),
    onRestore: restoreProject,
  };

  const isAdmin = me?.role === "admin";

  // Unique owners for the filter chips — sorted alphabetically.
  const owners = Array.from(new Set(projects.map((r) => r.owner).filter(Boolean) as string[])).sort();
  const visibleProjects = ownerFilter ? projects.filter((r) => r.owner === ownerFilter) : projects;

  // Archived rows live in their own section; statusOf() must never classify them as active/deployed.
  const archived = visibleProjects.filter((r) => r.archived);
  const liveProjects = visibleProjects.filter((r) => !r.archived);
  const active = liveProjects.filter((r) => statusOf(r).key !== "deployed");
  const shipped = liveProjects.filter((r) => statusOf(r).key === "deployed");
  const building = active.filter((r) => statusOf(r).key === "building");
  const researching = active.filter((r) => statusOf(r).key === "researching");
  const withAgents = active.filter((r) => { const k = statusOf(r).key; return (k === "building" || k === "researching") && (r.agents?.length || 0) > 0; }).length;
  const totalSpend = liveProjects.reduce((s, r) => s + (r.spent_usd || 0), 0);
  const orgName = org?.name || "Your organization";

  // Org-admin preview stats — built only from real org data (KB doc count + team member count
  // come from the live /api/org/docs and /api/org/members endpoints; degrade to — until loaded).
  const orgStats: [string, string][] = org
    ? ([
        ["Industry", org.industry || "—"],
        ["Scale", org.headcount || "—"],
        ["Knowledge base", docCount != null ? `${docCount} document${docCount === 1 ? "" : "s"}` : "—"],
        ["Connected systems", org.connected_systems?.length ? org.connected_systems.join(", ") : "—"],
        ["Team", memberCount != null ? `${memberCount} member${memberCount === 1 ? "" : "s"}` : "—"],
      ] as [string, string][])
    : [];

  return (
    <div style={{ height: "100vh", display: "flex", flexDirection: "column", background: T.bg, fontFamily: T.sans }}>
      {/* top bar */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "13px 26px", background: T.raised, borderBottom: `1px solid ${T.borderSubtle}`, flexShrink: 0 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <Wordmark />
          <span style={{ font: `400 13px/1 ${T.mono}`, color: T.tertiary }}>/</span>
          <button onClick={onOrg} title="Manage organization" style={{ display: "inline-flex", alignItems: "center", gap: 7, background: "none", border: "none", cursor: "pointer", padding: 0 }}>
            <Avatar name={orgName} size={22} tone="neutral" />
            <span style={{ font: `600 13px/1 ${T.sans}`, color: T.fg }}>{orgName}</span>
            <Icon name="chevronDown" size={14} color={T.tertiary} />
          </button>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
          <span style={{ display: "grid", placeItems: "center", width: 32, height: 32, borderRadius: "50%", border: `1px solid ${T.borderSubtle}`, background: T.raised }}><Icon name="search" size={15} color={T.secondary} /></span>
          <AccountMenu size={30} />
        </div>
      </div>

      {/* scroll body */}
      <div style={{ flex: 1, overflow: "auto", padding: "26px 26px 36px" }}>
        <div style={{ maxWidth: 1080, margin: "0 auto", display: "flex", flexDirection: "column", gap: 22 }}>

          {/* header row */}
          <div style={{ display: "flex", alignItems: "flex-end", justifyContent: "space-between", gap: 16, flexWrap: "wrap" }}>
            <div>
              <CategoryLabel style={{ marginBottom: 9 }}>Workspace</CategoryLabel>
              <h1 style={{ font: `700 30px/1.1 ${T.display}`, letterSpacing: "-0.02em", color: T.fg, margin: 0 }}>Your projects</h1>
              <p style={{ font: `400 14px/1.5 ${T.sans}`, color: T.secondary, margin: "7px 0 0" }}>Pick up where the factory left off, or start something new.</p>
            </div>
            <Btn variant="primary" size="lg" onClick={onNew}><Icon name="plus" size={15} color="#fff" /> New project</Btn>
          </div>

          {/* pulse strip — computed from real projects */}
          <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 12 }}>
            {loading ? (<><MetricCardSkel /><MetricCardSkel /><MetricCardSkel /><MetricCardSkel /></>) : (<>
              <MetricCard label="Active projects" value={String(active.length)} hint={`${withAgents} with agents working now`} accent />
              <MetricCard label="In build" value={String(building.length)} hint={`${researching.length} researching`} />
              <MetricCard label="Deployed" value={String(shipped.length)} hint={shipped[0] ? (shipped[0].name || draftLabel(shipped[0].project_id)) + " · live" : "none yet"} />
              <MetricCard label="Spend to date" value={money(totalSpend) === "—" ? "$0.00" : money(totalSpend)} hint={org?.monthly_budget_cap != null ? `of $${org.monthly_budget_cap} cap` : `across ${liveProjects.length} project${liveProjects.length === 1 ? "" : "s"}`} />
            </>)}
          </div>

          {/* org admin preview — ADMINS ONLY; non-admins see nothing (the list moves up). */}
          {isAdmin && org && (
            <button onClick={onOrg} style={{ width: "100%", textAlign: "left", cursor: "pointer", border: `1px solid ${T.borderSubtle}`, background: T.raised, borderRadius: T.rLg, overflow: "hidden", boxShadow: T.shadowXs }}
              onMouseEnter={(e) => (e.currentTarget.style.borderColor = T.brand)} onMouseLeave={(e) => (e.currentTarget.style.borderColor = T.borderSubtle)}>
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "12px 16px", borderBottom: `1px solid ${T.borderSubtle}`, background: T.sunken }}>
                <div style={{ display: "flex", alignItems: "center", gap: 9 }}>
                  <Avatar name={orgName} size={24} tone="neutral" />
                  <CategoryLabel style={{ color: T.fg }}>Organization</CategoryLabel>
                  <span style={{ font: `500 10px/1 ${T.mono}`, letterSpacing: "0.06em", color: T.brandDeep, background: T.brandSoft, padding: "3px 6px", borderRadius: 4 }}>ADMIN</span>
                </div>
                <span style={{ display: "inline-flex", alignItems: "center", gap: 5, font: `500 12.5px/1 ${T.sans}`, color: T.brandDeep }}>Manage organization <Icon name="arrowRight" size={13} color={T.brandDeep} /></span>
              </div>
              <div style={{ display: "grid", gridTemplateColumns: `repeat(${orgStats.length}, 1fr)`, gap: "1px", background: T.borderSubtle }}>
                {orgStats.map(([k, v]) => (
                  <div key={k} style={{ background: T.raised, padding: "11px 16px" }}>
                    <CategoryLabel style={{ display: "block", marginBottom: 4 }}>{k}</CategoryLabel>
                    <span style={{ font: `500 12.5px/1.3 ${T.sans}`, color: T.fg, overflow: "hidden", textOverflow: "ellipsis", display: "block", whiteSpace: "nowrap" }}>{v}</span>
                  </div>
                ))}
              </div>
            </button>
          )}

          {/* owner filter — only shown when there are multiple owners */}
          {owners.length > 1 && (
            <div style={{ display: "flex", alignItems: "center", gap: 6, flexWrap: "wrap" }}>
              {[{ email: "", label: "All team members" }, ...owners.map((o) => ({ email: o, label: emailToName(o) }))].map(({ email, label }) => {
                const on = ownerFilter === email;
                return (
                  <button key={email} onClick={() => setOwnerFilter(email)}
                    style={{ display: "inline-flex", alignItems: "center", gap: 5, padding: "5px 10px", borderRadius: 99,
                      border: `1px solid ${on ? T.brand : T.borderSubtle}`, background: on ? T.brandSoft : T.raised,
                      cursor: "pointer", font: `${on ? 600 : 500} 12px/1 ${T.sans}`,
                      color: on ? T.brandDeep : T.secondary }}>
                    {email && <Avatar name={label} size={16} tone="neutral" />}
                    {label}
                  </button>
                );
              })}
            </div>
          )}

          {/* in progress */}
          <div>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 10 }}>
              <CategoryLabel>In progress{loading ? "" : ` · ${active.length}`}</CategoryLabel>
              <span style={{ font: `400 11.5px/1 ${T.sans}`, color: T.tertiary }}>Sorted by last activity</span>
            </div>
            {loading ? (
              <div style={{ border: `1px solid ${T.borderSubtle}`, borderRadius: T.rLg, overflow: "hidden" }}>
                {[0, 1, 2].map((i) => <ProjectRowSkel key={i} first={i === 0} />)}
              </div>
            ) : (
              <ProjectList projects={active} onOpen={onOpen} handlers={handlers} empty='No projects in progress. Start one with "New project".' />
            )}
          </div>

          {/* deployed */}
          {shipped.length > 0 && (
            <div>
              <CategoryLabel style={{ marginBottom: 10 }}>Deployed · {shipped.length}</CategoryLabel>
              <ProjectList projects={shipped} onOpen={onOpen} handlers={handlers} empty="" />
            </div>
          )}

          {/* archived — only shown when there's at least one archived project */}
          {archived.length > 0 && (
            <div>
              <CategoryLabel style={{ marginBottom: 10 }}>Archived · {archived.length}</CategoryLabel>
              <ProjectList projects={archived} onOpen={onOpen} handlers={handlers} empty="" />
            </div>
          )}

        </div>
      </div>

      {confirm && <ConfirmModal action={confirm} onConfirm={runConfirm} onCancel={() => setConfirm(null)} />}
    </div>
  );
}
