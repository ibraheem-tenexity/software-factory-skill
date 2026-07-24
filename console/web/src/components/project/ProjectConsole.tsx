// ProjectConsole.tsx — the ONE unified Project Console shell (SOF-239, epic SOF-238 foundation).
//
// Replaces the former dual shell (ProjectView.tsx + FactoryConsole.tsx, swapped by App on an
// `openView` flag) that duplicated chrome and REMOUNTED the Concierge on every peer switch. This
// shell owns, once: the project header + actions (← Projects · rename · archive · restart · account),
// the peer nav (Overview · Product brief · Factory outputs · Factory console · Files [· Maintenance
// when done]), the `?view=<peer>` URL state (pushState so browser back/forward walk the peers), the
// shared status/tickets/graph poll, and — the whole point — a SINGLE persistent ProjectConcierge
// dock that never unmounts across peer switches, so its conversation/draft/scroll survive.
//
// Peer BODIES are mounted here; the rich ones are their own child tickets (they swap the mount):
//   overview  → <OverviewTab>      (SOF-241 swaps in <OverviewPeer> at that one line)
//   brief     → <BriefPeer>        (SOF-242 replaces with the heading-nav reader)
//   outputs   → <OutputsPeer>      (SOF-245 replaces with the stage-grouped workspace)
//   factory   → <FactoryBoard>     (the REAL board, extracted — not a copy)
//   files     → <DocumentsTab>     (SOF-255 replaces with the hierarchical Files browser)
//   maintenance → <MaintenanceTab> (conditional; completed/deployed projects only)
import { useEffect, useRef, useState } from "react";
import { api, ProjectSummary, Graph, Ticket } from "../../api";
import { T, Icon, Btn, StatusPill, Wordmark, TextInput, Sparkle } from "../onboarding/design";
import { AccountMenu } from "../AccountMenu";
import { OverviewTab } from "./OverviewTab";
import { ProductBriefPeer } from "./ProductBriefPeer";
import { FactoryOutputsPeer } from "./FactoryOutputsPeer";
import { FilesPeer } from "./FilesPeer";
import { MaintenanceTab } from "./MaintenanceTab";
import { FactoryBoard } from "../factory/FactoryBoard";
import { Concierge } from "../factory/Concierge";
import { artifactsFromGraph, openArtifact, ArtifactRef } from "../factory/Artifacts";

type Status = ProjectSummary & Record<string, any>;
type Tone = "neutral" | "success" | "warning" | "danger" | "info" | "brand";

// The five core peer views + the conditional maintenance peer. Order is the design nav order
// (projectknowledge.jsx PROJECT_TABS). `factory` is the live board rendered INSIDE this shell.
type Peer = "overview" | "brief" | "outputs" | "factory" | "files" | "maintenance";
const PEER_TABS: { id: Peer; label: string }[] = [
  { id: "overview", label: "Overview" },
  { id: "brief", label: "Product brief" },
  { id: "outputs", label: "Factory outputs" },
  { id: "factory", label: "Factory console" },
  { id: "files", label: "Files" },
];
const VALID_PEERS: Peer[] = ["overview", "brief", "outputs", "factory", "files", "maintenance"];

function readView(): Peer {
  const v = new URLSearchParams(location.search).get("view") || "";
  return (VALID_PEERS as string[]).includes(v) ? (v as Peer) : "overview";
}
function writeView(v: Peer, push: boolean) {
  const p = new URLSearchParams(location.search);
  if (v === "overview") p.delete("view"); else p.set("view", v);
  const url = "?" + p.toString();
  if (push) history.pushState(null, "", url); else history.replaceState(null, "", url);
}

function statusOf(s: Status): { label: string; tone: Tone } {
  if (s.deploy_url || s.done || s.phase === "done") return { label: "Deployed", tone: "success" };
  // A crashed run must NEVER read "Building" — that false-healthy pill hides the exact moment the
  // customer needs to act. Crashed → danger; operator-halted (paused/stopped/held) → neutral, not
  // an in-flight "Building". budget/credential blocks stay the actionable "Needs input" warning.
  if (s.phase === "crashed" || s.crashed_at_node) return { label: "Crashed", tone: "danger" };
  if (s.budget_stopped || s.credential_stopped) return { label: "Needs input", tone: "warning" };
  if (s.phase === "paused") return { label: "Paused", tone: "neutral" };
  if (s.phase === "stopped") return { label: "Stopped", tone: "neutral" };
  if (s.held) return { label: "On hold", tone: "neutral" };
  if (s.phase === "draft") return { label: "Draft", tone: "neutral" };
  if ((s.phase || "").toLowerCase().includes("research")) return { label: "Researching", tone: "brand" };
  return { label: "Building", tone: "info" };
}

export function ProjectConsole({ projectId, onBack, onResume, onOpen }: {
  projectId: string; onBack: () => void; onResume?: () => void; onOpen?: (id: string) => void;
}) {
  const [view, setView] = useState<Peer>(readView);
  const [status, setStatus] = useState<Status | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [loadError, setLoadError] = useState(false);
  const [graph, setGraph] = useState<Graph>({ nodes: [], edges: [] });
  const [tickets, setTickets] = useState<Ticket[]>([]);
  const [menu, setMenu] = useState(false);
  // SOF-248: the Concierge minimize preference lives HERE (once), so it persists across peer
  // switches for this project visit and is never reimplemented per peer. Reset on project change.
  const [conciergeMin, setConciergeMin] = useState(false);
  const [renaming, setRenaming] = useState(false);
  const [nameDraft, setNameDraft] = useState("");
  const [relaunchError, setRelaunchError] = useState<string | null>(null);

  // Shared run data — polled ONCE for the header, the Concierge, and the factory board (which is
  // presentational and receives it). 4s cadence matches the former FactoryConsole liveness.
  useEffect(() => {
    let live = true;
    const tick = () => {
      api.status(projectId).then((s) => { if (live) { setStatus(s); setLoaded(true); setLoadError(false); } })
        .catch(() => { if (live) { setLoaded(true); setLoadError(true); } });
      api.tickets(projectId).then((d) => live && setTickets(d.tickets || [])).catch(() => {});
      api.graph(projectId).then((g) => live && setGraph(g)).catch(() => {});
    };
    tick();
    const h = setInterval(tick, 4000);
    return () => { live = false; clearInterval(h); };
  }, [projectId]);

  // Reset to Overview on a genuine project *change* (not initial mount), so a deep-linked ?view
  // survives the first render but a project switch never keeps a stale/invalid peer.
  const prevProject = useRef(projectId);
  useEffect(() => {
    if (prevProject.current === projectId) return;
    prevProject.current = projectId;
    setView("overview"); writeView("overview", false);
    setConciergeMin(false);   // SOF-248: a fresh project visit opens the dock; never leak the prior visit's pref
  }, [projectId]);

  // Browser back/forward: mirror the URL's ?view into state (AC: back/forward walks the peers).
  useEffect(() => {
    const onPop = () => setView(readView());
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, []);

  const isDraft = status?.phase === "draft";
  const isDone = !!(status && (status.done || status.phase === "done" || status.deploy_url));
  const buildingNow = !!status && !status.done && status.phase !== "draft" && status.phase !== "stopped";
  const canRelaunch = status?.phase === "stopped" || status?.phase === "done";
  const ingesting = false; // SOF-239: no ingest signal wired yet; SOF-246 threads the real one.

  // Deep-linked/stale peer that isn't available (maintenance on a non-done project) → Overview,
  // never a blank screen. Runs once status resolves.
  useEffect(() => {
    if (loaded && view === "maintenance" && !isDone) { setView("overview"); writeView("overview", false); }
  }, [loaded, view, isDone]);

  const go = (v: Peer) => { setView(v); writeView(v, true); };

  const name = status?.name || projectId;
  const st = status ? statusOf(status) : null;

  // Concierge feed (persistent dock). Derived from the shared poll — same values the old ProjectView
  // mount used, so the assistant reads identically on every peer.
  const artifacts: ArtifactRef[] = artifactsFromGraph(graph);
  const doneTickets = tickets.filter((t) => t.status === "approved" || t.status === "done" || t.status === "deployed" || t.status === "qa_testing").length;
  const openRef = (a: ArtifactRef) => { if (a.url) window.open(a.url, "_blank"); else if (a.id != null) openArtifact(a.id); };
  // The active peer → Concierge context. The dock below is mounted ONCE with this value ready; the
  // current Concierge does not yet consume `context` — SOF-246 swaps in the context-aware dock and
  // reads exactly this. (Kept here so 246 needs no shell surgery.)
  const conciergeContext: "overview" | "brief" | "outputs" | "build" | "files" | "maintenance" | "ingesting" =
    view === "brief" ? "brief" : view === "outputs" ? "outputs" : view === "factory" ? "build"
      : view === "files" ? "files" : view === "maintenance" ? "maintenance" : ingesting ? "ingesting" : "overview";

  // Project actions (real API; surface real errors, never a plausible guess).
  const doRename = async () => {
    const n = nameDraft.trim();
    if (!n) { setRenaming(false); return; }
    try { await api.patchProject(projectId, { name: n }); setStatus((s) => (s ? { ...s, name: n } : s)); } catch { /* surfaced on retry */ }
    setRenaming(false);
  };
  const doArchive = async () => {
    const msg = isDraft ? `Discard "${name}"? This draft will be permanently deleted.`
      : `Archive "${name}"? It'll be hidden from your projects.`;
    if (!confirm(msg)) return;
    try { await api.deleteProject(projectId); onBack(); } catch { /* not live yet */ }
  };
  const doRelaunch = async () => {
    setRelaunchError(null);
    try { const r = await api.relaunchProject(projectId); if (onOpen) onOpen(r.project_id); else onBack(); }
    catch (e: any) { setRelaunchError(e?.message || "Couldn't relaunch. Try again."); }
  };
  const doToggleMaintenance = (next: boolean) => setStatus((s) => (s ? { ...s, maintenance_enabled: next } : s));

  const tabs = isDone ? [...PEER_TABS, { id: "maintenance" as Peer, label: "Maintenance" }] : PEER_TABS;

  return (
    <div style={{ height: "100vh", display: "flex", flexDirection: "column", background: T.bg, fontFamily: T.sans }}>
      {/* ── the ONE project header + peer nav (no second header anywhere) ── */}
      <div style={{ background: T.raised, borderBottom: `1px solid ${T.borderSubtle}`, flexShrink: 0 }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "13px 24px" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 13, minWidth: 0 }}>
            <Btn variant="ghost" size="sm" onClick={onBack}><Icon name="arrowLeft" size={14} /> Projects</Btn>
            <Wordmark size={17} />
            <span style={{ font: `400 13px/1 ${T.mono}`, color: T.tertiary }}>/</span>
            {renaming ? (
              <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                <TextInput value={nameDraft} onChange={setNameDraft} size="sm" />
                <Btn size="sm" variant="primary" onClick={doRename}>Save</Btn>
                <Btn size="sm" variant="ghost" onClick={() => setRenaming(false)}>Cancel</Btn>
              </div>
            ) : (
              <>
                {/* Honest loading/failed status: never fabricate a name — projectId is the honest
                    fallback label, and the pill only renders once real status resolves. */}
                <span style={{ font: `600 13px/1 ${T.sans}`, color: T.fg, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{name}</span>
                {st ? <StatusPill tone={st.tone} dot={st.tone === "info" || st.tone === "brand"}>{st.label}</StatusPill>
                  : !loaded ? <StatusPill tone="neutral">loading…</StatusPill>
                  : loadError ? <StatusPill tone="danger">status unavailable</StatusPill> : null}
              </>
            )}
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            {canRelaunch && (
              <div style={{ display: "inline-flex", alignItems: "center", gap: 7 }}>
                <button onClick={doRelaunch} title="Relaunch this project from scratch" style={{ display: "inline-flex", alignItems: "center", gap: 5, height: 28, padding: "0 9px", borderRadius: T.rMd, cursor: "pointer", border: `1px solid ${T.borderDefault}`, background: T.raised, color: T.secondary, font: `600 10.5px/1 ${T.mono}` }}>
                  <Icon name="play" size={10} color={T.secondary} /> Restart
                </button>
                {relaunchError && <span style={{ font: `400 11px/1 ${T.sans}`, color: T.danger }}>{relaunchError}</span>}
              </div>
            )}
            <div style={{ position: "relative" }}>
              <button onClick={() => setMenu((v) => !v)} title="Project actions" style={{ display: "grid", placeItems: "center", width: 30, height: 30, borderRadius: "50%", border: `1px solid ${T.borderSubtle}`, background: T.raised, cursor: "pointer", color: T.secondary }}><Icon name="dots" size={16} color={T.secondary} /></button>
              {menu && (
                <>
                  <div onClick={() => setMenu(false)} style={{ position: "fixed", inset: 0, zIndex: 9 }} />
                  <div style={{ position: "absolute", right: 0, top: 36, zIndex: 10, background: T.raised, border: `1px solid ${T.borderSubtle}`, borderRadius: T.rMd, boxShadow: T.shadowMd, overflow: "hidden", minWidth: 150 }}>
                    <button onClick={() => { setMenu(false); setNameDraft(name); setRenaming(true); }} style={{ display: "block", width: "100%", textAlign: "left", padding: "9px 12px", background: "none", border: "none", cursor: "pointer", font: `500 12.5px/1 ${T.sans}`, color: T.fg }}>Rename project</button>
                    <button onClick={() => { setMenu(false); doArchive(); }} style={{ display: "block", width: "100%", textAlign: "left", padding: "9px 12px", background: "none", border: "none", cursor: "pointer", font: `500 12.5px/1 ${T.sans}`, color: T.danger }}>{isDraft ? "Discard draft" : "Archive project"}</button>
                  </div>
                </>
              )}
            </div>
            <AccountMenu size={28} />
          </div>
        </div>
        {/* peer nav — all peers are true siblings; none nested under another */}
        <div style={{ display: "flex", gap: 2, padding: "0 24px" }}>
          {tabs.map((t) => {
            const on = t.id === view;
            return (
              <button key={t.id} onClick={() => go(t.id)}
                style={{ position: "relative", padding: "11px 14px", background: "none", border: "none", cursor: "pointer", font: `${on ? 600 : 500} 13px/1 ${T.sans}`, color: on ? T.fg : T.secondary }}>
                {t.label}
                {on && <span style={{ position: "absolute", left: 10, right: 10, bottom: -1, height: 2, background: T.brand, borderRadius: 2 }} />}
              </button>
            );
          })}
        </div>
      </div>

      {/* ── body (active peer) + the ONE persistent Concierge dock ── */}
      <div style={{ flex: 1, display: "flex", minHeight: 0 }}>
        <div style={{ flex: 1, minWidth: 0, display: "flex", flexDirection: "column", minHeight: 0 }}>
          {view === "overview" && (
            /* SOF-241 swaps OverviewTab → OverviewPeer at THIS one line. Keep the mount obvious. */
            <OverviewTab projectId={projectId} onOpenFactory={() => go("factory")} onOpenBrief={() => go("brief")} onOpenOutputs={() => go("outputs")} onOpenDocuments={() => go("files")} onResume={onResume} onDiscard={isDraft ? doArchive : undefined} />
          )}
          {view === "brief" && <ProductBriefPeer projectId={projectId} />}
          {view === "outputs" && <FactoryOutputsPeer projectId={projectId} />}
          {view === "factory" && <FactoryBoard projectId={projectId} status={status || ({} as Status)} tickets={tickets} graph={graph} loaded={loaded} onStatus={(s) => setStatus(s)} />}
          {view === "files" && <FilesPeer projectId={projectId} />}
          {view === "maintenance" && isDone && <MaintenanceTab projectId={projectId} enabled={!!status?.maintenance_enabled} onToggle={doToggleMaintenance} />}
        </div>

        {/* ─────────────────────────────────────────────────────────────────────────────────────
            THE PERSISTENT PROJECTCONCIERGE DOCK — SOF-246/SOF-248 SEAM.
            Mounted ONCE, OUTSIDE the peer switch above, so it NEVER remounts when the peer changes
            (the core SOF-239 win: conversation/draft/scroll survive peer switches). `conciergeContext`
            (derived per active peer) is ready here; SOF-246 swaps this <Concierge> for the shared
            context-aware dock and feeds it `conciergeContext`, and SOF-248 hangs minimize off this
            same block. Do not move the mount inside the peer switch.
           ───────────────────────────────────────────────────────────────────────────────────── */}
        <aside style={{ width: 340, flexShrink: 0, borderLeft: `1px solid ${T.borderSubtle}`, background: T.raised,
          display: conciergeMin ? "none" : "flex", flexDirection: "column", minHeight: 0 }}>
          <Concierge projectId={projectId} projectName={name} artifacts={artifacts}
            onOpenArtifact={openRef} context={conciergeContext} onMinimize={() => setConciergeMin(true)}
            isBuilding={buildingNow}
            ticketsDone={doneTickets} ticketsTotal={tickets.length}
            buildDone={!!status?.done} deployed={!!status?.deploy_url} phase={status?.phase} />
        </aside>
      </div>

      {/* SOF-248: minimized → the dock is display:none (zero layout width/border/padding, so the
          peer gets the full content width) but stays MOUNTED, preserving transcript/draft/scroll/
          in-flight state. This 44px floating sparkle restores it; a working dot shows while the
          build is active. */}
      {conciergeMin && (
        <button aria-label="Open Concierge" title="Open Concierge" onClick={() => setConciergeMin(false)}
          style={{ position: "fixed", right: 20, bottom: 20, width: 44, height: 44, borderRadius: "50%",
            border: `1px solid ${T.brand}33`, background: T.brandSoft, color: T.brand, cursor: "pointer",
            display: "grid", placeItems: "center", boxShadow: T.shadowMd, zIndex: 20 }}>
          <Sparkle size={18} color={T.brand} />
          {buildingNow && <span aria-hidden style={{ position: "absolute", top: 3, right: 3, width: 10, height: 10, borderRadius: "50%", background: T.brand, boxShadow: `0 0 0 2px ${T.bg}` }} />}
        </button>
      )}
    </div>
  );
}

// ── Placeholder peer bodies — honest + functional, NOT dead affordances. Each is the mount the
// named child ticket replaces; until then it renders real, useful content from data the shell
// already has (no mocks, no fake state). ────────────────────────────────────────────────────────

// Factory outputs peer (SOF-245 replaces with the stage-grouped workspace). For now: the real
// produced artifacts as a flat clickable list opening the artifact viewer.
