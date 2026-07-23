// OverviewTab.tsx — Project view §2.5a Overview: an understandable project SNAPSHOT, not an
// inventory of every subsystem (design projectknowledge.jsx → ProjectOverview / PRD §2.5a). It
// answers, from REAL run state only: what the project is, what has finished, what is happening now,
// what needs attention, and the next useful checkpoint. Services, individual agents, uploads, and
// inherited org context leave Overview — operational detail lives in Factory console, source
// material in Files. Sourced from GET /overview (brief/build), /status (blockers/phase), /brief
// (canonical product brief + headings), /documents (newest factory outputs). Nothing is fabricated:
// the status sentence is derived here from live fields, never a stored narrative flag.
import { useEffect, useState } from "react";
import {
  api, ProjectOverview, ProjectDocuments, ProjectArtifact, ProjectSummary, BriefResponse, phaseIsStale,
} from "../../api";
import { openArtifact } from "../factory/Artifacts";
import { T, Icon, Sparkle, CategoryLabel, Btn, Markdown } from "../onboarding/design";
import { PanelBodySkel } from "../skeleton";

type Tone = "neutral" | "success" | "warning" | "danger" | "info" | "brand";

const money = (v?: number) => (v != null ? `$${v.toFixed(2)}` : "—");

function fmtDate(v?: number | string): string {
  if (v == null || v === "") return "—";
  const n = typeof v === "number" ? v : Number(v);
  if (!isNaN(n) && n > 0) return new Date(n * 1000).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
  return String(v);
}

// The PRD is THE primary produced artifact — it gets the brand chip in the outputs preview.
const isPrd = (d: ProjectArtifact) =>
  (d.kind || "").toLowerCase() === "prd" || d.title.trim().toLowerCase() === "prd";

// Human phase label for the Build-status "current phase" row. When the recorded phase belongs to a
// different stage than the current one, it's stale (a new stage stamped its number before its agent
// emitted the first set-phase) — show "Stage N · starting" instead of the misleading prior name.
function phaseLabel(phase?: string, stage?: number): string {
  if (phaseIsStale(phase, stage)) return `Stage ${stage} · starting`;
  const p = (phase || "").trim();
  const named = p ? p.charAt(0).toUpperCase() + p.slice(1) : "";
  if (stage && named) return `Stage ${stage} · ${named}`;
  return named || (stage ? `Stage ${stage}` : "—");
}

// The plain-language status sentence + next checkpoint/action, DERIVED from real run state
// (blockers, done/deploy, stage/phase, tickets) — PRD §2.5a. Attention states win over progress.
type Snapshot = { tone: Tone; icon: string; title: string; detail: string;
  cta?: { label: string; onClick: () => void; primary?: boolean } };
function deriveSnapshot(
  st: (ProjectSummary & Record<string, any>) | null,
  build: NonNullable<ProjectOverview["build"]>,
  phase: string,
  stage: number,
  ticketsDone: number,
  ticketsTotal: number,
  routes: { resume?: () => void; factory: () => void; outputs: () => void },
): Snapshot {
  const deployUrl = st?.deploy_url || build.deploy_url || "";
  const done = !!(st?.done || build.done || deployUrl);

  if (phase === "draft") {
    return {
      tone: "warning", icon: "pencil",
      title: "Finish the project conversation before the factory starts.",
      detail: "Return to the Concierge to refine the brief, review what it learned, and hand off when you agree.",
      cta: routes.resume ? { label: "Resume conversation", onClick: routes.resume, primary: true } : undefined,
    };
  }
  if (st?.budget_stopped) {
    return {
      tone: "warning", icon: "pause",
      title: "The build paused at your budget cap.",
      detail: "Raise the cap in Build status below to let the factory keep going, or open the console to review the spend.",
      cta: { label: "Open factory console", onClick: routes.factory, primary: true },
    };
  }
  if (st?.credential_stopped) {
    return {
      tone: "warning", icon: "lock",
      title: "The build needs a credential before it can continue.",
      detail: "Provide the required key in the factory console to unblock the run.",
      cta: { label: "Open factory console", onClick: routes.factory, primary: true },
    };
  }
  if (st?.held || phase === "stopped") {
    return {
      tone: "warning", icon: "pause",
      title: "The build is paused and waiting on you.",
      detail: "Open the factory console to review what it needs and resume when you're ready.",
      cta: { label: "Open factory console", onClick: routes.factory, primary: true },
    };
  }
  if (done) {
    return {
      tone: "success", icon: "check",
      title: deployUrl ? "Your app is built and deployed." : "The build is complete.",
      detail: deployUrl ? "It's live — open it to try it out, or review everything the factory produced." : "Review what the factory produced, or open the console for the full delivery record.",
      cta: deployUrl
        ? { label: "Open the app", onClick: () => window.open(deployUrl, "_blank"), primary: true }
        : { label: "See what the factory produced", onClick: routes.outputs },
    };
  }
  // Active build — describe what has finished, what's happening, and the next checkpoint by stage.
  const active: Record<number, { title: string; detail: string }> = {
    1: {
      title: "Research and setup are underway.",
      detail: "The Concierge's brief is being turned into a product plan. The product plan (PRD) is the next output.",
    },
    2: {
      title: "Research is complete — the product plan and architecture are being prepared.",
      detail: "Architecture and the ticket plan come next, then the factory starts building.",
    },
    3: {
      title: ticketsTotal
        ? `The factory is building your app — ${ticketsDone} of ${ticketsTotal} tickets delivered.`
        : "The factory is building your app.",
      detail: "Building and testing are in progress. Deployment is the next checkpoint.",
    },
  };
  const a = active[stage] || {
    title: phase ? `The factory is working — ${phaseLabel(phase, stage).toLowerCase()}.` : "The factory is working on your project.",
    detail: "Open the console to watch the build, or see what it has produced so far.",
  };
  return {
    tone: "brand", icon: "zap", title: a.title, detail: a.detail,
    cta: { label: "See what the factory produced", onClick: routes.outputs },
  };
}

// Level-2/3 Markdown headings from the canonical product brief — a real contents preview, no fixed
// section count (PRD §2.5b). Falls back to H1s when the brief has no sub-headings.
function briefHeadings(md?: string | null): string[] {
  if (!md) return [];
  const lines = md.split("\n");
  const grab = (re: RegExp) => lines.map((l) => l.match(re)).filter(Boolean).map((m) => (m as RegExpMatchArray)[1].trim());
  const sub = grab(/^#{2,3}\s+(.+?)\s*#*$/);
  const pick = sub.length ? sub : grab(/^#\s+(.+?)\s*#*$/);
  return pick.slice(0, 4);
}

function Panel({ title, count, children, accent, action }:
  { title: string; count?: number; children: React.ReactNode; accent?: boolean; action?: React.ReactNode }) {
  return (
    <section style={{ background: T.raised, border: `1px solid ${accent ? T.brand + "44" : T.borderSubtle}`, borderRadius: T.rXl, boxShadow: T.shadowXs, display: "flex", flexDirection: "column", overflow: "hidden" }}>
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

// A tappable row (brief heading / factory output) with a leading badge and a chevron affordance.
function LinkRow({ badge, badgeTone, title, sub, first, onClick }:
  { badge: string; badgeTone?: "brand" | "neutral"; title: string; sub: string; first: boolean; onClick?: () => void }) {
  const brand = badgeTone === "brand";
  return (
    <button onClick={onClick} disabled={!onClick} style={{ width: "100%", display: "flex", alignItems: "center", gap: 10, padding: "10px 0", border: 0, borderTop: first ? "none" : `1px solid ${T.borderSubtle}`, background: "none", cursor: onClick ? "pointer" : "default", textAlign: "left" }}>
      <span style={{ minWidth: 30, height: 30, padding: "0 5px", borderRadius: 7, display: "grid", placeItems: "center", background: brand ? T.brandSoft : T.sunken, color: brand ? T.brandDeep : T.secondary, font: `700 9px/1 ${T.mono}`, letterSpacing: "0.04em" }}>{badge}</span>
      <span style={{ flex: 1, minWidth: 0 }}>
        <span style={{ display: "block", font: `600 12.5px/1.25 ${T.sans}`, color: T.fg, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{title}</span>
        <span style={{ display: "block", font: `400 11px/1.35 ${T.sans}`, color: T.tertiary, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{sub}</span>
      </span>
      {onClick && <Icon name="chevronRight" size={13} color={T.tertiary} />}
    </button>
  );
}

// Honest empty/unavailable state — icon + short explainer that NAMES the real reason (which stage
// produces the missing thing, or which projection failed to load). Never a dead affordance.
function Note({ icon, title, detail }: { icon: string; title: string; detail: string }) {
  return (
    <div style={{ minHeight: 96, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: 6, padding: "16px 12px", textAlign: "center" }}>
      <Icon name={icon} size={20} color={T.tertiary} />
      <span style={{ font: `600 12.5px/1.3 ${T.sans}`, color: T.secondary }}>{title}</span>
      <span style={{ font: `400 11.5px/1.45 ${T.sans}`, color: T.tertiary, maxWidth: 320 }}>{detail}</span>
    </div>
  );
}

export function OverviewTab({ projectId, onOpenFactory, onOpenDocuments, onOpenBrief, onOpenOutputs, onResume, onDiscard }:
  { projectId: string; onOpenFactory: () => void; onOpenDocuments?: () => void;
    onOpenBrief?: () => void; onOpenOutputs?: () => void; onResume?: () => void; onDiscard?: () => void }) {
  const [ov, setOv] = useState<ProjectOverview | null>(null);
  const [ovErr, setOvErr] = useState(false);
  const [st, setSt] = useState<(ProjectSummary & Record<string, any>) | null>(null);
  const [briefResp, setBriefResp] = useState<BriefResponse | null>(null);
  const [briefErr, setBriefErr] = useState(false);
  const [docs, setDocs] = useState<ProjectDocuments | null>(null);
  const [docsErr, setDocsErr] = useState(false);
  const [loading, setLoading] = useState(true);
  // Budget cap inline edit — same PUT /budget flow; the server's ACTUAL refusal is surfaced (never
  // swallowed) so a lower-than-spent rejection or transport error reads honestly (PRD §2.5a).
  const [capEditing, setCapEditing] = useState(false);
  const [capInput, setCapInput] = useState("");
  const [capError, setCapError] = useState("");

  const loadOverview = () => api.overview(projectId).then((o) => { setOv(o); setOvErr(false); }).catch(() => { setOv(null); setOvErr(true); });

  useEffect(() => {
    setLoading(true);
    setOvErr(false); setBriefErr(false); setDocsErr(false);
    Promise.allSettled([
      loadOverview(),
      api.status(projectId).then(setSt).catch(() => setSt(null)),
      api.brief(projectId).then((b) => { setBriefResp(b); setBriefErr(false); }).catch(() => { setBriefResp(null); setBriefErr(true); }),
      api.documents(projectId).then((d) => { setDocs(d); setDocsErr(false); }).catch(() => { setDocs(null); setDocsErr(true); }),
    ]).finally(() => setLoading(false));
  }, [projectId]);

  const brief = ov?.brief || {};
  const build = ov?.build || {};
  const phase = (st?.phase ?? brief.phase ?? "").toLowerCase();
  const stage = st?.stage ?? brief.stage ?? 0;
  const isDraft = phase === "draft";
  const pct = build.pct ?? 0;
  const briefUrl = briefResp?.brief_url || null;
  const headings = briefHeadings(briefResp?.brief_markdown);
  const produced: ProjectArtifact[] = [...(docs?.produced || [])].sort((a, b) => (b.ts || 0) - (a.ts || 0));
  const newest = produced.slice(0, 3);

  // Routes to full peer views. onOpenBrief/onOpenOutputs are the SOF-239 shell's dedicated peers;
  // until wired, fall back to a real destination that exists today — the finalized brief document
  // (new tab) and the Documents tab — so every route lands somewhere real, never a dead control.
  const openBrief = onOpenBrief || (briefUrl ? () => window.open(briefUrl, "_blank") : onOpenDocuments);
  const openOutputs = onOpenOutputs || onOpenDocuments;

  const snap = deriveSnapshot(st, build, phase, stage,
    build.tickets_done ?? 0, build.tickets_total ?? 0,
    { resume: onResume, factory: onOpenFactory, outputs: () => (openOutputs ? openOutputs() : onOpenFactory()) });

  const saveCap = () => {
    const n = parseFloat(capInput);
    if (isNaN(n) || n <= 0) { setCapError("Enter a dollar amount greater than 0."); return; }
    api.putBudget(projectId, n)
      .then(() => { setCapError(""); setCapEditing(false); return loadOverview(); })
      .catch((e: any) => setCapError(typeof e?.detail === "string" ? e.detail : e?.message || "Couldn't update the budget cap."));
  };

  if (loading) {
    return (
      <div style={{ flex: 1, overflow: "auto", backgroundImage: `radial-gradient(circle, ${T.borderSubtle} 1px, transparent 1px)`, backgroundSize: "22px 22px" }}>
        <div style={{ maxWidth: 1060, margin: "0 auto", padding: "22px 24px 38px" }}>
          <section style={{ marginBottom: 14, padding: "16px 18px", borderRadius: T.rXl, border: `1px solid ${T.borderSubtle}`, background: T.raised, boxShadow: T.shadowXs }}><PanelBodySkel rows={2} /></section>
          <div style={{ display: "grid", gridTemplateColumns: "minmax(0, 1.55fr) minmax(260px, .75fr)", gap: 14 }}>
            {[5, 5].map((r, i) => (
              <section key={i} style={{ background: T.raised, border: `1px solid ${T.borderSubtle}`, borderRadius: T.rXl, overflow: "hidden" }}>
                <div style={{ padding: "12px 16px", borderBottom: `1px solid ${T.borderSubtle}` }}><PanelBodySkel rows={1} /></div>
                <div style={{ padding: 16 }}><PanelBodySkel rows={r} /></div>
              </section>
            ))}
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14, marginTop: 14 }}>
            {[3, 3].map((r, i) => (
              <section key={i} style={{ background: T.raised, border: `1px solid ${T.borderSubtle}`, borderRadius: T.rXl, overflow: "hidden" }}>
                <div style={{ padding: "12px 16px", borderBottom: `1px solid ${T.borderSubtle}` }}><PanelBodySkel rows={1} /></div>
                <div style={{ padding: 16 }}><PanelBodySkel rows={r} /></div>
              </section>
            ))}
          </div>
        </div>
      </div>
    );
  }

  const bannerBorder = snap.tone === "warning" ? T.warning : snap.tone === "success" ? T.success : T.brand;
  const bannerBg = snap.tone === "warning" ? T.warningSoft : snap.tone === "success" ? (T.successSoft || T.brandSoft) : T.brandSoft;
  const bannerIconColor = snap.tone === "warning" ? T.warning : snap.tone === "success" ? T.success : T.brand;

  return (
    <div style={{ flex: 1, overflow: "auto", backgroundImage: `radial-gradient(circle, ${T.borderSubtle} 1px, transparent 1px)`, backgroundSize: "22px 22px" }}>
      <div style={{ maxWidth: 1060, margin: "0 auto", padding: "22px 24px 38px" }}>

        {/* ── Plain-language status sentence + next checkpoint/action (derived, never stored filler) ── */}
        <section style={{ display: "flex", alignItems: "center", gap: 14, marginBottom: 14, padding: "13px 15px", borderRadius: T.rXl, border: `1px solid ${bannerBorder}44`, background: bannerBg + "88", boxShadow: T.shadowXs }}>
          <span style={{ width: 30, height: 30, flexShrink: 0, borderRadius: "50%", background: T.raised, border: `1px solid ${bannerBorder}44`, display: "grid", placeItems: "center" }}>
            {snap.tone === "brand" ? <Sparkle size={13} color={T.brand} /> : <Icon name={snap.icon} size={13} color={bannerIconColor} />}
          </span>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ font: `700 14px/1.25 ${T.display}`, color: T.fg }}>{snap.title}</div>
            <div style={{ font: `400 12px/1.45 ${T.sans}`, color: T.secondary, marginTop: 3 }}>{snap.detail}</div>
          </div>
          {snap.cta && (
            <Btn variant={snap.cta.primary ? "primary" : "secondary"} size="sm" onClick={snap.cta.onClick}>
              {snap.cta.label} <Icon name="arrowRight" size={13} color={snap.cta.primary ? "#fff" : T.secondary} />
            </Btn>
          )}
        </section>

        {ovErr && (
          <div style={{ marginBottom: 14, padding: "11px 14px", borderRadius: T.rLg, border: `1px solid ${T.danger}44`, background: T.raised, font: `500 12px/1.4 ${T.sans}`, color: T.danger }}>
            Couldn't load the project overview (build status and brief details are unavailable right now).
          </div>
        )}

        {/* ── Product brief preview + Build status ── */}
        <div style={{ display: "grid", gridTemplateColumns: "minmax(0, 1.55fr) minmax(260px, .75fr)", gap: 14 }}>
          <Panel title="Product brief" accent
            action={<button onClick={() => openBrief && openBrief()} disabled={!openBrief} style={{ border: 0, background: "none", color: openBrief ? T.brandDeep : T.tertiary, cursor: openBrief ? "pointer" : "default", font: `600 11.5px/1 ${T.sans}` }}>Open brief →</button>}>
            <CategoryLabel>What you asked the factory to build</CategoryLabel>
            <div style={{ marginTop: 8, font: `400 14px/1.6 ${T.sans}`, color: T.fg }}>
              {(brief.goal || brief.description)
                ? <Markdown>{brief.goal || brief.description}</Markdown>
                : <span style={{ color: T.tertiary }}>No goal captured yet — it's set with the Concierge during onboarding.</span>}
            </div>
            {briefUrl ? (
              <button onClick={() => openBrief && openBrief()} className="sf-artchip" style={{ width: "100%", marginTop: 14, display: "flex", alignItems: "center", gap: 11, textAlign: "left", padding: "11px 12px", borderRadius: T.rLg, border: `1px solid ${T.brand}33`, background: T.brandSoft + "55", cursor: "pointer" }}>
                <span style={{ width: 34, height: 38, flexShrink: 0, display: "grid", placeItems: "center", borderRadius: 7, background: T.raised, color: T.brandDeep, font: `700 9px/1 ${T.mono}` }}>BRIEF</span>
                <span style={{ flex: 1, minWidth: 0 }}>
                  <b style={{ display: "block", font: `600 13px/1.2 ${T.sans}`, color: T.fg }}>{brief.name || "Product brief"}</b>
                  <span style={{ display: "block", marginTop: 3, font: `400 11px/1.3 ${T.sans}`, color: T.tertiary }}>Canonical Product Brief · created with the Concierge · newest version</span>
                </span>
                <Icon name="arrowRight" size={14} color={T.brandDeep} />
              </button>
            ) : briefErr ? (
              <div style={{ marginTop: 14, font: `400 12px/1.45 ${T.sans}`, color: T.danger }}>Couldn't load the product brief right now.</div>
            ) : (
              <div style={{ marginTop: 14, font: `400 12px/1.45 ${T.sans}`, color: T.tertiary }}>The Concierge hasn't finalized a Product Brief for this project yet — it's written during the onboarding conversation.</div>
            )}
          </Panel>

          <Panel title="Build status">
            {isDraft ? (
              <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                <span style={{ font: `700 26px/1 ${T.display}`, letterSpacing: "-0.01em", color: T.tertiary }}>Not started</span>
                <p style={{ margin: 0, font: `400 12px/1.5 ${T.sans}`, color: T.secondary }}>The factory hasn't run yet. Finish setup and hand off — the plan, tickets, agents, and spend appear once the build starts.</p>
                <div style={{ display: "flex", flexDirection: "column", gap: 9, padding: "11px 0", borderTop: `1px solid ${T.borderSubtle}`, borderBottom: `1px solid ${T.borderSubtle}` }}>
                  {([
                    ["Project brief", !!(brief.goal || brief.description)],
                    ["Scope of work", !!(brief.scope && brief.scope.length)],
                    [`Build engine · ${brief.runtime === "opencode" ? "OpenCode" : brief.runtime === "codex" ? "Codex" : "Claude"}`, true],
                    ["Materials (optional)", (docs?.uploaded?.length || 0) > 0],
                  ] as [string, boolean][]).map(([k, ok]) => (
                    <div key={k} style={{ display: "flex", alignItems: "center", gap: 9 }}>
                      <span style={{ width: 16, height: 16, borderRadius: "50%", flexShrink: 0, display: "grid", placeItems: "center", background: ok ? T.success : "transparent", border: `1.5px solid ${ok ? T.success : T.borderDefault}` }}>{ok && <Icon name="check" size={10} color="#fff" />}</span>
                      <span style={{ font: `500 12.5px/1.2 ${T.sans}`, color: ok ? T.fg : T.secondary }}>{k}</span>
                    </div>
                  ))}
                </div>
                {onResume && <Btn variant="primary" size="sm" full onClick={onResume}>Complete setup &amp; start building <Icon name="arrowRight" size={13} color="#fff" /></Btn>}
              </div>
            ) : (
              <div style={{ display: "flex", flexDirection: "column", gap: 11 }}>
                <div style={{ display: "flex", alignItems: "baseline", gap: 8 }}>
                  <span style={{ font: `700 30px/1 ${T.display}`, color: build.done ? T.success : T.brandDeep }}>{pct}%</span>
                  <span style={{ font: `500 11px/1 ${T.mono}`, color: T.tertiary }}>{build.done ? "deployed" : "complete"}</span>
                </div>
                <span style={{ display: "block", height: 7, borderRadius: 4, background: T.sunken, overflow: "hidden" }}><span style={{ display: "block", height: "100%", width: pct + "%", background: build.done ? T.success : T.brand }} /></span>
                <div style={{ display: "flex", flexDirection: "column", gap: 8, marginTop: 2 }}>
                  {([
                    ["Current phase", phaseLabel(phase, stage)],
                    ["Tickets", build.tickets_total != null ? `${build.tickets_done ?? 0} / ${build.tickets_total}` : "—"],
                    ["Agents working", build.agents_working != null ? String(build.agents_working) : "—"],
                  ] as [string, string][]).map(([k, v]) => (
                    <div key={k} style={{ display: "flex", justifyContent: "space-between" }}><span style={{ font: `400 12px/1 ${T.sans}`, color: T.secondary }}>{k}</span><b style={{ font: `600 11.5px/1 ${T.mono}`, color: T.fg }}>{v}</b></div>
                  ))}
                  {/* Spend — `$spent / $cap`; the pencil edits the cap in place (PUT /budget). */}
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                    <span style={{ font: `400 12px/1 ${T.sans}`, color: T.secondary }}>Spend</span>
                    {capEditing ? (
                      <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
                        <span style={{ font: `500 11.5px/1 ${T.mono}`, color: T.secondary }}>{money(build.spent_usd)} / $</span>
                        <input value={capInput} onChange={(e) => setCapInput(e.target.value)} autoFocus
                          onKeyDown={(e) => { if (e.key === "Enter") saveCap(); if (e.key === "Escape") { setCapEditing(false); setCapError(""); } }}
                          style={{ width: 58, font: `500 12px/1 ${T.mono}`, color: T.fg, background: T.bg, border: `1px solid ${T.borderDefault}`, borderRadius: 4, padding: "2px 5px", outline: "none" }} />
                        <button onClick={saveCap} style={{ background: "none", border: "none", cursor: "pointer", color: T.success, font: `600 11px/1 ${T.sans}`, padding: "0 2px" }}>Save</button>
                        <button onClick={() => { setCapEditing(false); setCapError(""); }} style={{ background: "none", border: "none", cursor: "pointer", color: T.tertiary, font: `500 11px/1 ${T.sans}`, padding: "0 2px" }}>Cancel</button>
                      </div>
                    ) : (
                      <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                        <b style={{ font: `600 11.5px/1 ${T.mono}`, color: T.fg }}>{money(build.spent_usd)} / {build.budget_ceiling ? money(build.budget_ceiling) : "—"}</b>
                        <button onClick={() => { setCapInput(build.budget_ceiling ? String(build.budget_ceiling) : ""); setCapError(""); setCapEditing(true); }} title="Edit budget cap" style={{ background: "none", border: "none", cursor: "pointer", color: T.tertiary, padding: 0, lineHeight: 1, display: "inline-flex" }}>
                          <Icon name="pencil" size={11} color={T.tertiary} />
                        </button>
                      </div>
                    )}
                  </div>
                  {capError && <span style={{ font: `500 11px/1.3 ${T.sans}`, color: T.danger, textAlign: "right" }}>{capError}</span>}
                </div>
                <Btn variant="primary" size="sm" full onClick={onOpenFactory}>Open factory console <Icon name="arrowRight" size={13} color="#fff" /></Btn>
              </div>
            )}
          </Panel>
        </div>

        {/* ── Project knowledge: brief section preview + newest factory outputs ── */}
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14, marginTop: 14 }}>
          <Panel title="Inside the brief"
            action={headings.length ? <button onClick={() => openBrief && openBrief()} style={{ border: 0, background: "none", color: T.brandDeep, cursor: "pointer", font: `600 11.5px/1 ${T.sans}` }}>Read the brief →</button> : undefined}>
            {headings.length ? (
              headings.map((h, i) => (
                <LinkRow key={h + i} badge={String(i + 1).padStart(2, "0")} badgeTone="brand" title={h}
                  sub="From the current Product Brief" first={i === 0} onClick={openBrief || undefined} />
              ))
            ) : briefErr ? (
              <Note icon="file" title="Couldn't load the brief" detail="The product brief projection is unavailable right now — try reloading." />
            ) : (
              <Note icon="file" title="No brief sections yet" detail="The Concierge writes the Product Brief during onboarding; its sections appear here once it's finalized." />
            )}
          </Panel>

          <Panel title="Factory outputs" count={produced.length || undefined}
            action={produced.length ? <button onClick={() => openOutputs && openOutputs()} style={{ border: 0, background: "none", color: T.brandDeep, cursor: "pointer", font: `600 11.5px/1 ${T.sans}` }}>View outputs →</button> : undefined}>
            {newest.length ? (
              newest.map((d, i) => (
                <LinkRow key={d.title + i} badge={(d.kind || "doc").slice(0, 4).toUpperCase()} badgeTone={isPrd(d) ? "brand" : "neutral"}
                  title={d.title} sub={d.agent ? `Produced by ${d.agent}` : "Factory artifact"} first={i === 0}
                  onClick={d.id ? () => openArtifact(d.id!) : d.path ? () => window.open(`/api/projects/${projectId}/artifact?path=${encodeURIComponent(d.path!)}&raw=1`, "_blank") : (openOutputs || undefined)} />
              ))
            ) : docsErr ? (
              <Note icon="layers" title="Couldn't load factory outputs" detail="The documents projection is unavailable right now — try reloading." />
            ) : (
              <Note icon="layers" title="No outputs yet" detail="Research reports, the product plan (PRD), architecture, and designs appear here as the factory completes each stage." />
            )}
          </Panel>
        </div>

        {onDiscard && isDraft && (
          <div style={{ marginTop: 14, textAlign: "center" }}>
            <button onClick={onDiscard} style={{ background: "none", border: "none", cursor: "pointer", font: `500 12px/1 ${T.sans}`, color: T.danger, padding: "4px 0" }}>Discard draft</button>
          </div>
        )}
      </div>
    </div>
  );
}
