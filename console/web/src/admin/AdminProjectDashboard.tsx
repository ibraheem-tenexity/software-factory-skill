import React from "react";
import { T } from "./tokens";
import { Icon } from "./primitives";
import { AdminBtn, Mono } from "./views";
import { api } from "../api";
import type { ProjectSummary } from "../api";
import { OverviewTab } from "../components/project/OverviewTab";
import { DocumentsTab } from "../components/project/DocumentsTab";
import { FactoryConsole } from "../components/factory/FactoryConsole";

type Tab = "overview" | "documents" | "factory";

export function AdminProjectDashboard({ projectId, onBack }: { projectId: string; onBack: () => void }) {
  const [tab, setTab] = React.useState<Tab>("overview");
  const [status, setStatus] = React.useState<(ProjectSummary & Record<string, any>) | null>(null);

  React.useEffect(() => {
    api.status(projectId).then(setStatus).catch(() => setStatus(null));
  }, [projectId]);

  const name = status?.name || projectId;
  const phase = status?.phase || "";

  const tabs: { id: Tab; label: string }[] = [
    { id: "overview", label: "Overview" },
    { id: "documents", label: "Documents" },
    { id: "factory", label: "Factory console" },
  ];

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%" }}>
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 14,
          padding: "12px 26px",
          borderBottom: `1px solid ${T.borderSubtle}`,
          background: T.raised,
          flexShrink: 0,
        }}
      >
        <AdminBtn onClick={onBack}>
          <Icon name="arrowLeft" size={14} /> Back
        </AdminBtn>
        <span style={{ font: `600 16px/1.2 ${T.sans}`, color: T.fg, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
          {name}
        </span>
        {phase && (
          <Mono style={{ color: T.brandDeep, background: T.brandSoft, padding: "3px 7px", borderRadius: 4, textTransform: "uppercase" }}>
            {phase}
          </Mono>
        )}
      </div>
      <div style={{ display: "flex", gap: 2, padding: "0 26px", borderBottom: `1px solid ${T.borderSubtle}`, background: T.raised, flexShrink: 0 }}>
        {tabs.map((t) => {
          const on = t.id === tab;
          return (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              style={{
                position: "relative",
                padding: "11px 14px",
                background: "none",
                border: "none",
                cursor: "pointer",
                font: `${on ? 600 : 500} 13px/1 ${T.sans}`,
                color: on ? T.fg : T.secondary,
              }}
            >
              {t.label}
              {on && <span style={{ position: "absolute", left: 10, right: 10, bottom: -1, height: 2, background: T.brand, borderRadius: 2 }} />}
            </button>
          );
        })}
      </div>
      <div style={{ flex: 1, minHeight: 0, overflow: "auto" }}>
        {tab === "overview" && (
          <OverviewTab
            projectId={projectId}
            onOpenFactory={() => setTab("factory")}
            onOpenDocuments={() => setTab("documents")}
          />
        )}
        {tab === "documents" && <DocumentsTab projectId={projectId} />}
        {tab === "factory" && <FactoryConsole projectId={projectId} onBack={() => setTab("overview")} />}
      </div>
    </div>
  );
}
