// Concierge.tsx — the one shared ProjectConcierge dock. SOF-246 made it context-aware; SOF-247
// replaces the Feed/Tray/Latest toggle + the detached "Recent activity" block with ONE chronological
// conversation: persisted customer/Concierge messages and persisted system events, interleaved by
// time (routine lifecycle = compact neutral row; attention/failure = restrained marker + expandable
// truthful detail; artifact-created = "Open output"). The normalization is the shared, reusable
// `eventTimeline` module (SOF-249's Activity mode consumes the same projection).
//
// display_context (SOF-246) is per-turn ephemeral send-time grounding — it is NEVER a timeline item.
import { useEffect, useRef, useState } from "react";
import { T, Icon, Sparkle, Composer, Message, CategoryLabel, StatusPill, WorkingPill, QuickReplies } from "../onboarding/design";
import { api, ProjectEvent } from "../../api";
import { linkify } from "../../linkify";
import { ArtifactRef } from "./Artifacts";
// SOF-245: the Factory Outputs peer publishes the artifact/stage the customer is currently reading;
// the concierge relays it as ephemeral display context for the next turn (never persisted, never
// alters memory retrieval).
import { useDisplayContext } from "./displayContext";
import { ChatMsg, TimelineItem, buildTimeline, collapseConsecutive } from "./eventTimeline";

// SOF-246: one shared Concierge, one identity — a single `context` value drives copy + display
// grounding on every peer. Only subtitle, chips, and the build-only Steer helper change.
type Ctx = "overview" | "brief" | "outputs" | "build" | "files" | "maintenance" | "ingesting";
const CTX: Record<Ctx, { subtitle: string; chips: string[]; steer?: boolean }> = {
  overview: { subtitle: "Watching this project", chips: ["How's the build going?", "What's left to do?", "Any blockers?"] },
  brief: { subtitle: "Working from your brief", chips: ["Explain this section", "Revise the brief in my words", "What changed in the latest version?"] },
  outputs: { subtitle: "Across the factory's work", chips: ["Explain this output", "How does this relate to the brief?", "What should I look at next?"] },
  build: { subtitle: "Relaying the build", chips: ["Summarize progress", "What's blocking the build?", "Reprioritize a ticket"], steer: true },
  files: { subtitle: "Across your source material", chips: ["What's in this material?", "Which file covers approvals?", "Where should an agent look first?"] },
  maintenance: { subtitle: "Watching the delivered project", chips: ["What changed since delivery?", "Anything to watch?", "How do I request a change?"] },
  ingesting: { subtitle: "Processing in background", chips: ["What are you reading?", "What happens next?", "How long will this take?"] },
};

// The EPHEMERAL display grounding string sent as ChatIn.display_context (#446): "Viewing …" prompt
// grounding injected into that one turn only, NEVER persisted, NEVER a retrieval boundary. Files
// deliberately makes NO scoped-retrieval claim (SOF-237 operator decision).
function displayContextStr(context: Ctx, selectedLabel?: string): string {
  switch (context) {
    case "brief": return `Viewing the Product brief${selectedLabel ? ` — section: ${selectedLabel}` : ""}`;
    case "outputs": return `Viewing factory outputs${selectedLabel ? `: ${selectedLabel}` : ""}`;
    case "build": return "Viewing the Factory console (the live build)";
    case "files": return `Viewing source material${selectedLabel ? `: ${selectedLabel}` : ""}`;
    case "maintenance": return "Viewing post-delivery maintenance";
    case "ingesting": return "On the project home while uploads process";
    default: return "Viewing the project overview";
  }
}

// One system-event row in the timeline. Routine = compact neutral line; attention/failure = a
// restrained left-accent marker with the truthful detail expandable; artifact events get "Open
// output" (routed through the real artifact ref when one matches by path/title).
function EventRow({ item, artifacts, onOpenArtifact }:
  { item: Extract<TimelineItem, { kind: "event" }>; artifacts: ArtifactRef[]; onOpenArtifact: (a: ArtifactRef) => void }) {
  const tone = item.severity === "failure" ? T.danger : item.severity === "attention" ? T.warning : T.tertiary;
  const icon = item.type === "done" ? "check" : item.severity !== "routine" ? "x" : "layers";
  const openOutput = item.artifact
    ? () => {
        const match = artifacts.find((a) => (item.artifact!.path && a.path === item.artifact!.path)
          || (item.artifact!.title && a.label === item.artifact!.title));
        onOpenArtifact(match || ({ label: item.artifact!.title || item.label, path: item.artifact!.path, url: item.artifact!.url } as ArtifactRef));
      }
    : undefined;
  // routine `done` carries a live URL in detail — show it inline; other routine detail stays inline too.
  const inline = item.severity === "routine" && item.detail ? `${item.label}: ${item.detail}` : item.label;
  const head = (
    <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "6px 9px", borderRadius: T.rMd, background: T.sunken,
      borderLeft: item.severity !== "routine" ? `3px solid ${tone}` : undefined }}>
      <Icon name={icon} size={12} color={tone} />
      <span style={{ flex: 1, minWidth: 0, font: `400 11.5px/1.35 ${T.sans}`, color: item.severity === "routine" ? T.secondary : T.fg }}>
        {linkify(inline)}{item.count && item.count > 1 ? ` ·×${item.count}` : ""}
      </span>
      {openOutput && (
        <button onClick={openOutput} style={{ border: 0, background: "none", color: T.brandDeep, cursor: "pointer", font: `600 10.5px/1 ${T.sans}`, flexShrink: 0 }}>Open output</button>
      )}
    </div>
  );
  // attention/failure with a reason → expandable truthful detail (never a plausible guess).
  if (item.detail && item.severity !== "routine") {
    return (
      <details>
        <summary style={{ listStyle: "none", cursor: "pointer" }}>{head}</summary>
        <div style={{ padding: "6px 12px 8px 24px", font: `400 11px/1.45 ${T.sans}`, color: T.tertiary, whiteSpace: "pre-wrap" }}>{linkify(item.detail)}</div>
      </details>
    );
  }
  return head;
}

export function Concierge({ projectId, projectName, artifacts, onOpenArtifact, isBuilding,
  ticketsDone, ticketsTotal, buildDone, deployed, phase,
  context = "build", selectedLabel, docChips, onMinimize }:
  { projectId: string; projectName?: string; artifacts: ArtifactRef[];
    onOpenArtifact: (a: ArtifactRef) => void; isBuilding?: boolean;
    ticketsDone?: number; ticketsTotal?: number; buildDone?: boolean; deployed?: boolean; phase?: string;
    // SOF-246: the active Project Console peer drives copy + display grounding. `selectedLabel` is the
    // selected heading/artifact/file when a peer has one; `docChips` overrides the Files chips.
    // SOF-248: the shell owns the minimize preference; `onMinimize` collapses the dock. When set,
    // the header shows one labelled Minimize control.
    context?: Ctx; selectedLabel?: string; docChips?: string[]; onMinimize?: () => void }) {
  const ctx = CTX[context];
  const subtitle = context === "build" && buildDone ? "Build complete" : ctx.subtitle;
  const chips = context === "files" && docChips && docChips.length ? docChips : ctx.chips;
  const [messages, setMessages] = useState<ChatMsg[]>([]);
  const [events, setEvents] = useState<ProjectEvent[]>([]);
  const [draft, setDraft] = useState("");
  const [sending, setSending] = useState(false);
  const [sendErr, setSendErr] = useState("");
  const feedRef = useRef<HTMLDivElement>(null);
  // Only relay display context for THIS project (the store is app-global).
  const dc = useDisplayContext();
  const displayCtx = dc && dc.projectId === projectId ? dc : null;

  // SOF-90: history includes the tool-call trace (msg_type tool_call/tool_result) so the model can
  // ground its self-reports; those are internal plumbing — buildTimeline filters them out.
  const loadHistory = () => api.chatHistory(projectId)
    .then((d) => setMessages((d.messages || []) as ChatMsg[]))
    .catch(() => {});

  useEffect(() => {
    let live = true;
    loadHistory();
    // Persisted run activity for the timeline. SOF-247 AC: do NOT truncate at the Concierge boundary
    // — render every persisted event the API returns; buildTimeline orders them and the feed scrolls.
    const tick = () => api.events(projectId).then((d) => live && setEvents(d.events || [])).catch(() => {});
    tick();
    const h = setInterval(tick, 4000);
    return () => { live = false; clearInterval(h); };
  }, [projectId]);

  const timeline = collapseConsecutive(buildTimeline(messages, events));

  useEffect(() => { if (feedRef.current) feedRef.current.scrollTop = feedRef.current.scrollHeight; }, [timeline.length]);

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
        // display_context is ephemeral per-turn grounding — injected into THIS turn's prompt only,
        // never persisted, never a retrieval boundary (never a timeline item). Most-specific-wins:
        // the actively-viewed artifact's summary (#446's useDisplayContext store) when one is open,
        // else the shared dock's per-peer string (SOF-246: context + selectedLabel). One always resolves.
        { project_id: projectId, project_name: projectName || "", message: msg,
          display_context: displayCtx ? displayCtx.summary : displayContextStr(context, selectedLabel) },
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
          // /api/chat is non-streaming: one `done` event carries the full reply (chat_dock.py).
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

  return (
    <aside style={{ display: "flex", flexDirection: "column", height: "100%", minHeight: 0 }}>
      {/* ── header band ── */}
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
          <CategoryLabel style={{ fontSize: 10 }}>{subtitle}</CategoryLabel>
          {selectedLabel && <span style={{ display: "block", marginTop: 2, font: `500 10px/1.2 ${T.mono}`, color: T.brandDeep, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>◆ {selectedLabel}</span>}
        </div>
        {sending ? <WorkingPill label="Thinking" /> : isBuilding ? <WorkingPill /> : <StatusPill tone="success">online</StatusPill>}
        {onMinimize && (
          <button onClick={onMinimize} aria-label="Minimize Concierge" title="Minimize Concierge"
            style={{ display: "grid", placeItems: "center", width: 26, height: 26, borderRadius: T.rMd, flexShrink: 0,
              border: `1px solid ${T.borderSubtle}`, background: T.raised, cursor: "pointer", color: T.secondary }}>
            <Icon name="chevronRight" size={14} color={T.secondary} />
          </button>
        )}
      </div>

      {/* ── ONE chronological conversation: messages + system events, time-ordered (SOF-247) ── */}
      <div ref={feedRef} style={{ flex: 1, minHeight: 0, overflowY: "auto", padding: "12px 16px",
        display: "flex", flexDirection: "column", gap: 10 }}>
        {timeline.length === 0 && !sending && (
          <Message who="agent" text="I'm watching this project — I'll relay build updates and answer your questions here." anim />
        )}
        {timeline.map((it, i) => it.kind === "message"
          ? <Message key={i} who={it.role} text={it.text} />
          : <EventRow key={i} item={it} artifacts={artifacts} onOpenArtifact={onOpenArtifact} />)}
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
        {!sending && (
          <div style={{ display: "flex", flexDirection: "column", gap: 7 }}>
            <CategoryLabel>Try asking</CategoryLabel>
            <QuickReplies options={chips} onPick={(o) => steer(o)} />
          </div>
        )}
        {ctx.steer && (
          <div style={{ padding: 11, borderRadius: T.rLg, border: `1px solid ${T.brand}33`, background: T.brandSoft + "66" }}>
            <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 5 }}>
              <Sparkle size={11} color={T.brandDeep} /><CategoryLabel tone="brand">Steer the build</CategoryLabel>
            </div>
            <p style={{ font: `400 12px/1.5 ${T.sans}`, color: T.secondary, margin: 0 }}>
              Ask me to reprioritize a ticket, change scope, or pause an agent — I'll pass it straight to the build team.
            </p>
          </div>
        )}
      </div>

      {/* ── composer band ── */}
      <div style={{ flexShrink: 0, padding: "12px 16px", borderTop: `1px solid ${T.borderSubtle}` }}>
        {/* SOF-245: show the customer that the concierge can see what they're reading — so asking
            "explain this" is grounded, and the context relay is a visible affordance, not silent. */}
        {displayCtx && (
          <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 7, padding: "5px 9px",
            borderRadius: T.rMd, background: T.brandSoft + "66", border: `1px solid ${T.brand}33` }}>
            <Icon name="file" size={12} color={T.brandDeep} />
            <span style={{ font: `400 11px/1.35 ${T.sans}`, color: T.secondary, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
              Viewing <strong style={{ color: T.fg }}>{displayCtx.title}</strong> · {displayCtx.stageLabel}
            </span>
          </div>
        )}
        {sendErr && <span style={{ display: "block", marginBottom: 6, font: `400 11.5px/1.4 ${T.sans}`, color: T.danger }}>{sendErr}</span>}
        <Composer placeholder="Ask or steer the build team…" value={draft} onChange={setDraft} onSend={() => steer()} loading={sending} />
      </div>
    </aside>
  );
}
