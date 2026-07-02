import React from "react";
import { T } from "./tokens";
import { Icon, Sparkle, StatusPill, Field, TextInput, Btn } from "./primitives";
import { api } from "../api";
import type { AdminAgent, AdminTool, AdminClient, AdminAccessUser } from "../api";
import { useAdminFetch, fmtRel, toolKind } from "./hooks";

const TYPE_C: Record<string, [string, string]> = {
  MCP: [T.brandSoft, T.brandDeep],
  API: [T.cHighSoft, T.cHigh],
  native: [T.successSoft, T.success],
  HTTP: ["#f3e9fb", "#7a3ea8"],
};

const overlay: React.CSSProperties = {
  position: "absolute",
  inset: 0,
  zIndex: 60,
  background: "rgba(9,12,18,0.45)",
  display: "grid",
  placeItems: "center",
  padding: 28,
  animation: "sfRise .18s ease both",
};

const modalCard: React.CSSProperties = {
  width: "min(620px, 100%)",
  maxHeight: "100%",
  background: T.raised,
  borderRadius: T.rXl,
  boxShadow: T.shadowMd,
  display: "flex",
  flexDirection: "column",
  overflow: "hidden",
};

const modalHeader: React.CSSProperties = {
  display: "flex",
  alignItems: "center",
  justifyContent: "space-between",
  padding: "16px 20px",
  borderBottom: `1px solid ${T.borderSubtle}`,
};

const Mono = ({ children, style }: { children: React.ReactNode; style?: React.CSSProperties }) => (
  <span style={{ font: `500 11px/1 ${T.mono}`, letterSpacing: "0.04em", color: T.tertiary, ...style }}>{children}</span>
);

// Preview/Edit segmented-toggle cell styles for the prompt panel.
const segIdleStyle: React.CSSProperties = {
  font: `500 11px/1 ${T.sans}`, padding: "6px 11px", borderRadius: 6, border: "1px solid transparent",
  background: "transparent", color: T.secondary, cursor: "pointer",
};
const segActiveStyle: React.CSSProperties = {
  font: `600 11px/1 ${T.sans}`, padding: "6px 11px", borderRadius: 6, border: `1px solid ${T.borderDefault}`,
  background: T.raised, color: T.fg, cursor: "pointer",
};

// ── Markdown view (read-only render of the SKILL.md / prompt body). Lightweight inline-style
//    renderer — no new dep. Handles the slice of markdown the stage SKILLs + PRD-shaped prompts use:
//    ATX headings, fenced code blocks, bold/italic/inline-code, unordered + ordered lists, hr,
//    blockquotes, and paragraphs. Faithful enough that an operator can read a SKILL.md as it'll read
//    to the runner, then hit Edit to drop into the textarea. ──
function MarkdownView({ md }: { md: string }) {
  const lines = (md || "").split("\n");
  const out: React.ReactNode[] = [];
  let i = 0;
  let key = 0;
  const k = () => `md${key++}`;
  const inline = (text: string): React.ReactNode => {
    // inline `code`, **bold**, *italic* — order matters: code first so its contents aren't re-parsed.
    const parts: React.ReactNode[] = [];
    let rest = text;
    let pi = 0;
    const re = /(`[^`]+`|\*\*[^*]+\*\*|\*[^*]+\*)/;
    while (rest.length) {
      const m = rest.match(re);
      if (!m || m.index == null) { parts.push(rest); break; }
      if (m.index > 0) parts.push(rest.slice(0, m.index));
      const tok = m[0];
      if (tok.startsWith("`")) parts.push(<code key={pi++} style={{ font: `400 12px/1 ${T.mono}`, background: T.sunken, padding: "1px 5px", borderRadius: 4, color: T.fg }}>{tok.slice(1, -1)}</code>);
      else if (tok.startsWith("**")) parts.push(<strong key={pi++} style={{ fontWeight: 700, color: T.fg }}>{tok.slice(2, -2)}</strong>);
      else parts.push(<em key={pi++}>{tok.slice(1, -1)}</em>);
      rest = rest.slice(m.index + tok.length);
    }
    return parts;
  };
  const listItem = (line: string, ol: boolean, idx: number) => (
    <div key={k()} style={{ display: "flex", gap: 8, padding: "1px 0" }}>
      <span style={{ font: `500 12.5px/1.6 ${T.mono}`, color: T.tertiary, minWidth: ol ? 18 : 14 }}>{ol ? `${idx + 1}.` : "•"}</span>
      <span style={{ font: `400 13px/1.6 ${T.sans}`, color: T.fg, flex: 1 }}>{inline(line)}</span>
    </div>
  );
  while (i < lines.length) {
    const line = lines[i];
    const t = line.trim();
    if (!t) { i++; continue; }
    if (t === "---" || t === "***") { out.push(<hr key={k()} style={{ border: "none", borderTop: `1px solid ${T.borderSubtle}`, margin: "10px 0" }} />); i++; continue; }
    const fence = t.match(/^```/);
    if (fence) {
      const buf: string[] = [];
      i++;
      while (i < lines.length && !lines[i].trim().startsWith("```")) { buf.push(lines[i]); i++; }
      i++; // closing fence
      out.push(<pre key={k()} style={{ font: `400 12px/1.55 ${T.mono}`, background: T.sunken, color: T.fg, padding: "11px 13px", borderRadius: T.rMd, overflow: "auto", margin: "6px 0" }}>{buf.join("\n")}</pre>);
      continue;
    }
    const h = t.match(/^(#{1,6})\s+(.*)$/);
    if (h) {
      const lvl = h[1].length;
      const sz = [20, 17, 15, 13.5, 12.5, 12][lvl - 1] || 13;
      out.push(<div key={k()} style={{ font: `700 ${sz}px/1.3 ${T.sans}`, color: T.fg, margin: "12px 0 5px", letterSpacing: "-0.01em" }}>{inline(h[2])}</div>);
      i++; continue;
    }
    if (/^[-*]\s+/.test(t)) {
      const items: string[] = [];
      while (i < lines.length && /^\s*[-*]\s+/.test(lines[i])) { items.push(lines[i].replace(/^\s*[-*]\s+/, "")); i++; }
      out.push(<div key={k()} style={{ margin: "3px 0" }}>{items.map((it, idx) => listItem(it, false, idx))}</div>);
      continue;
    }
    if (/^\d+\.\s+/.test(t)) {
      const items: string[] = [];
      while (i < lines.length && /^\s*\d+\.\s+/.test(lines[i])) { items.push(lines[i].replace(/^\s*\d+\.\s+/, "")); i++; }
      out.push(<div key={k()} style={{ margin: "3px 0" }}>{items.map((it, idx) => listItem(it, true, idx))}</div>);
      continue;
    }
    if (t.startsWith(">")) {
      const buf: string[] = [];
      while (i < lines.length && lines[i].trim().startsWith(">")) { buf.push(lines[i].trim().slice(1).trim()); i++; }
      out.push(<blockquote key={k()} style={{ borderLeft: `2px solid ${T.brand}`, margin: "6px 0", padding: "2px 12px", color: T.secondary, font: `400 13px/1.6 ${T.sans}` }}>{buf.map((b, idx) => <div key={idx}>{inline(b)}</div>)}</blockquote>);
      continue;
    }
    out.push(<p key={k()} style={{ margin: "4px 0", font: `400 13px/1.65 ${T.sans}`, color: T.fg }}>{inline(t)}</p>);
    i++;
  }
  return <div style={{ display: "flex", flexDirection: "column" }}>{out}</div>;
}

function CloseBtn({ onClick }: { onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      style={{
        width: 28,
        height: 28,
        display: "grid",
        placeItems: "center",
        borderRadius: T.rMd,
        border: "none",
        background: "transparent",
        color: T.tertiary,
        cursor: "pointer",
      }}
    >
      <Icon name="x" size={16} />
    </button>
  );
}

export function ConfirmDelete({
  title,
  detail,
  onConfirm,
  onClose,
}: {
  title: string;
  detail: string;
  onConfirm: () => void;
  onClose: () => void;
}) {
  return (
    <div style={overlay}>
      <div style={modalCard}>
        <div style={modalHeader}>
          <h2 style={{ font: `400 19px/1.2 ${T.display}`, color: T.fg, margin: 0 }}>{title}</h2>
          <CloseBtn onClick={onClose} />
        </div>
        <div style={{ padding: 18, display: "flex", flexDirection: "column", gap: 14 }}>
          <p style={{ margin: 0, font: `400 13px/1.5 ${T.sans}`, color: T.secondary }}>{detail}</p>
          <div style={{ display: "flex", gap: 10, justifyContent: "flex-end" }}>
            <Btn onClick={onClose}>Cancel</Btn>
            <Btn variant="danger" onClick={onConfirm}>
              Delete
            </Btn>
          </div>
        </div>
      </div>
    </div>
  );
}

export function AgentPromptPanel({ agent, onClose, onSaved }: { agent: AdminAgent; onClose: () => void; onSaved?: () => void }) {
  const isLive = !!agent.kind;
  const hasVariants = agent.variants && Object.keys(agent.variants).length > 0;
  const defaultRuntime = agent.runtime || (hasVariants ? Object.keys(agent.variants!)[0] : undefined);
  const [runtime, setRuntime] = React.useState<string | undefined>(defaultRuntime);
  const { data: detail, refetch } = useAdminFetch(() => api.adminAgent(agent.callsign, runtime));
  const [prompt, setPrompt] = React.useState(agent.prompt || "");
  const [tab, setTab] = React.useState<"prompt" | "tools" | "activity">("prompt");
  const [viewMode, setViewMode] = React.useState<"preview" | "edit">("preview");
  const [saving, setSaving] = React.useState(false);
  const [appliedNote, setAppliedNote] = React.useState<string | null>(null);
  React.useEffect(() => {
    if (detail?.prompt !== undefined) setPrompt(detail.prompt);
  }, [detail?.prompt]);
  const active = detail ?? agent;
  const dirty = prompt !== (detail?.prompt ?? agent.prompt ?? "");
  const isDefault = active.is_default ?? false;
  const save = () => {
    setSaving(true);
    api
      .adminPatchAgentPrompt(agent.callsign, prompt, runtime)
      .then((res) => {
        setSaving(false);
        setAppliedNote(`saved & applied · v${res.version ?? "?"}`);
        onSaved?.();
        refetch();
      })
      .catch(() => setSaving(false));
  };
  const revert = () => {
    if (!confirm("Revert to the built-in default prompt? Your override will be discarded.")) return;
    setSaving(true);
    api
      .adminRevertAgentPrompt(agent.callsign, runtime)
      .then((res) => {
        setSaving(false);
        setAppliedNote(`reverted to default · v${res.version ?? 0}`);
        refetch();
      })
      .catch(() => setSaving(false));
  };
  const promptLabel = isLive ? "Prompt source" : "System prompt";
  const sourceBadge =
    active.prompt_source === "skill_file"
      ? "live skill"
      : active.prompt_source === "code"
      ? "live concierge"
      : active.prompt_source || "live";
  return (
    <div
      onClick={onClose}
      style={{
        position: "absolute",
        inset: 0,
        zIndex: 60,
        background: "rgba(9,12,18,0.45)",
        display: "flex",
        justifyContent: "flex-end",
        animation: "sfRise .18s ease both",
      }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          width: "min(560px, 100%)",
          height: "100%",
          background: T.raised,
          boxShadow: T.shadowMd,
          display: "flex",
          flexDirection: "column",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "16px 20px", borderBottom: `1px solid ${T.borderSubtle}` }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <span style={{ font: `600 16px/1.2 ${T.sans}`, color: T.fg }}>{active.name || active.role}</span>
            <span style={{ width: 7, height: 7, borderRadius: "50%", background: active.on ? T.success : T.borderDefault }} />
            <span
              style={{
                font: `600 9.5px/1 ${T.mono}`,
                color: T.secondary,
                background: T.sunken,
                border: `1px solid ${T.borderSubtle}`,
                padding: "4px 5px",
                borderRadius: 4,
              }}
            >
              {active.callsign}
            </span>
          </div>
          <CloseBtn onClick={onClose} />
        </div>
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(3, 1fr)",
            gap: 1,
            background: T.borderSubtle,
            borderBottom: `1px solid ${T.borderSubtle}`,
          }}
        >
          {[
            ["Model", active.model],
            ["Callsign", active.sign],
            ["Success", active.success == null ? "—" : `${active.success}%`],
          ].map(([k, v]) => (
            <div key={k} style={{ background: T.raised, padding: "11px 16px" }}>
              <Mono style={{ display: "block", marginBottom: 4 }}>{k}</Mono>
              <Mono style={{ color: T.fg, fontSize: 12.5 }}>{v}</Mono>
            </div>
          ))}
        </div>
        <div style={{ display: "flex", gap: 2, padding: "8px 16px 0" }}>
          {[
            { id: "prompt", l: promptLabel },
            { id: "tools", l: "Tools" },
            { id: "activity", l: "Activity" },
          ].map((t) => {
            const on = tab === (t.id as typeof tab);
            return (
              <button
                key={t.id}
                onClick={() => setTab(t.id as typeof tab)}
                style={{
                  position: "relative",
                  padding: "9px 12px",
                  background: "none",
                  border: "none",
                  cursor: "pointer",
                  font: `${on ? 600 : 500} 12.5px/1 ${T.sans}`,
                  color: on ? T.fg : T.tertiary,
                }}
              >
                {t.l}
                {on && <span style={{ position: "absolute", left: 8, right: 8, bottom: -1, height: 2, background: T.brand }} />}
              </button>
            );
          })}
        </div>
        <div style={{ flex: 1, overflow: "auto", padding: "16px 20px" }}>
          {tab === "prompt" && (
            <>
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 8, flexWrap: "wrap", gap: 8 }}>
                <Mono>{promptLabel}</Mono>
                <span style={{ display: "inline-flex", alignItems: "center", gap: 8 }}>
                  {hasVariants && (
                    <select
                      value={runtime}
                      onChange={(e) => { setRuntime(e.target.value); }}
                      disabled={saving}
                      style={{
                        font: `500 11px/1 ${T.mono}`,
                        padding: "4px 7px",
                        borderRadius: 5,
                        border: `1px solid ${T.borderDefault}`,
                        background: T.bg,
                        color: T.fg,
                      }}
                    >
                      {Object.keys(agent.variants!).map((r) => (
                        <option key={r} value={r}>{r}</option>
                      ))}
                    </select>
                  )}
                  <span
                    style={{
                      font: `600 9px/1 ${T.mono}`,
                      letterSpacing: "0.05em",
                      textTransform: "uppercase",
                      padding: "3px 6px",
                      borderRadius: 3,
                      background: T.successSoft,
                      color: T.success,
                    }}
                  >
                    {sourceBadge}
                  </span>
                  {isLive && (
                    <span
                      style={{
                        font: `600 9px/1 ${T.mono}`,
                        letterSpacing: "0.05em",
                        textTransform: "uppercase",
                        padding: "3px 6px",
                        borderRadius: 3,
                        background: isDefault ? T.sunken : T.warningSoft,
                        color: isDefault ? T.secondary : T.warning,
                        border: `1px solid ${isDefault ? T.borderDefault : "transparent"}`,
                      }}
                    >
                      {isDefault ? "default" : "override"}
                    </span>
                  )}
                </span>
              </div>
              {isLive ? (
                <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                  <div style={{ display: "flex", alignItems: "center", justifyContent: "flex-end", gap: 4 }}>
                    <button onClick={() => setViewMode("preview")} disabled={saving} style={viewMode === "preview" ? segActiveStyle : segIdleStyle}>Preview</button>
                    <button onClick={() => setViewMode("edit")} disabled={saving} style={viewMode === "edit" ? segActiveStyle : segIdleStyle}>Edit</button>
                  </div>
                  {viewMode === "preview" ? (
                    <div style={{ width: "100%", boxSizing: "border-box", minHeight: 280, maxHeight: "calc(100vh - 360px)", padding: "14px 16px", borderRadius: T.rMd, border: `1px solid ${T.borderDefault}`, background: T.bg, overflow: "auto" }}>
                      <MarkdownView md={prompt} />
                    </div>
                  ) : (
                    <textarea
                      value={prompt}
                      onChange={(e) => setPrompt(e.target.value)}
                      disabled={saving}
                      style={{
                        width: "100%",
                        boxSizing: "border-box",
                        minHeight: 280,
                        padding: "13px 15px",
                        borderRadius: T.rMd,
                        resize: "vertical",
                        border: `1px solid ${T.brand}`,
                        background: T.bg,
                        color: T.fg,
                        font: `400 13px/1.65 ${T.mono}`,
                        outline: "none",
                      }}
                    />
                  )}
                </div>
              ) : (
                <div style={{ width: "100%", boxSizing: "border-box", minHeight: 280, maxHeight: "calc(100vh - 320px)", padding: "14px 16px", borderRadius: T.rMd, border: `1px solid ${T.borderDefault}`, background: T.bg, overflow: "auto" }}>
                  <MarkdownView md={prompt} />
                </div>
              )}
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginTop: 8, flexWrap: "wrap", gap: 8 }}>
                <Mono style={{ fontSize: 10.5 }}>
                  {prompt.length} chars
                  {active.version != null ? ` · version ${active.version}` : ""}
                  {active.source_ref || active.skill_path ? ` · ${active.source_ref || active.skill_path}` : ""}
                  {appliedNote ? ` · ${appliedNote}` : ""}
                </Mono>
                {isLive && (
                  <Mono style={{ fontSize: 10.5, color: T.warning }}>
                    Changes apply to new runs, not in-flight ones.
                  </Mono>
                )}
              </div>
            </>
          )}
          {tab === "tools" && (
            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              <Mono style={{ marginBottom: 2, display: "block" }}>Tools available to {active.sign}</Mono>
              {(detail?.tools ?? []).map((t) => {
                const kind = toolKind(t.config);
                const tc = TYPE_C[kind] || TYPE_C.MCP;
                return (
                  <div
                    key={t.name}
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: 10,
                      padding: "10px 12px",
                      borderRadius: T.rMd,
                      border: `1px solid ${T.borderSubtle}`,
                      background: T.bg,
                    }}
                  >
                    <span
                      style={{
                        font: `600 9px/1 ${T.mono}`,
                        color: tc[1],
                        background: tc[0],
                        padding: "3px 5px",
                        borderRadius: 3,
                      }}
                    >
                      {kind}
                    </span>
                    <span style={{ flex: 1, font: `500 13px/1.2 ${T.sans}`, color: T.fg }}>{t.name}</span>
                    <Mono style={{ fontSize: 10.5 }}>{t.has_key ? `key ••${t.key_last4}` : "no key"}</Mono>
                  </div>
                );
              })}
              {(detail?.tools ?? []).length === 0 && <Mono>No tools listed.</Mono>}
            </div>
          )}
          {tab === "activity" && (
            <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              {(detail?.activity ?? []).map((r, i, arr) => (
                <div
                  key={i}
                  style={{
                    display: "flex",
                    gap: 10,
                    paddingBottom: 10,
                    borderBottom: i < arr.length - 1 ? `1px solid ${T.borderSubtle}` : "none",
                  }}
                >
                  <span style={{ marginTop: 5, width: 6, height: 6, borderRadius: "50%", background: T.brand, flexShrink: 0 }} />
                  <span style={{ flex: 1, font: `400 13px/1.4 ${T.sans}`, color: T.secondary }}>{r.text}</span>
                  <Mono style={{ fontSize: 10.5 }}>{fmtRel(r.ts)}</Mono>
                </div>
              ))}
              {(detail?.activity ?? []).length === 0 && <Mono>No recent activity.</Mono>}
            </div>
          )}
        </div>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "13px 20px", borderTop: `1px solid ${T.borderSubtle}` }}>
          <span style={{ display: "inline-flex", alignItems: "center", gap: 7 }}>
            <span style={{ width: 7, height: 7, borderRadius: "50%", background: active.on ? T.success : T.borderDefault }} />
            <Mono style={{ fontSize: 11.5 }}>{active.on ? "active" : "idle"}</Mono>
          </span>
          <div style={{ display: "flex", gap: 9 }}>
            <Btn onClick={onClose}>Cancel</Btn>
            {isLive && (
              <Btn onClick={revert} disabled={isDefault || saving}>
                Revert to default
              </Btn>
            )}
            <Btn variant="primary" onClick={save} disabled={(!isLive && !dirty) || saving}>
              {saving ? "Saving…" : dirty ? "Save prompt" : "Saved"}
            </Btn>
          </div>
        </div>
      </div>
    </div>
  );
}

export function ClientModal({
  client,
  onClose,
  onSaved,
}: {
  client?: AdminClient;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [name, setName] = React.useState(client?.name ?? "");
  const [initials, setInitials] = React.useState(client?.initials ?? "");
  const [projects, setProjects] = React.useState(String(client?.projects ?? 0));
  const [tickets, setTickets] = React.useState(String(client?.tickets ?? 0));
  const [spend, setSpend] = React.useState(client?.spend ?? "$0.00");
  const [last, setLast] = React.useState(client?.last_activity ?? "");
  const [busy, setBusy] = React.useState(false);
  const save = () => {
    const body = {
      name,
      initials: initials || name.slice(0, 2).toUpperCase(),
      projects: Number(projects) || 0,
      tickets: Number(tickets) || 0,
      spend,
      last_activity: last,
    };
    setBusy(true);
    const p = client
      ? api.adminUpdateClient(client.org_id, body)
      : api.adminCreateClient(body as any);
    p.then(() => {
      setBusy(false);
      onSaved();
      onClose();
    }).catch(() => setBusy(false));
  };
  return (
    <div style={overlay}>
      <div style={modalCard}>
        <div style={modalHeader}>
          <h2 style={{ font: `400 19px/1.2 ${T.display}`, color: T.fg, margin: 0 }}>{client ? "Edit organization" : "New organization"}</h2>
          <CloseBtn onClick={onClose} />
        </div>
        <div style={{ padding: "18px 20px", display: "flex", flexDirection: "column", gap: 14, overflow: "auto" }}>
          <Field label="Organization name">
            <TextInput value={name} onChange={setName} placeholder="Acme Industrial Supply" />
          </Field>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
            <Field label="Initials">
              <TextInput value={initials} onChange={setInitials} placeholder="AC" />
            </Field>
            <Field label="Total spend">
              <TextInput value={spend} onChange={setSpend} placeholder="$0.00" />
            </Field>
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
            <Field label="Active projects">
              <TextInput type="number" value={projects} onChange={setProjects} />
            </Field>
            <Field label="In-flight tickets">
              <TextInput type="number" value={tickets} onChange={setTickets} />
            </Field>
          </div>
          <Field label="Last activity">
            <TextInput value={last} onChange={setLast} placeholder="—" />
          </Field>
          <div style={{ display: "flex", justifyContent: "flex-end", gap: 10, marginTop: 4 }}>
            <Btn onClick={onClose}>Cancel</Btn>
            <Btn variant="primary" onClick={save} disabled={!name || busy}>
              {busy ? "Saving…" : client ? "Save" : "Create"}
            </Btn>
          </div>
        </div>
      </div>
    </div>
  );
}

export function AgentModal({
  agent,
  onClose,
  onSaved,
}: {
  agent?: AdminAgent;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [callsign, setCallsign] = React.useState(agent?.callsign ?? "");
  const [sign, setSign] = React.useState(agent?.sign ?? "");
  const [role, setRole] = React.useState(agent?.role ?? "");
  const [desc, setDesc] = React.useState(agent?.desc ?? "");
  const [model, setModel] = React.useState(agent?.model ?? "");
  const [cost, setCost] = React.useState(String(agent?.cost_tier ?? 2));
  const [success, setSuccess] = React.useState(String(agent?.success ?? 90));
  const [on, setOn] = React.useState(agent?.on ?? true);
  const [busy, setBusy] = React.useState(false);
  const save = () => {
    const body: any = {
      callsign,
      sign,
      role,
      desc,
      model,
      cost_tier: Number(cost) || 2,
      success: Number(success) || 90,
      on,
    };
    setBusy(true);
    const p = agent ? api.adminUpdateAgent(agent.callsign, body) : api.adminCreateAgent(body);
    p.then(() => {
      setBusy(false);
      onSaved();
      onClose();
    }).catch(() => setBusy(false));
  };
  return (
    <div style={overlay}>
      <div style={modalCard}>
        <div style={modalHeader}>
          <h2 style={{ font: `400 19px/1.2 ${T.display}`, color: T.fg, margin: 0 }}>{agent ? "Edit agent" : "New agent"}</h2>
          <CloseBtn onClick={onClose} />
        </div>
        <div style={{ padding: "18px 20px", display: "flex", flexDirection: "column", gap: 14, overflow: "auto" }}>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
            <Field label="Callsign">
              <TextInput value={callsign} onChange={setCallsign} placeholder="AGENT.ROLE" disabled={!!agent} />
            </Field>
            <Field label="Sign / codename">
              <TextInput value={sign} onChange={setSign} placeholder="CODENAME" />
            </Field>
          </div>
          <Field label="Role / display name">
            <TextInput value={role} onChange={setRole} placeholder="e.g. Design Lead" />
          </Field>
          <Field label="Description">
            <TextInput value={desc} onChange={setDesc} placeholder="Short responsibility summary" />
          </Field>
          <div style={{ display: "grid", gridTemplateColumns: "2fr 1fr 1fr", gap: 12 }}>
            <Field label="Model">
              <TextInput value={model} onChange={setModel} placeholder="claude-sonnet-4" />
            </Field>
            <Field label="Cost tier (1-3)">
              <TextInput type="number" value={cost} onChange={setCost} />
            </Field>
            <Field label="Success %">
              <TextInput type="number" value={success} onChange={setSuccess} />
            </Field>
          </div>
          <label style={{ display: "flex", alignItems: "center", gap: 8, font: `500 13px/1 ${T.sans}`, color: T.fg }}>
            <input type="checkbox" checked={on} onChange={(e) => setOn(e.target.checked)} />
            Active
          </label>
          <div style={{ display: "flex", justifyContent: "flex-end", gap: 10, marginTop: 4 }}>
            <Btn onClick={onClose}>Cancel</Btn>
            <Btn variant="primary" onClick={save} disabled={!callsign || !role || busy}>
              {busy ? "Saving…" : agent ? "Save" : "Create"}
            </Btn>
          </div>
        </div>
      </div>
    </div>
  );
}

export function ToolModal({
  tool,
  onClose,
  onSaved,
}: {
  tool?: AdminTool;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [name, setName] = React.useState(tool?.name ?? "");
  const [configText, setConfigText] = React.useState(tool ? JSON.stringify(tool.config, null, 2) : "{\n  \n}");
  const [attachedText, setAttachedText] = React.useState((tool?.attached_to ?? []).join(", "));
  const [configError, setConfigError] = React.useState<string | null>(null);
  const [busy, setBusy] = React.useState(false);
  const [keyValue, setKeyValue] = React.useState("");
  const [keyShow, setKeyShow] = React.useState(false);
  const [keyBusy, setKeyBusy] = React.useState(false);

  const save = () => {
    let config: Record<string, unknown>;
    try {
      config = JSON.parse(configText);
    } catch (e: any) {
      setConfigError(e.message || "invalid JSON");
      return;
    }
    setConfigError(null);
    const attached_to = attachedText.split(",").map((s) => s.trim()).filter(Boolean);
    setBusy(true);
    const p = tool ? api.adminUpdateTool(tool.name, { config, attached_to })
                  : api.adminCreateTool({ name, config, attached_to });
    p.then(() => {
      setBusy(false);
      onSaved();
      onClose();
    }).catch((err) => { setBusy(false); setConfigError(err.message || "save failed"); });
  };

  const setKey = () => {
    if (!tool || !keyValue.trim()) return;
    setKeyBusy(true);
    api.adminSetToolKey(tool.name, keyValue).then(() => {
      setKeyBusy(false);
      setKeyValue("");
      onSaved();
    }).catch(() => setKeyBusy(false));
  };
  const removeKey = () => {
    if (!tool) return;
    setKeyBusy(true);
    api.adminDeleteToolKey(tool.name).then(() => { setKeyBusy(false); onSaved(); }).catch(() => setKeyBusy(false));
  };

  return (
    <div style={overlay}>
      <div style={modalCard}>
        <div style={modalHeader}>
          <h2 style={{ font: `400 19px/1.2 ${T.display}`, color: T.fg, margin: 0 }}>{tool ? "Edit tool" : "Register tool"}</h2>
          <CloseBtn onClick={onClose} />
        </div>
        <div style={{ padding: "18px 20px", display: "flex", flexDirection: "column", gap: 14, overflow: "auto" }}>
          <Field label="Tool / server name">
            <TextInput value={name} onChange={setName} placeholder="e.g. exa" disabled={!!tool} />
          </Field>
          <Field label='Config (JSON — the exact .mcp.json server block, or {"kind":"api",...})'>
            <textarea
              value={configText}
              onChange={(e) => setConfigText(e.target.value)}
              rows={8}
              spellCheck={false}
              style={{
                width: "100%",
                borderRadius: T.rMd,
                border: `1px solid ${configError ? T.danger : T.borderDefault}`,
                background: T.raised,
                padding: "9px 11px",
                font: `500 12px/1.5 ${T.mono}`,
                color: T.fg,
                resize: "vertical",
              }}
            />
            {configError && <Mono style={{ color: T.danger, marginTop: 4, display: "block" }}>{configError}</Mono>}
          </Field>
          <Field label="Attached to (comma-separated — system_agents callsigns / pipeline nodes)">
            <TextInput value={attachedText} onChange={setAttachedText} placeholder="STAGE-1, STAGE-2, STAGE-3, CONCIERGE" />
          </Field>
          {tool && (
            <Field label="Key">
              <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 8 }}>
                <Mono style={{ color: tool.has_key ? T.fg : T.tertiary }}>
                  {tool.has_key ? `••••••${tool.key_last4}` : "no key attached"}
                </Mono>
                {tool.has_key && (
                  <button onClick={removeKey} disabled={keyBusy}
                    style={{ font: `500 11px/1 ${T.sans}`, color: T.danger, border: "none", background: "transparent", cursor: "pointer" }}>
                    Remove
                  </button>
                )}
              </div>
              <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                <div style={{ position: "relative", flex: 1 }}>
                  <TextInput type={keyShow ? "text" : "password"} value={keyValue} onChange={setKeyValue}
                    placeholder={tool.has_key ? "replace with a new value" : "paste key value"} style={{ paddingRight: 40 }} />
                  <button onClick={() => setKeyShow(!keyShow)}
                    style={{ position: "absolute", right: 8, top: 8, border: "none", background: "transparent", cursor: "pointer", font: `500 11px/1 ${T.sans}`, color: T.secondary }}>
                    {keyShow ? "hide" : "show"}
                  </button>
                </div>
                <Btn size="md" onClick={setKey} disabled={!keyValue.trim() || keyBusy}>
                  {tool.has_key ? "Replace" : "Set key"}
                </Btn>
              </div>
            </Field>
          )}
          <div style={{ display: "flex", justifyContent: "flex-end", gap: 10, marginTop: 4 }}>
            <Btn onClick={onClose}>Cancel</Btn>
            <Btn variant="primary" onClick={save} disabled={!name || busy}>
              {busy ? "Saving…" : tool ? "Save" : "Register"}
            </Btn>
          </div>
        </div>
      </div>
    </div>
  );
}
