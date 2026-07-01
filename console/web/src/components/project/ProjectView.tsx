// ProjectView.tsx — Project view §2.5 shell: peer-tab views Overview · Factory console · Documents
// (design orgproject.jsx → ProjectDashboard). Overview + Documents render inline (my components);
// the "Factory console" tab is a NAV CALLBACK into the existing console (onOpenFactory) — it is NOT
// rendered inline, so this stays fully decoupled from the factory components.
import { useEffect, useRef, useState } from "react";
import { api, ProjectSummary } from "../../api";
import { T, Icon, Btn, StatusPill, Wordmark, TextInput } from "../onboarding/design";
import { AccountMenu } from "../AccountMenu";
import { OverviewTab } from "./OverviewTab";
import { DocumentsTab } from "./DocumentsTab";

type Tab = "overview" | "documents";
type Tone = "neutral" | "success" | "warning" | "danger" | "info" | "brand";

function statusOf(s: ProjectSummary & Record<string, any>): { label: string; tone: Tone } {
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

function setParam(key: string, value: string | null) {
  const p = new URLSearchParams(location.search);
  if (value === null) p.delete(key); else p.set(key, value);
  history.replaceState(null, "", "?" + p.toString());
}

export function ProjectView({ projectId, onBack, onOpenFactory, onResume, onOpen }: { projectId: string; onBack: () => void; onOpenFactory: () => void; onResume?: () => void; onOpen?: (id: string) => void }) {
  const [tab, setTab] = useState<Tab>(() => {
    const t = new URLSearchParams(location.search).get("tab");
    return (t === "documents" ? t : "overview") as Tab;
  });
  const [status, setStatus] = useState<(ProjectSummary & Record<string, any>) | null>(null);
  const [menu, setMenu] = useState(false);
  const [renaming, setRenaming] = useState(false);
  const [nameDraft, setNameDraft] = useState("");
  const [relaunchError, setRelaunchError] = useState<string | null>(null);

  // Reset tab only on genuine project *change* (not initial mount) so URL-seeded tab survives render.
  const prevProjectRef = useRef(projectId);
  useEffect(() => {
    if (prevProjectRef.current === projectId) return;
    prevProjectRef.current = projectId;
    setTab("overview");
    setParam("tab", null);
  }, [projectId]);
  useEffect(() => { setParam("tab", tab === "overview" ? null : tab); }, [tab]);
  useEffect(() => {
    api.status(projectId).then(setStatus).catch(() => setStatus(null));
  }, [projectId]);

  const name = status?.name || projectId;
  const st = status ? statusOf(status) : null;

  // Project CRUD (NEW endpoints — graceful until tjyb5gmy ships).
  const doRename = async () => {
    const n = nameDraft.trim();
    if (!n) { setRenaming(false); return; }
    try { await api.patchProject(projectId, { name: n }); setStatus((s) => (s ? { ...s, name: n } : s)); } catch { /* not live yet */ }
    setRenaming(false);
  };
  const isDraft = status?.phase === "draft";
  const canRelaunch = status?.phase === "stopped" || status?.phase === "done";
  const doRelaunch = async () => {
    setRelaunchError(null);
    try {
      const r = await api.relaunchProject(projectId);
      if (onOpen) onOpen(r.project_id); else onBack();
    } catch (e: any) {
      setRelaunchError(e?.message || "Couldn't relaunch. Try again.");
    }
  };
  const doArchive = async () => {
    const msg = isDraft
      ? `Discard "${name}"? This draft will be permanently deleted.`
      : `Archive "${name}"? It'll be hidden from your projects.`;
    if (!confirm(msg)) return;
    try { await api.deleteProject(projectId); onBack(); } catch { /* not live yet */ }
  };

  return (
    <div style={{ height: "100vh", display: "flex", flexDirection: "column", background: T.bg, fontFamily: T.sans }}>
      {/* top bar + peer-tab strip */}
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
                <span style={{ font: `600 13px/1 ${T.sans}`, color: T.fg, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{name}</span>
                {st && <StatusPill tone={st.tone} dot={st.tone === "info" || st.tone === "brand"}>{st.label}</StatusPill>}
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
      {tab === "overview" && <OverviewTab projectId={projectId} onOpenFactory={onOpenFactory} onOpenDocuments={() => setTab("documents")} onResume={onResume} onDiscard={isDraft ? doArchive : undefined} />}
      {tab === "documents" && <DocumentsTab projectId={projectId} />}
    </div>
  );
}
