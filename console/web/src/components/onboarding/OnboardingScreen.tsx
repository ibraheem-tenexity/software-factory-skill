// OnboardingScreen.tsx — Single-Page Intake + Docked Concierge. 1:1 port of the design's
// optionC.jsx, with the source's PREVIEW affordances replaced by live data:
//   - the First-time/Returning Segmented toggle is DROPPED; the path is derived from GET /api/org
//     (no org → 'fresh'; org on file → 'returning').
//   - onFile / org are live (GET /api/org); the returning ON-FILE card + Manage editor read/write
//     GET/PATCH /api/org; the first-time handoff POSTs /api/org then creates the project + brief.
//   - the design's mock <BuildProgress> is NOT ported — "Hand off to factory" creates the run
//     (POST /api/runs with the goal+scope as the brief) and hands off to the existing build console.
//   - walkthrough video + supporting docs are model-only (the Dropzone toggles a flag; no upload
//     pipeline in v1).
import React, { useEffect, useState } from "react";
import { api, Org, OrgInput } from "../../api";
import {
  T, Icon, Sparkle, Wordmark, Avatar, StatusPill, CategoryLabel, Btn, TextInput, TextArea,
  Field, Chips, IndustryTile, IntegrationRow, Dropzone, Message,
  INDUSTRIES, SIZES, REVENUE, ROLES, INTEGRATIONS,
} from "./design";
// Note: the design's docked Composer is intentionally not used here — the onboarding rail is
// relay/observe only; the live Concierge lives in the build console after handoff.

type Check = { id: string; label: string; done: boolean; optional?: boolean; nudge?: string };

function CheckRow({ c }: { c: Check }) {
  return (
    <div style={{ display: "flex", alignItems: "flex-start", gap: 9, padding: "8px 12px", borderBottom: `1px solid ${T.borderSubtle}` }}>
      <span style={{ marginTop: 1, width: 15, height: 15, flexShrink: 0, borderRadius: "50%", display: "grid", placeItems: "center", background: c.done ? T.success : "transparent", border: c.done ? "none" : `1.5px solid ${T.borderDefault}` }}>{c.done && <Icon name="check" size={10} color="#fff" />}</span>
      <div style={{ flex: 1 }}>
        <span style={{ display: "block", font: `500 12.5px/1.3 ${T.sans}`, color: c.done ? T.fg : T.secondary }}>{c.label}{c.optional && <span style={{ color: T.tertiary, fontWeight: 400 }}> · optional</span>}</span>
        {!c.done && c.nudge && <span style={{ display: "block", marginTop: 2, font: `400 11.5px/1.4 ${T.sans}`, color: T.tertiary }}>{c.nudge}</span>}
      </div>
    </div>
  );
}

function GroupHead({ children, tone }: { children: React.ReactNode; tone?: "success" }) {
  return <div style={{ padding: "8px 12px", borderBottom: `1px solid ${T.borderSubtle}`, background: tone === "success" ? T.successSoft : T.sunken, display: "flex", alignItems: "center", gap: 6 }}>
    {tone === "success" && <Icon name="check" size={12} color={T.success} />}<CategoryLabel style={tone === "success" ? { color: T.success } : undefined}>{children}</CategoryLabel></div>;
}

const SCOPE = ["Quoting / RFQ", "Order entry", "Pricing & approvals", "Inventory", "AP / AR", "Customer comms"];

// Resolve an industry tile id → its display label (orgs store the label, the fresh form picks an id).
const industryLabel = (idOrLabel: string) =>
  INDUSTRIES.find((i) => i.id === idOrLabel)?.label || idOrLabel;
// Integration id → label, for the returning ON-FILE summary.
const integrationLabel = (id: string) => INTEGRATIONS.find((i) => i.id === id)?.label || id;

// The build of the brief that goes to the factory: goal prose + the selected scope.
function composeDescription(goal: string, scope: string[]): string {
  const scopeLine = scope.length ? `\n\nScope of work: ${scope.join(", ")}.` : "";
  return `${goal.trim()}${scopeLine}`;
}

export function OnboardingScreen({ onComplete }: { onComplete: (runId: string) => void }) {
  // Path is DATA-driven: null while loading, then 'fresh' (no org) | 'returning' (org on file).
  const [mode, setMode] = useState<"loading" | "fresh" | "returning">("loading");
  const [onFile, setOnFile] = useState<Org | null>(null);
  const [editOrg, setEditOrg] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  // returning Manage-editor draft (seeded from the org on file)
  const [org, setOrg] = useState<{ name: string; size: string; revenue: string; ints: string[] }>(
    { name: "", size: "", revenue: "", ints: [] });

  // fresh-user company setup (empty — nothing on file yet)
  const [f, setF] = useState<{ industry: string; sub: string[]; name: string; size: string; revenue: string; role: string; site: string; ints: string[] }>(
    { industry: "", sub: [], name: "", size: "", revenue: "", role: "", site: "", ints: [] });
  const setFresh = (k: string, v: any) => setF((x) => ({ ...x, [k]: v }));

  // project answers (shared)
  const [p, setP] = useState<{ name: string; goal: string; scope: string[]; video: boolean; docs: boolean }>(
    { name: "", goal: "", scope: [], video: false, docs: false });
  const setProj = (k: string, v: any) => setP((x) => ({ ...x, [k]: v }));

  useEffect(() => {
    api.getOrg().then(({ org: o }) => {
      setOnFile(o);
      setMode(o ? "returning" : "fresh");
      if (o) setOrg({ name: o.name, size: o.headcount || "", revenue: o.revenue || "", ints: o.connected_systems || [] });
    }).catch(() => setMode("fresh"));
  }, []);

  const fresh = mode === "fresh";

  const projChecks: Check[] = [
    { id: "name", label: "Project name", done: !!p.name },
    { id: "goal", label: "What you’re building", done: p.goal.length > 20 },
    { id: "scope", label: "Scope of work", done: p.scope.length > 0 },
  ];
  const companyChecks: Check[] = [
    { id: "industry", label: "Industry", done: !!f.industry },
    { id: "profile", label: "Company profile", done: !!f.name && !!f.size },
    { id: "systems", label: "Connect a system", done: f.ints.length > 0, optional: true, nudge: "Optional — lets the factory pull real SKUs & pricing." },
  ];
  const projReady = projChecks.every((c) => c.done);
  const ready = fresh ? !!(f.industry && f.name && f.size && projReady) : projReady;

  const saveManage = async () => {
    try {
      const { org: updated } = await api.patchOrg({
        name: org.name, headcount: org.size, revenue: org.revenue, connected_systems: org.ints,
      });
      setOnFile(updated);
      setEditOrg(false);
    } catch (e: any) {
      setError(String(e?.message || e));
    }
  };

  const handoff = async () => {
    if (!ready || submitting) return;
    setSubmitting(true);
    setError("");
    try {
      // First-time: create the org + link the user, then create the project. Returning: org already on file.
      if (fresh) {
        const body: OrgInput = {
          name: f.name, industry: industryLabel(f.industry), sub_focus: f.sub,
          headcount: f.size, revenue: f.revenue, location: undefined, website: f.site || undefined,
          connected_systems: f.ints, role_description: f.role || undefined,
          designation: f.role || undefined,
        };
        await api.createOrg(body);
      }
      const { run_id } = await api.createRun({
        project_name: p.name, description: composeDescription(p.goal, p.scope),
      });
      onComplete(run_id);
    } catch (e: any) {
      setError(String(e?.message || e));
      setSubmitting(false);
    }
  };

  const Card = ({ cat, title, desc, children, accent }:
    { cat: string; title: string; desc?: string; children: React.ReactNode; accent?: boolean }) => (
    <section style={{ background: T.raised, border: `1px solid ${accent ? T.brand + "55" : T.borderSubtle}`, borderRadius: T.rXl, padding: "22px 24px", boxShadow: T.shadowXs }}>
      <CategoryLabel style={{ marginBottom: 7 }} tone={accent ? "brand" : "tertiary"}>{cat}</CategoryLabel>
      <h3 style={{ font: `700 19px/1.25 ${T.display}`, letterSpacing: "-0.015em", color: T.fg, margin: 0 }}>{title}</h3>
      {desc && <p style={{ font: `400 13px/1.5 ${T.sans}`, color: T.secondary, margin: "6px 0 0" }}>{desc}</p>}
      <div style={{ marginTop: 18 }}>{children}</div>
    </section>
  );

  if (mode === "loading") {
    return <div style={{ height: "100%", display: "grid", placeItems: "center", background: T.bg }}>
      <span style={{ display: "inline-flex", alignItems: "center", gap: 8, font: `500 13px/1 ${T.sans}`, color: T.tertiary }}>
        <Sparkle size={13} color={T.brand} /> Loading your workspace…</span>
    </div>;
  }

  const company = onFile?.name || "";
  const scaleText = [onFile?.headcount && `${onFile.headcount} people`, onFile?.revenue].filter(Boolean).join(" · ");

  return (
    <div style={{ height: "100%", display: "flex", flexDirection: "column", background: T.bg, fontFamily: T.sans }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "14px 24px", background: T.raised, borderBottom: `1px solid ${T.borderSubtle}`, flexShrink: 0 }}>
        <Wordmark />
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          {!fresh && company && <div style={{ display: "flex", alignItems: "center", gap: 8 }}><Avatar name={company} size={24} tone="neutral" /><span style={{ font: `500 12.5px/1.2 ${T.sans}`, color: T.secondary }}>{company}</span></div>}
        </div>
      </div>

      <div style={{ flex: 1, display: "flex", minHeight: 0 }}>
        {/* scrolling intake column */}
        <div style={{ flex: 1, minWidth: 0, display: "flex", flexDirection: "column" }}>
          <div style={{ flex: 1, overflow: "auto", padding: "26px 32px" }}>
            <div style={{ maxWidth: 720, margin: "0 auto", display: "flex", flexDirection: "column", gap: 16 }}>

              {fresh ? (
                <>
                  <div>
                    <CategoryLabel style={{ marginBottom: 9 }} tone="brand">Welcome to the Software Factory</CategoryLabel>
                    <h1 style={{ font: `700 30px/1.15 ${T.display}`, letterSpacing: "-0.02em", color: T.fg, margin: 0 }}>Let’s set up your company, then your first project</h1>
                    <p style={{ font: `400 14px/1.5 ${T.sans}`, color: T.secondary, margin: "8px 0 0", maxWidth: 560 }}>
                      We’ll remember all of this — next time you start a project we won’t ask again. The Concierge on the right will guide you.
                    </p>
                  </div>

                  <Card cat="Your company" title="What kind of operation is this?" desc="Tuned for industrial & IT distribution.">
                    <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 9 }}>
                      {INDUSTRIES.map((it) => <IndustryTile key={it.id} item={it} compact selected={f.industry === it.id} onClick={() => setFresh("industry", it.id)} />)}
                    </div>
                    <div style={{ marginTop: 16 }}><Field label="Sub-focus" optional><Chips multi options={["MRO / maintenance", "OEM supply", "Project / spec", "E-commerce", "Field service"]} value={f.sub} onChange={(v) => setFresh("sub", v)} /></Field></div>
                  </Card>

                  <Card cat="Your company" title="Company profile">
                    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
                      <Field label="Company name" style={{ gridColumn: "1 / -1" }}><TextInput value={f.name} onChange={(v) => setFresh("name", v)} placeholder="e.g. Acme Industrial Supply" /></Field>
                      <Field label="Headcount"><Chips options={SIZES} value={f.size} onChange={(v) => setFresh("size", v)} /></Field>
                      <Field label="Annual revenue"><Chips options={REVENUE} value={f.revenue} onChange={(v) => setFresh("revenue", v)} /></Field>
                      <Field label="Your role"><Chips options={ROLES} value={f.role} onChange={(v) => setFresh("role", v)} /></Field>
                      <Field label="Website" optional><TextInput value={f.site} onChange={(v) => setFresh("site", v)} placeholder="acme-industrial.com" /></Field>
                    </div>
                  </Card>

                  <Card cat="Your company" title="Connect your systems" desc="Link a system to pull in real SKUs, customers, and pricing. You’ll only do this once.">
                    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
                      {INTEGRATIONS.map((it) => <IntegrationRow key={it.id} item={it} connected={f.ints.includes(it.id)}
                        onToggle={() => setFresh("ints", f.ints.includes(it.id) ? f.ints.filter((x) => x !== it.id) : [...f.ints, it.id])} />)}
                    </div>
                  </Card>

                  <Card cat="Your first project" title="Project basics" accent>
                    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
                      <Field label="Project name"><TextInput value={p.name} onChange={(v) => setProj("name", v)} placeholder="e.g. Quote-to-Epicor automation" /></Field>
                      <Field label="What are you building?" hint="One or two sentences on the outcome you want.">
                        <TextArea rows={3} value={p.goal} onChange={(v) => setProj("goal", v)} placeholder="e.g. Replace the manual quoting spreadsheet and write won quotes back to Epicor…" />
                      </Field>
                    </div>
                  </Card>
                  <Card cat="Your first project" title="Scope of work" desc="Which parts of the business does this project touch?">
                    <Chips multi options={SCOPE} value={p.scope} onChange={(v) => setProj("scope", v)} />
                  </Card>
                  <Card cat="Your first project" title="Project materials" desc="A walkthrough recording is the highest-signal input you can give.">
                    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
                      <Field label="Walkthrough video" optional><Dropzone kind="video" filled={p.video} onToggle={() => setProj("video", !p.video)} /></Field>
                      <Field label="Supporting documents" optional><Dropzone kind="docs" compact filled={p.docs} onToggle={() => setProj("docs", !p.docs)} /></Field>
                    </div>
                  </Card>
                </>
              ) : (
                <>
                  <div>
                    <CategoryLabel style={{ marginBottom: 9 }}>New project</CategoryLabel>
                    <h1 style={{ font: `700 30px/1.15 ${T.display}`, letterSpacing: "-0.02em", color: T.fg, margin: 0 }}>What are we building this time?</h1>
                    <p style={{ font: `400 14px/1.5 ${T.sans}`, color: T.secondary, margin: "8px 0 0", maxWidth: 560 }}>
                      Your company context is already on file — no need to repeat it. Just tell the Concierge about this project.
                    </p>
                  </div>

                  <section style={{ borderRadius: T.rXl, border: `1px solid ${T.borderSubtle}`, background: T.sunken, overflow: "hidden" }}>
                    <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "14px 20px" }}>
                      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                        <Icon name="check" size={15} color={T.success} />
                        <span style={{ font: `600 13.5px/1.2 ${T.sans}`, color: T.fg }}>From {company} · on file</span>
                        <span style={{ font: `400 12px/1.2 ${T.sans}`, color: T.tertiary }}>· reused automatically</span>
                      </div>
                      <button onClick={() => setEditOrg((v) => !v)} style={{ font: `500 12.5px/1 ${T.sans}`, color: T.brandDeep, background: "none", border: "none", cursor: "pointer", display: "inline-flex", alignItems: "center", gap: 4 }}>
                        {editOrg ? "Done" : "Manage"} <Icon name={editOrg ? "chevronDown" : "chevronRight"} size={13} color={T.brandDeep} />
                      </button>
                    </div>
                    {!editOrg ? (
                      <div style={{ display: "grid", gridTemplateColumns: "repeat(2, 1fr)", gap: "1px", background: T.borderSubtle, borderTop: `1px solid ${T.borderSubtle}` }}>
                        {([
                          ["Company", company],
                          ["Industry", industryLabel(onFile?.industry || "") || "—"],
                          ["Scale", scaleText || "—"],
                          ["Connected systems", (onFile?.connected_systems || []).map(integrationLabel).join(", ") || "—"],
                          ["Sub-focus", (onFile?.sub_focus || []).join(", ") || "—"],
                          ["Website", onFile?.website || "—"],
                        ] as [string, string][]).map(([k, v]) => (
                          <div key={k} style={{ background: T.raised, padding: "11px 20px" }}>
                            <CategoryLabel style={{ display: "block", marginBottom: 4 }}>{k}</CategoryLabel>
                            <span style={{ font: `500 13px/1.35 ${T.sans}`, color: T.fg }}>{v}</span>
                          </div>
                        ))}
                      </div>
                    ) : (
                      <div style={{ background: T.raised, borderTop: `1px solid ${T.borderSubtle}`, padding: "18px 20px", display: "flex", flexDirection: "column", gap: 16 }}>
                        <Field label="Company name"><TextInput value={org.name} onChange={(v) => setOrg({ ...org, name: v })} /></Field>
                        <Field label="Headcount"><Chips options={SIZES} value={org.size} onChange={(v) => setOrg({ ...org, size: v })} /></Field>
                        <Field label="Annual revenue"><Chips options={REVENUE} value={org.revenue} onChange={(v) => setOrg({ ...org, revenue: v })} /></Field>
                        <Field label="Connected systems" hint="Linked once, reused across every project.">
                          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
                            {INTEGRATIONS.map((it) => <IntegrationRow key={it.id} item={it} connected={org.ints.includes(it.id)}
                              onToggle={() => setOrg({ ...org, ints: org.ints.includes(it.id) ? org.ints.filter((x) => x !== it.id) : [...org.ints, it.id] })} />)}
                          </div>
                        </Field>
                        <Btn variant="primary" size="sm" onClick={saveManage} style={{ alignSelf: "flex-start" }}>Save changes</Btn>
                      </div>
                    )}
                  </section>

                  <Card cat="This project" title="Project basics" accent>
                    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
                      <Field label="Project name"><TextInput value={p.name} onChange={(v) => setProj("name", v)} placeholder="e.g. Quote-to-Epicor automation" /></Field>
                      <Field label="What are you building?" hint="One or two sentences on the outcome you want.">
                        <TextArea rows={3} value={p.goal} onChange={(v) => setProj("goal", v)} placeholder="e.g. Replace the manual quoting spreadsheet…" />
                      </Field>
                    </div>
                  </Card>
                  <Card cat="This project" title="Scope of work" desc="Which parts of the business does this project touch?">
                    <Chips multi options={SCOPE} value={p.scope} onChange={(v) => setProj("scope", v)} />
                  </Card>
                  <Card cat="This project" title="Project materials" desc="We already have your line card & pricing on file — only add what's specific to this project.">
                    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
                      <Field label="Project walkthrough video" optional><Dropzone kind="video" filled={p.video} onToggle={() => setProj("video", !p.video)} /></Field>
                      <Field label="Extra documents" optional><Dropzone kind="docs" compact filled={p.docs} onToggle={() => setProj("docs", !p.docs)} /></Field>
                    </div>
                  </Card>
                </>
              )}
            </div>
          </div>

          <div style={{ flexShrink: 0, display: "flex", alignItems: "center", justifyContent: "space-between", padding: "13px 32px", borderTop: `1px solid ${T.borderSubtle}`, background: T.raised }}>
            <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
              <Icon name="check" size={14} color={T.success} />
              <span style={{ font: `400 12.5px/1.3 ${T.sans}`, color: error ? T.danger : T.secondary }}>
                {error
                  ? `Couldn’t hand off: ${error}`
                  : fresh
                    ? <>Set up once, reused forever — <b style={{ color: T.fg }}>{[companyChecks[0], companyChecks[1], ...projChecks].filter((c) => c.done).length}/5</b> essentials done</>
                    : <>Company context reused — <b style={{ color: T.fg }}>{projChecks.filter((c) => c.done).length}/{projChecks.length}</b> project questions answered</>}
              </span>
            </div>
            <Btn variant="primary" onClick={handoff} disabled={!ready || submitting} title={ready ? "Hand off to the build factory" : (fresh ? "Set up your company & project to continue" : "Answer the project questions to continue")} style={ready ? { background: T.success } : undefined}>{submitting ? "Handing off…" : "Hand off to factory"} <Icon name="arrowRight" size={14} color="#fff" /></Btn>
          </div>
        </div>

        {/* docked Concierge rail */}
        <div style={{ width: 320, flexShrink: 0, borderLeft: `1px solid ${T.borderSubtle}`, background: T.raised, display: "flex", flexDirection: "column", minHeight: 0 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 9, padding: "16px 18px", borderBottom: `1px solid ${T.borderSubtle}` }}>
            <span style={{ width: 30, height: 30, borderRadius: "50%", display: "grid", placeItems: "center", background: T.brandSoft, color: T.brand, boxShadow: `inset 0 0 0 1px ${T.brand}33` }}><Sparkle size={14} color={T.brand} /></span>
            <div style={{ flex: 1 }}><span style={{ display: "block", font: `600 13px/1.2 ${T.sans}`, color: T.fg }}>Concierge</span><CategoryLabel style={{ fontSize: 10 }}>{fresh ? "Setting you up" : "With you through launch"}</CategoryLabel></div>
            <StatusPill tone="success">online</StatusPill>
          </div>

          <div style={{ flex: 1, overflow: "auto", padding: "16px 18px", display: "flex", flexDirection: "column", gap: 12 }}>
            <Message who="agent" text={fresh
              ? "Welcome! I’m your Concierge. First a quick company profile — I’ll remember it so you never re-enter it — then tell me about your first project."
              : `Welcome back. I already have ${company || "your company"}'s profile and connected systems from earlier projects — I'm reusing all of it. Let's just scope this project.`} />

            <div style={{ border: `1px solid ${T.borderSubtle}`, borderRadius: T.rLg, overflow: "hidden" }}>
              {fresh ? (
                <>
                  <GroupHead>Your company</GroupHead>
                  {companyChecks.map((c) => <CheckRow key={c.id} c={c} />)}
                  <GroupHead>Your first project</GroupHead>
                  {projChecks.map((c) => <CheckRow key={c.id} c={c} />)}
                </>
              ) : (
                <>
                  <GroupHead tone="success">On file · reused</GroupHead>
                  {["Company profile", "Industry & scale", ...(onFile?.connected_systems || []).map((s) => `${integrationLabel(s)} connection`)].map((l) => (
                    <div key={l} style={{ display: "flex", alignItems: "center", gap: 9, padding: "8px 12px", borderBottom: `1px solid ${T.borderSubtle}` }}>
                      <Icon name="check" size={13} color={T.success} /><span style={{ font: `500 12.5px/1.3 ${T.sans}`, color: T.fg }}>{l}</span>
                    </div>
                  ))}
                  <GroupHead>This project · to do</GroupHead>
                  {projChecks.map((c) => <CheckRow key={c.id} c={c} />)}
                </>
              )}
            </div>

            <Message who="agent" anim text={ready
              ? "That’s everything I need. I’ve drafted the architecture and a design step for your screens — hand off whenever you’re ready."
              : fresh
                ? (f.industry ? "Great. Now the company basics — name and size — then we’ll scope your first project." : "Start by picking the kind of operation you run.")
                : (p.scope.length ? "Good. For the parts you picked, is the bottleneck more about speed, errors into your system, or manager visibility?" : "To start: what should this project actually do for the team?")} />

            <div style={{ padding: 12, borderRadius: T.rLg, border: `1px solid ${T.brand}33`, background: T.brandSoft + "66" }}>
              <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 6 }}><Icon name="arrowRight" size={12} color={T.brandDeep} /><CategoryLabel tone="brand">After handoff</CategoryLabel></div>
              <p style={{ font: `400 12px/1.5 ${T.sans}`, color: T.secondary, margin: 0 }}>I stay on. I'll relay what the build agents are doing — and you steer them by talking to me.</p>
            </div>
          </div>

          <div style={{ flexShrink: 0, padding: "12px 16px", borderTop: `1px solid ${T.borderSubtle}` }}>
            {/* Composer is relay/observe only here — the live Concierge lives in the build console. */}
            <Btn full variant="secondary" onClick={() => undefined} title="The Concierge is available in the build console" style={{ justifyContent: "flex-start", color: T.tertiary }}>
              <Icon name="bot" size={14} color={T.tertiary} /> Hand off to talk to the Concierge
            </Btn>
          </div>
        </div>
      </div>
    </div>
  );
}
