// InterviewView.tsx — Step 3 of Intake→Processing→Interview→Handoff. Deliberately JUST A CHAT BOX
// (operator architecture, 2026-07-02; Minimum Machinery, SOF-137): all interview behavior lives in
// the Concierge's system prompt — the project context is in the agent's prompt/history
// server-side, the agent opens the conversation (an LLM replies with a question because that's
// what LLMs do), asks one question per turn, expresses any doubt IN CHAT (never a side-channel
// flag/gate/resolve UI), and STOPS when its prompt says it has enough (finalizing the product
// brief + inviting hand-off, or calling hand_off_to_factory itself). No queue machinery, no
// readiness conditions computed here — hand-off's only gate is a product brief existing.
import React, { useEffect, useRef, useState } from "react";
import { api } from "../../api";
import { T, Icon, CategoryLabel, Wordmark, Btn, StatusPill, Message, Composer, SuggestedResponseList } from "./design";

type ChatTurn = { who: "user" | "agent"; text: string; suggested?: { response: string; type: "single select" | "multi select" }[] };

export function InterviewView({ draftId, projectName, onBack, onHandoff, onPromoted, submitting, error }: {
  draftId: string; projectName: string; goal?: string; onBack: () => void; onHandoff: () => void; onPromoted: () => void; submitting: boolean; error: string;
}) {
  const [turns, setTurns] = useState<ChatTurn[]>([]);
  const [thinking, setThinking] = useState(false);
  const [draft, setDraft] = useState("");
  const kickedOff = useRef(false);
  const scroller = useRef<HTMLDivElement | null>(null);

  const send = async (text: string) => {
    const t = (text || "").trim();
    if (thinking) return;
    if (t) setTurns((x) => [...x, { who: "user", text: t }]);
    setDraft("");
    setThinking(true);

    // SOF-154: prose streams in token-by-token, then chips arrive one at a time. The live bubble
    // is only pushed once the FIRST real content arrives (a token or a chip) — while the agent is
    // still tool-calling ("working"), the existing "Thinking…" indicator below covers it, exactly
    // as before; no empty bubble sits on screen during that phase.
    let bubbleStarted = false;
    const ensureBubble = () => {
      if (!bubbleStarted) {
        bubbleStarted = true;
        setTurns((x) => [...x, { who: "agent", text: "", suggested: [] }]);
      }
    };
    const updateBubble = (fn: (t: ChatTurn) => ChatTurn) => {
      setTurns((x) => {
        const next = [...x];
        next[next.length - 1] = fn(next[next.length - 1]);
        return next;
      });
    };
    const fail = () => {
      ensureBubble();
      updateBubble(() => ({ who: "agent", text: "Something went wrong on that turn — say that again?", suggested: [] }));
    };

    try {
      // Empty message = "the agent opens" (the kickoff). Everything else is a normal turn.
      const resp = await api.converseStream(draftId, t);
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
          if (evt.type === "token") {
            ensureBubble();
            updateBubble((last) => ({ ...last, text: last.text + evt.text }));
          } else if (evt.type === "option") {
            ensureBubble();
            updateBubble((last) => ({
              ...last,
              suggested: [...(last.suggested || []), {
                response: evt.text,
                type: evt.option_type === "multi" ? "multi select" : "single select",
              }],
            }));
          } else if (evt.type === "done") {
            // Authoritative reconciliation — silent (identical to what already streamed) in the
            // normal case; only visibly changes anything if the stream genuinely drifted.
            ensureBubble();
            updateBubble(() => ({ who: "agent", text: evt.response, suggested: evt.suggested_responses || [] }));
            if (evt.handed_off) onPromoted();
          } else if (evt.type === "error") {
            fail();
          }
          // "working" needs no UI action of its own — the pre-bubble "Thinking…" indicator covers it.
        }
      }
    } catch {
      fail();
    } finally {
      setThinking(false);
    }
  };

  useEffect(() => {
    if (!kickedOff.current) { kickedOff.current = true; send(""); }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [draftId]);

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
              {/* SOF-154: chips render as they stream in, one at a time — no longer gated on
                  !thinking, since the reply's prose is already fully streamed by the time its
                  first <option> tag closes; m === last already stops this from showing on a
                  stale turn once a new one begins. */}
              {m.who === "agent" && m === last && (m.suggested?.length ?? 0) > 0 && (
                <div style={{ marginLeft: 35 }}>
                  <SuggestedResponseList options={m.suggested!} onSubmit={(values) => {
                    const joined = values.join(", ");
                    if (joined === "Hand off to the factory") onHandoff(); else send(joined);
                  }} />
                </div>
              )}
            </div>
          ))}
          {/* SOF-154: once the streaming bubble appears (last turn is the live agent reply),
              its own streaming prose IS the working indicator — this separate spinner is only for
              the pre-content phase (tool-calling/connecting), matching "working" events. */}
          {thinking && last?.who !== "agent" && (
            <div style={{ display: "flex", alignItems: "center", gap: 8, font: `400 12.5px/1 ${T.sans}`, color: T.tertiary }}>
              <span className="sf-spin" style={{ display: "inline-flex" }}><Icon name="refresh" size={13} color={T.tertiary} /></span>
              {started ? "Thinking…" : "Reading your project and materials…"}
            </div>
          )}
        </div>
      </div>

      <div style={{ flexShrink: 0, borderTop: `1px solid ${T.borderSubtle}`, background: T.raised }}>
        <div style={{ maxWidth: 720, margin: "0 auto", padding: "12px 24px", display: "flex", flexDirection: "column", gap: 8 }}>
          {submitting ? (
            // SOF-193: hand-off is the single most consequential, one-way moment of the interview.
            // Once it's underway, replace the composer + Send row entirely with an active, on-brand
            // confirmation — so the UI reads "you've committed, the factory has it" instead of a
            // greyed/stuck-looking pill next to a composer still inviting more input. The spinner
            // (never a disabled control) is the unambiguous in-progress signal; the brand-soft card
            // with a brand left-accent matches the Concierge/agent surface in the design system.
            <div role="status" aria-live="polite" style={{ display: "flex", alignItems: "center", gap: 12,
                 padding: "13px 15px", borderRadius: T.rLg, background: T.brandSoft,
                 border: `1px solid ${T.brand}`, borderLeft: `3px solid ${T.brand}` }}>
              <span className="sf-spin" style={{ display: "inline-flex", flexShrink: 0 }}>
                <Icon name="refresh" size={16} color={T.brand} />
              </span>
              <span style={{ display: "flex", flexDirection: "column", gap: 2, minWidth: 0, flex: 1 }}>
                <span style={{ font: `600 13px/1.2 ${T.sans}`, color: T.brandDeep }}>Handing off to the factory…</span>
                <span style={{ font: `400 12px/1.4 ${T.sans}`, color: T.secondary }}>
                  Your brief is locked in — the factory is taking it from here. Nothing more to do.
                </span>
              </span>
              <Icon name="arrowRight" size={16} color={T.brand} />
            </div>
          ) : (
            <>
              <Composer placeholder="Answer, ask, or add anything…" value={draft} onChange={setDraft} onSend={() => send(draft)} loading={thinking} />
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                <span style={{ font: `400 12px/1.3 ${T.sans}`, color: error ? T.danger : T.tertiary }}>
                  {error || "Hand off whenever you're ready — the Concierge will tell you when it has enough."}
                </span>
                <Btn variant="primary" size="sm" onClick={onHandoff} disabled={!started}>
                  Hand off to factory <Icon name="arrowRight" size={13} color="#fff" />
                </Btn>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
