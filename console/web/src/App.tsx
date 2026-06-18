import { useEffect, useState } from "react";
import { api, RunSummary } from "./api";
import { GraphView } from "./components/GraphView";
import { KanbanView, appsOf } from "./components/KanbanView";
import { ChatPanel } from "./components/ChatPanel";
import { ProjectsScreen } from "./components/ProjectsScreen";

type View = "graph" | "kanban";

function readInitial(): { run: string | null; view: View } {
  const p = new URLSearchParams(location.search);
  const view = (p.get("view") || localStorage.getItem("sf_view") || "graph") === "kanban" ? "kanban" : "graph";
  return { run: p.get("run"), view };
}

export function App() {
  const init = readInitial();
  const [runId, setRunId] = useState<string | null>(init.run);
  const [view, setViewState] = useState<View>(init.view);
  const [showProjects, setShowProjects] = useState<boolean>(!init.run);
  const [status, setStatus] = useState<RunSummary & Record<string, any>>({} as any);
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [appFilter, setAppFilter] = useState<string>("all");
  const [apps, setApps] = useState<string[]>([]);

  const syncUrl = (run: string | null, v: View) => {
    const p = new URLSearchParams();
    if (run) p.set("run", run);
    if (v === "kanban") p.set("view", "kanban");
    history.replaceState(null, "", "?" + p.toString());
  };
  const setView = (v: View) => { setViewState(v); localStorage.setItem("sf_view", v); syncUrl(runId, v); };

  useEffect(() => { api.runs().then((d) => setRuns(d.runs || [])).catch(() => {}); }, [showProjects]);

  useEffect(() => {
    if (!runId) return;
    syncUrl(runId, view);
    let live = true;
    const tick = () => {
      api.status(runId).then((s) => live && setStatus(s)).catch(() => {});
      api.tickets(runId).then((d) => live && setApps(appsOf(d.tickets))).catch(() => {});
    };
    tick();
    const h = setInterval(tick, 2000);
    return () => { live = false; clearInterval(h); };
  }, [runId]);

  const openRun = (id: string) => { setRunId(id); setShowProjects(false); syncUrl(id, view); };

  if (showProjects) {
    return (
      <ProjectsScreen
        onOpen={openRun}
        onNew={() => { setRunId(null); setShowProjects(false); syncUrl(null, view); }}
      />
    );
  }

  return (
    <div className="app">
      <header className="toolbar">
        <span className="brand" onClick={() => setShowProjects(true)} style={{ cursor: "pointer" }}>
          Software Factory<small>Research → Design → Build → Deploy</small>
        </span>
        <select value={runId || ""} onChange={(e) => (e.target.value ? openRun(e.target.value) : null)}>
          <option value="">— select run —</option>
          {runs.map((r) => <option key={r.run_id} value={r.run_id}>{r.name || r.run_id}</option>)}
        </select>
        <div className="view-toggle" role="tablist" aria-label="Build view">
          <button className={view === "graph" ? "active" : ""} onClick={() => setView("graph")}>Graph</button>
          <button className={view === "kanban" ? "active" : ""} onClick={() => setView("kanban")}>Kanban</button>
        </div>
        {view === "kanban" && apps.length > 0 && (
          <select value={appFilter} onChange={(e) => setAppFilter(e.target.value)}>
            <option value="all">all apps</option>
            {apps.map((a) => <option key={a} value={a}>{a}</option>)}
          </select>
        )}
        {status.phase && <span className="pill">{status.phase}</span>}
        <span className="spacer" />
        <span className="pill cost">${(status.spent_usd || 0).toFixed(2)}</span>
      </header>
      <div className="body">
        <ChatPanel runId={runId} onRunCreated={openRun} />
        <div className="canvas">
          {runId && view === "graph" && <GraphView runId={runId} />}
          {runId && view === "kanban" && <KanbanView runId={runId} appFilter={appFilter} />}
          {!runId && <div className="empty">Start the interview in the chat to create a project.</div>}
        </div>
      </div>
    </div>
  );
}
