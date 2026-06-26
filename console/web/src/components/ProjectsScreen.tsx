import { useEffect, useState } from "react";
import { api, phaseIsStale, ProjectSummary } from "../api";

export function ProjectsScreen({ onOpen, onNew }: { onOpen: (id: string) => void; onNew: () => void }) {
  const [projects, setProjects] = useState<ProjectSummary[]>([]);

  useEffect(() => {
    api.projects().then((d) => setProjects(d.projects || [])).catch(() => setProjects([]));
  }, []);

  // Drafts (the interview-in-progress) surface first so a refresh resumes onboarding.
  const drafts = projects.filter((r) => r.phase === "draft");
  const live = projects.filter((r) => r.phase !== "draft");

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
      <div className="project-grid">
        {drafts.map((r) => (
          <div className="project-card" key={r.project_id} onClick={() => onOpen(r.project_id)}>
            <div className="name">{r.name || "Untitled draft"}</div>
            <div className="meta">interview in progress</div>
          </div>
        ))}
      </div>
      {live.length > 0 && <h3 style={{ marginTop: 24 }}>Projects</h3>}
      <div className="project-grid">
        {live.map((r) => (
          <div className="project-card" key={r.project_id} onClick={() => onOpen(r.project_id)}>
            <div className="name">{r.name || r.project_id}</div>
            <div className="meta">
              {phaseIsStale(r.phase, r.stage) ? `stage ${r.stage} · starting` : (r.phase || "—")} · ${(r.spent_usd || 0).toFixed(2)}
            </div>
          </div>
        ))}
      </div>
      {projects.length === 0 && <div className="empty">Start your first autonomous build above.</div>}
    </div>
  );
}
