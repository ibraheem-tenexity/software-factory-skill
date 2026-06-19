import { useEffect, useState } from "react";
import { api, Ticket, TicketsResponse } from "../api";

const COLUMNS: { status: Ticket["status"]; label: string }[] = [
  { status: "open", label: "Open" },
  { status: "in_progress", label: "In Progress" },
  { status: "done", label: "Done" },
  { status: "deployed", label: "Deployed" },
  { status: "qa_testing", label: "QA Testing" },
  { status: "approved", label: "Approved" },
];

function Card({ t }: { t: Ticket }) {
  const prov = t.provenance
    ? t.provenance_type === "pr"
      ? `PR #${t.provenance}`
      : String(t.provenance).slice(0, 9)
    : "";
  return (
    <div className="kb-card">
      <div className="kb-card-top">
        <span className="kb-wave">W{t.wave}</span>
        {t.diff_lines > 0 && <span className="kb-diff">+{t.diff_lines}</span>}
      </div>
      <div className="kb-title">{t.title}</div>
      <div className="kb-meta">
        {t.app && <span className="kb-app">{t.app}</span>}
        <span className={"kb-agent" + (t.agent ? "" : " none")}>{t.agent || "unassigned"}</span>
        {prov && <span className="kb-agent">{prov}</span>}
      </div>
    </div>
  );
}

export function KanbanView({ runId, appFilter }: { runId: string; appFilter: string }) {
  const [data, setData] = useState<TicketsResponse>({ tickets: [], waves: [] });

  useEffect(() => {
    let live = true;
    const tick = () => api.tickets(runId).then((d) => live && setData(d)).catch(() => {});
    tick();
    const h = setInterval(tick, 2000);
    return () => {
      live = false;
      clearInterval(h);
    };
  }, [runId]);

  const items = appFilter === "all" ? data.tickets : data.tickets.filter((t) => (t.app || "") === appFilter);
  if (!items.length) {
    return (
      <div className="kanban">
        <div className="kb-empty">No build tickets yet — these appear once the Design stage (Stage 2) plans the work.</div>
      </div>
    );
  }

  return (
    <div className="kanban">
      <div className="kb-board">
        {COLUMNS.map(({ status, label }) => {
          const colItems = items.filter((t) => t.status === status);
          const waves = [...new Set(colItems.map((t) => t.wave))].sort((a, b) => a - b);
          return (
            <div className="kb-col" data-status={status} key={status}>
              <div className="kb-col-head">
                <span>{label}</span>
                <span className="kb-count">{colItems.length}</span>
              </div>
              {waves.map((w) => (
                <div key={w}>
                  <div className="kb-lane-label">Wave {w}</div>
                  {colItems.filter((t) => t.wave === w).map((t) => <Card key={t.id} t={t} />)}
                </div>
              ))}
            </div>
          );
        })}
      </div>
    </div>
  );
}

export function appsOf(tickets: Ticket[]): string[] {
  return [...new Set(tickets.map((t) => t.app).filter(Boolean) as string[])];
}
