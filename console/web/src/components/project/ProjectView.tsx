// ProjectView.tsx — Project view §2.5 shell: peer-tab views Overview · Factory console · Documents
// (design orgproject.jsx → ProjectDashboard). Overview + Documents render inline (my components);
// the "Factory console" tab is a NAV CALLBACK into the existing console (onOpenFactory) — it is NOT
// rendered inline, so this stays fully decoupled from the factory components.
import { useEffect, useState } from "react";
import { api, RunSummary } from "../../api";
import { T, Icon, Btn, StatusPill, Avatar, Wordmark } from "../onboarding/design";
import { OverviewTab } from "./OverviewTab";
import { DocumentsTab } from "./DocumentsTab";

type Tab = "overview" | "documents";
type Tone = "neutral" | "success" | "warning" | "danger" | "info" | "brand";

function statusOf(s: RunSummary & Record<string, any>): { label: string; tone: Tone } {
  if (s.deploy_url || s.done || s.phase === "done") return { label: "Deployed", tone: "success" };
  if (s.budget_stopped || s.held) return { label: "Needs input", tone: "warning" };
  if (s.phase === "draft") return { label: "Draft", tone: "neutral" };
  if ((s.phase || "").toLowerCase().includes("research")) return { label: "Researching", tone: "brand" };
  return { label: "Building", tone: "info" };
}

const TABS: { id: Tab | "factory"; label: string }[] = [
  { id: "overview", label: "Overview" },
  { id: "factory", label: "Factory console" },
  { id: "documents", label: "Documents" },
];

export function ProjectView({ runId, onBack, onOpenFactory }: { runId: string; onBack: () => void; onOpenFactory: () => void }) {
  const [tab, setTab] = useState<Tab>("overview");
  const [status, setStatus] = useState<(RunSummary & Record<string, any>) | null>(null);
  const [email, setEmail] = useState("");

  useEffect(() => { setTab("overview"); }, [runId]);
  useEffect(() => {
    api.status(runId).then(setStatus).catch(() => setStatus(null));
    api.me().then((m) => setEmail(m.email || "")).catch(() => {});
  }, [runId]);

  const name = status?.name || runId;
  const st = status ? statusOf(status) : null;

  return (
    <div style={{ height: "100vh", display: "flex", flexDirection: "column", background: T.bg, fontFamily: T.sans }}>
      {/* top bar + peer-tab strip */}
      <div style={{ background: T.raised, borderBottom: `1px solid ${T.borderSubtle}`, flexShrink: 0 }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "13px 24px" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 13, minWidth: 0 }}>
            <Btn variant="ghost" size="sm" onClick={onBack}><Icon name="arrowLeft" size={14} /> Projects</Btn>
            <Wordmark size={17} />
            <span style={{ font: `400 13px/1 ${T.mono}`, color: T.tertiary }}>/</span>
            <span style={{ font: `600 13px/1 ${T.sans}`, color: T.fg, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{name}</span>
            {st && <StatusPill tone={st.tone} dot={st.tone === "info" || st.tone === "brand"}>{st.label}</StatusPill>}
          </div>
          <Avatar name={email || "You"} size={28} tone="brand" />
        </div>
        <div style={{ display: "flex", gap: 2, padding: "0 24px" }}>
          {TABS.map((t) => {
            const on = t.id === tab;
            return (
              <button key={t.id} onClick={() => (t.id === "factory" ? onOpenFactory() : setTab(t.id as Tab))}
                style={{ position: "relative", padding: "11px 14px", background: "none", border: "none", cursor: "pointer", font: `${on ? 600 : 500} 13px/1 ${T.sans}`, color: on ? T.fg : T.secondary }}>
                {t.label}
                {on && <span style={{ position: "absolute", left: 10, right: 10, bottom: -1, height: 2, background: T.brand, borderRadius: 2 }} />}
              </button>
            );
          })}
        </div>
      </div>

      {/* tab content (peer views; Factory console navigates out via onOpenFactory) */}
      {tab === "overview"
        ? <OverviewTab runId={runId} onOpenFactory={onOpenFactory} />
        : <DocumentsTab runId={runId} />}
    </div>
  );
}
