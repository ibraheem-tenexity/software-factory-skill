// Concierge.tsx — the left rail. v1 is relay/observe + steer:
//   · the design's ConciergeHeader band (concierge.jsx): 30px sparkle avatar with a pulsing green
//     presence dot, "Concierge" + context subtitle, online StatusPill vs Working pill.
//   · prior Concierge conversation (GET /api/chat/{id}/history → {messages:[{role,content,ts}]})
//     rendered through the shared Message primitive — plus 1-2 status bubbles synthesized from the
//     LIVE build state (tickets done, blocker heads-up from real events) so the rail always relays
//     the build and the feed is never blank.
//   · recent real run activity (GET /api/projects/{id}/events → {events:[{ts,type,payload}]})
//   · QuickReplies suggestion chips + the "Steer the build" promo card (design: concierge.jsx
//     ProjectConcierge), and a steer composer that POSTs to /api/chat (api.chat).
//   · the produced-artifacts list (passed in from the real graph).
//   · Feed / Tray / Latest view toggle to switch between conversation, artifacts, and activity.
import { useEffect, useRef, useState } from "react";
import { T, Icon, Sparkle, Composer, Message, CategoryLabel, StatusPill, WorkingPill, QuickReplies } from "../onboarding/design";
import { api, ProjectEvent } from "../../api";
import { ArtifactList, ArtifactRef } from "./Artifacts";

type ChatMsg = { role: string; content: string; ts: number; msg_type?: string };
type Rail = "feed" | "tray" | "latest";

const RAIL_TABS: { id: Rail; label: string }[] = [
  { id: "feed", label: "Feed" },
  { id: "tray", label: "Tray" },
  { id: "latest", label: "Latest" },
];

const SUGGESTIONS = ["Summarize progress", "What's blocking the build?", "Reprioritize a ticket"];

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

// 1-2 relay bubbles derived ONLY from real state (design copy tone: buildprogress.jsx:84-96).
function synthBubbles(args: { buildDone?: boolean; deployed?: boolean; ticketsDone?: number;
  ticketsTotal?: number; phase?: string; events: ProjectEvent[] }): string[] {
  const { buildDone, deployed, ticketsDone = 0, ticketsTotal = 0, phase, events } = args;
  const out: string[] = [];
  if (buildDone) {
    out.push(ticketsTotal > 0
      ? `All ${ticketsTotal} tickets are green${deployed ? " and the app is deployed" : ""}. Ask me anything about the build.`
      : `The build is complete${deployed ? " and the app is deployed" : ""}. Ask me anything about it.`);
  } else if (ticketsTotal > 0) {
    out.push(`Build is underway — ${ticketsDone}/${ticketsTotal} tickets done. I'll relay updates from the build team here.`);
  } else if (phase) {
    out.push(`The factory is working — the run is in the ${phase} phase. I'll relay updates here as they land.`);
  } else {
    out.push("I'm watching this project — I'll relay build updates here as they land.");
  }
  const blocker = events.find((e) => e.type === "blocker" && e.payload?.what);
  if (blocker) out.push(`Heads up: ${blocker.payload.what} — the build team has it flagged.`);
  return out.slice(0, 2);
}

export function Concierge({ projectId, projectName, artifacts, onOpenArtifact, isBuilding,
  ticketsDone, ticketsTotal, buildDone, deployed, phase }:
  { projectId: string; projectName?: string; artifacts: ArtifactRef[];
    onOpenArtifact: (a: ArtifactRef) => void; isBuilding?: boolean;
    ticketsDone?: number; ticketsTotal?: number; buildDone?: boolean; deployed?: boolean; phase?: string }) {
  const [messages, setMessages] = useState<ChatMsg[]>([]);
  const [events, setEvents] = useState<ProjectEvent[]>([]);
  const [draft, setDraft] = useState("");
  const [sending, setSending] = useState(false);
  const [sendErr, setSendErr] = useState("");
  const [rail, setRail] = useState<Rail>("feed");
  const feedRef = useRef<HTMLDivElement>(null);

  // SOF-90: the concierge now persists its real tool-call trace, and /api/chat/{id}/history returns
  // it (rows tagged msg_type "tool_call"/"tool_result") so the model can ground its self-reports.
  // Those are internal plumbing — hide them from the user's chat feed; the concierge reports what it
  // did in prose when asked. Only "text" utterances are shown.
  const loadHistory = () => api.chatHistory(projectId)
    .then((d) => setMessages(((d.messages || []) as ChatMsg[])
      .filter((m) => m.msg_type !== "tool_call" && m.msg_type !== "tool_result")))
    .catch(() => {});

  useEffect(() => {
    let live = true;
    loadHistory();
    const tick = () => api.events(projectId).then((d) => live && setEvents((d.events || []).slice(-8).reverse())).catch(() => {});
    tick();
    const h = setInterval(tick, 4000);
    return () => { live = false; clearInterval(h); };
  }, [projectId]);

  useEffect(() => { if (feedRef.current) feedRef.current.scrollTop = feedRef.current.scrollHeight; }, [messages]);

  const steer = async (text?: string) => {
    const msg = (text ?? draft).trim();
    if (!msg || sending) return;
    setSending(true);
    setSendErr("");
    setMessages((m) => [...m, { role: "user", content: msg, ts: Date.now() / 1000 }]);
    setDraft("");
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), 90_000);
    try {
      const resp = await api.chatStream(
        { project_id: projectId, project_name: projectName || "", message: msg },
        ctrl.signal,
      );
      const reader = resp.body!.getReader();
      const decoder = new TextDecoder();
      let buf = "";
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buf += decoder.decode(value, { stream: true });
        const lines = buf.split("\n");
        buf = lines.pop()!;
        for (const line of lines) {
          if (!line.trim()) continue;
          const evt = JSON.parse(line);
          // /api/chat is NON-streaming: ChatAgent.run() is one call, so the backend emits a single
          // `done` event carrying the full reply (chat_dock.py). The `sending` typing indicator
          // covers the wait; the real assistant message(s) land here on done. No token deltas.
          if (evt.type === "done") {
            setMessages((m) => [...m, ...(evt.messages || []) as ChatMsg[]]);
          } else if (evt.type === "error") {
            setSendErr(evt.detail || "Message failed — try again.");
          }
        }
      }
    } catch (e: any) {
      setSendErr(ctrl.signal.aborted ? "Response timed out — try again." : String(e?.message || "Message failed — try again."));
    } finally {
      clearTimeout(timer);
      setSending(false);
    }
  };

  const synth = synthBubbles({ buildDone, deployed, ticketsDone, ticketsTotal, phase, events });

  return (
    <aside style={{ display: "flex", flexDirection: "column", height: "100%", minHeight: 0 }}>
      {/* ── header band (design: concierge.jsx ConciergeHeader) ── */}
      <div style={{ display: "flex", alignItems: "center", gap: 9, padding: "14px 18px",
        borderBottom: `1px solid ${T.borderSubtle}`, flexShrink: 0 }}>
        <span style={{ position: "relative", width: 30, height: 30, borderRadius: "50%", display: "grid", placeItems: "center",
          background: T.brandSoft, color: T.brand, boxShadow: `inset 0 0 0 1px ${T.brand}33` }}>
          <Sparkle size={14} color={T.brand} />
          <span style={{ position: "absolute", right: -1, bottom: -1, width: 9, height: 9, borderRadius: "50%",
            background: T.success, boxShadow: `0 0 0 2px ${T.raised}`, animation: "sfPulse 1.6s ease-in-out infinite" }} />
        </span>
        <div style={{ flex: 1, minWidth: 0 }}>
          <span style={{ display: "block", font: `600 13px/1.2 ${T.sans}`, color: T.fg }}>Concierge</span>
          <CategoryLabel style={{ fontSize: 10 }}>{buildDone ? "Build complete" : "Relaying the build"}</CategoryLabel>
        </div>
        {sending ? <WorkingPill label="Thinking" /> : isBuilding ? <WorkingPill /> : <StatusPill tone="success">online</StatusPill>}
      </div>

      {/* Feed / Tray / Latest toggle */}
      <div style={{ display: "flex", gap: 2, background: T.sunken, borderRadius: T.rMd, padding: 3, margin: "10px 16px 0", flexShrink: 0 }}>
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
        <div ref={feedRef} style={{ flex: 1, minHeight: 0, overflowY: "auto", padding: "12px 16px",
          display: "flex", flexDirection: "column", gap: 12 }}>
          {/* status bubbles synthesized from the live run — the rail relays the build, never blank */}
          {synth.map((text, i) => <Message key={`s${i}`} who="agent" text={text} anim={i === 0} />)}
          {messages.map((m, i) => (
            <Message key={i} who={m.role === "assistant" ? "agent" : "user"} text={m.content} />
          ))}
          {/* typing indicator while the (non-streaming) turn is in flight — the reply arrives as a
              single done event, so without this the feed would sit blank with no waiting state */}
          {sending && (
            <article style={{ display: "flex", gap: 10 }}>
              <span style={{ marginTop: 1, width: 28, height: 28, flexShrink: 0, borderRadius: "50%", display: "grid", placeItems: "center",
                background: T.brandSoft, color: T.brand, boxShadow: `inset 0 0 0 1px ${T.brand}33` }}><Sparkle size={13} color={T.brand} /></span>
              <div style={{ display: "inline-flex", alignItems: "center", gap: 5, border: `1px solid ${T.brand}33`,
                background: T.brandSoft + "4d", borderRadius: T.rLg, padding: "13px 14px" }}>
                {[0, 1, 2].map((i) => (
                  <span key={i} style={{ width: 6, height: 6, borderRadius: "50%", background: T.brand,
                    animation: "sfPulse 1.2s ease-in-out infinite", animationDelay: `${i * 0.18}s` }} />
                ))}
              </div>
            </article>
          )}
          {events.length > 0 && (
            <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
              <span style={{ font: `500 10px/1 ${T.sans}`, letterSpacing: "0.1em", textTransform: "uppercase", color: T.tertiary, padding: "2px 0" }}>Recent activity</span>
              {events.map((e, i) => (
                <div key={i} style={{ display: "flex", alignItems: "center", gap: 8, padding: "5px 8px", borderRadius: T.rMd, background: T.sunken }}>
                  <Icon name={EVENT_ICON[e.type] || "dots"} size={12} color={e.type === "blocker" ? T.danger : e.type === "done" ? T.success : T.tertiary} />
                  <span style={{ font: `400 11.5px/1.35 ${T.sans}`, color: T.secondary }}>{eventText(e)}</span>
                </div>
              ))}
            </div>
          )}
          {/* suggestion chips (design: concierge.jsx QuickReplies, build context) */}
          {!sending && (
            <div style={{ display: "flex", flexDirection: "column", gap: 7 }}>
              <CategoryLabel>Try asking</CategoryLabel>
              <QuickReplies options={SUGGESTIONS} onPick={(o) => steer(o)} />
            </div>
          )}
          {/* Steer-the-build promo card (design: concierge.jsx ProjectConcierge) */}
          <div style={{ padding: 11, borderRadius: T.rLg, border: `1px solid ${T.brand}33`, background: T.brandSoft + "66" }}>
            <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 5 }}>
              <Sparkle size={11} color={T.brandDeep} /><CategoryLabel tone="brand">Steer the build</CategoryLabel>
            </div>
            <p style={{ font: `400 12px/1.5 ${T.sans}`, color: T.secondary, margin: 0 }}>
              Ask me to reprioritize a ticket, change scope, or pause an agent — I'll pass it straight to the build team.
            </p>
          </div>
        </div>
      )}

      {rail === "tray" && (
        <div style={{ flex: 1, minHeight: 0, overflowY: "auto", padding: "12px 16px" }}>
          <ArtifactList artifacts={artifacts} onOpen={onOpenArtifact} />
        </div>
      )}

      {rail === "latest" && (
        <div style={{ flex: 1, minHeight: 0, overflowY: "auto", padding: "12px 16px", display: "flex", flexDirection: "column", gap: 4 }}>
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

      {/* ── composer band ── */}
      <div style={{ flexShrink: 0, padding: "12px 16px", borderTop: `1px solid ${T.borderSubtle}` }}>
        {sendErr && <span style={{ display: "block", marginBottom: 6, font: `400 11.5px/1.4 ${T.sans}`, color: T.danger }}>{sendErr}</span>}
        <Composer placeholder="Ask or steer the build team…" value={draft} onChange={setDraft} onSend={() => steer()} loading={sending} />
      </div>
    </aside>
  );
}
