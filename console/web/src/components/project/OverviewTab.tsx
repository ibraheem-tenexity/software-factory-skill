// OverviewTab.tsx — Project view §2.5 Overview: a mission-control board of zone panels over a
// dotted canvas (design orgproject.jsx → ProjectDashboard Overview). Driven by tjyb5gmy's locked
// endpoints (PR #13): GET /api/projects/{id}/overview (brief/build/services/agents/org + counts) and
// GET /api/projects/{id}/documents (the materials + produced LISTS). Every panel degrades to an
// empty/"—" state until the data is live.
import { useEffect, useRef, useState } from "react";
import { api, ProjectOverview, ProjectDocuments, ProjectMaterial, ProjectArtifact } from "../../api";
import { openArtifact } from "../factory/Artifacts";
import { T, Icon, CategoryLabel, Btn, StatusPill, Avatar, TextInput, TextArea } from "../onboarding/design";

const fileToB64 = (file: File): Promise<string> => new Promise((resolve) => {
  const r = new FileReader();
  r.onload = () => resolve(String(r.result || "").split(",")[1] || "");
  r.onerror = () => resolve("");
  r.readAsDataURL(file);
});

type Tone = "neutral" | "success" | "warning" | "danger" | "info" | "brand";

const FILE_KIND: Record<string, [string, string, string]> = {
  pdf: ["PDF", "#fbe3e3", "#c0392f"], xlsx: ["XLS", "#e4f8ef", "#1f8a5b"], csv: ["CSV", "#e4f8ef", "#1f8a5b"],
  doc: ["DOC", "#e8f1ff", "#1A7BFF"], md: ["MD", "#e8f1ff", "#1A7BFF"], svg: ["SVG", "#f3e9fb", "#7a3ea8"],
  video: ["MP4", "#f3e9fb", "#7a3ea8"], img: ["IMG", "#fbefdc", "#b06f12"],
};
const money = (v?: number) => (v != null ? `$${v.toFixed(2)}` : "—");
function fmtDate(v?: number | string): string {
  if (v == null || v === "") return "—";
  const n = typeof v === "number" ? v : Number(v);
  if (!isNaN(n) && n > 0) return new Date(n * 1000).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
  return String(v);
}
function fmtBytes(n?: number): string {
  if (!n) return "";
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${Math.round(n / 1024)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}
// Derive a pill tone from a free-text service/agent status (backend sends real status strings).
function statusTone(s?: string): Tone {
  const v = (s || "").toLowerCase();
  if (/fail|error|blocked/.test(v)) return "danger";
  if (/pending|idle|queued|waiting/.test(v)) return "neutral";
  if (/run|sync|active|live|deploy|done|connected/.test(v)) return "success";
  return "info";
}

function Panel({ title, count, children, span = 1, accent, action }:
  { title: string; count?: number; children: React.ReactNode; span?: number; accent?: boolean; action?: React.ReactNode }) {
  return (
    <section style={{ gridColumn: `span ${span}`, background: T.raised, border: `1px solid ${accent ? T.brand + "44" : T.borderSubtle}`, borderRadius: T.rXl, boxShadow: T.shadowXs, display: "flex", flexDirection: "column", overflow: "hidden" }}>
      <header style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "12px 16px", borderBottom: `1px solid ${T.borderSubtle}` }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <CategoryLabel tone={accent ? "brand" : "tertiary"}>{title}</CategoryLabel>
          {count != null && <span style={{ font: `500 10px/1 ${T.mono}`, color: T.tertiary, background: T.sunken, borderRadius: 9, padding: "2px 6px" }}>{count}</span>}
        </div>
        {action}
      </header>
      <div style={{ padding: 16, flex: 1 }}>{children}</div>
    </section>
  );
}

function FileRow({ label, kind, sub, onOpen }: { label: string; kind?: string; sub?: string; onOpen?: () => void }) {
  const k = FILE_KIND[kind || "doc"] || FILE_KIND.doc;
  return (
    <button onClick={onOpen} disabled={!onOpen} style={{ display: "flex", alignItems: "center", gap: 10, width: "100%", textAlign: "left", background: "none", border: "none", padding: 0, cursor: onOpen ? "pointer" : "default" }}>
      <span style={{ font: `700 9px/1 ${T.mono}`, color: k[2], background: k[1], padding: "4px 5px", borderRadius: 4, flexShrink: 0 }}>{k[0]}</span>
      <span style={{ flex: 1, minWidth: 0, font: `500 12.5px/1.3 ${T.sans}`, color: T.fg, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{label}</span>
      {sub && <span style={{ font: `400 11px/1 ${T.mono}`, color: T.tertiary, flexShrink: 0 }}>{sub}</span>}
    </button>
  );
}

function Empty({ children }: { children: React.ReactNode }) {
  return <div style={{ font: `400 12px/1.4 ${T.sans}`, color: T.tertiary }}>{children}</div>;
}

export function OverviewTab({ projectId, onOpenFactory, onOpenDocuments, onResume, onDiscard }:
  { projectId: string; onOpenFactory: () => void; onOpenDocuments?: () => void; onResume?: () => void; onDiscard?: () => void }) {
  const [ov, setOv] = useState<ProjectOverview | null>(null);
  const [docs, setDocs] = useState<ProjectDocuments | null>(null);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState(false);
  const [goalDraft, setGoalDraft] = useState("");
  const [scopeDraft, setScopeDraft] = useState("");
  const [capEditing, setCapEditing] = useState(false);
  const [capInput, setCapInput] = useState("");
  const addInputRef = useRef<HTMLInputElement | null>(null);

  const loadDocs = () => api.documents(projectId).then(setDocs).catch(() => setDocs(null));
  const loadOverview = () => api.overview(projectId).then(setOv).catch(() => setOv(null));
  useEffect(() => {
    setLoading(true);
    Promise.allSettled([
      api.overview(projectId).then(setOv).catch(() => setOv(null)),       // backend pending → graceful empty
      api.documents(projectId).then(setDocs).catch(() => setDocs(null)),  // materials + produced lists
    ]).finally(() => setLoading(false));
  }, [projectId]);

  const brief = ov?.brief || {};
  const build = ov?.build || {};
  const services = ov?.services || [];
  const agents = ov?.agents || [];
  const org = ov?.org || {};
  const materials: ProjectMaterial[] = docs?.uploaded || [];
  const produced: ProjectArtifact[] = docs?.produced || [];
  const pct = build.pct ?? 0;
  // A draft = onboarding intake not yet handed off (factory hasn't started). Drives the whole
  // "finish setup" treatment instead of the build-oriented overview.
  const isDraft = (brief.phase || "").toLowerCase() === "draft";

  // "+ Add" on Uploaded materials → attach a real file via POST /api/projects/{id}/materials, refetch.
  const addMaterials = async (list: FileList | null) => {
    if (!list || !list.length) return;
    for (const file of Array.from(list)) {
      try { await api.uploadMaterial(projectId, { name: file.name, content_type: file.type || undefined, data_b64: await fileToB64(file) }); }
      catch { /* endpoint not live yet — degrade silently */ }
    }
    await loadDocs();
  };

  // Edit the project brief post-promote: goal via PUT /api/projects/{id}/brief (live); scope via
  // PATCH /api/projects/{id} {scope} (graceful until tjyb5gmy ships it).
  const startEdit = () => { setGoalDraft(brief.goal || brief.description || ""); setScopeDraft((brief.scope || []).join(", ")); setEditing(true); };
  const saveBrief = async () => {
    const goal = goalDraft.trim();
    const scope = scopeDraft.split(",").map((s) => s.trim()).filter(Boolean);
    try { if (goal) await api.putBrief(projectId, { goals: goal }); } catch { /* ignore */ }
    try { await api.patchProject(projectId, { scope }); } catch { /* scope endpoint not live yet */ }
    await loadOverview();
    setEditing(false);
  };

  if (loading) {
    return <div style={{ flex: 1, display: "grid", placeItems: "center", background: T.bg }}>
      <span style={{ display: "inline-flex", alignItems: "center", gap: 8, font: `500 13px/1 ${T.sans}`, color: T.tertiary }}><Icon name="layers" size={14} color={T.tertiary} /> Loading project...</span>
    </div>;
  }

  return (
    <div style={{ flex: 1, overflow: "auto", backgroundImage: `radial-gradient(circle, ${T.borderSubtle} 1px, transparent 1px)`, backgroundSize: "22px 22px" }}>
      <div style={{ padding: "22px 24px 36px" }}>
        <div style={{ maxWidth: 1080, margin: "0 auto", display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 14, alignItems: "start" }}>

          {/* draft banner — the factory hasn't started; finish intake to kick it off */}
          {isDraft && (
            <section style={{ gridColumn: "1 / -1", display: "flex", alignItems: "center", gap: 16, padding: "16px 20px", borderRadius: T.rXl, border: `1px solid ${T.warning}`, background: T.warningSoft, boxShadow: T.shadowXs }}>
              <span style={{ width: 13, height: 13, background: T.warning, transform: "rotate(45deg)", borderRadius: 2, flexShrink: 0 }} />
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ font: `700 15px/1.2 ${T.display}`, letterSpacing: "-0.01em", color: T.fg }}>Finish setup to start building</div>
                <p style={{ margin: "4px 0 0", font: `400 12.5px/1.5 ${T.sans}`, color: T.secondary }}>This project is still a draft — the factory hasn't started. Complete the brief and scope, then hand off to kick off the pipeline.</p>
              </div>
              <div style={{ display: "flex", flexDirection: "column", gap: 8, alignItems: "flex-end" }}>
                {onResume && <Btn variant="primary" onClick={onResume}>Complete setup &amp; start building <Icon name="arrowRight" size={14} color="#fff" /></Btn>}
                {onDiscard && <button onClick={onDiscard} style={{ background: "none", border: "none", cursor: "pointer", font: `500 12px/1 ${"'Hanken Grotesk', ui-sans-serif, system-ui, sans-serif"}`, color: T.danger, padding: "4px 0" }}>Discard draft</button>}
              </div>
            </section>
          )}

          {/* project brief */}
          <Panel title="Project brief" span={2} accent>
            <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
              {!isDraft && (
                <div style={{ display: "flex", justifyContent: "flex-end", marginBottom: -8 }}>
                  {editing
                    ? <div style={{ display: "flex", gap: 8 }}><Btn variant="ghost" size="sm" onClick={() => setEditing(false)}>Cancel</Btn><Btn variant="primary" size="sm" onClick={saveBrief}>Save</Btn></div>
                    : <Btn variant="secondary" size="sm" onClick={startEdit}>Edit brief</Btn>}
                </div>
              )}
              {editing ? (
                <>
                  <div>
                    <CategoryLabel style={{ marginBottom: 6 }}>Goal</CategoryLabel>
                    <TextArea rows={3} value={goalDraft} onChange={setGoalDraft} placeholder="What should this project do?" />
                  </div>
                  <div>
                    <CategoryLabel style={{ marginBottom: 6 }}>Scope (comma-separated)</CategoryLabel>
                    <TextInput value={scopeDraft} onChange={setScopeDraft} placeholder="Quoting / RFQ, Pricing & approvals" />
                  </div>
                </>
              ) : (
                <>
                  <div>
                    <CategoryLabel style={{ marginBottom: 6 }}>Goal</CategoryLabel>
                    <p style={{ margin: 0, font: `400 14px/1.55 ${T.sans}`, color: T.fg }}>{brief.goal || brief.description || <Empty>No goal captured yet.</Empty>}</p>
                  </div>
                  {!!(brief.scope && brief.scope.length) ? (
                    <div>
                      <CategoryLabel style={{ marginBottom: 7 }}>Scope</CategoryLabel>
                      <div style={{ display: "flex", flexWrap: "wrap", gap: 7 }}>
                        {brief.scope.map((s) => <span key={s} style={{ font: `500 12px/1 ${T.sans}`, color: T.brandDeep, background: T.brandSoft, padding: "6px 11px", borderRadius: 9999 }}>{s}</span>)}
                      </div>
                    </div>
                  ) : isDraft ? (
                    <div>
                      <CategoryLabel style={{ marginBottom: 7 }}>Scope</CategoryLabel>
                      <span style={{ font: `400 12.5px/1.4 ${T.sans}`, color: T.tertiary, fontStyle: "italic" }}>Defined during setup.</span>
                    </div>
                  ) : null}
                </>
              )}
              <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 10, paddingTop: 4 }}>
                {([["Created by", brief.created_by || brief.owner], ["Created", fmtDate(brief.created)], ["Owner", brief.owner], ["Phase", brief.phase]] as [string, string | undefined][]).map(([k, v]) => (
                  <div key={k}><CategoryLabel style={{ display: "block", marginBottom: 4 }}>{k}</CategoryLabel><span style={{ font: `500 12.5px/1.3 ${T.sans}`, color: T.fg, wordBreak: "break-all" }}>{v || "—"}</span></div>
                ))}
              </div>
            </div>
          </Panel>

          {/* build status — draft = setup checklist; live = progress + factory console */}
          <Panel title="Build status">
            {isDraft ? (
              <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                <span style={{ font: `700 24px/1.1 ${T.display}`, letterSpacing: "-0.01em", color: T.tertiary }}>Not started</span>
                <p style={{ margin: 0, font: `400 12px/1.5 ${T.sans}`, color: T.secondary }}>The factory hasn't run yet. Finish setup and hand off — agents, tickets, and spend appear once the build starts.</p>
                <div style={{ display: "flex", flexDirection: "column", gap: 9, padding: "11px 0", borderTop: `1px solid ${T.borderSubtle}`, borderBottom: `1px solid ${T.borderSubtle}` }}>
                  {([
                    ["Project brief", !!(brief.goal || brief.description)],
                    ["Scope of work", !!(brief.scope && brief.scope.length)],
                    [`Build engine · ${brief.runtime === "opencode" ? "OpenCode" : "Claude"}`, true],
                    ["Materials (optional)", materials.length > 0],
                  ] as [string, boolean][]).map(([k, done]) => (
                    <div key={k} style={{ display: "flex", alignItems: "center", gap: 9 }}>
                      <span style={{ width: 16, height: 16, borderRadius: "50%", flexShrink: 0, display: "grid", placeItems: "center", background: done ? T.success : "transparent", border: `1.5px solid ${done ? T.success : T.borderDefault}` }}>{done && <Icon name="check" size={10} color="#fff" />}</span>
                      <span style={{ font: `500 12.5px/1.2 ${T.sans}`, color: done ? T.fg : T.secondary }}>{k}</span>
                    </div>
                  ))}
                </div>
                {onResume && <Btn variant="primary" size="sm" full onClick={onResume}>Complete setup &amp; start building <Icon name="arrowRight" size={13} color="#fff" /></Btn>}
              </div>
            ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: 13 }}>
              <div style={{ display: "flex", alignItems: "baseline", gap: 8 }}>
                <span style={{ font: `700 30px/1 ${T.display}`, color: T.brandDeep }}>{pct}%</span>
                <span style={{ font: `500 12px/1 ${T.mono}`, color: T.tertiary }}>{build.done ? "deployed" : "complete"}</span>
              </div>
              <span style={{ height: 7, borderRadius: 4, background: T.sunken, overflow: "hidden" }}><span style={{ display: "block", height: "100%", width: pct + "%", background: build.done ? T.success : T.brand }} /></span>
              <div style={{ display: "flex", flexDirection: "column", gap: 7 }}>
                {([
                  ["Tickets done", build.tickets_total != null ? `${build.tickets_done ?? 0} / ${build.tickets_total}` : "—"],
                  ["Agents working", build.agents_working != null ? String(build.agents_working) : "—"],
                  ["Spend", money(build.spent_usd)],
                ] as [string, string][]).map(([k, v]) => (
                  <div key={k} style={{ display: "flex", justifyContent: "space-between" }}><span style={{ font: `400 12.5px/1 ${T.sans}`, color: T.secondary }}>{k}</span><span style={{ font: `500 12.5px/1 ${T.mono}`, color: T.fg }}>{v}</span></div>
                ))}
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <span style={{ font: `400 12.5px/1 ${T.sans}`, color: T.secondary }}>Budget cap</span>
                  {capEditing ? (
                    <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
                      <span style={{ font: `500 12px/1 ${T.mono}`, color: T.secondary }}>$</span>
                      <input value={capInput} onChange={(e) => setCapInput(e.target.value)}
                        onKeyDown={(e) => { if (e.key === "Enter") { const n = parseFloat(capInput); if (!isNaN(n) && n > 0) { api.putBudget(projectId, n).then(loadOverview).catch(() => undefined); } setCapEditing(false); } if (e.key === "Escape") setCapEditing(false); }}
                        style={{ width: 58, font: `500 12.5px/1 ${T.mono}`, color: T.fg, background: T.bg, border: `1px solid ${T.borderDefault}`, borderRadius: 4, padding: "2px 5px", outline: "none" }} autoFocus />
                      <button onClick={() => { const n = parseFloat(capInput); if (!isNaN(n) && n > 0) { api.putBudget(projectId, n).then(loadOverview).catch(() => undefined); } setCapEditing(false); }}
                        style={{ background: "none", border: "none", cursor: "pointer", color: T.success, font: `600 11px/1 ${T.sans}`, padding: "0 2px" }}>Save</button>
                      <button onClick={() => setCapEditing(false)}
                        style={{ background: "none", border: "none", cursor: "pointer", color: T.tertiary, font: `500 11px/1 ${T.sans}`, padding: "0 2px" }}>Cancel</button>
                    </div>
                  ) : (
                    <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                      <span style={{ font: `500 12.5px/1 ${T.mono}`, color: T.fg }}>{build.budget_ceiling != null ? money(build.budget_ceiling) : "—"}</span>
                      <button onClick={() => { setCapInput(build.budget_ceiling != null ? String(build.budget_ceiling) : ""); setCapEditing(true); }}
                        style={{ background: "none", border: "none", cursor: "pointer", color: T.tertiary, padding: 0, lineHeight: 1, display: "inline-flex" }} title="Edit budget cap">
                        <Icon name="pencil" size={11} color={T.tertiary} />
                      </button>
                    </div>
                  )}
                </div>
              </div>
              <Btn variant="primary" size="sm" full onClick={onOpenFactory}>Open factory console <Icon name="arrowRight" size={13} color="#fff" /></Btn>
            </div>
            )}
          </Panel>

          {/* services at work */}
          <Panel title="Services at work" count={services.length || undefined} span={2}>
            {services.length ? (
              <div style={{ display: "grid", gridTemplateColumns: "repeat(2, 1fr)", gap: 10 }}>
                {services.map((s) => (
                  <div key={s.label} style={{ display: "flex", gap: 11, padding: "11px 12px", borderRadius: T.rLg, border: `1px solid ${T.borderSubtle}`, background: T.bg }}>
                    <span style={{ width: 32, height: 32, flexShrink: 0, borderRadius: 8, display: "grid", placeItems: "center", background: T.raised, border: `1px solid ${T.borderSubtle}`, color: T.secondary, font: `700 11px/1 ${T.mono}` }}>{s.label.slice(0, 2).toUpperCase()}</span>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ display: "flex", alignItems: "center", gap: 7 }}>
                        <span style={{ font: `600 13px/1.2 ${T.sans}`, color: T.fg }}>{s.label}</span>
                        {s.kind && <CategoryLabel style={{ fontSize: 10 }}>{s.kind}</CategoryLabel>}
                        {s.status && <StatusPill tone={statusTone(s.status)} dot>{s.status}</StatusPill>}
                      </div>
                      {(s.detail || s.url) && <p style={{ margin: "3px 0 0", font: `400 11.5px/1.4 ${T.sans}`, color: T.tertiary, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{s.detail || s.url}</p>}
                    </div>
                  </div>
                ))}
              </div>
            ) : <Empty>{isDraft ? "No services connected yet — you'll link them during setup." : "No services connected yet."}</Empty>}
          </Panel>

          {/* agents on this project */}
          <Panel title="Agents on this project" count={agents.length || undefined}>
            {agents.length ? (
              <div style={{ display: "flex", flexDirection: "column", gap: 9 }}>
                {agents.map((a, i) => (
                  <div key={a.role + i} style={{ display: "flex", alignItems: "center", gap: 10 }}>
                    <Avatar name={a.role} size={26} />
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <span style={{ display: "block", font: `600 12.5px/1.2 ${T.sans}`, color: T.fg }}>{a.role}{a.model && <span style={{ color: T.tertiary, fontWeight: 400 }}> · {a.model}</span>}</span>
                      {a.task && <span style={{ display: "block", font: `400 11px/1.3 ${T.sans}`, color: T.tertiary, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{a.task}</span>}
                    </div>
                    {a.status === "running" && <span style={{ width: 6, height: 6, borderRadius: "50%", background: T.success }} />}
                  </div>
                ))}
              </div>
            ) : <Empty>{isDraft ? "No agents yet — they spin up when the build starts." : "No agents on this project yet."}</Empty>}
          </Panel>

          {/* uploaded materials — "+ Add" attaches a real file (POST /api/projects/{id}/materials) */}
          <Panel title="Uploaded materials" count={materials.length || undefined}
            action={<>
              <input ref={addInputRef} type="file" multiple style={{ display: "none" }} onChange={(e) => { addMaterials(e.target.files); e.currentTarget.value = ""; }} />
              <button onClick={() => addInputRef.current?.click()} style={{ font: `500 11.5px/1 ${T.sans}`, color: T.brandDeep, background: "none", border: "none", cursor: "pointer" }}>+ Add</button>
            </>}>
            {materials.length ? <div style={{ display: "flex", flexDirection: "column", gap: 9 }}>{materials.map((d, i) => <FileRow key={d.name + i} label={d.name} kind={d.kind} sub={fmtBytes(d.size_bytes)} />)}</div> : <Empty>Nothing uploaded.</Empty>}
          </Panel>

          {/* produced documents */}
          <Panel title="Produced documents" count={produced.length || undefined} span={2}
            action={!isDraft && onOpenDocuments ? <button onClick={onOpenDocuments} style={{ font: `500 11.5px/1 ${T.sans}`, color: T.brandDeep, background: "none", border: "none", cursor: "pointer" }}>View all →</button> : null}>
            {produced.length ? (
              <div style={{ display: "grid", gridTemplateColumns: "repeat(2, 1fr)", gap: 10 }}>
                {produced.map((d, i) => <FileRow key={d.title + i} label={d.title} kind={d.kind} sub={d.agent} onOpen={d.id ? () => openArtifact(d.id!) : d.path ? () => window.open(`/api/projects/${projectId}/artifact?path=${encodeURIComponent(d.path!)}&raw=1`, "_blank") : undefined} />)}
              </div>
            ) : <Empty>{isDraft ? "The factory produces PRDs, architecture, designs, and tickets here once the build starts." : "The factory hasn't produced documents yet."}</Empty>}
          </Panel>

          {/* inherited org context */}
          <Panel title="Inherited org context">
            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              {([["Company", org.name], ["Industry", org.industry], ["Systems", org.connected_systems?.join(", ")]] as [string, string | undefined][]).map(([k, v]) => (
                <div key={k} style={{ display: "flex", justifyContent: "space-between", gap: 10 }}>
                  <CategoryLabel>{k}</CategoryLabel>
                  <span style={{ font: `500 12px/1.3 ${T.sans}`, color: T.fg, textAlign: "right" }}>{v || "—"}</span>
                </div>
              ))}
            </div>
          </Panel>

        </div>
      </div>
    </div>
  );
}
