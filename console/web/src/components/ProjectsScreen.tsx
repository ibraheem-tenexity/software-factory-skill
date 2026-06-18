import { useEffect, useState } from "react";
import { api, RunSummary } from "../api";

export function ProjectsScreen({ onOpen, onNew }: { onOpen: (id: string) => void; onNew: () => void }) {
  const [runs, setRuns] = useState<RunSummary[]>([]);

  useEffect(() => {
    api.runs().then((d) => setRuns(d.runs || [])).catch(() => setRuns([]));
  }, []);

  // Drafts (the interview-in-progress) surface first so a refresh resumes onboarding.
  const drafts = runs.filter((r) => r.phase === "draft");
  const live = runs.filter((r) => r.phase !== "draft");

  return (
    <div className="projects">
      <h1>Software Factory</h1>
      <p className="subhead">Describe a product. Get a deployed, browser-verified demo — autonomously.</p>
      <div className="pipeline-strip">
        <span>Research</span><span>Design</span><span>Build</span><span>Deploy</span>
      </div>
      <button className="btn" onClick={onNew}>+ New project</button>
      <div style={{ height: 20 }} />
      {drafts.length > 0 && <h3>Drafts</h3>}
      <div className="run-grid">
        {drafts.map((r) => (
          <div className="run-card" key={r.run_id} onClick={() => onOpen(r.run_id)}>
            <div className="name">{r.name || "Untitled draft"}</div>
            <div className="meta">interview in progress</div>
          </div>
        ))}
      </div>
      {live.length > 0 && <h3 style={{ marginTop: 24 }}>Projects</h3>}
      <div className="run-grid">
        {live.map((r) => (
          <div className="run-card" key={r.run_id} onClick={() => onOpen(r.run_id)}>
            <div className="name">{r.name || r.run_id}</div>
            <div className="meta">
              {r.phase || "—"} · ${(r.spent_usd || 0).toFixed(2)}
            </div>
          </div>
        ))}
      </div>
      {runs.length === 0 && <div className="empty">Start your first autonomous build above.</div>}
    </div>
  );
}
