// OrgAdminScreen.tsx — Organization admin (PRD §2.3, design orgproject.jsx → OrgAdmin). Reached
// from the dashboard's org switcher / "Manage organization →". Faithful TSX port, wired to the
// LOCKED org-admin contract (docs/plans/org-admin-api.md): Company profile + Connected systems via
// /api/org (GET/PATCH); Team via org-scoped /api/org/members; Knowledge base via /api/org/docs;
// Usage & billing via /api/org/usage (+ PATCH /api/org/billing). Every section degrades to an empty
// state until its backend lands, so the screen ships independently.
import { useEffect, useRef, useState } from "react";
import { api, Org, Member, OrgDoc, OrgUsage, Me } from "../api";
import { T, Icon, Sparkle, CategoryLabel, Btn, StatusPill, Avatar, Wordmark, Field, TextInput } from "./onboarding/design";
import { AccountMenu } from "./AccountMenu";
import { ListRowSkel, FileTileSkel, MetricCardSkel } from "./skeleton";

type Section = "profile" | "knowledge" | "systems" | "team" | "billing";

const SECTIONS: { id: Section; label: string }[] = [
  { id: "profile", label: "Company profile" },
  { id: "knowledge", label: "Knowledge base" },
  { id: "systems", label: "Connected systems" },
  { id: "team", label: "Team & access" },
  { id: "billing", label: "Usage & billing" },
];

// Known org-level integrations; "connected" is driven by org.connected_systems.
const SYSTEM_CATALOG: { id: string; label: string; kind: string; scope?: string; note?: string }[] = [
  { id: "epicor", label: "Epicor", kind: "ERP", scope: "SKUs · price book · orders", note: "Primary system of record" },
  { id: "salesforce", label: "Salesforce", kind: "CRM" },
  { id: "quickbooks", label: "QuickBooks", kind: "Accounting" },
  { id: "netsuite", label: "NetSuite", kind: "ERP" },
];

const FILE_KIND: Record<string, [string, string, string]> = {
  pdf: ["PDF", "#fbe3e3", "#c0392f"], xlsx: ["XLS", "#e4f8ef", "#1f8a5b"], csv: ["CSV", "#e4f8ef", "#1f8a5b"],
  doc: ["DOC", "#e8f1ff", "#1A7BFF"], video: ["MP4", "#f3e9fb", "#7a3ea8"], img: ["IMG", "#fbefdc", "#b06f12"],
};

function money(v: number): string { return `$${v.toFixed(2)}`; }
function nameFromEmail(email: string): string { return email.split("@")[0].replace(/[._]/g, " "); }
function fmtBytes(n?: number): string {
  if (!n) return "";
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${Math.round(n / 1024)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}
function relTime(epoch?: number): string {
  if (!epoch) return "";
  const s = Math.max(0, Date.now() / 1000 - epoch);
  if (s < 86400) return "today";
  return `${Math.floor(s / 86400)}d ago`;
}

function SecHead({ title, desc, action }: { title: string; desc?: string; action?: React.ReactNode }) {
  return (
    <div style={{ display: "flex", alignItems: "flex-end", justifyContent: "space-between", gap: 14, marginBottom: 18 }}>
      <div>
        <h2 style={{ font: `700 22px/1.2 ${T.display}`, letterSpacing: "-0.015em", color: T.fg, margin: 0 }}>{title}</h2>
        {desc && <p style={{ font: `400 13px/1.5 ${T.sans}`, color: T.secondary, margin: "6px 0 0" }}>{desc}</p>}
      </div>
      {action}
    </div>
  );
}

function MetricCard({ label, value, hint, accent }: { label: string; value: string; hint?: string; accent?: boolean }) {
  return (
    <div style={{ background: T.raised, border: `1px solid ${T.borderSubtle}`, borderRadius: T.rLg, padding: "14px 16px", boxShadow: T.shadowXs }}>
      <CategoryLabel>{label}</CategoryLabel>
      <div style={{ font: `700 26px/1.1 ${T.display}`, letterSpacing: "-0.02em", color: accent ? T.brandDeep : T.fg, marginTop: 8 }}>{value}</div>
      {hint && <div style={{ font: `400 11.5px/1.3 ${T.sans}`, color: T.tertiary, marginTop: 4 }}>{hint}</div>}
    </div>
  );
}

function FileTile({ d, onDelete, onSave }: { d: OrgDoc; onDelete?: () => void; onSave?: (name: string, tag: string) => void }) {
  const k = FILE_KIND[d.kind || "doc"] || FILE_KIND.doc;
  const [editing, setEditing] = useState(false);
  const [name, setName] = useState(d.name);
  const [tag, setTag] = useState(d.tag || "");
  if (editing) {
    return (
      <div style={{ background: T.raised, border: `1px solid ${T.brand}55`, borderRadius: T.rLg, padding: "13px 14px", display: "flex", flexDirection: "column", gap: 8, boxShadow: T.shadowXs }}>
        <Field label="Name"><TextInput value={name} onChange={setName} size="sm" /></Field>
        <Field label="Tag"><TextInput value={tag} onChange={setTag} size="sm" placeholder="e.g. Price book" /></Field>
        <div style={{ display: "flex", gap: 6, justifyContent: "flex-end" }}>
          <Btn variant="ghost" size="sm" onClick={() => { setEditing(false); setName(d.name); setTag(d.tag || ""); }}>Cancel</Btn>
          <Btn variant="primary" size="sm" onClick={() => { onSave?.(name.trim() || d.name, tag.trim()); setEditing(false); }}>Save</Btn>
        </div>
      </div>
    );
  }
  return (
    <div style={{ background: T.raised, border: `1px solid ${T.borderSubtle}`, borderRadius: T.rLg, padding: "13px 14px", display: "flex", flexDirection: "column", gap: 10, boxShadow: T.shadowXs }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <span style={{ font: `700 9px/1 ${T.mono}`, letterSpacing: "0.05em", color: k[2], background: k[1], padding: "4px 6px", borderRadius: 4 }}>{k[0]}</span>
        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
          {d.tag && <CategoryLabel style={{ fontSize: 9.5 }}>{d.tag}</CategoryLabel>}
          {onSave && <button onClick={() => { setName(d.name); setTag(d.tag || ""); setEditing(true); }} title="Rename / retag" style={{ font: `500 11px/1 ${T.sans}`, color: T.brandDeep, border: "none", background: "transparent", cursor: "pointer", padding: 0 }}>Edit</button>}
          {onDelete && <button onClick={onDelete} title="Delete document" style={{ display: "grid", placeItems: "center", width: 22, height: 22, borderRadius: 5, border: "none", background: "transparent", cursor: "pointer", color: T.tertiary }}><Icon name="x" size={13} color={T.tertiary} /></button>}
        </div>
      </div>
      <span style={{ font: `600 13px/1.3 ${T.sans}`, color: T.fg, wordBreak: "break-word" }}>{d.name}</span>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", font: `400 11px/1 ${T.mono}`, color: T.tertiary }}>
        <span>{fmtBytes(d.size_bytes) || relTime(d.updated)}</span>
        {d.used_count != null && <span>{d.used_count} project{d.used_count === 1 ? "" : "s"}</span>}
      </div>
    </div>
  );
}

export function OrgAdminScreen({ onBack }: { onBack: () => void }) {
  const [sec, setSec] = useState<Section>("profile");
  const [org, setOrg] = useState<Org | null>(null);
  const [me, setMe] = useState<Me | null>(null);
  const [members, setMembers] = useState<Member[]>([]);
  const [membersLoading, setMembersLoading] = useState(true);
  const [docs, setDocs] = useState<OrgDoc[]>([]);
  const [docsLoading, setDocsLoading] = useState(true);
  const [usage, setUsage] = useState<OrgUsage | null>(null);
  const [usageLoading, setUsageLoading] = useState(true);
  const [notice, setNotice] = useState("");

  // profile edit
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState<Partial<Org>>({});
  const [saving, setSaving] = useState(false);

  // invite
  const [inviting, setInviting] = useState(false);
  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteRole, setInviteRole] = useState("member");

  // billing edit ("Manage plan")
  const [editPlan, setEditPlan] = useState(false);
  const [planDraft, setPlanDraft] = useState<{ plan: string; cap: string }>({ plan: "", cap: "" });

  const docsInputRef = useRef<HTMLInputElement | null>(null);

  const loadMembers = () => api.orgMembers().then((d) => { setMembers(d.members || []); setMembersLoading(false); }).catch(() => { setMembers([]); setMembersLoading(false); });
  const loadUsage = () => api.orgUsage().then((u) => { setUsage(u); setUsageLoading(false); }).catch(() => { setUsage(null); setUsageLoading(false); });
  const loadDocs = () => { setDocsLoading(true); api.orgDocs().then((d) => setDocs(d.docs || [])).catch(() => setDocs([])).finally(() => setDocsLoading(false)); };

  // KB: real upload (FileReader→base64→POST /api/org/docs) + delete.
  const uploadDocs = async (list: FileList | null) => {
    if (!list || !list.length) return;
    setNotice("");
    try {
      for (const file of Array.from(list)) {
        const data_b64 = await new Promise<string>((resolve) => {
          const r = new FileReader();
          r.onload = () => resolve(String(r.result || "").split(",")[1] || "");
          r.onerror = () => resolve("");
          r.readAsDataURL(file);
        });
        await api.orgDocUpload({ name: file.name, content_type: file.type || undefined, data_b64 });
      }
      await loadDocs();
    } catch { setNotice("Upload failed (admin only)."); }
  };
  const deleteDoc = async (docId: string) => {
    try { await api.orgDocDelete(docId); await loadDocs(); }
    catch { setNotice("Couldn’t delete document."); }
  };
  const renameDoc = async (docId: string, name: string, tag: string) => {
    try { await api.orgDocPatch(docId, { name, tag }); await loadDocs(); }
    catch { setNotice("Couldn’t update document."); }
  };
  const savePlan = async () => {
    try {
      const cap = parseFloat(planDraft.cap);
      await api.patchBilling({ plan: planDraft.plan || undefined, monthly_budget_cap: isNaN(cap) ? undefined : cap });
      setEditPlan(false); await loadUsage();
    } catch { setNotice("Couldn’t update plan."); }
  };

  useEffect(() => {
    api.getOrg().then((d) => setOrg(d.org)).catch(() => setOrg(null));
    api.me().then(setMe).catch(() => setMe(null));
    loadMembers();
    loadDocs();
    loadUsage();
  }, []);

  const startEdit = () => { setDraft({ ...org }); setEditing(true); setNotice(""); };
  const saveProfile = async () => {
    setSaving(true);
    try {
      const d = await api.patchOrg({
        name: draft.name, industry: draft.industry, sub_focus: draft.sub_focus,
        headcount: draft.headcount, revenue: draft.revenue, location: draft.location, website: draft.website,
      });
      setOrg(d.org); setEditing(false);
    } catch { setNotice("Couldn’t save — try again."); }
    setSaving(false);
  };

  const toggleSystem = async (id: string, connect: boolean) => {
    if (!org) return;
    const current = org.connected_systems || [];
    const next = connect ? Array.from(new Set([...current, id])) : current.filter((s) => s !== id);
    try { const d = await api.patchOrg({ connected_systems: next }); setOrg(d.org); }
    catch { setNotice("Couldn’t update connections — try again."); }
  };

  const sendInvite = async () => {
    const email = inviteEmail.trim().toLowerCase();
    if (!email) return;
    try { await api.inviteMember({ email, role: inviteRole }); await loadMembers(); setInviteEmail(""); setInviting(false); }
    catch { setNotice("Invite failed (admin only)."); }
  };
  const changeRole = async (email: string, role: string) => {
    try { await api.updateMember(email, { role }); await loadMembers(); }
    catch { setNotice("Couldn’t update member."); }
  };
  const removeMember = async (email: string) => {
    try { await api.removeMember(email); await loadMembers(); }
    catch { setNotice("Couldn’t remove member."); }
  };

  const orgName = org?.name || "Your organization";
  const v = (x?: string | null) => (x && x.trim() ? x : "—");
  const profileRows: [string, string][] = [
    ["Legal name", v(org?.name)],
    ["Industry", v(org?.industry)],
    ["Sub-focus", org?.sub_focus?.length ? org.sub_focus.join(", ") : "—"],
    ["Headquarters", v(org?.location)],
    ["Headcount", v(org?.headcount)],
    ["Annual revenue", v(org?.revenue)],
    ["Website", v(org?.website)],
  ];

  const byProject = (usage?.by_project || []).filter((r) => r.spent_usd > 0).sort((a, b) => b.spent_usd - a.spent_usd);
  const maxSpend = byProject.reduce((m, r) => Math.max(m, r.spent_usd), 0) || 1;
  const isYou = (m: Member) => m.you ?? (!!me?.email && m.email.toLowerCase() === me.email.toLowerCase());

  return (
    <div style={{ height: "100vh", display: "flex", flexDirection: "column", background: T.bg, fontFamily: T.sans }}>
      {/* top bar */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "13px 24px", background: T.raised, borderBottom: `1px solid ${T.borderSubtle}`, flexShrink: 0 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <Btn variant="ghost" size="sm" onClick={onBack}><Icon name="arrowLeft" size={14} /> Projects</Btn>
          <Wordmark size={17} />
          <span style={{ font: `400 13px/1 ${T.mono}`, color: T.tertiary }}>/</span>
          <span style={{ font: `600 13px/1 ${T.sans}`, color: T.fg }}>Organization</span>
        </div>
        <AccountMenu size={30} />
      </div>

      <div style={{ flex: 1, display: "flex", minHeight: 0 }}>
        {/* sub nav */}
        <div style={{ width: 224, flexShrink: 0, borderRight: `1px solid ${T.borderSubtle}`, background: T.raised, padding: "22px 16px" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10, padding: "0 10px 16px" }}>
            <Avatar name={orgName} size={34} tone="neutral" />
            <div style={{ minWidth: 0 }}>
              <div style={{ font: `600 13px/1.2 ${T.sans}`, color: T.fg, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{orgName}</div>
              <CategoryLabel style={{ fontSize: 10 }}>Admin</CategoryLabel>
            </div>
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
            {SECTIONS.map((s) => {
              const on = sec === s.id;
              return (
                <button key={s.id} onClick={() => { setSec(s.id); setNotice(""); }} style={{ display: "flex", alignItems: "center", gap: 10, padding: "9px 11px", borderRadius: T.rMd, width: "100%",
                  cursor: "pointer", background: on ? T.brandSoft : "transparent", border: "none", textAlign: "left",
                  font: `${on ? 600 : 500} 13px/1.2 ${T.sans}`, color: on ? T.brandDeep : T.secondary }}>{s.label}</button>
              );
            })}
          </div>
        </div>

        {/* content */}
        <div style={{ flex: 1, minWidth: 0, overflow: "auto", padding: "28px 32px" }}>
          <div style={{ maxWidth: 760 }}>
            <CategoryLabel style={{ marginBottom: 12 }}>Organization · context</CategoryLabel>
            {notice && <div style={{ font: `500 12.5px/1.4 ${T.sans}`, color: T.danger, marginBottom: 12 }}>{notice}</div>}

            {/* ── Company profile ── */}
            {sec === "profile" && (
              <>
                <SecHead title="Company profile" desc="The canonical context every project inherits — set once, reused everywhere."
                  action={editing
                    ? <div style={{ display: "flex", gap: 8 }}><Btn variant="ghost" size="sm" onClick={() => setEditing(false)}>Cancel</Btn><Btn variant="primary" size="sm" onClick={saveProfile} disabled={saving}>{saving ? "Saving…" : "Save"}</Btn></div>
                    : <Btn variant="secondary" size="sm" onClick={startEdit}>Edit profile</Btn>} />
                {!editing ? (
                  <div style={{ border: `1px solid ${T.borderSubtle}`, borderRadius: T.rLg, overflow: "hidden", background: T.raised, boxShadow: T.shadowXs }}>
                    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1px", background: T.borderSubtle }}>
                      {profileRows.map(([k, val]) => (
                        <div key={k} style={{ background: T.raised, padding: "13px 18px" }}>
                          <CategoryLabel style={{ display: "block", marginBottom: 5 }}>{k}</CategoryLabel>
                          <span style={{ font: `500 13.5px/1.35 ${T.sans}`, color: T.fg }}>{val}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                ) : (
                  <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14 }}>
                    <Field label="Legal name"><TextInput value={draft.name || ""} onChange={(x) => setDraft({ ...draft, name: x })} /></Field>
                    <Field label="Industry"><TextInput value={draft.industry || ""} onChange={(x) => setDraft({ ...draft, industry: x })} /></Field>
                    <Field label="Sub-focus (comma-separated)"><TextInput value={(draft.sub_focus || []).join(", ")} onChange={(x) => setDraft({ ...draft, sub_focus: x.split(",").map((s) => s.trim()).filter(Boolean) })} /></Field>
                    <Field label="Headquarters"><TextInput value={draft.location || ""} onChange={(x) => setDraft({ ...draft, location: x })} /></Field>
                    <Field label="Headcount"><TextInput value={draft.headcount || ""} onChange={(x) => setDraft({ ...draft, headcount: x })} /></Field>
                    <Field label="Annual revenue"><TextInput value={draft.revenue || ""} onChange={(x) => setDraft({ ...draft, revenue: x })} /></Field>
                    <Field label="Website"><TextInput value={draft.website || ""} onChange={(x) => setDraft({ ...draft, website: x })} /></Field>
                  </div>
                )}
                <div style={{ marginTop: 14, display: "flex", alignItems: "flex-start", gap: 10, padding: "13px 15px", borderRadius: T.rLg, border: `1px solid ${T.brand}33`, background: T.brandSoft + "55" }}>
                  <Sparkle size={13} color={T.brand} style={{ marginTop: 2 }} />
                  <p style={{ margin: 0, font: `400 12.5px/1.55 ${T.sans}`, color: T.secondary }}>The Concierge reuses this profile to skip questions on every new project. Keep it current and onboarding stays one-click.</p>
                </div>
              </>
            )}

            {/* ── Knowledge base ── */}
            {sec === "knowledge" && (
              <>
                <input ref={docsInputRef} type="file" multiple accept=".pdf,.doc,.docx,.xls,.xlsx,.csv,.txt,.md,image/*" style={{ display: "none" }} onChange={(e) => { uploadDocs(e.target.files); e.target.value = ""; }} />
                <SecHead title="Knowledge base" desc="Org-scoped documents the factory can draw on for any project."
                  action={<Btn variant="primary" size="sm" onClick={() => docsInputRef.current?.click()}><Icon name="upload" size={14} color="#fff" /> Upload</Btn>} />
                {docsLoading ? (
                  <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 12 }}>
                    {Array.from({ length: 3 }, (_, i) => <FileTileSkel key={i} />)}
                  </div>
                ) : docs.length ? (
                  <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 12 }}>
                    {docs.map((d) => <FileTile key={d.id} d={d} onDelete={() => deleteDoc(d.id)} onSave={(name, tag) => renameDoc(d.id, name, tag)} />)}
                  </div>
                ) : (
                  <div style={{ border: `1px dashed ${T.borderDefault}`, borderRadius: T.rLg, padding: "30px", textAlign: "center", font: `400 13px/1.5 ${T.sans}`, color: T.tertiary }}>
                    No org documents yet. Upload price books, line cards, policies, and SOPs here so every project can reuse them.
                  </div>
                )}
              </>
            )}

            {/* ── Connected systems ── */}
            {sec === "systems" && (
              <>
                <SecHead title="Connected systems" desc="Linked once at the org level — every project reuses these connections." />
                <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                  {SYSTEM_CATALOG.map((s) => {
                    const connected = (org?.connected_systems || []).includes(s.id);
                    return (
                      <div key={s.id} style={{ display: "flex", alignItems: "center", gap: 13, padding: "14px 16px", borderRadius: T.rLg, border: `1px solid ${connected ? T.brand + "55" : T.borderSubtle}`, background: connected ? T.brandSoft + "44" : T.raised }}>
                        <span style={{ width: 38, height: 38, borderRadius: 9, flexShrink: 0, display: "grid", placeItems: "center", background: connected ? T.brand : T.sunken, color: connected ? "#fff" : T.secondary, font: `700 13px/1 ${T.mono}` }}>{s.label.slice(0, 2).toUpperCase()}</span>
                        <div style={{ flex: 1 }}>
                          <div style={{ display: "flex", alignItems: "center", gap: 9 }}>
                            <span style={{ font: `600 14px/1.2 ${T.sans}`, color: T.fg }}>{s.label}</span>
                            <CategoryLabel style={{ fontSize: 10 }}>{s.kind}</CategoryLabel>
                            {connected && <StatusPill tone="success">Connected</StatusPill>}
                          </div>
                          <p style={{ margin: "4px 0 0", font: `400 12px/1.4 ${T.sans}`, color: T.tertiary }}>{connected ? (s.scope ? `${s.scope}${s.note ? " · " + s.note : ""}` : "Connected") : "Not connected"}</p>
                        </div>
                        <Btn variant={connected ? "ghost" : "secondary"} size="sm" onClick={() => toggleSystem(s.id, !connected)}>{connected ? "Disconnect" : "Link"}</Btn>
                      </div>
                    );
                  })}
                </div>
              </>
            )}

            {/* ── Team & access ── */}
            {sec === "team" && (
              <>
                <SecHead title="Team & access" desc="Who can see and steer projects in this organization."
                  action={<Btn variant="primary" size="sm" onClick={() => setInviting((x) => !x)}><Icon name="plus" size={14} color="#fff" /> Invite</Btn>} />
                {inviting && (
                  <div style={{ display: "flex", alignItems: "flex-end", gap: 10, marginBottom: 14, padding: "14px 16px", border: `1px solid ${T.borderSubtle}`, borderRadius: T.rLg, background: T.raised }}>
                    <Field label="Work email" style={{ flex: 1 }}><TextInput type="email" value={inviteEmail} onChange={setInviteEmail} placeholder="name@company.com" /></Field>
                    <Field label="Role">
                      <select value={inviteRole} onChange={(e) => setInviteRole(e.target.value)} style={{ height: 36, borderRadius: T.rMd, border: `1px solid ${T.borderDefault}`, padding: "0 10px", font: `500 13px/1 ${T.sans}`, color: T.fg, background: T.raised }}>
                        <option value="member">Member</option>
                        <option value="admin">Admin</option>
                      </select>
                    </Field>
                    <Btn variant="primary" size="md" onClick={sendInvite}>Send invite</Btn>
                  </div>
                )}
                <div style={{ border: `1px solid ${T.borderSubtle}`, borderRadius: T.rLg, overflow: "hidden", background: T.raised, boxShadow: T.shadowXs }}>
                  {membersLoading ? <div style={{ padding: "12px 16px" }}><ListRowSkel rows={3} /></div> : (members.length === 0 && <div style={{ padding: "20px", textAlign: "center", font: `400 13px/1.4 ${T.sans}`, color: T.tertiary }}>No members yet — invite your team above.</div>)}
                  {members.map((m, i) => {
                    const you = isYou(m);
                    return (
                      <div key={m.email} style={{ display: "flex", alignItems: "center", gap: 12, padding: "13px 16px", borderTop: i ? `1px solid ${T.borderSubtle}` : "none" }}>
                        <Avatar name={nameFromEmail(m.email)} size={34} />
                        <div style={{ flex: 1, minWidth: 0 }}>
                          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                            <span style={{ font: `600 13.5px/1.2 ${T.sans}`, color: T.fg }}>{nameFromEmail(m.email)}</span>
                            {you && <span style={{ font: `500 10px/1 ${T.sans}`, color: T.brandDeep, background: T.brandSoft, padding: "2px 6px", borderRadius: 4 }}>You</span>}
                          </div>
                          <span style={{ font: `400 12px/1 ${T.sans}`, color: T.tertiary }}>{m.designation ? `${m.email} · ${m.designation}` : m.email}</span>
                        </div>
                        <select value={m.role} disabled={you} onChange={(e) => changeRole(m.email, e.target.value)}
                          style={{ height: 30, borderRadius: T.rMd, border: `1px solid ${T.borderDefault}`, padding: "0 8px", font: `500 12px/1 ${T.sans}`, color: T.secondary, background: T.raised }}>
                          <option value="member">Member</option>
                          <option value="admin">Admin</option>
                        </select>
                        {!you && <button onClick={() => removeMember(m.email)} title="Remove member" style={{ display: "grid", placeItems: "center", width: 30, height: 30, borderRadius: T.rMd, border: `1px solid ${T.borderSubtle}`, background: T.raised, cursor: "pointer" }}><Icon name="x" size={14} color={T.tertiary} /></button>}
                      </div>
                    );
                  })}
                </div>
              </>
            )}

            {/* ── Usage & billing ── */}
            {sec === "billing" && (
              <>
                <SecHead title="Usage & billing" desc="Spend across every project in this organization."
                  action={editPlan
                    ? <div style={{ display: "flex", gap: 8 }}><Btn variant="ghost" size="sm" onClick={() => setEditPlan(false)}>Cancel</Btn><Btn variant="primary" size="sm" onClick={savePlan}>Save</Btn></div>
                    : <Btn variant="secondary" size="sm" onClick={() => { setPlanDraft({ plan: usage?.plan || "", cap: usage?.monthly_budget_cap != null ? String(usage.monthly_budget_cap) : "" }); setEditPlan(true); }}>Manage plan</Btn>} />
                {editPlan && (
                  <div style={{ display: "flex", alignItems: "flex-end", gap: 12, marginBottom: 16, padding: "14px 16px", border: `1px solid ${T.borderSubtle}`, borderRadius: T.rLg, background: T.raised }}>
                    <Field label="Plan" style={{ flex: 1 }}><TextInput value={planDraft.plan} onChange={(v) => setPlanDraft({ ...planDraft, plan: v })} placeholder="e.g. Team" /></Field>
                    <Field label="Monthly budget cap ($)" style={{ flex: 1 }}><TextInput value={planDraft.cap} onChange={(v) => setPlanDraft({ ...planDraft, cap: v })} placeholder="120" /></Field>
                  </div>
                )}
                <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 12, marginBottom: 16 }}>
                  {usageLoading ? (
                    <><MetricCardSkel /><MetricCardSkel /><MetricCardSkel /></>
                  ) : (
                    <>
                      <MetricCard label="Plan" value={usage?.plan || "—"} hint={usage?.monthly_budget_cap != null ? `${money(usage.monthly_budget_cap)} / mo cap` : "billing not yet configured"} accent />
                      <MetricCard label="Spent this month" value={usage?.spent != null ? money(usage.spent) : "—"} hint={usage?.monthly_budget_cap ? `${Math.round(((usage.spent || 0) / usage.monthly_budget_cap) * 100)}% of cap` : ""} />
                      <MetricCard label="Active projects" value={usage?.active_projects != null ? String(usage.active_projects) : "—"} hint={usage?.total_projects != null ? `${usage.total_projects} total` : ""} />
                    </>
                  )}
                </div>
                <div style={{ border: `1px solid ${T.borderSubtle}`, borderRadius: T.rLg, overflow: "hidden", background: T.raised, boxShadow: T.shadowXs }}>
                  <div style={{ padding: "10px 16px", borderBottom: `1px solid ${T.borderSubtle}`, background: T.sunken }}><CategoryLabel>Spend by project</CategoryLabel></div>
                  {byProject.length === 0 && <div style={{ padding: "20px", textAlign: "center", font: `400 13px/1.4 ${T.sans}`, color: T.tertiary }}>No spend recorded yet.</div>}
                  {byProject.map((r, i) => (
                    <div key={r.project_id || r.name + i} style={{ display: "flex", alignItems: "center", gap: 12, padding: "12px 16px", borderTop: i ? `1px solid ${T.borderSubtle}` : "none" }}>
                      <span style={{ flex: 1, font: `500 13px/1.2 ${T.sans}`, color: T.fg, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{r.name}</span>
                      <span style={{ width: 120, height: 6, borderRadius: 3, background: T.sunken, overflow: "hidden" }}><span style={{ display: "block", height: "100%", width: Math.round((r.spent_usd / maxSpend) * 100) + "%", background: T.brand }} /></span>
                      <span style={{ width: 56, textAlign: "right", font: `500 12px/1 ${T.mono}`, color: T.secondary }}>{money(r.spent_usd)}</span>
                    </div>
                  ))}
                </div>
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
