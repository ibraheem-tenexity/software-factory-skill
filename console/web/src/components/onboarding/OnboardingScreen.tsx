// OnboardingScreen.tsx — Single-Page Intake + Docked Concierge (design optionC.jsx), on the
// DRAFT MODEL (docs/plans/concierge-onboarding-api.md):
//   - EAGER DRAFT on mount (POST /api/drafts) — the form + the Concierge rail share ONE draft id.
//   - DEBOUNCED write-through (PATCH /api/projects/{id}/draft {name,goal,scope}) — never per-keystroke,
//     and the response NEVER overwrites local input state (that would re-introduce focus loss).
//   - Server composes `description` from goal+scope (composeDescription DELETED from the FE).
//   - Materials attach via POST /api/projects/{id}/attach (real file → base64).
//   - Handoff = POST /api/projects/{id}/promote → into the build console.
//   - Concierge rail Composer → POST /api/chat with the shared draft project_id.
//
// FOCUS-LOSS FIX (Bug B): every field/section component is defined at MODULE scope (a component
// defined inside render gets a new identity each keystroke → React remounts the <input> → focus
// lost). Keep it that way — do NOT move Card/CheckRow/GroupHead back inside the component.
import React, { useCallback, useEffect, useRef, useState } from "react";
import { api, Org, OrgInput } from "../../api";
import {
  T, Icon, Sparkle, Wordmark, Avatar, StatusPill, CategoryLabel, Btn, TextInput, TextArea,
  Field, Chips, IndustryTile, IntegrationRow, Dropzone, Message, Composer,
  INDUSTRIES, SIZES, REVENUE, ROLES, INTEGRATIONS,
} from "./design";

type Check = { id: string; label: string; done: boolean; optional?: boolean; nudge?: string };
type ChatMsg = { role: string; content: string };

const SCOPE = ["Quoting / RFQ", "Order entry", "Pricing & approvals", "Inventory", "AP / AR", "Customer comms"];

// id↔label helpers (orgs store labels; the fresh form picks tile/integration ids).
const industryLabel = (idOrLabel: string) => INDUSTRIES.find((i) => i.id === idOrLabel)?.label || idOrLabel;
const integrationLabel = (id: string) => INTEGRATIONS.find((i) => i.id === id)?.label || id;

// ── Module-scope presentational components (HOISTED — props only, no state closure). Defining
//    these inside the screen's render is what caused the one-keystroke focus loss. ──
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

function Card({ cat, title, desc, children, accent }:
  { cat: string; title: string; desc?: string; children: React.ReactNode; accent?: boolean }) {
  return (
    <section style={{ background: T.raised, border: `1px solid ${accent ? T.brand + "55" : T.borderSubtle}`, borderRadius: T.rXl, padding: "22px 24px", boxShadow: T.shadowXs }}>
      <CategoryLabel style={{ marginBottom: 7 }} tone={accent ? "brand" : "tertiary"}>{cat}</CategoryLabel>
      <h3 style={{ font: `700 19px/1.25 ${T.display}`, letterSpacing: "-0.015em", color: T.fg, margin: 0 }}>{title}</h3>
      {desc && <p style={{ font: `400 13px/1.5 ${T.sans}`, color: T.secondary, margin: "6px 0 0" }}>{desc}</p>}
      <div style={{ marginTop: 18 }}>{children}</div>
    </section>
  );
}

const fileToB64 = (file: File): Promise<string> => new Promise((resolve) => {
  const r = new FileReader();
  r.onload = () => resolve(String(r.result || "").split(",")[1] || "");
  r.onerror = () => resolve("");
  r.readAsDataURL(file);
});
function fmtBytes(n: number): string {
  if (!n) return "";
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${Math.round(n / 1024)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}

export function OnboardingScreen({ onComplete }: { onComplete: (projectId: string) => void }) {
  const [mode, setMode] = useState<"loading" | "fresh" | "returning">("loading");
  const [onFile, setOnFile] = useState<Org | null>(null);
  const [editOrg, setEditOrg] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  // the one eager draft the form + rail share
  const [draftId, setDraftId] = useState<string | null>(null);

  // returning Manage-editor draft (seeded from the org on file)
  const [org, setOrg] = useState<{ name: string; size: string; revenue: string; ints: string[] }>({ name: "", size: "", revenue: "", ints: [] });

  // fresh-user company setup
  const [f, setF] = useState<{ industry: string; sub: string[]; name: string; size: string; revenue: string; role: string; site: string; ints: string[] }>(
    { industry: "", sub: [], name: "", size: "", revenue: "", role: "", site: "", ints: [] });
  const setFresh = (k: string, v: any) => setF((x) => ({ ...x, [k]: v }));

  // project answers (shared)
  const [p, setP] = useState<{ name: string; goal: string; scope: string[]; video: boolean; docs: boolean }>(
    { name: "", goal: "", scope: [], video: false, docs: false });
  // Real uploaded filenames per material slot (drives the Dropzone list — no dummy data).
  const [mats, setMats] = useState<{ video: { name: string; size?: string }[]; docs: { name: string; size?: string }[] }>({ video: [], docs: [] });
  const setProj = (k: string, v: any) => setP((x) => ({ ...x, [k]: v }));

  // concierge rail chat (shares draftId)
  const [composer, setComposer] = useState("");
  const [msgs, setMsgs] = useState<ChatMsg[]>([]);
  const [chatBusy, setChatBusy] = useState(false);
  const [chatErr, setChatErr] = useState("");

  const videoInputRef = useRef<HTMLInputElement | null>(null);
  const docsInputRef = useRef<HTMLInputElement | null>(null);
  const orgSavedRef = useRef(false);   // fresh: org POSTed once, then PATCH
  const orgBusyRef = useRef(false);

  // mount: resolve org path + mint the eager draft
  useEffect(() => {
    api.getOrg().then(({ org: o }) => {
      setOnFile(o);
      setMode(o ? "returning" : "fresh");
      if (o) setOrg({ name: o.name, size: o.headcount || "", revenue: o.revenue || "", ints: o.connected_systems || [] });
    }).catch(() => setMode("fresh"));
    api.createDraft().then(({ project_id }) => setDraftId(project_id)).catch(() => {});
  }, []);

  // DEBOUNCED project write-through. Fire-and-forget — the response is intentionally ignored so it
  // can never overwrite what the user is typing (the focus-loss trap).
  useEffect(() => {
    if (!draftId) return;
    if (!p.name && !p.goal && !p.scope.length) return;
    const t = setTimeout(() => {
      api.patchDraft(draftId, { name: p.name, goal: p.goal, scope: p.scope }).catch(() => {});
    }, 700);
    return () => clearTimeout(t);
  }, [draftId, p.name, p.goal, p.scope]);

  // fresh company write-through: POST once (create + link), PATCH thereafter. Guarded against dup.
  const saveCompanyFresh = useCallback(async () => {
    if (orgBusyRef.current || !f.name.trim()) return;
    orgBusyRef.current = true;
    const body = {
      name: f.name, industry: industryLabel(f.industry), sub_focus: f.sub, headcount: f.size,
      revenue: f.revenue, website: f.site || undefined, connected_systems: f.ints,
      designation: f.role || undefined, role_description: f.role || undefined,
    };
    try {
      if (!orgSavedRef.current) { await api.createOrg(body as OrgInput); orgSavedRef.current = true; }
      else { await api.patchOrg(body); }
    } catch { /* transient — retried on next debounce / flushed at handoff */ }
    orgBusyRef.current = false;
  }, [f]);

  useEffect(() => {
    if (mode !== "fresh" || !f.name.trim()) return;
    const t = setTimeout(() => { saveCompanyFresh(); }, 800);
    return () => clearTimeout(t);
  }, [mode, f, saveCompanyFresh]);

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
      const { org: updated } = await api.patchOrg({ name: org.name, headcount: org.size, revenue: org.revenue, connected_systems: org.ints });
      setOnFile(updated);
      setEditOrg(false);
    } catch (e: any) { setError(String(e?.message || e)); }
  };

  const attachFiles = async (list: FileList | null, kind: "video" | "docs") => {
    if (!draftId || !list || !list.length) return;
    const picked = Array.from(list);
    try {
      const files = await Promise.all(picked.map(async (file) => ({ name: file.name, content_b64: await fileToB64(file) })));
      await api.attach(draftId, files);
      setProj(kind, true);
      // record the REAL filenames so the Dropzone lists what was actually uploaded (video = replace)
      const added = picked.map((f) => ({ name: f.name, size: fmtBytes(f.size) }));
      setMats((m) => ({ ...m, [kind]: kind === "video" ? added.slice(-1) : [...m[kind], ...added] }));
    } catch (e: any) { setError(`Couldn’t attach files: ${String(e?.message || e)}`); }
  };

  const handoff = async () => {
    if (!ready || submitting || !draftId) return;
    setSubmitting(true);
    setError("");
    try {
      if (fresh) await saveCompanyFresh();                                    // flush company
      await api.patchDraft(draftId, { name: p.name, goal: p.goal, scope: p.scope }).catch(() => {}); // flush project
      const { project_id } = await api.promote(draftId, { target: "railway" });
      onComplete(project_id);
    } catch (e: any) {
      const msg = String(e?.message || e);
      setError(msg.includes("409")
        ? "That project name is already taken, or this draft was already handed off — try a different name."
        : `Couldn’t hand off: ${msg}`);
      setSubmitting(false);
    }
  };

  const sendChat = async () => {
    const text = composer.trim();
    if (!text || !draftId || chatBusy) return;
    setMsgs((m) => [...m, { role: "user", content: text }]);
    setComposer(""); setChatBusy(true); setChatErr("");
    try {
      const r = await api.chat({ message: text, project_id: draftId });
      const replies = (r.messages || []).filter((x: any) => x && x.role !== "user").map((x: any) => ({ role: x.role || "assistant", content: x.content || "" }));
      setMsgs((m) => [...m, ...replies]);
      // bridge: reflect any company values the concierge wrote (project name/goal/scope have no GET yet)
      api.getOrg().then(({ org: o }) => { if (o) setOnFile(o); }).catch(() => {});
    } catch (e: any) {
      const msg = String(e?.message || e);
      setChatErr(msg.includes("503") ? "Concierge chat needs a model key (available on the deployed app)." : "Message failed — try again.");
    }
    setChatBusy(false);
  };

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

      {/* hidden inputs powering the material Dropzones (real attach) */}
      <input ref={videoInputRef} type="file" accept="video/*" style={{ display: "none" }} onChange={(e) => { attachFiles(e.target.files, "video"); e.target.value = ""; }} />
      <input ref={docsInputRef} type="file" multiple accept=".pdf,.doc,.docx,.xls,.xlsx,.csv,.txt,.md,image/*" style={{ display: "none" }} onChange={(e) => { attachFiles(e.target.files, "docs"); e.target.value = ""; }} />

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
                      <Field label="Walkthrough video" optional><Dropzone kind="video" files={mats.video} onToggle={() => videoInputRef.current?.click()} /></Field>
                      <Field label="Supporting documents" optional><Dropzone kind="docs" compact files={mats.docs} onToggle={() => docsInputRef.current?.click()} /></Field>
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
                        ] as [string, string][]).map(([k, val]) => (
                          <div key={k} style={{ background: T.raised, padding: "11px 20px" }}>
                            <CategoryLabel style={{ display: "block", marginBottom: 4 }}>{k}</CategoryLabel>
                            <span style={{ font: `500 13px/1.35 ${T.sans}`, color: T.fg }}>{val}</span>
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
                      <Field label="Project walkthrough video" optional><Dropzone kind="video" files={mats.video} onToggle={() => videoInputRef.current?.click()} /></Field>
                      <Field label="Extra documents" optional><Dropzone kind="docs" compact files={mats.docs} onToggle={() => docsInputRef.current?.click()} /></Field>
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
                  ? error
                  : fresh
                    ? <>Set up once, reused forever — <b style={{ color: T.fg }}>{[companyChecks[0], companyChecks[1], ...projChecks].filter((c) => c.done).length}/5</b> essentials done</>
                    : <>Company context reused — <b style={{ color: T.fg }}>{projChecks.filter((c) => c.done).length}/{projChecks.length}</b> project questions answered</>}
              </span>
            </div>
            <Btn variant="primary" onClick={handoff} disabled={!ready || submitting || !draftId} title={ready ? "Hand off to the build factory" : (fresh ? "Set up your company & project to continue" : "Answer the project questions to continue")} style={ready ? { background: T.success } : undefined}>{submitting ? "Handing off…" : "Hand off to factory"} <Icon name="arrowRight" size={14} color="#fff" /></Btn>
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

            {/* live concierge exchange (shares the draft id) */}
            {msgs.map((m, i) => <Message key={i} who={m.role === "user" ? "user" : "agent"} text={m.content} />)}
            {chatBusy && <span style={{ font: `400 11.5px/1 ${T.sans}`, color: T.tertiary }}>Concierge is thinking…</span>}
            {chatErr && <span style={{ font: `500 11.5px/1.4 ${T.sans}`, color: T.tertiary }}>{chatErr}</span>}

            <div style={{ padding: 12, borderRadius: T.rLg, border: `1px solid ${T.brand}33`, background: T.brandSoft + "66" }}>
              <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 6 }}><Icon name="arrowRight" size={12} color={T.brandDeep} /><CategoryLabel tone="brand">After handoff</CategoryLabel></div>
              <p style={{ font: `400 12px/1.5 ${T.sans}`, color: T.secondary, margin: 0 }}>I stay on. I'll relay what the build agents are doing — and you steer them by talking to me.</p>
            </div>
          </div>

          <div style={{ flexShrink: 0, padding: "12px 16px", borderTop: `1px solid ${T.borderSubtle}` }}>
            <Composer placeholder="Tell the Concierge…" value={composer} onChange={setComposer} onSend={sendChat} />
          </div>
        </div>
      </div>
    </div>
  );
}
