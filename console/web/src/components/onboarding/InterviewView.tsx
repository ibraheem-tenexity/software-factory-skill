// InterviewView.tsx — Step 3 of the Intake→Processing→Interview→Handoff flow (PRD §2.4a "Step 3
// — InterviewView + InterviewRail"). Two columns: a calm read-only main column reviewing what the
// Concierge learned, and a fixed-width (340px) InterviewRail that asks outstanding questions ONE
// AT A TIME with a segmented progress strip — mirrors optionC.jsx's InterviewRail, not a
// simplified all-at-once form. The queue (open SOF-37 reflection questions, then the brief
// sections the promote gate requires beyond "goals") is derived fresh from live polled state each
// render, never a locally-tracked index — so it can never drift from server truth. Nothing here
// invents new backend behavior: api.resolveReflection and api.putBrief both already exist and are
// already tested; onboarding just never called them before hand-off, which is why every hand-off
// 409'd regardless of project name.
import React, { useEffect, useState } from "react";
import { api, Assumption, ReflectionQuestion } from "../../api";
import { T, Icon, CategoryLabel, Wordmark, Btn, TextArea, StatusPill } from "./design";

// Mirrors brief.py's REQUIRED_SECTIONS minus "goals" (already collected by the intake form's
// "What are you building?" field). If REQUIRED_SECTIONS ever changes, update this list to match.
const BRIEF_FOLLOWUPS: { key: string; label: string; prompt: string }[] = [
  { key: "success_metrics", label: "Success Metrics", prompt: "What does success look like for this project? How will you know it worked?" },
  { key: "definition_of_done", label: "Definition of Done", prompt: "What has to be true for you to consider this shipped?" },
];

type QueueItem =
  | { kind: "reflection"; question: ReflectionQuestion }
  | { kind: "brief"; key: string; label: string; prompt: string };

export function InterviewView({ draftId, projectName, goal, onBack, onHandoff, submitting, error }: {
  draftId: string; projectName: string; goal: string; onBack: () => void; onHandoff: () => void; submitting: boolean; error: string;
}) {
  const [assumptions, setAssumptions] = useState<Assumption[]>([]);
  const [questions, setQuestions] = useState<ReflectionQuestion[]>([]);
  const [coverage, setCoverage] = useState<Record<string, boolean>>({});
  const [loaded, setLoaded] = useState(false);
  const [answeredCount, setAnsweredCount] = useState(0);

  const refresh = () => api.brief(draftId).then((d) => {
    setAssumptions(d.assumptions || []);
    setQuestions(d.reflection_questions || []);
    setCoverage(d.coverage || {});
    setLoaded(true);
  }).catch(() => setLoaded(true));

  useEffect(() => {
    let live = true;
    const load = () => { if (live) refresh(); };
    load();
    const h = setInterval(load, 5000);
    return () => { live = false; clearInterval(h); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [draftId]);

  const openQuestions = questions.filter((q) => q.status === "open");
  const missingSections = BRIEF_FOLLOWUPS.filter((s) => !coverage[s.key]);
  // Fixed order: clarify facts from the materials first, then the strategic brief questions —
  // recomputed fresh from live state every render.
  const queue: QueueItem[] = [
    ...openQuestions.map((question) => ({ kind: "reflection" as const, question })),
    ...missingSections.map((s) => ({ kind: "brief" as const, key: s.key, label: s.label, prompt: s.prompt })),
  ];
  const current = queue[0];
  const ready = loaded && queue.length === 0;
  const total = answeredCount + queue.length;

  const resolveQuestion = async (questionId: string, action: "answer" | "dismiss", answer?: string) => {
    const d = await api.resolveReflection(draftId, questionId, action, answer);
    setQuestions(d.reflection_questions);
    setAnsweredCount((n) => n + 1);
  };

  const submitFollowup = async (key: string, text: string) => {
    const d = await api.putBrief(draftId, { [key]: text });
    setCoverage(d.coverage);
    setAnsweredCount((n) => n + 1);
  };

  return (
    <div style={{ height: "100%", display: "flex", flexDirection: "column", background: T.bg, fontFamily: T.sans }}>
      <div style={{ display: "flex", alignItems: "center", gap: 10, padding: "14px 24px", background: T.raised, borderBottom: `1px solid ${T.borderSubtle}`, flexShrink: 0 }}>
        <Btn variant="ghost" size="sm" onClick={onBack}><Icon name="arrowLeft" size={14} /> Setup</Btn>
        <Wordmark /><span style={{ color: T.tertiary }}>/</span>
        <span style={{ font: `600 13px/1.2 ${T.sans}`, color: T.fg }}>{projectName || "Untitled project"}</span>
        <span style={{ marginLeft: "auto", font: `600 11px/1 ${T.mono}`, color: T.tertiary, letterSpacing: "0.06em" }}>STEP 3 OF 3 · INTERVIEW</span>
      </div>

      <div style={{ flex: 1, display: "flex", minHeight: 0 }}>
        {/* main column — calm review, NOT the active Q&A (that's the rail, on the right) */}
        <div style={{ flex: 1, minWidth: 0, display: "flex", flexDirection: "column" }}>
          <div style={{ flex: 1, overflow: "auto", padding: "32px" }}>
            <div style={{ maxWidth: 640, margin: "0 auto", display: "flex", flexDirection: "column", gap: 16 }}>
              <div>
                <CategoryLabel tone="brand" style={{ marginBottom: 9 }}>Materials processed · Interviewing</CategoryLabel>
                <h1 style={{ font: `700 26px/1.2 ${T.display}`, letterSpacing: "-0.02em", color: T.fg, margin: 0 }}>Let's confirm what I learned</h1>
                <p style={{ font: `400 14px/1.5 ${T.sans}`, color: T.secondary, margin: "8px 0 0", maxWidth: 560 }}>
                  I read everything you gave me and drafted the assumptions below. Answer my questions on the right to confirm or correct them — then we hand off to the factory.
                </p>
              </div>

              {assumptions.length === 0 ? (
                <p style={{ font: `400 13px/1.5 ${T.sans}`, color: T.tertiary, margin: 0 }}>Nothing referenced yet — that's fine, the rail on the right covers what's still needed.</p>
              ) : (
                <section style={{ background: T.raised, border: `1px solid ${T.borderSubtle}`, borderRadius: T.rXl, padding: "20px 22px" }}>
                  <CategoryLabel tone="brand" style={{ marginBottom: 10 }}>What I learned from your materials</CategoryLabel>
                  <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                    {assumptions.map((f, i) => (
                      <div key={i} style={{ display: "flex", alignItems: "baseline", gap: 10, padding: "8px 0", borderBottom: i < assumptions.length - 1 ? `1px solid ${T.borderSubtle}` : "none" }}>
                        <p style={{ flex: 1, margin: 0, font: `400 13px/1.5 ${T.sans}`, color: T.fg }}>{f.fact}</p>
                        <span style={{ flexShrink: 0, display: "inline-flex", alignItems: "center", gap: 4, font: `500 11px/1 ${T.sans}`, color: T.brandDeep, background: T.brandSoft, padding: "4px 10px", borderRadius: 9999, whiteSpace: "nowrap" }}>
                          <Icon name="file" size={10} color={T.brandDeep} /> {f.document_name}{f.section_path ? ` · ${f.section_path}` : ""}
                        </span>
                      </div>
                    ))}
                  </div>
                </section>
              )}

              <section style={{ background: T.raised, border: `1px solid ${T.borderSubtle}`, borderRadius: T.rXl, padding: "20px 22px" }}>
                <CategoryLabel style={{ marginBottom: 8 }}>This project</CategoryLabel>
                <h3 style={{ font: `700 16px/1.3 ${T.display}`, color: T.fg, margin: "0 0 8px" }}>{projectName || "Untitled project"}</h3>
                <p style={{ font: `400 13px/1.55 ${T.sans}`, color: T.secondary, margin: 0, whiteSpace: "pre-wrap" }}>{goal}</p>
              </section>
            </div>
          </div>

          <div style={{ flexShrink: 0, display: "flex", alignItems: "center", justifyContent: "space-between", padding: "13px 32px", borderTop: `1px solid ${T.borderSubtle}`, background: T.raised }}>
            <span style={{ font: `400 12.5px/1.3 ${T.sans}`, color: error ? T.danger : T.secondary }}>
              {error || (ready ? "Interview complete" : "Finish the rail on the right to continue")}
            </span>
            <Btn variant="primary" onClick={onHandoff} disabled={!ready || submitting} style={ready ? { background: T.success } : undefined}>
              {submitting ? "Handing off…" : "Hand off to factory"} <Icon name="arrowRight" size={14} color="#fff" />
            </Btn>
          </div>
        </div>

        {/* InterviewRail — the active Q&A, one item at a time */}
        <div style={{ width: 340, flexShrink: 0, borderLeft: `1px solid ${T.borderSubtle}`, background: T.raised, display: "flex", flexDirection: "column", minHeight: 0 }}>
          <div style={{ padding: "16px 18px", borderBottom: `1px solid ${T.borderSubtle}` }}>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 10 }}>
              <span style={{ font: `600 13px/1.2 ${T.sans}`, color: T.fg }}>Interview</span>
              <StatusPill tone={ready ? "success" : "info"}>{ready ? "done" : `${answeredCount}/${Math.max(total, 1)}`}</StatusPill>
            </div>
            <div style={{ display: "flex", gap: 4 }}>
              {Array.from({ length: Math.max(total, 1) }).map((_, i) => (
                <span key={i} style={{ flex: 1, height: 4, borderRadius: 2, background: i < answeredCount ? T.success : (i === answeredCount && !ready ? T.brand : T.borderSubtle) }} />
              ))}
            </div>
          </div>

          <div style={{ flex: 1, overflow: "auto", padding: "18px" }}>
            {!loaded ? (
              <span style={{ font: `400 12.5px/1.4 ${T.sans}`, color: T.tertiary }}>Loading…</span>
            ) : current?.kind === "reflection" ? (
              <ReflectionQuestionCard question={current.question} onResolve={resolveQuestion} />
            ) : current?.kind === "brief" ? (
              <BriefFollowupCard label={current.label} prompt={current.prompt} onSubmit={(text) => submitFollowup(current.key, text)} />
            ) : (
              <div style={{ display: "flex", alignItems: "center", gap: 10, padding: "12px 4px" }}>
                <Icon name="check" size={16} color={T.success} />
                <span style={{ font: `600 13px/1.3 ${T.sans}`, color: T.fg }}>Ready to build</span>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

// MODULE-SCOPE (never define inside render — remounts the <textarea> on each keystroke).
function ReflectionQuestionCard({ question, onResolve }: {
  question: ReflectionQuestion;
  onResolve: (questionId: string, action: "answer" | "dismiss", answer?: string) => Promise<void>;
}) {
  const [answer, setAnswer] = useState("");
  const [busy, setBusy] = useState(false);
  const submit = async (action: "answer" | "dismiss") => {
    if (busy || (action === "answer" && !answer.trim())) return;
    setBusy(true);
    try { await onResolve(question.id, action, action === "answer" ? answer : undefined); } finally { setBusy(false); }
  };
  return (
    <div>
      <CategoryLabel tone="brand" style={{ marginBottom: 8 }}>Clarify one thing</CategoryLabel>
      <p style={{ margin: "0 0 12px", font: `500 14px/1.4 ${T.sans}`, color: T.fg }}>{question.fact}</p>
      <TextArea rows={2} value={answer} onChange={setAnswer} placeholder="Clarify…" />
      <div style={{ marginTop: 10, display: "flex", gap: 8, justifyContent: "flex-end" }}>
        <Btn variant="ghost" size="sm" disabled={busy} onClick={() => submit("dismiss")}>Not needed</Btn>
        <Btn variant="secondary" size="sm" disabled={!answer.trim() || busy} onClick={() => submit("answer")}>{busy ? "Saving…" : "Answer"}</Btn>
      </div>
    </div>
  );
}

function BriefFollowupCard({ label, prompt, onSubmit }: { label: string; prompt: string; onSubmit: (text: string) => Promise<void> }) {
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const submit = async () => {
    if (text.trim().length < 24 || busy) return;
    setBusy(true);
    try { await onSubmit(text.trim()); } finally { setBusy(false); }
  };
  return (
    <div>
      <CategoryLabel tone="brand" style={{ marginBottom: 8 }}>{label}</CategoryLabel>
      <p style={{ margin: "0 0 12px", font: `500 14px/1.4 ${T.sans}`, color: T.fg }}>{prompt}</p>
      <TextArea rows={4} value={text} onChange={setText} placeholder="A sentence or two is enough…" />
      <div style={{ marginTop: 10, display: "flex", justifyContent: "flex-end" }}>
        <Btn variant="secondary" size="sm" disabled={text.trim().length < 24 || busy} onClick={submit}>{busy ? "Saving…" : "Continue"}</Btn>
      </div>
    </div>
  );
}
