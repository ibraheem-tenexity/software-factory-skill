// OverviewTab.tsx — Project view §2.5 Overview: a mission-control board of zone panels over a
// dotted canvas (design orgproject.jsx → ProjectDashboard Overview). Driven by tjyb5gmy's locked
// endpoints (PR #13): GET /api/projects/{id}/overview (brief/build/services/agents/org + counts) and
// GET /api/projects/{id}/documents (the materials + produced LISTS). Every panel degrades to an
// empty/“—” state until the data is live.
import { useEffect, useState } from "react";
import { api, ProjectOverview, ProjectDocuments, ProjectMaterial, ProjectArtifact } from "../../api";
import { T, Icon, CategoryLabel, Btn, StatusPill, Avatar } from "../onboarding/design";

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

function Panel({ title, count, children, span = 1, accent }:
  { title: string; count?: number; children: React.ReactNode; span?: number; accent?: boolean }) {
  return (
    <section style={{ gridColumn: `span ${span}`, background: T.raised, border: `1px solid ${accent ? T.brand + "44" : T.borderSubtle}`, borderRadius: T.rXl, boxShadow: T.shadowXs, display: "flex", flexDirection: "column", overflow: "hidden" }}>
      <header style={{ display: "flex", alignItems: "center", gap: 8, padding: "12px 16px", borderBottom: `1px solid ${T.borderSubtle}` }}>
        <CategoryLabel tone={accent ? "brand" : "tertiary"}>{title}</CategoryLabel>
        {count != null && <span style={{ font: `500 10px/1 ${T.mono}`, color: T.tertiary, background: T.sunken, borderRadius: 9, padding: "2px 6px" }}>{count}</span>}
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

export function OverviewTab({ projectId, onOpenFactory }: { projectId: string; onOpenFactory: () => void }) {
  const [ov, setOv] = useState<ProjectOverview | null>(null);
  const [docs, setDocs] = useState<ProjectDocuments | null>(null);

  useEffect(() => {
    api.overview(projectId).then(setOv).catch(() => setOv(null));      // backend pending → graceful empty
    api.documents(projectId).then(setDocs).catch(() => setDocs(null)); // materials + produced lists
  }, [projectId]);

  const brief = ov?.brief || {};
  const build = ov?.build || {};
  const services = ov?.services || [];
  const agents = ov?.agents || [];
  const org = ov?.org || {};
  const materials: ProjectMaterial[] = docs?.uploaded || [];
  const produced: ProjectArtifact[] = docs?.produced || [];
  const pct = build.pct ?? 0;

  return (
    <div style={{ flex: 1, overflow: "auto", backgroundImage: `radial-gradient(circle, ${T.borderSubtle} 1px, transparent 1px)`, backgroundSize: "22px 22px" }}>
      <div style={{ padding: "22px 24px 36px" }}>
        <div style={{ maxWidth: 1080, margin: "0 auto", display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 14, alignItems: "start" }}>

          {/* project brief */}
          <Panel title="Project brief" span={2} accent>
            <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
              <div>
                <CategoryLabel style={{ marginBottom: 6 }}>Goal</CategoryLabel>
                <p style={{ margin: 0, font: `400 14px/1.55 ${T.sans}`, color: T.fg }}>{brief.goal || brief.description || <Empty>No goal captured yet.</Empty>}</p>
              </div>
              {!!(brief.scope && brief.scope.length) && (
                <div>
                  <CategoryLabel style={{ marginBottom: 7 }}>Scope</CategoryLabel>
                  <div style={{ display: "flex", flexWrap: "wrap", gap: 7 }}>
                    {brief.scope.map((s) => <span key={s} style={{ font: `500 12px/1 ${T.sans}`, color: T.brandDeep, background: T.brandSoft, padding: "6px 11px", borderRadius: 9999 }}>{s}</span>)}
                  </div>
                </div>
              )}
              <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 10, paddingTop: 4 }}>
                {([["Owner", brief.owner], ["Created", fmtDate(brief.created)], ["Phase", brief.phase]] as [string, string | undefined][]).map(([k, v]) => (
                  <div key={k}><CategoryLabel style={{ display: "block", marginBottom: 4 }}>{k}</CategoryLabel><span style={{ font: `500 12.5px/1.3 ${T.sans}`, color: T.fg }}>{v || "—"}</span></div>
                ))}
              </div>
            </div>
          </Panel>

          {/* build status */}
          <Panel title="Build status">
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
                  ["Spend", build.budget_ceiling != null ? `${money(build.spent_usd)} / ${money(build.budget_ceiling)}` : money(build.spent_usd)],
                ] as [string, string][]).map(([k, v]) => (
                  <div key={k} style={{ display: "flex", justifyContent: "space-between" }}><span style={{ font: `400 12.5px/1 ${T.sans}`, color: T.secondary }}>{k}</span><span style={{ font: `500 12.5px/1 ${T.mono}`, color: T.fg }}>{v}</span></div>
                ))}
              </div>
              <Btn variant="primary" size="sm" full onClick={onOpenFactory}>Open factory console <Icon name="arrowRight" size={13} color="#fff" /></Btn>
            </div>
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
            ) : <Empty>No services connected yet.</Empty>}
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
            ) : <Empty>No agents on this project yet.</Empty>}
          </Panel>

          {/* uploaded materials */}
          <Panel title="Uploaded materials" count={materials.length || undefined}>
            {materials.length ? <div style={{ display: "flex", flexDirection: "column", gap: 9 }}>{materials.map((d, i) => <FileRow key={d.name + i} label={d.name} kind={d.kind} sub={fmtBytes(d.size_bytes)} />)}</div> : <Empty>Nothing uploaded.</Empty>}
          </Panel>

          {/* produced documents */}
          <Panel title="Produced documents" count={produced.length || undefined} span={2}>
            {produced.length ? (
              <div style={{ display: "grid", gridTemplateColumns: "repeat(2, 1fr)", gap: 10 }}>
                {produced.map((d, i) => <FileRow key={d.title + i} label={d.title} kind={d.kind} sub={d.agent} onOpen={d.path ? () => window.open(`/api/projects/${projectId}/artifact?path=${encodeURIComponent(d.path!)}&raw=1`, "_blank") : undefined} />)}
              </div>
            ) : <Empty>The factory hasn’t produced documents yet.</Empty>}
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
