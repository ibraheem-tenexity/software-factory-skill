// FactoryConsole.tsx — PRD §2.6 "THE CORE SCREEN". A faithful assembly of the factory-console
// design, wired ENTIRELY to real backend data (no client-side build simulation).
//
// Layout: top bar (← back · wordmark · project · phase pill · spend/cap) · LEFT Concierge rail ·
// MAIN column (Stage rail · stage-triggered Wait-for-deps · Kanban/Tree/Map toggle · delivery
// footer). A DocViewer modal opens artifacts + ticket bodies.
//
// Liveness: polls status + tickets + graph every 4s (agents run server-side; no sim button).
import { useEffect, useState } from "react";
import { T, Icon, Wordmark, StatusPill, Btn } from "../onboarding/design";
import { AccountMenu } from "../AccountMenu";
import { api, ProjectSummary, Graph, Ticket } from "../../api";
import { phaseStatesFromGraph, atWaitForDeps, PhaseStatus } from "./pipeline";
import { StageRail } from "./StageRail";
import { WaitForDeps } from "./WaitForDeps";
import { BuildBoard } from "./BuildBoard";
import { TreeView, MapView } from "./NodeMap";
import { Concierge } from "./Concierge";
import { DocViewer, artifactsFromGraph, ArtifactRef, openArtifact } from "./Artifacts";
import { RecoveryBar } from "./RecoveryBar";

type Status = ProjectSummary & Record<string, any>;
type View = "kanban" | "tree" | "map";
type Doc = { label: string; path?: string; content?: string } | null;

const VIEWS: { id: View; label: string; icon: string }[] = [
  { id: "kanban", label: "Kanban", icon: "kanban" },
  { id: "tree", label: "Tree", icon: "tree" },
  { id: "map", label: "Map", icon: "map" },
];
const VIEW_TITLE: Record<View, string> = { kanban: "Build board", tree: "Process tree", map: "Process graph" };

function phaseTone(phase?: string): "success" | "warning" | "danger" | "neutral" {
  if (phase === "done") return "success";
  if (phase === "stopped" || phase === "crashed") return "danger";
  if (phase === "paused") return "warning";
  if (phase) return "warning";   // an in-flight phase (design renders the build phase amber)
  return "neutral";
}

function setParam(key: string, value: string | null) {
  const p = new URLSearchParams(location.search);
  if (value === null) p.delete(key); else p.set(key, value);
  history.replaceState(null, "", "?" + p.toString());
}

export function FactoryConsole({ projectId, onBack }: { projectId: string; onBack: () => void }) {
  const [status, setStatus] = useState<Status>({} as Status);
  const [graph, setGraph] = useState<Graph>({ nodes: [], edges: [] });
  const [tickets, setTickets] = useState<Ticket[]>([]);
  const [view, setView] = useState<View>(() => {
    const v = new URLSearchParams(location.search).get("fview");
    return (["tree", "map"].includes(v || "") ? v : "kanban") as View;
  });
  const [doc, setDoc] = useState<Doc>(null);

  useEffect(() => { setParam("fview", view === "kanban" ? null : view); }, [view]);

  useEffect(() => {
    let live = true;
    const tick = () => {
      api.status(projectId).then((s) => live && setStatus(s)).catch(() => {});
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

  // Recovery: paused/crashed runs show the RecoveryBar + halted rail state
  const halted = status.phase === "paused" || status.phase === "crashed";
  const haltedNode: string | undefined = status.paused_at_node || status.crashed_at_node;
  const doneNodes = Object.entries(phaseStates).filter(([, s]) => s === "done").map(([id]) => id);

  // manual kill-switch — only while a live run is in flight (a stage/poller to halt)
  const running = !!status.phase && !status.deploy_url && !status.done && !["done", "draft", "stopped", "paused", "crashed"].includes(status.phase);
  const stopRun = async () => {
    if (!confirm("Stop all work on this project? Running agents will be halted.")) return;
    try { const s = await api.stopProject(projectId); setStatus(s as Status); } catch { /* run-control endpoint ships in qsvigmth's PR */ }
  };

  return (
    <div style={{ height: "100vh", display: "flex", flexDirection: "column", background: T.bg, color: T.fg, font: `400 14px/1.5 ${T.sans}` }}>
      {/* ── top bar ── */}
      <header style={{ display: "flex", alignItems: "center", gap: 14, padding: "0 18px", height: 56,
        borderBottom: `1px solid ${T.borderSubtle}`, background: T.raised, flexShrink: 0 }}>
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
              : `phase ${status.phase} · stage ${status.stage || ""}`}
          </StatusPill>
        )}
        <span style={{ font: `500 12px/1 ${T.mono}`, color: overCap ? T.danger : T.secondary }}>
          spent <b style={{ color: overCap ? T.danger : T.fg }}>${spent.toFixed(2)}</b>{cap > 0 && ` / $${cap.toFixed(0)} cap`}
        </span>
        {running && (
          <button onClick={stopRun} title="Stop all work on this project"
            style={{ display: "inline-flex", alignItems: "center", gap: 6, height: 30, padding: "0 12px", borderRadius: T.rMd, cursor: "pointer", border: `1px solid ${T.danger}`, background: "transparent", color: T.danger, font: `600 12.5px/1 ${T.sans}` }}>
            <span style={{ width: 9, height: 9, borderRadius: 2, background: T.danger, flexShrink: 0 }} /> Stop all progress
          </button>
        )}
        <AccountMenu size={26} />
      </header>

      {/* ── body: Concierge rail + main column ── */}
      <div style={{ flex: 1, minHeight: 0, display: "grid", gridTemplateColumns: "340px 1fr", gap: 0 }}>
        <div style={{ borderRight: `1px solid ${T.borderSubtle}`, padding: 16, overflowY: "auto", background: T.raised }}>
          <Concierge projectId={projectId} projectName={status.name || ""} artifacts={artifacts}
            onOpenArtifact={(a) => a.id ? openArtifact(a.id) : setDoc({ label: a.label, path: a.path })} isBuilding={running} />
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
            <div style={{ display: "inline-flex", gap: 2, padding: 2, borderRadius: T.rMd, background: T.sunken, border: `1px solid ${T.borderSubtle}` }}>
              {VIEWS.map((v) => (
                <button key={v.id} onClick={() => setView(v.id)}
                  style={{ display: "inline-flex", alignItems: "center", gap: 5, padding: "6px 11px", borderRadius: 6,
                    cursor: "pointer", border: "none", font: `500 11.5px/1 ${T.sans}`,
                    background: view === v.id ? T.raised : "transparent", color: view === v.id ? T.fg : T.tertiary,
                    boxShadow: view === v.id ? T.shadowXs : "none" }}>
                  <Icon name={v.icon} size={13} color={view === v.id ? T.brand : T.tertiary} />{v.label}
                </button>
              ))}
            </div>
          </div>

          {view === "kanban" && <BuildBoard tickets={tickets}
            onOpenTicket={(t) => setDoc({ label: `#${t.id} ${t.title}`, content: t.description || "(no description)" })} />}
          {view === "tree" && <TreeView graph={graph} onOpenArtifact={(path, label) => setDoc({ label, path })} />}
          {view === "map" && <MapView graph={graph} />}

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
        </main>
      </div>

      <DocViewer projectId={projectId} doc={doc} onClose={() => setDoc(null)} />
    </div>
  );
}
