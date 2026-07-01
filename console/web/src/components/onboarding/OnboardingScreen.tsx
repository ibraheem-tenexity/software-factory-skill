// OnboardingScreen.tsx — Single-Page Intake + Docked Concierge (design optionC.jsx), on the
// DRAFT MODEL (docs/plans/concierge-onboarding-api.md):
//   - DEFERRED DRAFT: POST /api/drafts on first name keystroke OR first Concierge message — the form
//     + the Concierge rail share ONE draft id.
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
  T, Icon, Sparkle, Wordmark, Avatar, StatusPill, CategoryLabel, SectionDivider, Btn, TextInput, TextArea,
  Field, Chip, Chips, IndustryTile, IntegrationRow, Dropzone, Message, Composer, Segmented,
  OrgImportPicker, ChoiceList, INDUSTRIES, SIZES, REVENUE, ROLES, INTEGRATIONS,
} from "./design";

type Check = { id: string; label: string; done: boolean; optional?: boolean; nudge?: string };
type ChatMsg = { role: string; content: string; choices?: string[] };

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

// One cell of the returning "on file" org grid: label + value, or an inline input in Manage mode.
// MODULE-SCOPE (never define inside render — that remounts the <input> on each keystroke → focus loss).
function OrgCell({ label, value, editing, onChange }: { label: string; value: string; editing: boolean; onChange: (v: string) => void }) {
  return (
    <div style={{ background: T.raised, padding: "11px 20px" }}>
      <CategoryLabel style={{ display: "block", marginBottom: editing ? 6 : 4 }}>{label}</CategoryLabel>
      {editing ? (
        <input value={value} onChange={(e) => onChange(e.target.value)} placeholder="—"
          style={{ width: "100%", boxSizing: "border-box", height: 30, padding: "0 9px", borderRadius: T.rSm, border: `1px solid ${T.borderDefault}`, background: T.bg, color: T.fg, font: `500 13px/1 ${T.sans}`, outline: "none" }} />
      ) : (
        <span style={{ font: `500 13px/1.35 ${T.sans}`, color: value ? T.fg : T.tertiary }}>{value || "—"}</span>
      )}
    </div>
  );
}

// Scope-of-work multi-select with a "+ Add" affordance for a custom scope / software type.
function ScopeOfWork({ options, value, onChange, onAddOption }:
  { options: string[]; value: string[]; onChange: (v: string[]) => void; onAddOption: (o: string) => void }) {
  const [adding, setAdding] = useState(false);
  const [text, setText] = useState("");
  const inputRef = useRef<HTMLInputElement | null>(null);
  useEffect(() => { if (adding && inputRef.current) inputRef.current.focus(); }, [adding]);
  const sel = value || [];
  const toggle = (o: string) => onChange(sel.includes(o) ? sel.filter((x) => x !== o) : [...sel, o]);
  const commit = () => {
    const t = text.trim();
    if (t) { onAddOption(t); if (!sel.includes(t)) onChange([...sel, t]); }
    setText(""); setAdding(false);
  };
  return (
    <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
      {options.map((o) => <Chip key={o} selected={sel.includes(o)} onClick={() => toggle(o)}>{o}</Chip>)}
      {adding ? (
        <span style={{ display: "inline-flex", alignItems: "center", gap: 4, padding: "3px 4px 3px 11px", borderRadius: 9999, border: `1px solid ${T.brand}`, background: T.brandSoft }}>
          <input ref={inputRef} value={text} onChange={(e) => setText(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); commit(); } else if (e.key === "Escape") { setText(""); setAdding(false); } }}
            onBlur={commit} placeholder="Custom scope or software…"
            style={{ width: 168, border: "none", outline: "none", background: "transparent", font: `500 13px/1 ${T.sans}`, color: T.brandDeep }} />
          <button onMouseDown={(e) => e.preventDefault()} onClick={commit} title="Add" style={{ width: 24, height: 24, flexShrink: 0, display: "grid", placeItems: "center", borderRadius: "50%", border: "none", background: T.brand, color: "#fff", cursor: "pointer" }}><Icon name="check" size={12} color="#fff" /></button>
        </span>
      ) : (
        <button onClick={() => setAdding(true)} style={{ display: "inline-flex", alignItems: "center", gap: 5, font: `500 13px/1 ${T.sans}`, padding: "8px 13px", borderRadius: 9999, cursor: "pointer", border: `1px dashed ${T.borderDefault}`, background: T.raised, color: T.secondary }}>
          <Icon name="plus" size={13} color={T.tertiary} /> Add
        </button>
      )}
    </div>
  );
}

// ── Build engine picker (the "Build engine" card). MODULE-SCOPE — never define inside render
//    (that remounts inputs on each keystroke → focus loss). provider=claude|opencode;
//    model=kimi|glm; keySource=tenexity|byok. Backend persists `runtime` + maps `model` to the
//    full id (kimi→moonshot, glm→z-ai/glm-5.2). BYOK key POSTs to /creds (Vault-stored) and the
//    runtime-specific runner key (ANTHROPIC_API_KEY / OPENROUTER_API_KEY) wins over the platform key. ──
export type EngineValue = { provider: "claude" | "opencode"; model: "kimi" | "glm"; keySource: "tenexity" | "byok"; key: string };

const ENGINES = [
  { id: "claude", name: "Claude", tag: "Default", desc: "Anthropic Claude — the factory's native build agent." },
  { id: "opencode", name: "OpenCode", tag: "", desc: "Open-source agent runtime — pick the model below." },
] as const;
const OC_MODELS = [
  { id: "kimi", name: "Kimi K2.7", vendor: "Moonshot AI" },
  { id: "glm", name: "GLM 5.2", vendor: "Zhipu AI" },
] as const;

// One selectable engine radio-card. Selected = brand border + soft fill; "Default"/"SOON" tag inline.
function EngineCardBtn({ item, selected, onClick, disabled }:
  { item: { id: string; name: string; tag: string; desc: string }; selected: boolean; onClick: () => void; disabled?: boolean }) {
  return (
    <button onClick={disabled ? undefined : onClick} disabled={disabled}
      style={{ textAlign: "left", cursor: disabled ? "not-allowed" : "pointer", flex: 1, background: selected ? T.brandSoft : T.raised,
        border: `1px solid ${selected ? T.brand : T.borderDefault}`, borderRadius: T.rLg, padding: "12px 14px",
        opacity: disabled ? 0.6 : 1, display: "flex", flexDirection: "column", gap: 3 }}>
      <span style={{ display: "flex", alignItems: "center", gap: 6 }}>
        <span style={{ font: `600 14px/1.2 ${T.sans}`, color: selected ? T.brandDeep : T.fg }}>{item.name}</span>
        {item.tag && <span style={{ font: `700 8px/1 ${T.mono}`, color: T.brandDeep, background: T.brandSoft, padding: "2px 5px", borderRadius: 3 }}>{item.tag.toUpperCase()}</span>}
      </span>
      <span style={{ font: `400 12px/1.4 ${T.sans}`, color: T.secondary }}>{item.desc}</span>
    </button>
  );
}

function EnginePicker({ value, onChange }:
  { value: EngineValue; onChange: (v: EngineValue) => void }) {
  const set = (patch: Partial<EngineValue>) => onChange({ ...value, ...patch });
  // Switching provider away from opencode resets model to the default (kimi); switching to opencode
  // keeps whatever model was set (default kimi). key is cleared whenever BYOK is left.
  const chooseProvider = (p: "claude" | "opencode") => set({ provider: p, key: p === "claude" ? "" : value.key });
  const chooseKeySource = (k: string) => set({ keySource: k as "tenexity" | "byok", key: k === "tenexity" ? "" : value.key });
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      <div style={{ display: "flex", gap: 10 }}>
        {ENGINES.map((it) => (
          <EngineCardBtn key={it.id} item={it} selected={value.provider === it.id} onClick={() => chooseProvider(it.id as "claude" | "opencode")} />
        ))}
      </div>

      {value.provider === "opencode" && (
        <Field label="OpenCode model">
          <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
            {OC_MODELS.map((m) => {
              const on = value.model === m.id;
              return (
                <button key={m.id} onClick={() => set({ model: m.id as "kimi" | "glm" })}
                  style={{ font: `500 13px/1 ${T.sans}`, padding: "8px 13px", borderRadius: 9999, cursor: "pointer",
                    border: `1px solid ${on ? T.brand : T.borderSubtle}`, background: on ? T.brandSoft : T.sunken,
                    color: on ? T.brandDeep : T.secondary,
                    display: "inline-flex", alignItems: "center", gap: 5 }}>
                  {m.name} <span style={{ font: `400 11px/1 ${T.sans}`, color: T.tertiary }}>· {m.vendor}</span>
                </button>
              );
            })}
          </div>
        </Field>
      )}

      <Field label="API key">
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          <Segmented value={value.keySource} onChange={chooseKeySource}
            options={[{ id: "tenexity", label: "Use Tenexity's key" }, { id: "byok", label: "Bring your own key" }]} />
          {value.keySource === "tenexity"
            ? <div style={{ display: "flex", alignItems: "center", gap: 6, padding: "9px 11px", background: T.brandSoft + "66", border: `1px solid ${T.brand}33`, borderRadius: T.rMd }}>
              <Sparkle size={12} color={T.brandDeep} />
              <span style={{ font: `400 12px/1.4 ${T.sans}`, color: T.secondary }}>
                {value.provider === "claude" ? "Claude" : "OpenCode"} runs on Tenexity's key — billed through your plan + rolled into the project budget.
              </span>
            </div>
            : <TextInput type="password" value={value.key} onChange={(v) => set({ key: v })}
                placeholder={value.provider === "claude" ? "sk-ant-…" : "paste provider API key"} />}
        </div>
      </Field>
    </div>
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

const BUDGET_PRESETS = [30, 60, 120, 250];

function BudgetPicker({ value, onChange }: { value: number | null; onChange: (v: number | null) => void }) {
  const [custom, setCustom] = React.useState(false);
  const [customVal, setCustomVal] = React.useState("");
  const isPreset = value != null && BUDGET_PRESETS.includes(value);
  const isCustom = custom || (value != null && !BUDGET_PRESETS.includes(value));
  const selectPreset = (n: number) => { setCustom(false); setCustomVal(""); onChange(n); };
  const openCustom = () => { setCustom(true); setCustomVal(value != null && !BUDGET_PRESETS.includes(value) ? String(value) : ""); if (!isCustom) onChange(null); };
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
        {BUDGET_PRESETS.map((n) => {
          const on = isPreset && value === n && !isCustom;
          return (
            <button key={n} onClick={() => selectPreset(n)}
              style={{ padding: "7px 14px", borderRadius: 9999, border: `1.5px solid ${on ? T.brand : T.borderDefault}`, background: on ? T.brandSoft : T.raised, color: on ? T.brandDeep : T.fg, font: `${on ? 600 : 500} 13px/1 ${T.sans}`, cursor: "pointer" }}>
              ${n}
            </button>
          );
        })}
        <button onClick={openCustom}
          style={{ padding: "7px 14px", borderRadius: 9999, border: `1.5px solid ${isCustom ? T.brand : T.borderDefault}`, background: isCustom ? T.brandSoft : T.raised, color: isCustom ? T.brandDeep : T.fg, font: `${isCustom ? 600 : 500} 13px/1 ${T.sans}`, cursor: "pointer" }}>
          Custom
        </button>
      </div>
      {isCustom && (
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <span style={{ font: `500 14px/1 ${T.mono}`, color: T.secondary }}>$</span>
          <input value={customVal} onChange={(e) => { setCustomVal(e.target.value); const n = parseFloat(e.target.value); onChange(!isNaN(n) && n > 0 ? n : null); }}
            placeholder="e.g. 200" type="number" min={1}
            style={{ width: 120, font: `500 13px/1 ${T.mono}`, color: T.fg, background: T.bg, border: `1.5px solid ${T.borderDefault}`, borderRadius: T.rMd, padding: "8px 10px", outline: "none" }} autoFocus />
        </div>
      )}
      <p style={{ margin: 0, font: `400 11.5px/1.4 ${T.sans}`, color: T.tertiary }}>
        {value != null ? `Factory stops and notifies you when spend reaches $${value}.` : "No cap - the factory runs to completion (billed at actual cost)."}
      </p>
    </div>
  );
}

export function OnboardingScreen({ onComplete, onBack, resumeProjectId }: { onComplete: (projectId: string) => void; onBack?: () => void; resumeProjectId?: string | null }) {
  const [mode, setMode] = useState<"loading" | "fresh" | "returning">("loading");
  const [onFile, setOnFile] = useState<Org | null>(null);
  const [editOrg, setEditOrg] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  // the one draft the form + rail share — created explicitly when the user saves Project basics
  const [draftId, setDraftId] = useState<string | null>(null);
  const [savingBasics, setSavingBasics] = useState(false);

  // returning "on file" org card — inline-edit (Manage) state, seeded from onFile when editing starts.
  const [orgEdit, setOrgEdit] = useState<{ company: string; industry: string; scale: string; systems: string; subFocus: string; website: string }>(
    { company: "", industry: "", scale: "", systems: "", subFocus: "", website: "" });
  // Scope-of-work options; grows when the user adds a custom scope/software via "+ Add".
  const [scopeOptions, setScopeOptions] = useState<string[]>(SCOPE);

  // fresh-user company setup
  const [f, setF] = useState<{ industry: string; sub: string[]; name: string; size: string; revenue: string; role: string; site: string; ints: string[] }>(
    { industry: "", sub: [], name: "", size: "", revenue: "", role: "", site: "", ints: [] });
  const setFresh = (k: string, v: any) => setF((x) => ({ ...x, [k]: v }));

  // project answers (shared)
  const [p, setP] = useState<{ name: string; goal: string; scope: string[]; video: boolean; docs: boolean }>(
    { name: "", goal: "", scope: [], video: false, docs: false });
  // Build engine (Claude | OpenCode+Kimi/GLM). Default = Claude on Tenexity's key. BYOK is live:
  // a user-entered key POSTs to /creds (Vault-stored); promote threads it into the runner env, BYOK
  // wins over the platform key. The key NAME is runtime-specific (ANTHROPIC_API_KEY / OPENROUTER_API_KEY).
  const [engine, setEngine] = useState<EngineValue>({ provider: "claude", model: "kimi", keySource: "tenexity", key: "" });
  const [budget, setBudget] = useState<number | null>(null);
  const budgetRef = useRef<number | null>(null);
  useEffect(() => { budgetRef.current = budget; }, [budget]);
  // Real uploaded filenames per material slot (drives the Dropzone list — no dummy data).
  const [mats, setMats] = useState<{ video: { name: string; size?: string; uploading?: boolean }[]; docs: { name: string; size?: string; uploading?: boolean }[] }>({ video: [], docs: [] });
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
  const draftCreatingRef = useRef(false);  // guard against concurrent createDraft calls
  const engineProviderRef = useRef(engine.provider);
  useEffect(() => { engineProviderRef.current = engine.provider; }, [engine.provider]);

  // mount: resolve org path. RESUME adopts existing pid and rehydrates — NO new POST /api/drafts.
  // Fresh start defers POST /api/drafts until the user types a project name (see below).
  useEffect(() => {
    api.getOrg().then(({ org: o }) => {
      setOnFile(o);
      setMode(o ? "returning" : "fresh");
    }).catch(() => setMode("fresh"));
    if (resumeProjectId) {
      setDraftId(resumeProjectId);
      api.getDraft(resumeProjectId).then((d) => {
        setP((x) => ({ ...x, name: d.name || "", goal: d.goal || d.description || "", scope: d.scope || [] }));
        if (d.scope) setScopeOptions((opts) => Array.from(new Set([...opts, ...d.scope])));
      }).catch(() => {});
      api.documents(resumeProjectId).then((docs) => {
        const ups = docs.uploaded || [];
        const vids = ups.filter((m) => m.kind === "video").map((m) => ({ name: m.name, size: fmtBytes(m.size_bytes || 0) }));
        const others = ups.filter((m) => m.kind !== "video").map((m) => ({ name: m.name, size: fmtBytes(m.size_bytes || 0) }));
        setMats({ video: vids, docs: others });
        setP((x) => ({ ...x, video: vids.length > 0, docs: others.length > 0 }));
      }).catch(() => {});
    }
  }, [resumeProjectId]);

  // Draft creation is explicit: the user fills Project basics and clicks Save (see saveBasics).
  // Until then draftId is null and the downstream cards stay locked. Navigating away without
  // saving creates zero orphan rows.

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

  // DEBOUNCED build-engine write-through: runtime (claude|opencode) + model (kimi|glm) persist on
  // the draft (DraftCreateIn/DraftPatchIn). keySource/key are passthrough (ignored by Pydantic) —
  // the real BYOK path is submitCreds below. Without this the eager create's runtime (default
  // claude) is the value used at promote, silently dropping an OpenCode selection.
  useEffect(() => {
    if (!draftId) return;
    const t = setTimeout(() => {
      api.patchDraft(draftId, { runtime: engine.provider, model: engine.model, keySource: engine.keySource, key: engine.key }).catch(() => {});
    }, 500);
    return () => clearTimeout(t);
  }, [draftId, engine.provider, engine.model, engine.keySource, engine.key]);

  // Budget write-through: persist the selected ceiling on the draft whenever it changes.
  useEffect(() => {
    if (!draftId || budget == null) return;
    api.patchDraft(draftId, { budget }).catch(() => {});
  }, [draftId, budget]);

  // BYOK key submission: when the user brings their own key, POST it to /creds (Vault-stored; promote
  // threads creds_vault_ids into the runner env, BYOK wins over the platform key). The key NAME is
  // runtime-specific (ANTHROPIC_API_KEY for claude, OPENROUTER_API_KEY for opencode) — the runner-key
  // _launch_stage resolves. Debounced so a paste + edit doesn't fire per keystroke; the response is
  // ignored (never surfaces the key back). Only fires when keySource is byok AND a non-empty key exists.
  const byokBusyRef = useRef(false);
  useEffect(() => {
    if (!draftId || engine.keySource !== "byok" || !engine.key.trim()) return;
    const keyName = engine.provider === "claude" ? "ANTHROPIC_API_KEY" : "OPENROUTER_API_KEY";
    const t = setTimeout(() => {
      if (byokBusyRef.current) return;
      byokBusyRef.current = true;
      api.submitCreds(draftId, { [keyName]: engine.key.trim() })
        .catch(() => {/* transient — retried on next change / flushed at handoff */})
        .finally(() => { byokBusyRef.current = false; });
    }, 600);
    return () => clearTimeout(t);
  }, [draftId, engine.keySource, engine.provider, engine.key]);

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

  // Returning org card: "Manage" seeds the inline editor from onFile; "Done" commits via PATCH /api/org
  // (the same org-patch the OrgAdmin screen uses) and refreshes the on-file card.
  const startManage = () => {
    setOrgEdit({
      company: onFile?.name || "",
      industry: industryLabel(onFile?.industry || ""),
      scale: onFile?.headcount || "",
      systems: (onFile?.connected_systems || []).map(integrationLabel).join(", "),
      subFocus: (onFile?.sub_focus || []).join(", "),
      website: onFile?.website || "",
    });
    setEditOrg(true);
  };
  const doneManage = async () => {
    setEditOrg(false);
    const list = (s: string) => s.split(",").map((x) => x.trim()).filter(Boolean);
    // map connected-system LABELS back to their ids where known (custom values pass through)
    const sysIds = list(orgEdit.systems).map((x) => INTEGRATIONS.find((i) => i.label === x)?.id || x);
    try {
      const { org: updated } = await api.patchOrg({
        name: orgEdit.company, industry: orgEdit.industry, headcount: orgEdit.scale,
        connected_systems: sysIds, sub_focus: list(orgEdit.subFocus), website: orgEdit.website || undefined,
      });
      setOnFile(updated);
    } catch (e: any) { setError(String(e?.message || e)); }
  };
  const addScopeOption = (o: string) => setScopeOptions((s) => (s.includes(o) ? s : [...s, o]));

  // Save Project basics → mint the draft (POST /api/drafts) and unlock the rest of the form.
  const saveBasics = async () => {
    if (!p.name.trim() || draftId || draftCreatingRef.current) return;
    draftCreatingRef.current = true;
    setSavingBasics(true);
    setError("");
    try {
      const { project_id } = await api.createDraft({ runtime: engineProviderRef.current, project_name: p.name, budget: budgetRef.current ?? undefined });
      setDraftId(project_id);
    } catch (e: any) {
      draftCreatingRef.current = false;
      setError(`Couldn’t save project: ${String(e?.message || e)}`);
    } finally {
      setSavingBasics(false);
    }
  };

  const attachFiles = async (list: FileList | null, kind: "video" | "docs") => {
    if (!draftId || !list || !list.length) return;
    const picked = Array.from(list);
    // Show uploading tokens immediately so the user sees in-flight feedback.
    const optimistic = picked.map((f) => ({ name: f.name, size: fmtBytes(f.size), uploading: true }));
    setMats((m) => ({ ...m, [kind]: kind === "video" ? optimistic.slice(-1) : [...m[kind], ...optimistic] }));
    const inFlight = new Set(picked.map((f) => f.name));
    try {
      const files = await Promise.all(picked.map(async (file) => ({ name: file.name, content_b64: await fileToB64(file) })));
      await api.attach(draftId, files);
      setProj(kind, true);
      // Replace only this batch’s uploading tokens with confirmed entries.
      const added = picked.map((f) => ({ name: f.name, size: fmtBytes(f.size) }));
      setMats((m) => ({ ...m, [kind]: kind === "video" ? added.slice(-1) : [...m[kind].filter((f) => !(f.uploading && inFlight.has(f.name))), ...added] }));
    } catch (e: any) {
      // Remove only this batch’s optimistic tokens on failure.
      setMats((m) => ({ ...m, [kind]: m[kind].filter((f) => !(f.uploading && inFlight.has(f.name))) }));
      setError(`Couldn’t attach files: ${String(e?.message || e)}`);
    }
  };

  const handoff = async () => {
    if (!ready || submitting || !draftId) return;
    setSubmitting(true);
    setError("");
    try {
      if (fresh) await saveCompanyFresh();                                    // flush company
      await api.patchDraft(draftId, { name: p.name, goal: p.goal, scope: p.scope }).catch(() => {}); // flush project
      await api.patchDraft(draftId, { runtime: engine.provider, model: engine.model, keySource: engine.keySource, key: engine.key }).catch(() => {}); // flush engine
      if (budget != null) await api.patchDraft(draftId, { budget }).catch(() => {});  // flush budget cap
      if (engine.keySource === "byok" && engine.key.trim()) {                 // flush BYOK key → Vault
        const keyName = engine.provider === "claude" ? "ANTHROPIC_API_KEY" : "OPENROUTER_API_KEY";
        await api.submitCreds(draftId, { [keyName]: engine.key.trim() }).catch(() => {});
      }
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

  // One Concierge conversation turn (shared by the Composer and the ChoiceList). Ensures a draft
  // exists, posts the message, appends the agent's reply — plain text or up to 4 choices.
  const sendTurn = async (raw: string) => {
    const text = raw.trim();
    if (!text || chatBusy) return;
    // Create the draft on first message if the user hasn't named the project yet — the concierge
    // can gather that itself, so the form doesn't need to come first.
    let pid = draftId;
    if (!pid) {
      try {
        // Chat-first (no project named yet): mint the draft with a placeholder name the user/agent
        // refines later — create_draft requires a non-empty name.
        const { project_id } = await api.createDraft({ runtime: engineProviderRef.current, project_name: p.name.trim() || "Untitled project" });
        setDraftId(project_id);
        pid = project_id;
      } catch {
        setChatErr("Couldn't start a session — try again.");
        return;
      }
    }
    setMsgs((m) => [...m, { role: "user", content: text }]);
    setComposer(""); setChatBusy(true); setChatErr("");
    try {
      const r = await api.converse(pid, text);
      setMsgs((m) => [...m, { role: "agent", content: r.message, choices: r.choices }]);
    } catch {
      setChatErr("Message failed — try again.");
    }
    setChatBusy(false);
  };
  const sendChat = () => sendTurn(composer);

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
        <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
          {onBack && <Btn variant="ghost" size="sm" onClick={onBack}><Icon name="arrowLeft" size={14} /> Projects</Btn>}
          <Wordmark />
        </div>
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

                  <SectionDivider label="Your organization" sub="set up once · reused on every project" icon="building" />

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

                  <SectionDivider label="This project" sub="specific to what you’re building now" icon="layers" />

                  <Card cat="Your first project" title="Project basics" accent>
                    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
                      <Field label="Project name"><TextInput value={p.name} onChange={(v) => setProj("name", v)} placeholder="e.g. Quote-to-Epicor automation" /></Field>
                      <Field label="What are you building?" hint="One or two sentences on the outcome you want.">
                        <TextArea rows={3} value={p.goal} onChange={(v) => setProj("goal", v)} placeholder="e.g. Replace the manual quoting spreadsheet and write won quotes back to Epicor…" />
                      </Field>
                      <Field label="Budget cap" optional hint="Stop and notify when spend reaches this amount. Leave unset to run to completion.">
                        <BudgetPicker value={budget} onChange={setBudget} />
                      </Field>
                    </div>
                    {/* Create-the-project gate (PRD §2.4/§24): a real POST /api/drafts in `draft` state. */}
                    <div style={{ marginTop: 18, paddingTop: 16, borderTop: `1px solid ${T.borderSubtle}` }}>
                      {draftId ? (
                        <div style={{ display: "flex", alignItems: "center", gap: 9 }}>
                          <span style={{ width: 22, height: 22, borderRadius: "50%", background: T.successSoft, display: "grid", placeItems: "center", flexShrink: 0 }}><Icon name="check" size={13} color={T.success} /></span>
                          <span style={{ font: `400 12.5px/1.45 ${T.sans}`, color: T.secondary }}><b style={{ color: T.success }}>Project created</b> — “{p.name || "Untitled project"}” is saved. Enrich it below to move it toward build.</span>
                        </div>
                      ) : (
                        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 14, flexWrap: "wrap" }}>
                          <span style={{ font: `400 12.5px/1.45 ${T.sans}`, color: T.tertiary, maxWidth: 380 }}>Name the project and save to create it. The rest — scope, engine &amp; materials — unlocks once it exists.</span>
                          <Btn variant="primary" onClick={saveBasics} disabled={!p.name.trim() || savingBasics} title={p.name.trim() ? "Create this project" : "Enter a project name first"}>
                            {savingBasics ? "Creating…" : <><Icon name="check" size={14} color="#fff" /> Create project</>}
                          </Btn>
                        </div>
                      )}
                    </div>
                  </Card>
                  {/* Scope / Build engine / Materials stay locked until the project is created. */}
                  <div style={{ position: "relative" }}>
                    <div aria-hidden={!draftId} style={draftId
                      ? { display: "flex", flexDirection: "column", gap: 16 }
                      : { display: "flex", flexDirection: "column", gap: 16, opacity: 0.4, filter: "grayscale(0.5)", pointerEvents: "none", userSelect: "none" }}>
                  <Card cat="Your first project" title="Scope of work" desc="Which parts of the business does this project touch?">
                    <ScopeOfWork options={scopeOptions} value={p.scope} onChange={(v) => setProj("scope", v)} onAddOption={addScopeOption} />
                  </Card>
                  <Card cat="Your first project" title="Build engine" desc="Choose the coding agent that builds this project. The factory, console, and output look the same either way.">
                    <EnginePicker value={engine} onChange={setEngine} />
                  </Card>
                  <Card cat="Your first project" title="Project materials" desc="A walkthrough recording is the highest-signal input you can give.">
                    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
                      <OrgImportPicker />
                      <Field label="Walkthrough video" optional><Dropzone kind="video" files={mats.video} onToggle={() => videoInputRef.current?.click()} /></Field>
                      <Field label="Supporting documents" optional><Dropzone kind="docs" compact files={mats.docs} onToggle={() => docsInputRef.current?.click()} /></Field>
                    </div>
                  </Card>
                    </div>
                    {!draftId && (
                      <div style={{ position: "absolute", inset: 0, display: "flex", alignItems: "flex-start", justifyContent: "center", paddingTop: 30 }}>
                        <div style={{ display: "inline-flex", alignItems: "center", gap: 9, padding: "11px 17px", borderRadius: 9999, background: T.raised, border: `1px solid ${T.borderDefault}`, boxShadow: T.shadowSm, font: `500 12.5px/1 ${T.sans}`, color: T.secondary }}>
                          <Icon name="lock" size={14} color={T.tertiary} /> Create the project above to unlock
                        </div>
                      </div>
                    )}
                  </div>
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

                  <SectionDivider label="Your organization" sub="on file · reused automatically" icon="building" />

                  <section style={{ borderRadius: T.rXl, border: `1px solid ${editOrg ? T.brand + "55" : T.borderSubtle}`, background: T.sunken, overflow: "hidden" }}>
                    <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "14px 20px" }}>
                      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                        <Icon name="check" size={15} color={T.success} />
                        <span style={{ font: `600 13.5px/1.2 ${T.sans}`, color: T.fg }}>From {company} · on file</span>
                        <span style={{ font: `400 12px/1.2 ${T.sans}`, color: T.tertiary }}>· reused automatically</span>
                      </div>
                      <button onClick={() => (editOrg ? doneManage() : startManage())} style={{ font: `500 12.5px/1 ${T.sans}`, color: T.brandDeep, background: "none", border: "none", cursor: "pointer", display: "inline-flex", alignItems: "center", gap: 4 }}>
                        {editOrg ? "Done" : "Manage"} <Icon name={editOrg ? "chevronDown" : "chevronRight"} size={13} color={T.brandDeep} />
                      </button>
                    </div>
                    <div style={{ display: "grid", gridTemplateColumns: "repeat(2, 1fr)", gap: "1px", background: T.borderSubtle, borderTop: `1px solid ${T.borderSubtle}` }}>
                      <OrgCell label="Company" editing={editOrg} value={editOrg ? orgEdit.company : company} onChange={(v) => setOrgEdit({ ...orgEdit, company: v })} />
                      <OrgCell label="Industry" editing={editOrg} value={editOrg ? orgEdit.industry : (industryLabel(onFile?.industry || "") || "")} onChange={(v) => setOrgEdit({ ...orgEdit, industry: v })} />
                      <OrgCell label="Scale" editing={editOrg} value={editOrg ? orgEdit.scale : scaleText} onChange={(v) => setOrgEdit({ ...orgEdit, scale: v })} />
                      <OrgCell label="Connected systems" editing={editOrg} value={editOrg ? orgEdit.systems : (onFile?.connected_systems || []).map(integrationLabel).join(", ")} onChange={(v) => setOrgEdit({ ...orgEdit, systems: v })} />
                      <OrgCell label="Sub-focus" editing={editOrg} value={editOrg ? orgEdit.subFocus : (onFile?.sub_focus || []).join(", ")} onChange={(v) => setOrgEdit({ ...orgEdit, subFocus: v })} />
                      <OrgCell label="Website" editing={editOrg} value={editOrg ? orgEdit.website : (onFile?.website || "")} onChange={(v) => setOrgEdit({ ...orgEdit, website: v })} />
                    </div>
                    {editOrg && (
                      <div style={{ display: "flex", alignItems: "center", gap: 7, padding: "10px 20px", borderTop: `1px solid ${T.borderSubtle}`, background: T.raised }}>
                        <Sparkle size={11} color={T.brandDeep} />
                        <span style={{ font: `400 11.5px/1.4 ${T.sans}`, color: T.tertiary }}>Edits update your organization profile — reused on every future project.</span>
                      </div>
                    )}
                  </section>

                  <SectionDivider label="This project" sub="specific to what you're building now" icon="layers" />

                  <Card cat="This project" title="Project basics" accent>
                    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
                      <Field label="Project name"><TextInput value={p.name} onChange={(v) => setProj("name", v)} placeholder="e.g. Quote-to-Epicor automation" /></Field>
                      <Field label="What are you building?" hint="One or two sentences on the outcome you want.">
                        <TextArea rows={3} value={p.goal} onChange={(v) => setProj("goal", v)} placeholder="e.g. Replace the manual quoting spreadsheet…" />
                      </Field>
                      <Field label="Budget cap" optional hint="Stop and notify when spend reaches this amount. Leave unset to run to completion.">
                        <BudgetPicker value={budget} onChange={setBudget} />
                      </Field>
                    </div>
                    {/* Create-the-project gate (PRD §2.4/§24): a real POST /api/drafts in `draft` state. */}
                    <div style={{ marginTop: 18, paddingTop: 16, borderTop: `1px solid ${T.borderSubtle}` }}>
                      {draftId ? (
                        <div style={{ display: "flex", alignItems: "center", gap: 9 }}>
                          <span style={{ width: 22, height: 22, borderRadius: "50%", background: T.successSoft, display: "grid", placeItems: "center", flexShrink: 0 }}><Icon name="check" size={13} color={T.success} /></span>
                          <span style={{ font: `400 12.5px/1.45 ${T.sans}`, color: T.secondary }}><b style={{ color: T.success }}>Project created</b> — “{p.name || "Untitled project"}” is saved. Enrich it below to move it toward build.</span>
                        </div>
                      ) : (
                        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 14, flexWrap: "wrap" }}>
                          <span style={{ font: `400 12.5px/1.45 ${T.sans}`, color: T.tertiary, maxWidth: 380 }}>Name the project and save to create it. The rest — scope, engine &amp; materials — unlocks once it exists.</span>
                          <Btn variant="primary" onClick={saveBasics} disabled={!p.name.trim() || savingBasics} title={p.name.trim() ? "Create this project" : "Enter a project name first"}>
                            {savingBasics ? "Creating…" : <><Icon name="check" size={14} color="#fff" /> Create project</>}
                          </Btn>
                        </div>
                      )}
                    </div>
                  </Card>
                  {/* Scope / Build engine / Materials stay locked until the project is created. */}
                  <div style={{ position: "relative" }}>
                    <div aria-hidden={!draftId} style={draftId
                      ? { display: "flex", flexDirection: "column", gap: 16 }
                      : { display: "flex", flexDirection: "column", gap: 16, opacity: 0.4, filter: "grayscale(0.5)", pointerEvents: "none", userSelect: "none" }}>
                  <Card cat="This project" title="Scope of work" desc="Which parts of the business does this project touch?">
                    <ScopeOfWork options={scopeOptions} value={p.scope} onChange={(v) => setProj("scope", v)} onAddOption={addScopeOption} />
                  </Card>
                  <Card cat="This project" title="Build engine" desc="Choose the coding agent that builds this project. The factory, console, and output look the same either way.">
                    <EnginePicker value={engine} onChange={setEngine} />
                  </Card>
                  <Card cat="This project" title="Project materials" desc="We already have your line card & pricing on file — only add what's specific to this project.">
                    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
                      <OrgImportPicker />
                      <Field label="Project walkthrough video" optional><Dropzone kind="video" files={mats.video} onToggle={() => videoInputRef.current?.click()} /></Field>
                      <Field label="Extra documents" optional><Dropzone kind="docs" compact files={mats.docs} onToggle={() => docsInputRef.current?.click()} /></Field>
                    </div>
                  </Card>
                    </div>
                    {!draftId && (
                      <div style={{ position: "absolute", inset: 0, display: "flex", alignItems: "flex-start", justifyContent: "center", paddingTop: 30 }}>
                        <div style={{ display: "inline-flex", alignItems: "center", gap: 9, padding: "11px 17px", borderRadius: 9999, background: T.raised, border: `1px solid ${T.borderDefault}`, boxShadow: T.shadowSm, font: `500 12.5px/1 ${T.sans}`, color: T.secondary }}>
                          <Icon name="lock" size={14} color={T.tertiary} /> Create the project above to unlock
                        </div>
                      </div>
                    )}
                  </div>
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
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              {onBack && <Btn variant="ghost" onClick={onBack}>Save & finish later</Btn>}
              <Btn variant="primary" onClick={handoff} disabled={!ready || submitting || !draftId} title={ready ? "Hand off to the build factory" : (fresh ? "Set up your company & project to continue" : "Answer the project questions to continue")} style={ready ? { background: T.success } : undefined}>{submitting ? "Handing off…" : "Hand off to factory"} <Icon name="arrowRight" size={14} color="#fff" /></Btn>
            </div>
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
            {msgs.map((m, i) => (
              <React.Fragment key={i}>
                <Message who={m.role === "user" ? "user" : "agent"} text={m.content} />
                {m.role === "agent" && m.choices && m.choices.length > 0 && i === msgs.length - 1 && (
                  <ChoiceList options={m.choices} onPick={sendTurn} disabled={chatBusy} />
                )}
              </React.Fragment>
            ))}
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
