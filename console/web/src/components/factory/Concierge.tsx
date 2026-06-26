// Concierge.tsx — the left rail. v1 is relay/observe + steer:
//   · prior Concierge conversation (GET /api/chat/{id}/history → {messages:[{role,content,ts}]})
//   · recent real run activity (GET /api/projects/{id}/events → {events:[{ts,type,payload}]})
//   · a steer composer that POSTs to /api/chat (api.chat) with the project_id so the operator can
//     nudge the build mid-flight.
//   · the produced-artifacts list (passed in from the real graph).
//   · Feed / Tray / Latest view toggle to switch between conversation, artifacts, and activity.
import { useEffect, useRef, useState } from "react";
import { T, Icon, Sparkle, Avatar, Composer } from "../onboarding/design";
import { api, ProjectEvent } from "../../api";
import { ArtifactList, ArtifactRef } from "./Artifacts";

type ChatMsg = { role: string; content: string; ts: number };
type Rail = "feed" | "tray" | "latest";

const RAIL_TABS: { id: Rail; label: string }[] = [
  { id: "feed", label: "Feed" },
  { id: "tray", label: "Tray" },
  { id: "latest", label: "Latest" },
];

const EVENT_ICON: Record<string, string> = { phase: "layers", artifact: "file", blocker: "x", done: "check" };
function eventText(e: ProjectEvent): string {
  const p = e.payload || {};
  switch (e.type) {
    case "phase": return `${p.name} → ${p.status}`;
    case "artifact": return `Produced ${p.title || p.path}`;
    case "blocker": return `Blocked: ${p.what}`;
    case "done": return `Verified live${p.url ? `: ${p.url}` : ""}`;
    default: return e.type;
  }
}

export function Concierge({ projectId, projectName, artifacts, onOpenArtifact, isBuilding }:
  { projectId: string; projectName?: string; artifacts: ArtifactRef[]; onOpenArtifact: (a: ArtifactRef) => void; isBuilding?: boolean }) {
  const [messages, setMessages] = useState<ChatMsg[]>([]);
  const [events, setEvents] = useState<ProjectEvent[]>([]);
  const [draft, setDraft] = useState("");
  const [sending, setSending] = useState(false);
  const [steerErr, setSteerErr] = useState("");
  const [rail, setRail] = useState<Rail>("feed");
  const feedRef = useRef<HTMLDivElement>(null);

  const loadHistory = () => api.chatHistory(projectId).then((d) => setMessages((d.messages || []) as ChatMsg[])).catch(() => {});

  useEffect(() => {
    let live = true;
    loadHistory();
    const tick = () => api.events(projectId).then((d) => live && setEvents((d.events || []).slice(-8).reverse())).catch(() => {});
    tick();
    const h = setInterval(tick, 4000);
    return () => { live = false; clearInterval(h); };
  }, [projectId]);

  useEffect(() => { if (feedRef.current) feedRef.current.scrollTop = feedRef.current.scrollHeight; }, [messages]);

  const steer = async () => {
    const text = draft.trim();
    if (!text || sending) return;
    setSending(true);
    setMessages((m) => [...m, { role: "user", content: text, ts: Date.now() / 1000 }]);
    setDraft("");
    try {
      const r = await api.chat({ project_id: projectId, project_name: projectName || "", message: text });
      const reply = (r.messages || []) as ChatMsg[];
      setMessages((m) => [...m, ...reply]);
      setSteerErr("");
    } catch (e: any) {
      setSteerErr(String(e?.message || "Message failed — try again."));
    } finally { setSending(false); }
  };

  return (
    <aside style={{ display: "flex", flexDirection: "column", gap: 10, height: "100%", minHeight: 0 }}>
      {/* header: icon + title + Working chip */}
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <span style={{ width: 26, height: 26, borderRadius: "50%", display: "grid", placeItems: "center",
          background: T.brandSoft, color: T.brand, boxShadow: `inset 0 0 0 1px ${T.brand}33` }}><Sparkle size={12} color={T.brand} /></span>
        <span style={{ font: `600 14px/1 ${T.sans}`, color: T.fg, flex: 1 }}>Concierge</span>
        {isBuilding && (
          <span style={{ display: "inline-flex", alignItems: "center", gap: 4, padding: "3px 7px", borderRadius: 99, background: T.brandSoft, border: `1px solid ${T.brand}33` }}>
            <span style={{ width: 6, height: 6, borderRadius: "50%", background: T.brand, flexShrink: 0, animation: "pulse 1.4s ease-in-out infinite" }} />
            <span style={{ font: `600 10px/1 ${T.mono}`, letterSpacing: "0.06em", color: T.brand }}>Working</span>
          </span>
        )}
      </div>

      {/* Feed / Tray / Latest toggle */}
      <div style={{ display: "flex", gap: 2, background: T.sunken, borderRadius: T.rMd, padding: 3 }}>
        {RAIL_TABS.map((t) => (
          <button key={t.id} onClick={() => setRail(t.id)}
            style={{ flex: 1, padding: "5px 0", borderRadius: T.rSm, border: "none", cursor: "pointer",
              background: rail === t.id ? T.raised : "transparent",
              font: `${rail === t.id ? 600 : 500} 12px/1 ${T.sans}`,
              color: rail === t.id ? T.fg : T.secondary,
              boxShadow: rail === t.id ? T.shadowXs : "none" }}>
            {t.label}
          </button>
        ))}
      </div>

      {/* main rail body */}
      {rail === "feed" && (
        <div ref={feedRef} style={{ flex: 1, minHeight: 0, overflowY: "auto", display: "flex", flexDirection: "column", gap: 10 }}>
          {messages.map((m, i) => (
            <article key={i} style={{ display: "flex", gap: 9 }}>
              {m.role === "assistant"
                ? <span style={{ marginTop: 1, width: 24, height: 24, flexShrink: 0, borderRadius: "50%", display: "grid", placeItems: "center", background: T.brandSoft, color: T.brand, boxShadow: `inset 0 0 0 1px ${T.brand}33` }}><Sparkle size={11} color={T.brand} /></span>
                : <Avatar name="You" size={24} />}
              <div style={{ flex: 1, minWidth: 0, border: `1px solid ${m.role === "assistant" ? T.brand + "33" : T.borderSubtle}`,
                background: m.role === "assistant" ? T.brandSoft + "4d" : T.raised, borderRadius: T.rLg, padding: "8px 11px" }}>
                <span style={{ font: `600 11px/1 ${T.sans}`, color: T.fg }}>{m.role === "assistant" ? "Concierge" : "You"}</span>
                <p style={{ margin: "5px 0 0", font: `400 12.5px/1.5 ${T.sans}`, color: m.role === "assistant" ? T.secondary : T.fg, whiteSpace: "pre-wrap" }}>{m.content}</p>
              </div>
            </article>
          ))}
          {events.length > 0 && (
            <div style={{ marginTop: 4, display: "flex", flexDirection: "column", gap: 4 }}>
              <span style={{ font: `500 10px/1 ${T.sans}`, letterSpacing: "0.1em", textTransform: "uppercase", color: T.tertiary, padding: "2px 0" }}>Recent activity</span>
              {events.map((e, i) => (
                <div key={i} style={{ display: "flex", alignItems: "center", gap: 8, padding: "5px 8px", borderRadius: T.rMd, background: T.sunken }}>
                  <Icon name={EVENT_ICON[e.type] || "dots"} size={12} color={e.type === "blocker" ? T.danger : e.type === "done" ? T.success : T.tertiary} />
                  <span style={{ font: `400 11.5px/1.35 ${T.sans}`, color: T.secondary }}>{eventText(e)}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {rail === "tray" && (
        <div style={{ flex: 1, minHeight: 0, overflowY: "auto" }}>
          <ArtifactList artifacts={artifacts} onOpen={onOpenArtifact} />
        </div>
      )}

      {rail === "latest" && (
        <div style={{ flex: 1, minHeight: 0, overflowY: "auto", display: "flex", flexDirection: "column", gap: 4 }}>
          {events.length === 0
            ? <span style={{ font: `400 12.5px/1.5 ${T.sans}`, color: T.tertiary }}>No activity yet.</span>
            : events.map((e, i) => (
              <div key={i} style={{ display: "flex", alignItems: "center", gap: 8, padding: "6px 9px", borderRadius: T.rMd, background: T.sunken }}>
                <Icon name={EVENT_ICON[e.type] || "dots"} size={12} color={e.type === "blocker" ? T.danger : e.type === "done" ? T.success : T.tertiary} />
                <span style={{ font: `400 12px/1.35 ${T.sans}`, color: T.secondary }}>{eventText(e)}</span>
              </div>
            ))}
        </div>
      )}

      {steerErr && (
        <span style={{ font: `500 11.5px/1.4 ${T.sans}`, color: T.secondary }}>{steerErr}</span>
      )}
      <div>
        <Composer placeholder="Steer the build…" value={draft} onChange={setDraft} onSend={steer} loading={sending} />
      </div>
    </aside>
  );
}
