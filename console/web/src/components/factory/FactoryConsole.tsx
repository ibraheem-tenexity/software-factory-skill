// FactoryConsole.tsx — PRD §2.6 "THE CORE SCREEN". A faithful assembly of the factory-console
// design, wired ENTIRELY to real backend data (no client-side build simulation).
//
// Layout: top bar (← back · wordmark · project · phase pill · spend/cap) · LEFT Concierge rail ·
// MAIN column (Stage rail · stage-triggered Wait-for-deps · Kanban/Tree/Map toggle · delivery
// footer). A DocViewer modal opens artifacts + ticket bodies.
//
// Liveness: polls status + tickets + graph every 4s (agents run server-side; no sim button).
import { useEffect, useState } from "react";
import { T, Icon, Wordmark, StatusPill, Btn, Segmented, TextInput, CategoryLabel } from "../onboarding/design";
import { AccountMenu } from "../AccountMenu";
import { api, phaseIsStale, ProjectSummary, Graph, Ticket, RepoAccess, DepsResponse } from "../../api";
import { phaseStatesFromGraph, atWaitForDeps, PhaseStatus, toneForHaltedPhase } from "./pipeline";
import { StageRail } from "./StageRail";
import { WaitForDeps } from "./WaitForDeps";
import { BuildBoard } from "./BuildBoard";
import { TreeView, MapView } from "./NodeMap";
import { Concierge } from "./Concierge";
import { DocViewer, artifactsFromGraph, ArtifactRef, openArtifact } from "./Artifacts";
import { RecoveryBar } from "./RecoveryBar";
import { KanbanCardSkel, MessageSkel } from "../skeleton";

type Status = ProjectSummary & Record<string, any>;
type View = "kanban" | "tree" | "map";
type Doc = { label: string; path?: string; content?: string; id?: number; url?: string | null; agent?: string; kind?: string } | null;

// SOF-100: the click-through ticket panel used to dump raw `description` — the goal/acceptance/
// dod/design_refs/dependencies/scope_genre/implementation_notes fields never rendered anywhere.
// Reuses the existing DocViewer (path: "ticket.md" so it renders as markdown) rather than a new
// bespoke component.
function ticketDetailMarkdown(t: Ticket, projectId: string): string {
  const lines: string[] = [];
  if (t.goal) lines.push(`**Goal:** ${t.goal}`, "");
  if (t.scope_genre) lines.push(`**Scope genre:** ${t.scope_genre}`, "");
  lines.push("## Acceptance Criteria", "", t.acceptance || "_(none recorded)_", "");
  lines.push("## Definition of Done", "", t.dod || "_(none recorded)_", "");
  if (t.design_refs && t.design_refs.length > 0) {
    lines.push("## Design References", "");
    for (const scr of t.design_refs) {
      const href = `/api/projects/${projectId}/artifact?path=${encodeURIComponent(`mockups/${scr}.html`)}&raw=1`;
      lines.push(`- [${scr}](${href})`);
    }
    lines.push("");
  }
  if (t.dependencies && t.dependencies.length > 0) {
    lines.push("## Dependencies", "");
    for (const dep of t.dependencies) lines.push(`- ${dep}`);
    lines.push("");
  }
  if (t.implementation_notes) lines.push("## Implementation Notes", "", t.implementation_notes, "");
  // SOF-118: null = not yet closed (mark_done sets it); [] = an honest "nothing to declare".
  if (t.decision_log === null || t.decision_log === undefined) {
    lines.push("## Decision Log", "", "_(not yet closed — recorded when this ticket is marked done)_", "");
  } else if (t.decision_log.length === 0) {
    lines.push("## Decision Log", "", "_Nothing declared — no assumptions, shortcuts, or known gaps._", "");
  } else {
    lines.push("## Decision Log", "");
    for (const entry of t.decision_log) {
      const label = entry.type === "known-gap" ? "Known Gap" : entry.type === "shortcut" ? "Shortcut" : "Assumption";
      lines.push(`**${label}: ${entry.statement}**`);
      lines.push(`- Reason: ${entry.reason}`);
      lines.push(`- Affected surface: ${entry.affected_surface}`, "");
    }
  }
  if (t.description) lines.push("## Description", "", t.description, "");
  return lines.join("\n") || "(no ticket detail recorded)";
}

const VIEWS: { id: View; label: string; icon: string }[] = [
  { id: "kanban", label: "Kanban", icon: "kanban" },
  { id: "tree", label: "Tree", icon: "tree" },
  { id: "map", label: "Map", icon: "map" },
];
const VIEW_TITLE: Record<View, string> = { kanban: "Build board", tree: "Process tree", map: "Process graph" };

function phaseTone(phase?: string): "success" | "warning" | "danger" | "neutral" {
  const halted = toneForHaltedPhase(phase);
  if (halted) return halted;
  if (phase) return "warning";   // an in-flight phase (design renders the build phase amber)
  return "neutral";
}

function setParam(key: string, value: string | null) {
  const p = new URLSearchParams(location.search);
  if (value === null) p.delete(key); else p.set(key, value);
  history.replaceState(null, "", "?" + p.toString());
}

// The three §2.5 peer tabs rendered inside the console header (design: buildprogress.jsx:132-143).
const PEER_TABS: { id: "overview" | "build" | "documents"; label: string }[] = [
  { id: "overview", label: "Overview" },
  { id: "build", label: "Factory console" },
  { id: "documents", label: "Documents" },
];

// A plain card wrapper for the operational panels re-homed here from Overview (SOF-241 review).
function ConsolePanel({ title, count, children, action }:
  { title: string; count?: number; children: React.ReactNode; action?: React.ReactNode }) {
  return (
    <section style={{ background: T.raised, border: `1px solid ${T.borderSubtle}`, borderRadius: T.rXl, boxShadow: T.shadowXs, overflow: "hidden" }}>
      <header style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "12px 16px", borderBottom: `1px solid ${T.borderSubtle}` }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <CategoryLabel>{title}</CategoryLabel>
          {count != null && <span style={{ font: `500 10px/1 ${T.mono}`, color: T.tertiary, background: T.sunken, borderRadius: 9, padding: "2px 6px" }}>{count}</span>}
        </div>
        {action}
      </header>
      <div style={{ padding: 16 }}>{children}</div>
    </section>
  );
}

// Repository access — the GitHub-invite flow for this project's build repo. Self-contained (owns its
// own fetch/state). Moved here from the Overview snapshot (SOF-241 review; temporary — SOF-250
// finalizes the placement). The owner enters/updates a GitHub username and requests an invite; the
// server's real status/detail (and any failure reason) is surfaced verbatim, never a dead control.
function RepositoryAccessPanel({ projectId }: { projectId: string }) {
  const [repoAccess, setRepoAccess] = useState<RepoAccess | null>(null);
  const [githubUsername, setGithubUsername] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const load = () => api.repoAccess(projectId).then((a) => {
    setRepoAccess(a); setGithubUsername(a.github_username || "");
  }).catch(() => setRepoAccess(null));
  useEffect(() => { load(); }, [projectId]);

  const normalized = githubUsername.trim().replace(/^@/, "");
  const stored = repoAccess?.github_username || "";
  const needsRequest = repoAccess?.status !== "invited" || normalized !== stored;
  const request = async () => {
    if (!normalized || submitting) return;
    setSubmitting(true); setError("");
    try {
      const a = await api.requestRepoAccess(projectId, normalized);
      setRepoAccess(a); setGithubUsername(a.github_username || normalized);
    } catch (e: any) {
      setError(typeof e?.detail === "string" ? e.detail : "Could not request repository access.");
    } finally { setSubmitting(false); }
  };

  return (
    <ConsolePanel title="Repository access">
      <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
        {repoAccess?.repo_url && (
          <a href={repoAccess.repo_url} target="_blank" rel="noopener noreferrer"
            style={{ display: "inline-flex", alignItems: "center", gap: 6, width: "fit-content", font: `500 12px/1.2 ${T.sans}`, color: T.brandDeep, textDecoration: "none" }}>
            <Icon name="github" size={14} color={T.brandDeep} /> Open repository <Icon name="external" size={11} color={T.brandDeep} />
          </a>
        )}
        <div>
          <CategoryLabel style={{ display: "block", marginBottom: 6 }}>GitHub username</CategoryLabel>
          <TextInput value={githubUsername} onChange={setGithubUsername} placeholder="e.g. octocat" />
        </div>
        {repoAccess && (
          <div style={{ display: "flex", alignItems: "flex-start", gap: 7 }}>
            <StatusPill tone={repoAccess.status === "invited" ? "success" : repoAccess.status === "failed" ? "danger" : "neutral"}>
              {repoAccess.status === "invited" ? "Invited" : repoAccess.status === "failed" ? "Invite failed" : repoAccess.status === "waiting_for_repo" ? "Waiting for repo" : "Not invited"}
            </StatusPill>
            <span style={{ flex: 1, font: `400 11.5px/1.4 ${T.sans}`, color: repoAccess.status === "failed" ? T.danger : T.tertiary, overflowWrap: "anywhere" }}>{repoAccess.detail}</span>
          </div>
        )}
        {error && <span style={{ font: `500 11.5px/1.3 ${T.sans}`, color: T.danger }}>{error}</span>}
        {needsRequest && <Btn variant="secondary" size="sm" full disabled={!normalized || submitting} onClick={request}>
          {submitting ? "Requesting…" : repoAccess?.status === "failed" ? "Retry invitation" : "Request invitation"}
        </Btn>}
      </div>
    </ConsolePanel>
  );
}

// #107 post-deploy "provide your own key": a mocked provider dep (e.g. OPENROUTER_API_KEY) can be
// swapped for a real value AFTER the fact, pushing onto the LIVE app's Railway service (redeploy)
// via POST /deps/provide. Self-contained; moved here from Overview (SOF-241 review; temporary —
// SOF-250 finalizes placement). Only meaningful post-deploy, so the caller gates on status.done.
const DISPOSITION_PILL: Record<string, ["neutral" | "success" | "warning" | "info", string]> = {
  mock: ["warning", "Mocked ⚠️"],
  provide: ["success", "Provided ✓"],
  mcp: ["info", "Self-handled ✓"],
  "deploy-db": ["info", "Factory-provided ✓"],
};

function DependenciesPanel({ projectId }: { projectId: string }) {
  const [deps, setDeps] = useState<DepsResponse | null>(null);
  const [editing, setEditing] = useState<string | null>(null);
  const [value, setValue] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [errors, setErrors] = useState<Record<string, string>>({});
  // Soft (non-error) note: the key WAS applied to the live app but the vault write failed, so it
  // wasn't recorded — a later replace would need it re-entered.
  const [warnings, setWarnings] = useState<Record<string, string>>({});
  const load = () => api.deps(projectId).then(setDeps).catch(() => setDeps(null));
  useEffect(() => { load(); }, [projectId]);

  if (!deps || !deps.deps_required.length) return null;

  const submit = async (name: string) => {
    if (!value.trim()) return;
    setSubmitting(true);
    try {
      const r = await api.provideDep(projectId, name, value);
      if (r.ok) {
        setEditing(null); setValue("");
        setErrors((e) => ({ ...e, [name]: "" }));
        setWarnings((w) => ({ ...w, [name]: r.vault_saved === false
          ? "Applied to your app — it's using the new key now — but it wasn't saved to your vault. You'll need to re-enter it if you replace it again." : "" }));
        load();
      } else {
        setErrors((e) => ({ ...e, [name]: r.detail || "Failed to apply key" }));
      }
    } catch {
      setErrors((e) => ({ ...e, [name]: "Failed to apply key" }));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <ConsolePanel title="Dependencies" count={deps.deps_required.length}>
      <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
        {deps.deps_required.map((name) => {
          const disp = deps.disposition[name] || "mock";
          const [tone, label] = DISPOSITION_PILL[disp] || ["neutral", disp];
          const canReplace = disp === "mock" || disp === "provide";
          return (
            <div key={name} style={{ display: "flex", flexDirection: "column", gap: 6, padding: "9px 11px", borderRadius: T.rLg, border: `1px solid ${T.borderSubtle}`, background: T.bg }}>
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8, flexWrap: "wrap" }}>
                <span style={{ font: `500 12px/1.2 ${T.mono}`, color: T.fg, wordBreak: "break-all" }}>{name}</span>
                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <StatusPill tone={tone}>{label}</StatusPill>
                  {canReplace && editing !== name && (
                    <button onClick={() => { setEditing(name); setValue(""); }}
                      style={{ font: `500 11.5px/1 ${T.sans}`, color: T.brandDeep, background: "none", border: "none", cursor: "pointer" }}>
                      {disp === "mock" ? "Provide key" : "Replace"}
                    </button>
                  )}
                </div>
              </div>
              {disp === "mock" && (
                <p style={{ margin: 0, font: `400 11.5px/1.4 ${T.sans}`, color: T.tertiary }}>
                  Using a placeholder — provide your key to enable live AI.
                </p>
              )}
              {editing === name && (
                <div style={{ display: "flex", gap: 6 }}>
                  <input type="password" value={value} onChange={(e) => setValue(e.target.value)} placeholder="paste your real key"
                    style={{ flex: 1, height: 30, padding: "0 9px", borderRadius: T.rMd, border: `1px solid ${T.borderDefault}`, background: T.raised, color: T.fg, font: `400 12px/1 ${T.mono}`, outline: "none" }} />
                  <Btn size="sm" variant="primary" disabled={!value.trim() || submitting} onClick={() => submit(name)}>{submitting ? "Applying…" : "Apply"}</Btn>
                  <Btn size="sm" variant="ghost" onClick={() => { setEditing(null); setValue(""); }}>Cancel</Btn>
                </div>
              )}
              {errors[name] && <span style={{ font: `500 11.5px/1.3 ${T.sans}`, color: T.danger }}>{errors[name]}</span>}
              {warnings[name] && <span style={{ font: `500 11.5px/1.3 ${T.sans}`, color: T.warning }}>{warnings[name]}</span>}
            </div>
          );
        })}
      </div>
    </ConsolePanel>
  );
}

export function FactoryConsole({ projectId, onBack, onSwitchTab }:
  { projectId: string; onBack: () => void;
    // Navigate back to the ProjectView with the given tab active (App threads this through).
    onSwitchTab?: (tab: "overview" | "documents") => void }) {
  const [status, setStatus] = useState<Status>({} as Status);
  const [graph, setGraph] = useState<Graph>({ nodes: [], edges: [] });
  const [tickets, setTickets] = useState<Ticket[]>([]);
  const [view, setView] = useState<View>(() => {
    const v = new URLSearchParams(location.search).get("fview");
    return (["tree", "map"].includes(v || "") ? v : "kanban") as View;
  });
  const [doc, setDoc] = useState<Doc>(null);
  const [previewDoc, setPreviewDoc] = useState<Doc>(null);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => { setParam("fview", view === "kanban" ? null : view); }, [view]);

  useEffect(() => {
    let live = true;
    const tick = () => {
      api.status(projectId).then((s) => { if (live) { setStatus(s); setLoaded(true); } }).catch(() => {});
      api.tickets(projectId).then((d) => live && setTickets(d.tickets || [])).catch(() => {});
      api.graph(projectId).then((g) => live && setGraph(g)).catch(() => {});
    };
    tick();
    const h = setInterval(tick, 4000);
    return () => { live = false; clearInterval(h); };
  }, [projectId]);

  const phaseStates: Record<string, PhaseStatus> = phaseStatesFromGraph(graph.nodes);
  const artifacts: ArtifactRef[] = artifactsFromGraph(graph);
  const showDeps = atWaitForDeps(status);

  const cap = status.budget_ceiling || 0;
  const spent = status.spent_usd || 0;
  const overCap = cap > 0 && spent > cap;

  // ticket progress (Done column = approved); pct drives the header bar.
  const doneTickets = tickets.filter((t) => t.status === "approved").length;
  const pct = tickets.length ? Math.round((doneTickets / tickets.length) * 100) : 0;
  const allTicketsDone = tickets.length > 0 && doneTickets === tickets.length;

  // delivery footer: surface repo + live app once the run shipped (deployed / all approved).
  const repoArt = artifacts.find((a) => a.url && /repo|github/i.test(a.label));
  const liveArt = artifacts.find((a) => a.url && /live|app|deploy/i.test(a.label));
  const delivered = status.done || allTicketsDone;
  const liveUrl = liveArt?.url || status.deploy_url;

  // Open an artifact ref: full viewer when it has an id, else the in-console DocViewer (with the
  // producing agent + kind so the viewer header can render its badge + "produced by" line).
  const openDocFromRef = (a: ArtifactRef) =>
    a.id ? openArtifact(a.id) : setDoc({ label: a.label, path: a.path, agent: a.agent, kind: a.kind });
  const previewDocFromRef = (a: ArtifactRef) =>
    setPreviewDoc({ label: a.label, path: a.path, url: a.url, id: a.id, agent: a.agent, kind: a.kind });

  // Recovery: paused/crashed runs show the RecoveryBar + halted rail state
  const halted = status.phase === "paused" || status.phase === "crashed";
  const haltedNode: string | undefined = status.paused_at_node || status.crashed_at_node;
  const doneNodes = Object.entries(phaseStates).filter(([, s]) => s === "done").map(([id]) => id);

  // manual kill-switch — only while a live run is in flight (a stage/poller to halt)
  const running = !!status.phase && !status.deploy_url && !status.done && !["done", "draft", "stopped", "paused", "crashed"].includes(status.phase);
  const pauseRun = async () => {
    try { const s = await api.pauseProject(projectId); setStatus(s as Status); } catch { /* noop */ }
  };

  return (
    <div style={{ height: "100vh", display: "flex", flexDirection: "column", background: T.bg, color: T.fg, font: `400 14px/1.5 ${T.sans}` }}>
      {/* ── top bar (+ §2.5 peer-tab strip) ── */}
      <div style={{ borderBottom: `1px solid ${T.borderSubtle}`, background: T.raised, flexShrink: 0 }}>
      <header style={{ display: "flex", alignItems: "center", gap: 14, padding: "0 18px", height: 56 }}>
        <button onClick={onBack} style={{ display: "inline-flex", alignItems: "center", gap: 6, cursor: "pointer",
          border: "none", background: "transparent", color: T.secondary, font: `500 13px/1 ${T.sans}`, padding: "6px 8px", borderRadius: T.rMd }}>
          <Icon name="arrowLeft" size={15} /> Projects
        </button>
        <Wordmark size={17} />
        {status.name && (
          <>
            <span style={{ font: `400 13px/1 ${T.mono}`, color: T.tertiary }}>/</span>
            <span style={{ font: `600 13px/1 ${T.sans}`, color: T.fg }}>{status.name}</span>
          </>
        )}
        <span style={{ flex: 1 }} />
        {(status.runtime || status.model) && (
          <span style={{ display: "inline-flex", alignItems: "center", gap: 5,
            font: `500 11px/1 ${T.mono}`, color: T.tertiary,
            padding: "3px 9px", borderRadius: T.rMd, border: `1px solid ${T.borderSubtle}` }}>
            engine
            <span style={{ color: T.fg }}>{status.model || status.runtime}</span>
            ·
            <span style={{ color: status.key_source === "BYOK" ? T.brand : T.secondary }}>
              {status.key_source === "BYOK" ? "BYO KEY" : "TENEXITY KEY"}
            </span>
          </span>
        )}
        {status.phase && (
          <StatusPill tone={phaseTone(status.phase)}>
            {status.phase === "done" || status.phase === "stopped" ? status.phase
            : status.phase === "paused" || status.phase === "crashed"
              ? `${status.phase}${haltedNode ? ` at ${haltedNode}` : ""}`
              : phaseIsStale(status.phase, status.stage)
                ? `stage ${status.stage} · starting`
                : `phase ${status.phase} · stage ${status.stage || ""}`}
          </StatusPill>
        )}
        <span style={{ font: `500 12px/1 ${T.mono}`, color: overCap ? T.danger : T.secondary }}>
          spent <b style={{ color: overCap ? T.danger : T.fg }}>${spent.toFixed(2)}</b>{cap > 0 && ` / $${cap.toFixed(0)} cap`}
        </span>
        {running && (
          <button onClick={pauseRun} title="Pause this run — can be resumed"
            style={{ display: "inline-flex", alignItems: "center", gap: 5, height: 28, padding: "0 9px", borderRadius: T.rMd, cursor: "pointer", border: `1px solid ${T.borderDefault}`, background: T.raised, color: T.secondary, font: `600 10.5px/1 ${T.mono}` }}>
            <Icon name="pause" size={11} color={T.secondary} /> Pause
          </button>
        )}
        <AccountMenu size={26} />
      </header>
      {onSwitchTab && (
        <div style={{ display: "flex", gap: 2, padding: "0 18px" }}>
          {PEER_TABS.map((t) => {
            const on = t.id === "build";
            return (
              <button key={t.id} onClick={on ? undefined : () => onSwitchTab(t.id as "overview" | "documents")}
                style={{ position: "relative", padding: "11px 14px", background: "none", border: "none",
                  cursor: on ? "default" : "pointer", font: `${on ? 600 : 500} 13px/1 ${T.sans}`, color: on ? T.fg : T.secondary }}>
                {t.label}
                {on && <span style={{ position: "absolute", left: 10, right: 10, bottom: -1, height: 2, background: T.brand, borderRadius: 2 }} />}
              </button>
            );
          })}
        </div>
      )}
      </div>

      {/* ── body: Concierge rail + main column ── */}
      <div style={{ flex: 1, minHeight: 0, display: "grid", gridTemplateColumns: "340px 1fr", gap: 0 }}>
        <div style={{ borderRight: `1px solid ${T.borderSubtle}`, background: T.raised, minHeight: 0, overflow: "hidden",
          display: "flex", flexDirection: "column" }}>
          {!loaded ? (
            <div style={{ display: "flex", flexDirection: "column", gap: 12, padding: 16 }}>
              {[0, 1, 2].map((i) => <MessageSkel key={i} />)}
            </div>
          ) : (
            <Concierge projectId={projectId} projectName={status.name || ""} artifacts={artifacts}
              onOpenArtifact={openDocFromRef} isBuilding={running}
              ticketsDone={doneTickets} ticketsTotal={tickets.length}
              buildDone={delivered} deployed={!!liveUrl} phase={status.phase} />
          )}
        </div>

        <main style={{ overflowY: "auto", padding: 20, display: "flex", flexDirection: "column", gap: 16 }}>
          <StageRail graph={graph} phaseStates={phaseStates} depsSatisfied={!!status.deps_satisfied} atDeps={showDeps}
            haltedNode={halted ? haltedNode : undefined}
            onRewind={halted && haltedNode ? (node) => api.rewindTo(projectId, node).then((s) => setStatus(s as Status)).catch(() => {}) : undefined} />

          {halted && haltedNode && (
            <RecoveryBar projectId={projectId} phase={status.phase as "paused" | "crashed"}
              haltedNode={haltedNode} doneNodes={doneNodes}
              onUpdate={(s) => setStatus(s as Status)} />
          )}

          {showDeps && <WaitForDeps projectId={projectId} onResolved={() => api.status(projectId).then(setStatus).catch(() => {})} />}

          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 10 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
              <span style={{ font: `700 16px/1 ${T.display}`, letterSpacing: "-0.015em", color: T.fg }}>{VIEW_TITLE[view]}</span>
              <span style={{ font: `500 11px/1 ${T.mono}`, color: T.secondary }}>{doneTickets}/{tickets.length} tickets · {pct}%</span>
              <span style={{ width: 110, height: 6, borderRadius: 3, background: T.sunken, overflow: "hidden", display: "inline-block" }}>
                <span style={{ display: "block", height: "100%", width: pct + "%", background: allTicketsDone ? T.success : T.brand, transition: "width .5s" }} />
              </span>
            </div>
            <Segmented value={view} onChange={(v) => setView(v as View)} options={VIEWS} />
          </div>

          {view === "kanban" && !loaded && (
            <div style={{ display: "grid", gridTemplateColumns: "repeat(5, 1fr)", gap: 12, alignItems: "start" }}>
              {[0, 1, 2, 3, 4].map((i) => (
                <div key={i} style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                  <KanbanCardSkel dark />
                  <KanbanCardSkel dark />
                </div>
              ))}
            </div>
          )}
          {view === "kanban" && loaded && <BuildBoard tickets={tickets}
            onOpenTicket={(t) => setDoc({ label: `#${t.id} ${t.title}`, path: "ticket.md",
              content: ticketDetailMarkdown(t, projectId) })} />}
          {view === "tree" && <TreeView graph={graph} onOpenArtifact={openDocFromRef}
            ticketsDone={doneTickets} ticketsTotal={tickets.length} onViewBoard={() => setView("kanban")} />}
          {view === "map" && <MapView graph={graph} onPreviewArtifact={previewDocFromRef} />}

          {/* ── delivery footer ── (design: delivered ⇒ green repo+live; otherwise the QA loop note) */}
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12, flexWrap: "wrap",
            padding: "11px 15px", borderRadius: T.rLg,
            background: delivered ? T.successSoft : T.raised, border: `1px solid ${delivered ? T.success : T.borderSubtle}` }}>
            {delivered ? (
              <>
                <span style={{ display: "inline-flex", alignItems: "center", gap: 8, font: `600 13px/1.3 ${T.sans}`, color: T.success }}>
                  <Icon name="check" size={15} color={T.success} /> Deployed · green across the Playwright suite
                </span>
                <div style={{ display: "flex", gap: 9 }}>
                  {repoArt?.url && <Btn variant="secondary" size="sm" onClick={() => window.open(repoArt.url!, "_blank")}><Icon name="github" size={14} /> Repository</Btn>}
                  {liveUrl && <Btn variant="primary" size="sm" onClick={() => window.open(liveUrl, "_blank")}>Open live app <Icon name="arrowRight" size={13} color="#fff" /></Btn>}
                </div>
              </>
            ) : (
              <>
                <span style={{ font: `400 12.5px/1.4 ${T.sans}`, color: T.secondary }}>
                  Bugs found in <b style={{ color: T.fg }}>Testing</b> loop back to <b style={{ color: T.fg }}>Building</b> before a ticket reaches <b style={{ color: T.fg }}>Done</b>.
                </span>
                <span style={{ font: `500 11px/1 ${T.mono}`, color: T.tertiary }}>deploy unlocks at 100%</span>
              </>
            )}
          </div>

          {/* Operational panels re-homed from Overview (SOF-241 review; temporary — SOF-250 finalizes
              placement): repository access always available; the post-deploy dependency key-swap
              (#107) only once the app is live. */}
          <RepositoryAccessPanel projectId={projectId} />
          {status.done && <DependenciesPanel projectId={projectId} />}
        </main>
      </div>

      <DocViewer projectId={projectId} doc={doc} onClose={() => setDoc(null)} />
      <DocViewer projectId={projectId} doc={previewDoc} preview onClose={() => setPreviewDoc(null)} />
    </div>
  );
}
