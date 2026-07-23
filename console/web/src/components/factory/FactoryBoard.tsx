// FactoryBoard.tsx — the Factory console PEER BODY (SOF-239). The real factory board
// (StageRail · Wait-for-deps · Kanban/Tree/Map · delivery footer) extracted from the former
// FactoryConsole full-screen shell so it renders INSIDE the unified Project Console shell
// (ProjectConsole.tsx) as the `factory` peer — no second header, no second Concierge. The shell
// owns the single header, peer nav, and the one persistent Concierge; it polls status/tickets/graph
// once and passes them here, so this component is presentational + owns only its board-local view
// state (?fview) and its DocViewer modals. A compact factory sub-header keeps the factory-specific
// controls (engine · spend/cap · Pause) that the minimal shell header does not carry.
import { useEffect, useState, type ReactNode } from "react";
import { T, Icon, StatusPill, Btn, Segmented, TextInput, CategoryLabel } from "../onboarding/design";
import { api, phaseIsStale, ProjectSummary, Graph, Ticket, RepoAccess, DepsResponse } from "../../api";
import { phaseStatesFromGraph, atWaitForDeps, PhaseStatus, toneForHaltedPhase } from "./pipeline";
import { StageRail } from "./StageRail";
import { WaitForDeps } from "./WaitForDeps";
import { BuildBoard } from "./BuildBoard";
import { TreeView, MapView } from "./NodeMap";
import { DocViewer, artifactsFromGraph, ArtifactRef, openArtifact } from "./Artifacts";
import { RecoveryBar } from "./RecoveryBar";
import { FactoryActivity } from "./FactoryActivity";
import { KanbanCardSkel } from "../skeleton";

type Status = ProjectSummary & Record<string, any>;
type View = "activity" | "kanban" | "tree" | "map";
type Doc = { label: string; path?: string; content?: string; id?: number; url?: string | null; agent?: string; kind?: string } | null;

// SOF-100: render the full ticket detail (goal/acceptance/dod/design_refs/deps/notes/decision-log)
// through the existing DocViewer (path "ticket.md" ⇒ markdown), not a bespoke panel.
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
  { id: "activity", label: "Activity", icon: "activity" },
  { id: "kanban", label: "Kanban", icon: "kanban" },
  { id: "tree", label: "Tree", icon: "tree" },
  { id: "map", label: "Map", icon: "map" },
];
const VIEW_TITLE: Record<View, string> = { activity: "Activity", kanban: "Build board", tree: "Process tree", map: "Process graph" };
const VALID_VIEWS: View[] = ["activity", "kanban", "tree", "map"];

// Last console mode, remembered ONLY for the current project visit (SOF-249 AC): an in-memory map,
// so switching to another peer and back restores the mode, but a full reload / fresh entry falls
// back to the Kanban default unless the URL (an alert deep-link) directs otherwise. Not persisted.
const lastModeByProject: Record<string, View> = {};

function phaseTone(phase?: string): "success" | "warning" | "danger" | "neutral" {
  const halted = toneForHaltedPhase(phase);
  if (halted) return halted;
  if (phase) return "warning";
  return "neutral";
}

function setFview(value: string | null) {
  const p = new URLSearchParams(location.search);
  if (value === null) p.delete("fview"); else p.set("fview", value);
  history.replaceState(null, "", "?" + p.toString());
}

// The factory peer body. Shared run data (status/tickets/graph/loaded) is polled ONCE by the shell
// and passed down; `onStatus` lets a board action (pause/rewind/deps-resolved) push a fresh status
// back up so the whole shell (header, Concierge) stays consistent.
// ── Ops panels re-homed from the former FactoryConsole (SOF-239 shell delete + SOF-250 finalize) ──
// #443's SOF-241 review (1b91fbc) parked these two in FactoryConsole "temporary — SOF-250 finalizes
// placement"; the shell deletes FactoryConsole, so they live here now. Self-contained (own fetch/state),
// both surface the server's real status/detail/refusal text — never a dead control.
function ConsolePanel({ title, count, children, action }:
  { title: string; count?: number; children: ReactNode; action?: ReactNode }) {
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

// Repository access — the GitHub-invite flow for this project's build repo. Owner enters/updates a
// GitHub username and requests an invite; the server's real status/detail is surfaced verbatim.
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

// #107 post-deploy "provide your own key": a mocked provider dep (e.g. OPENROUTER_API_KEY) swapped for
// a real value AFTER the fact, pushed onto the LIVE app's Railway service (redeploy) via POST /deps/provide.
// Only meaningful post-deploy, so the caller gates on status.done.
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

export function FactoryBoard({ projectId, status, tickets, graph, loaded, onStatus }: {
  projectId: string; status: Status; tickets: Ticket[]; graph: Graph; loaded: boolean;
  onStatus: (s: Status) => void;
}) {
  // Mode precedence (SOF-249): URL ?fview (an alert deep-link / reload) wins, then the mode remembered
  // for this project visit, then the Kanban default for an ordinary first entry.
  const [view, setView] = useState<View>(() => {
    const v = new URLSearchParams(location.search).get("fview") || "";
    if ((VALID_VIEWS as string[]).includes(v)) return v as View;
    return lastModeByProject[projectId] || "kanban";
  });
  // The event an alert asked us to focus (?fevent) — Activity selects + scrolls to it. Read once at
  // mount: an alert navigates via the shell (?view=factory), which remounts this board fresh.
  const [selectedEventId] = useState<string | null>(() => new URLSearchParams(location.search).get("fevent"));
  const [doc, setDoc] = useState<Doc>(null);
  const [previewDoc, setPreviewDoc] = useState<Doc>(null);

  useEffect(() => {
    lastModeByProject[projectId] = view;
    setFview(view === "kanban" ? null : view);
  }, [view, projectId]);

  const phaseStates: Record<string, PhaseStatus> = phaseStatesFromGraph(graph.nodes);
  const artifacts: ArtifactRef[] = artifactsFromGraph(graph);
  const showDeps = atWaitForDeps(status);

  const cap = status.budget_ceiling || 0;
  const spent = status.spent_usd || 0;
  const overCap = cap > 0 && spent > cap;

  const doneTickets = tickets.filter((t) => t.status === "approved").length;
  const pct = tickets.length ? Math.round((doneTickets / tickets.length) * 100) : 0;
  const allTicketsDone = tickets.length > 0 && doneTickets === tickets.length;

  const repoArt = artifacts.find((a) => a.url && /repo|github/i.test(a.label));
  const liveArt = artifacts.find((a) => a.url && /live|app|deploy/i.test(a.label));
  const delivered = status.done || allTicketsDone;
  const liveUrl = liveArt?.url || status.deploy_url;

  const openDocFromRef = (a: ArtifactRef) =>
    a.id ? openArtifact(a.id) : setDoc({ label: a.label, path: a.path, agent: a.agent, kind: a.kind });
  const previewDocFromRef = (a: ArtifactRef) =>
    setPreviewDoc({ label: a.label, path: a.path, url: a.url, id: a.id, agent: a.agent, kind: a.kind });

  const halted = status.phase === "paused" || status.phase === "crashed";
  const haltedNode: string | undefined = status.paused_at_node || status.crashed_at_node;
  const doneNodes = Object.entries(phaseStates).filter(([, s]) => s === "done").map(([id]) => id);

  const running = !!status.phase && !status.deploy_url && !status.done
    && !["done", "draft", "stopped", "paused", "crashed"].includes(status.phase);
  const pauseRun = async () => {
    try { const s = await api.pauseProject(projectId); onStatus(s as Status); } catch { /* noop */ }
  };

  return (
    <div style={{ height: "100%", display: "flex", flexDirection: "column", background: T.bg, color: T.fg, minHeight: 0 }}>
      {/* factory sub-header: engine · phase · spend/cap · Pause (controls the minimal shell header omits) */}
      <div style={{ display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap", padding: "10px 20px",
        borderBottom: `1px solid ${T.borderSubtle}`, background: T.raised, flexShrink: 0 }}>
        {(status.runtime || status.model) && (
          <span style={{ display: "inline-flex", alignItems: "center", gap: 5, font: `500 11px/1 ${T.mono}`, color: T.tertiary,
            padding: "3px 9px", borderRadius: T.rMd, border: `1px solid ${T.borderSubtle}` }}>
            engine <span style={{ color: T.fg }}>{status.model || status.runtime}</span> ·
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
        <span style={{ flex: 1 }} />
        <span style={{ font: `500 12px/1 ${T.mono}`, color: overCap ? T.danger : T.secondary }}>
          spent <b style={{ color: overCap ? T.danger : T.fg }}>${spent.toFixed(2)}</b>{cap > 0 && ` / $${cap.toFixed(0)} cap`}
        </span>
        {running && (
          <button onClick={pauseRun} title="Pause this run — can be resumed"
            style={{ display: "inline-flex", alignItems: "center", gap: 5, height: 28, padding: "0 9px", borderRadius: T.rMd,
              cursor: "pointer", border: `1px solid ${T.borderDefault}`, background: T.raised, color: T.secondary, font: `600 10.5px/1 ${T.mono}` }}>
            <Icon name="pause" size={11} color={T.secondary} /> Pause
          </button>
        )}
      </div>

      <main style={{ flex: 1, overflowY: "auto", padding: 20, display: "flex", flexDirection: "column", gap: 16, minHeight: 0 }}>
        <StageRail graph={graph} phaseStates={phaseStates} depsSatisfied={!!status.deps_satisfied} atDeps={showDeps}
          haltedNode={halted ? haltedNode : undefined}
          onRewind={halted && haltedNode ? (node) => api.rewindTo(projectId, node).then((s) => onStatus(s as Status)).catch(() => {}) : undefined} />

        {halted && haltedNode && (
          <RecoveryBar projectId={projectId} phase={status.phase as "paused" | "crashed"}
            haltedNode={haltedNode} doneNodes={doneNodes} onUpdate={(s) => onStatus(s as Status)} />
        )}

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

        {view === "activity" && (
          <FactoryActivity projectId={projectId} artifacts={artifacts} onOpenArtifact={openDocFromRef}
            selectedEventId={selectedEventId}
            depsPanel={showDeps
              ? <WaitForDeps projectId={projectId} onResolved={() => api.status(projectId).then((s) => onStatus(s as Status)).catch(() => {})} />
              : undefined} />
        )}
        {view === "kanban" && !loaded && (
          <div style={{ display: "grid", gridTemplateColumns: "repeat(5, 1fr)", gap: 12, alignItems: "start" }}>
            {[0, 1, 2, 3, 4].map((i) => (
              <div key={i} style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                <KanbanCardSkel dark /><KanbanCardSkel dark />
              </div>
            ))}
          </div>
        )}
        {view === "kanban" && loaded && <BuildBoard tickets={tickets}
          onOpenTicket={(t) => setDoc({ label: `#${t.id} ${t.title}`, path: "ticket.md", content: ticketDetailMarkdown(t, projectId) })} />}
        {view === "tree" && <TreeView graph={graph} onOpenArtifact={openDocFromRef}
          ticketsDone={doneTickets} ticketsTotal={tickets.length} onViewBoard={() => setView("kanban")} />}
        {view === "map" && <MapView graph={graph} onPreviewArtifact={previewDocFromRef} />}

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

        {/* Ops panels re-homed from FactoryConsole (panel-carry; #443 1b91fbc parked them there
            "temporary — SOF-250 finalizes placement"): repo access (always) + #107 post-deploy key
            replacement (post-deploy → gated on status.done). No live capability lost on the delete. */}
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(300px, 1fr))", gap: 16 }}>
          <RepositoryAccessPanel projectId={projectId} />
          {status.done && <DependenciesPanel projectId={projectId} />}
        </div>
      </main>

      <DocViewer projectId={projectId} doc={doc} onClose={() => setDoc(null)} />
      <DocViewer projectId={projectId} doc={previewDoc} preview onClose={() => setPreviewDoc(null)} />
    </div>
  );
}
