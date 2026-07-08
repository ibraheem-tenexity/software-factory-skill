// InterviewView.tsx — Step 3 of Intake→Processing→Interview→Handoff. Deliberately JUST A CHAT BOX
// (operator architecture, 2026-07-02): all interview behavior lives in the Concierge's system
// prompt — the project context is in the agent's prompt/history server-side, the agent opens the
// conversation (an LLM replies with a question because that's what LLMs do), asks one question per
// turn, flags/resolves its own verification questions via tools, and STOPS when its prompt says it
// has enough (finalizing the product brief + inviting hand-off). No queue machinery, no readiness
// conditions computed here — the user decides when to hand off; the server's promote gate is the
// only gate.
import React, { useEffect, useRef, useState } from "react";
import { api, type ReflectionQuestion } from "../../api";
import { T, Icon, CategoryLabel, Wordmark, Btn, StatusPill, Message, Composer, SuggestedResponseList } from "./design";

// SOF-97: open verification flags the Concierge raised (flag_for_verification) block hand-off
// server-side. There is no agent-side resolve tool (removed on purpose), so the USER resolves
// them here — answer (records text) or dismiss (not needed) — via PATCH /reflection/{id}. This is
// the only path out of the hand-off gate, so it must always be reachable while a flag is open.
function OpenFlags({ items, onResolve }: {
  items: ReflectionQuestion[];
  onResolve: (id: string, action: "answer" | "dismiss", answer?: string) => Promise<void>;
}) {
  const [answering, setAnswering] = useState<string | null>(null);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const resolve = async (id: string, action: "answer" | "dismiss", answer?: string) => {
    setBusy(id);
    try { await onResolve(id, action, answer); setAnswering(null); setText(""); }
    finally { setBusy(null); }
  };
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 8, padding: "10px 12px", background: T.raised, border: `1px solid ${T.borderSubtle}`, borderRadius: 10 }}>
      <CategoryLabel tone="brand">{items.length} open question{items.length === 1 ? "" : "s"} — resolve to hand off</CategoryLabel>
      {items.map((q) => (
        <div key={q.id} style={{ display: "flex", flexDirection: "column", gap: 6, paddingTop: 6, borderTop: `1px solid ${T.borderSubtle}` }}>
          <span style={{ font: `400 12.5px/1.4 ${T.sans}`, color: T.fg }}>{q.fact}</span>
          {answering === q.id ? (
            <div style={{ display: "flex", gap: 6 }}>
              <input autoFocus value={text} onChange={(e) => setText(e.target.value)}
                onKeyDown={(e) => { if (e.key === "Enter" && text.trim()) resolve(q.id, "answer", text.trim()); }}
                placeholder="Your answer…"
                style={{ flex: 1, font: `400 12.5px/1.3 ${T.sans}`, color: T.fg, background: T.bg, border: `1px solid ${T.borderDefault}`, borderRadius: 8, padding: "6px 9px" }} />
              <Btn variant="primary" size="sm" onClick={() => text.trim() && resolve(q.id, "answer", text.trim())} disabled={busy === q.id || !text.trim()}>Save</Btn>
            </div>
          ) : (
            <div style={{ display: "flex", gap: 6 }}>
              <Btn variant="secondary" size="sm" onClick={() => { setAnswering(q.id); setText(""); }} disabled={busy === q.id}>Answer</Btn>
              <Btn variant="ghost" size="sm" onClick={() => resolve(q.id, "dismiss")} disabled={busy === q.id}>Dismiss</Btn>
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

type ChatTurn = { who: "user" | "agent"; text: string; suggested?: { response: string; type: "single select" | "multi select" }[] };

export function InterviewView({ draftId, projectName, onBack, onHandoff, submitting, error }: {
  draftId: string; projectName: string; goal?: string; onBack: () => void; onHandoff: () => void; submitting: boolean; error: string;
}) {
  const [turns, setTurns] = useState<ChatTurn[]>([]);
  const [thinking, setThinking] = useState(false);
  const [draft, setDraft] = useState("");
  const [openFlags, setOpenFlags] = useState<ReflectionQuestion[]>([]);
  const kickedOff = useRef(false);
  const scroller = useRef<HTMLDivElement | null>(null);

  // Pull the Concierge's open verification flags (SOF-97). Refreshed after each turn (the agent may
  // flag mid-conversation) and after a hand-off attempt, so the only path past the promote gate is
  // always visible while a flag is open.
  const refreshFlags = async () => {
    try {
      const b = await api.brief(draftId);
      setOpenFlags((b.reflection_questions || []).filter((q) => q.status === "open"));
    } catch { /* non-fatal — flags just won't show this cycle */ }
  };

  const send = async (text: string) => {
    const t = (text || "").trim();
    if (thinking) return;
    if (t) setTurns((x) => [...x, { who: "user", text: t }]);
    setDraft("");
    setThinking(true);
    try {
      // Empty message = "the agent opens" (the kickoff). Everything else is a normal turn.
      const r = await api.converse(draftId, t);
      setTurns((x) => [...x, { who: "agent", text: r.response, suggested: r.suggested_responses || [] }]);
    } catch {
      setTurns((x) => [...x, { who: "agent", text: "Something went wrong on that turn — say that again?" }]);
    } finally {
      setThinking(false);
      refreshFlags();
    }
  };

  useEffect(() => {
    if (!kickedOff.current) { kickedOff.current = true; send(""); }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [draftId]);

  // A failed hand-off (e.g. the open-questions 409) may be the first sign a flag is outstanding —
  // re-pull so the resolve affordances appear right when the user needs them.
  useEffect(() => { if (error) refreshFlags(); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [error]);

  useEffect(() => { const el = scroller.current; if (el) el.scrollTop = el.scrollHeight; }, [turns, thinking]);

  const last = turns[turns.length - 1];
  const started = turns.some((t) => t.who === "agent");

  return (
    <div style={{ height: "100%", display: "flex", flexDirection: "column", background: T.bg, fontFamily: T.sans }}>
      <div style={{ display: "flex", alignItems: "center", gap: 10, padding: "14px 24px", background: T.raised, borderBottom: `1px solid ${T.borderSubtle}`, flexShrink: 0 }}>
        <Btn variant="ghost" size="sm" onClick={onBack}><Icon name="arrowLeft" size={14} /> Setup</Btn>
        <Wordmark /><span style={{ color: T.tertiary }}>/</span>
        <span style={{ font: `600 13px/1.2 ${T.sans}`, color: T.fg }}>{projectName || "Untitled project"}</span>
        <span style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 10 }}>
          <StatusPill tone={thinking ? "info" : "success"}>{thinking ? "thinking" : "online"}</StatusPill>
          <span style={{ font: `600 11px/1 ${T.mono}`, color: T.tertiary, letterSpacing: "0.06em" }}>STEP 3 OF 3 · INTERVIEW</span>
        </span>
      </div>

      {/* the chat — the whole screen */}
      <div ref={scroller} style={{ flex: 1, overflow: "auto", padding: "28px 24px" }}>
        <div style={{ maxWidth: 720, margin: "0 auto", display: "flex", flexDirection: "column", gap: 14 }}>
          <CategoryLabel tone="brand">Materials processed · Interview</CategoryLabel>
          {turns.map((m, i) => (
            <div key={i} style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              <Message who={m.who} text={m.text} anim={i === turns.length - 1} />
              {m.who === "agent" && m === last && !thinking && (m.suggested?.length ?? 0) > 0 && (
                <div style={{ marginLeft: 35 }}>
                  <SuggestedResponseList options={m.suggested!} onSubmit={(values) => {
                    const joined = values.join(", ");
                    if (joined === "Hand off to the factory") onHandoff(); else send(joined);
                  }} />
                </div>
              )}
            </div>
          ))}
          {thinking && (
            <div style={{ display: "flex", alignItems: "center", gap: 8, font: `400 12.5px/1 ${T.sans}`, color: T.tertiary }}>
              <span className="sf-spin" style={{ display: "inline-flex" }}><Icon name="refresh" size={13} color={T.tertiary} /></span>
              {started ? "Thinking…" : "Reading your project and materials…"}
            </div>
          )}
        </div>
      </div>

      <div style={{ flexShrink: 0, borderTop: `1px solid ${T.borderSubtle}`, background: T.raised }}>
        <div style={{ maxWidth: 720, margin: "0 auto", padding: "12px 24px", display: "flex", flexDirection: "column", gap: 8 }}>
          {openFlags.length > 0 && (
            <OpenFlags items={openFlags} onResolve={async (id, action, answer) => {
              await api.resolveReflection(draftId, id, action, answer);
              await refreshFlags();
            }} />
          )}
          <Composer placeholder="Answer, ask, or add anything…" value={draft} onChange={setDraft} onSend={() => send(draft)} loading={thinking} />
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
            <span style={{ font: `400 12px/1.3 ${T.sans}`, color: error ? T.danger : T.tertiary }}>
              {error || "Hand off whenever you're ready — the Concierge will tell you when it has enough."}
            </span>
            <Btn variant="primary" size="sm" onClick={onHandoff} disabled={submitting || !started}>
              {submitting ? "Handing off…" : "Hand off to factory"} <Icon name="arrowRight" size={13} color="#fff" />
            </Btn>
          </div>
        </div>
      </div>
    </div>
  );
}
