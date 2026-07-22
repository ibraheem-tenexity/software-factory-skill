// concierge.jsx — the one constant Concierge across the whole product.
//   • ProcessingScreen  — intermediary ingest step (form → PROCESSING → interview).
//                          Large uploads can be sent to the background → Project home.
//   • InterviewRail      — the docked Concierge as an ACTIVE Q&A the user must
//                          complete before handoff (replaces the passive checklist
//                          rail during the interview phase).
//   • ProjectConcierge   — the persistent, minimizable dock shared by every
//                          Project Console view. Context-aware, same shell everywhere.

// ---- shared typing simulation hook -------------------------------------------
function conciergeClock() {
  return new Date().toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
}

function useConciergeChat(seed, replyFor) {
  const [messages, setMessages] = React.useState(seed);
  const [draft, setDraft] = React.useState('');
  const [thinking, setThinking] = React.useState(null);
  const scroller = React.useRef(null);
  const timers = React.useRef([]);
  const LABELS = ['Reading the project…', 'Checking the latest state…', 'Pulling the artifacts…', 'Looking through your documents…'];
  React.useEffect(() => () => timers.current.forEach(clearTimeout), []);
  React.useEffect(() => { const el = scroller.current; if (el) el.scrollTop = el.scrollHeight; }, [messages, thinking]);
  const push = (m) => setMessages((x) => [...x, m]);
  const sendText = (text) => {
    const t = (text != null ? text : draft).trim(); if (!t || thinking) return;
    push({ who: 'user', text: t, time: conciergeClock() }); setDraft('');
    let i = 0; setThinking(LABELS[0]);
    const rot = setInterval(() => { i = (i + 1) % LABELS.length; setThinking(LABELS[i]); }, 850);
    timers.current.push(rot);
    const done = setTimeout(() => {
      clearInterval(rot); setThinking(null);
      push({ who: 'agent', text: replyFor ? replyFor(t) : 'On it — I’ve noted that and I’ll surface anything relevant here.', time: conciergeClock() });
    }, 1900);
    timers.current.push(done);
  };
  return { messages, draft, setDraft, thinking, scroller, sendText, push, setMessages };
}

// Consistent header used by every Concierge surface — this sameness IS the point.
function ConciergeHeader({ subtitle, live = true, working, label = 'Concierge', onCollapse }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 9, padding: '14px 18px', borderBottom: `1px solid ${T.borderSubtle}`, flexShrink: 0 }}>
      <span style={{ position: 'relative', width: 30, height: 30, borderRadius: '50%', display: 'grid', placeItems: 'center', background: T.brandSoft, color: T.brand, boxShadow: `inset 0 0 0 1px ${T.brand}33` }}>
        <Sparkle size={14} color={T.brand} />
        {live && <span style={{ position: 'absolute', right: -1, bottom: -1, width: 9, height: 9, borderRadius: '50%', background: T.success, boxShadow: `0 0 0 2px ${T.raised}`, animation: 'sfPulse 1.6s ease-in-out infinite' }} />}
      </span>
      <div style={{ flex: 1, minWidth: 0 }}>
        <span style={{ display: 'block', font: `600 13px/1.2 ${T.sans}`, color: T.fg }}>{label}</span>
        <CategoryLabel style={{ fontSize: 10 }}>{subtitle}</CategoryLabel>
      </div>
      {onCollapse && <button onClick={onCollapse} title="Minimize Concierge" aria-label="Minimize Concierge" style={{ width: 28, height: 28, display: 'grid', placeItems: 'center', border: `1px solid ${T.borderSubtle}`, borderRadius: T.rMd, background: T.raised, color: T.tertiary, cursor: 'pointer' }}><Icon name="chevronRight" size={14} color={T.tertiary} /></button>}
      {working ? <WorkingPill label={typeof working === 'string' ? working : 'Working'} /> : <StatusPill tone="success">online</StatusPill>}
    </div>
  );
}

function QuickReplies({ options, onPick }) {
  if (!options || !options.length) return null;
  return (
    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 7 }}>
      {options.map((o) => (
        <button key={o} onClick={() => onPick(o)} style={{ font: `500 12px/1 ${T.sans}`, padding: '7px 11px', borderRadius: 9999, cursor: 'pointer',
          border: `1px solid ${T.brand}55`, background: T.brandSoft, color: T.brandDeep, transition: 'all .12s' }}>{o}</button>
      ))}
    </div>
  );
}

// Checkable option list for interview answers. mode='single' submits on click;
// mode='multi' lets the user tick several, then Confirm submits the joined set.
function ChoiceList({ options, mode = 'single', onSubmit, disabled }) {
  const [sel, setSel] = React.useState([]);
  const multi = mode === 'multi';
  const toggle = (o) => {
    if (disabled) return;
    if (!multi) { onSubmit(o); return; }
    setSel((s) => s.includes(o) ? s.filter((x) => x !== o) : [...s, o]);
  };
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 7 }}>
      <CategoryLabel>{multi ? 'Select all that apply' : 'Choose one'}</CategoryLabel>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
        {options.map((o) => {
          const on = sel.includes(o);
          return (
            <button key={o} onClick={() => toggle(o)} disabled={disabled} style={{ display: 'flex', alignItems: 'center', gap: 10, width: '100%', textAlign: 'left',
              cursor: disabled ? 'default' : 'pointer', padding: '9px 11px', borderRadius: T.rMd, font: `500 13px/1.3 ${T.sans}`,
              border: `1px solid ${on ? T.brand : T.borderDefault}`, background: on ? T.brandSoft : T.raised, color: on ? T.brandDeep : T.fg, transition: 'all .12s' }}>
              <span style={{ width: 18, height: 18, flexShrink: 0, display: 'grid', placeItems: 'center', borderRadius: multi ? 5 : '50%',
                border: `1.5px solid ${on ? T.brand : T.borderDefault}`, background: on ? T.brand : 'transparent', transition: 'all .12s' }}>
                {on && <Icon name="check" size={12} color="#fff" strokeWidth={3} />}
              </span>
              <span style={{ flex: 1 }}>{o}</span>
            </button>
          );
        })}
      </div>
      {multi && (
        <Btn variant="primary" size="sm" disabled={!sel.length || disabled} onClick={() => onSubmit(sel.join(', '))} style={{ alignSelf: 'flex-start', marginTop: 2 }}>
          Confirm{sel.length ? ` (${sel.length})` : ''} <Icon name="arrowRight" size={13} color="#fff" />
        </Btn>
      )}
    </div>
  );
}

// ====== PROCESSING SCREEN =====================================================
// Sits between project creation and the interview. Ingests uploaded materials —
// large files can be heavy, so it shows real progress, a streaming log, an ETA,
// and a "continue in the background" escape to the live Project home.
const INGEST_STEPS = [
  { file: 'process-walkthrough.mp4', size: '86 MB', kind: 'video', lines: ['Uploading process-walkthrough.mp4…', 'Transcribing audio (4:12)…', 'Detecting on-screen steps in Epicor…', 'Extracted the quote → re-key → approval flow.'] },
  { file: 'standard-pricing.xlsx', size: '142 KB', kind: 'csv', lines: ['Parsing standard-pricing.xlsx…', 'Read 1,840 SKUs across 6 product lines.', 'Mapped tiered discounts by customer class.'] },
  { file: 'rfq-sop.pdf', size: '320 KB', kind: 'pdf', lines: ['Reading rfq-sop.pdf…', 'Indexed the inbound-RFQ standard operating procedure.'] },
  { file: 'discount-matrix.xlsx', size: '64 KB', kind: 'csv', lines: ['Parsing discount-matrix.xlsx…', 'Approval threshold found: >15% routes to a sales manager.'] },
  { file: 'line-card.pdf', size: '1.1 MB', kind: 'pdf', lines: ['Reading line-card.pdf…', 'Catalogued carried product lines & manufacturers.'] },
];

function ProcessingScreen({ projectName, onDone, onBackground }) {
  const allLines = React.useMemo(() => INGEST_STEPS.flatMap((s) => s.lines.map((l) => ({ l, file: s.file }))), []);
  const total = allLines.length;
  const [logN, setLogN] = React.useState(0);
  const logRef = React.useRef(null);
  const firedDone = React.useRef(false);
  React.useEffect(() => {
    const t = setInterval(() => setLogN((n) => (n >= total ? n : n + 1)), 720);
    return () => clearInterval(t);
  }, [total]);
  React.useEffect(() => { const el = logRef.current; if (el) el.scrollTop = el.scrollHeight; }, [logN]);
  // derive everything from logN — single source of truth (no nested setState)
  const done = logN >= total;
  const pct = Math.round((logN / total) * 100);
  let acc = 0, fileN = 0; for (let i = 0; i < INGEST_STEPS.length; i++) { acc += INGEST_STEPS[i].lines.length; if (logN <= acc) { fileN = i; break; } fileN = i; }
  React.useEffect(() => { if (done && !firedDone.current) { firedDone.current = true; const t = setTimeout(() => onDone && onDone(), 900); return () => clearTimeout(t); } }, [done]);
  const remainingFiles = INGEST_STEPS.length - fileN - (done ? 0 : 1);
  const eta = done ? 'Done' : `about ${Math.max(1, Math.ceil((total - logN) * 0.7))}s left`;

  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column', background: T.bg, fontFamily: T.sans }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '14px 24px', background: T.raised, borderBottom: `1px solid ${T.borderSubtle}`, flexShrink: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}><Wordmark /><span style={{ font: `400 13px/1 ${T.mono}`, color: T.tertiary }}>/</span><span style={{ font: `600 13px/1 ${T.sans}`, color: T.fg }}>{projectName}</span></div>
        <WorkingPill label="Processing" />
      </div>
      <div style={{ flex: 1, overflow: 'auto', display: 'grid', placeItems: 'center', padding: '32px' }}>
        <div style={{ width: '100%', maxWidth: 660, display: 'flex', flexDirection: 'column', gap: 20 }}>
          <div>
            <CategoryLabel tone="brand" style={{ marginBottom: 9 }}>Step 2 of 3 · Processing your materials</CategoryLabel>
            <h1 style={{ font: `700 28px/1.2 ${T.display}`, letterSpacing: '-0.02em', color: T.fg, margin: 0 }}>{done ? 'Materials processed' : 'Reading everything you gave me'}</h1>
            <p style={{ font: `400 14px/1.55 ${T.sans}`, color: T.secondary, margin: '8px 0 0', maxWidth: 520 }}>
              I’m ingesting your uploads and connected systems so the interview is sharp. Large files — like a long screen recording — can take a moment.
            </p>
          </div>

          {/* progress */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 9 }}>
            <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between' }}>
              <span style={{ font: `600 13px/1 ${T.sans}`, color: T.fg }}>{done ? 'Complete' : `Processing ${INGEST_STEPS[Math.min(fileN, INGEST_STEPS.length - 1)].file}`}</span>
              <span style={{ font: `500 12px/1 ${T.mono}`, color: done ? T.success : T.tertiary }}>{pct}% · {eta}</span>
            </div>
            <span style={{ height: 8, borderRadius: 5, background: T.sunken, overflow: 'hidden' }}>
              <span style={{ display: 'block', height: '100%', width: pct + '%', background: done ? T.success : T.brand, transition: 'width .4s var(--ease-out, ease)' }} />
            </span>
            <span style={{ font: `400 12px/1.4 ${T.sans}`, color: T.tertiary }}>{done ? `${INGEST_STEPS.length} files processed` : `${INGEST_STEPS.length} files · ${remainingFiles > 0 ? remainingFiles + ' still in queue' : 'finishing up'}`}</span>
          </div>

          {/* status log */}
          <div style={{ border: `1px solid ${T.borderSubtle}`, borderRadius: T.rLg, background: T.ink, overflow: 'hidden' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 7, padding: '9px 13px', borderBottom: `1px solid #2a2a30` }}>
              <span style={{ width: 7, height: 7, borderRadius: '50%', background: done ? T.success : T.brand }} />
              <CategoryLabel style={{ color: '#a8a8b0' }}>Ingest log</CategoryLabel>
            </div>
            <div ref={logRef} style={{ maxHeight: 188, overflow: 'auto', padding: '11px 14px', display: 'flex', flexDirection: 'column', gap: 6 }}>
              {allLines.slice(0, logN).map((row, i) => (
                <div key={i} style={{ display: 'flex', gap: 9, font: `400 12px/1.5 ${T.mono}`, color: i === logN - 1 && !done ? '#fff' : '#9a9aa2', animation: 'sfRise .25s var(--ease-out, ease) both' }}>
                  <span style={{ color: T.success, flexShrink: 0 }}>{i === logN - 1 && !done ? '›' : '✓'}</span>
                  <span>{row.l}</span>
                </div>
              ))}
              {!done && <div style={{ display: 'flex', gap: 9, font: `400 12px/1.5 ${T.mono}`, color: '#6a6a72' }}><span className="sf-spin" style={{ display: 'inline-flex' }}><Icon name="refresh" size={12} color="#6a6a72" /></span><span>working…</span></div>}
            </div>
          </div>

          {/* actions */}
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 14, flexWrap: 'wrap' }}>
            <div style={{ display: 'flex', alignItems: 'flex-start', gap: 9, maxWidth: 360 }}>
              <span style={{ marginTop: 1, flexShrink: 0 }}><Icon name="alert" size={15} color={T.tertiary} /></span>
              <span style={{ font: `400 12px/1.5 ${T.sans}`, color: T.tertiary }}>Big upload? You don’t have to wait. Send this to the background and I’ll keep processing — you’ll watch progress live on your project home.</span>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              {onBackground && <Btn variant="secondary" onClick={onBackground} disabled={done}>Continue in background <Icon name="arrowRight" size={14} /></Btn>}
              <Btn variant="primary" onClick={() => onDone && onDone()} disabled={!done} style={done ? { background: T.success } : null}>{done ? <React.Fragment>Start the interview <Icon name="arrowRight" size={14} color="#fff" /></React.Fragment> : 'Processing…'}</Btn>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

// ====== INTERVIEW RAIL ========================================================
// The docked Concierge, now an ACTIVE interview. Asks document-grounded
// questions one at a time; the user must answer all of them before the build
// can be handed off. Calls onComplete() when the last answer lands.
// Each question declares a `select` mode the model chooses per question:
//   'single' — radio-style, one answer, submits on click.
//   'multi'  — checkbox-style, tick several, Confirm submits the set.
const INTERVIEW_Q = [
  { q: "I watched process-walkthrough.mp4 — quotes are built in spreadsheets, then re-keyed into Epicor, and that re-keying is the slow part. Did I read the bottleneck right?", select: 'single', opts: ['Yes, that’s it', 'Mostly — but pricing too', 'Not quite'] },
  { q: "Roughly how many quotes does the team build per week?", select: 'single', opts: ['Under 50', '50–100', '~120', '200+'] },
  { q: "Your discount-matrix.xlsx says anything over a 15% discount goes to a sales manager. Still accurate?", select: 'single', opts: ['Yes, still 15%', 'It changed'] },
  { q: "Last one — for v1, which outcomes matter? Pick every one that applies.", select: 'multi', opts: ['Faster quoting', 'Fewer Epicor errors', 'Manager visibility', 'Consistent pricing'] },
];

function InterviewRail({ onComplete }) {
  const seed = [{ who: 'agent', text: "I’ve read your profile and everything you uploaded. I’ve drafted assumptions in the panel on the left — a few questions to sharpen the build before we start." }, { who: 'agent', text: INTERVIEW_Q[0].q }];
  const chat = useConciergeChat(seed, null);
  const [step, setStep] = React.useState(0); // questions answered
  const total = INTERVIEW_Q.length;
  const finished = step >= total;
  const timers = React.useRef([]);
  React.useEffect(() => () => timers.current.forEach(clearTimeout), []);

  const answer = (text) => {
    if (finished || chat.thinking) return;
    const t = (text != null ? text : chat.draft).trim(); if (!t) return;
    chat.push({ who: 'user', text: t }); chat.setDraft('');
    const next = step + 1;
    timers.current.push(setTimeout(() => {
      if (next < total) {
        chat.push({ who: 'agent', text: 'Got it.' });
        timers.current.push(setTimeout(() => chat.push({ who: 'agent', text: INTERVIEW_Q[next].q }), 650));
      } else {
        chat.push({ who: 'agent', text: 'That’s everything I need. I’ve turned this into a build plan and a design step for your screens — hand off whenever you’re ready.' });
        if (onComplete) onComplete();
      }
      setStep(next);
    }, 700));
  };

  return (
    <div style={{ width: 340, flexShrink: 0, borderLeft: `1px solid ${T.borderSubtle}`, background: T.raised, display: 'flex', flexDirection: 'column', minHeight: 0 }}>
      <ConciergeHeader subtitle={finished ? 'Interview complete' : `Interview · ${step}/${total}`} working={chat.thinking ? 'Thinking' : false} />
      {/* progress strip */}
      <div style={{ display: 'flex', gap: 4, padding: '10px 18px', borderBottom: `1px solid ${T.borderSubtle}`, flexShrink: 0 }}>
        {INTERVIEW_Q.map((_, i) => <span key={i} style={{ flex: 1, height: 4, borderRadius: 2, background: i < step ? T.success : i === step && !finished ? T.brand : T.sunken, transition: 'background .3s' }} />)}
      </div>
      <div ref={chat.scroller} style={{ flex: 1, overflow: 'auto', padding: '14px 16px', display: 'flex', flexDirection: 'column', gap: 12 }}>
        {chat.messages.map((m, i) => <Message key={i} who={m.who} text={m.text} confidence={m.confidence} anim={i >= seed.length} />)}
        {chat.thinking && <TypingIndicator label={chat.thinking} />}
        {!finished && !chat.thinking && step < total && <ChoiceList key={step} options={INTERVIEW_Q[step].opts} mode={INTERVIEW_Q[step].select || 'single'} onSubmit={(t) => answer(t)} />}
        {finished && (
          <div style={{ padding: 11, borderRadius: T.rLg, border: `1px solid ${T.success}55`, background: T.successSoft + '88' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 5 }}><Icon name="check" size={13} color={T.success} /><CategoryLabel style={{ color: T.success }}>Ready to build</CategoryLabel></div>
            <p style={{ font: `400 12px/1.5 ${T.sans}`, color: T.secondary, margin: 0 }}>I have what I need. Hand off to the factory on the left — I’ll stay with you through the whole build.</p>
          </div>
        )}
      </div>
      <div style={{ flexShrink: 0, padding: '12px 16px', borderTop: `1px solid ${T.borderSubtle}` }}>
        <Composer placeholder={finished ? 'Interview complete — ask me anything…' : 'Type your answer…'} value={chat.draft} onChange={chat.setDraft} onSend={() => answer()} />
      </div>
    </div>
  );
}

// ====== PERSISTENT PROJECT CONCIERGE =========================================
// One shared dock across the Project Console. It can leave the layout entirely
// while its floating restore control keeps the same transcript and draft alive.
const FACTORY_ACTIVITY = [
  { id: 'plan-done', time: '12:17', kind: 'stage', tone: 'success', label: 'Plan stage completed', detail: 'The planner produced 11 build tickets and handed them to the build stage.' },
  { id: 'build-active', time: '12:18', kind: 'stage', tone: 'neutral', label: 'Build stage started', detail: 'Two implementation agents claimed the first available tickets.' },
  { id: 'retry-started', time: '12:21', kind: 'retry', tone: 'neutral', label: 'Build retry started', meta: 'attempt 3' },
  { id: 'silent-stage', time: '12:24', kind: 'attention', tone: 'warning', label: 'Stage silent for about 90 seconds', detail: 'Flagged for review. No action was taken automatically.' },
  { id: 'build-blocked', time: '12:27', kind: 'attention', tone: 'danger', label: 'Build blocked by the deployment database', detail: 'Provisioning returned no service id. A prior marker points to a possible orphaned Postgres instance that needs reconciliation.' },
  { id: 'build-resumed', time: '12:29', kind: 'stage', tone: 'success', label: 'Build resumed', detail: 'The affected ticket returned to Building after the dependency was reconciled.' },
  { id: 'design-produced', time: '12:32', kind: 'artifact', tone: 'neutral', label: 'design-spec.md produced', detail: 'The Design agent recorded the approved screen behavior for the build agents.', artifactId: 'designspec' },
];

function SystemEvent({ event, compact = false, onOpen }) {
  const important = event.tone === 'danger' || event.tone === 'warning';
  const [expanded, setExpanded] = React.useState(important);
  const tone = event.tone === 'danger' ? T.danger : event.tone === 'warning' ? T.warning : event.tone === 'success' ? T.success : T.tertiary;
  const soft = event.tone === 'danger' ? T.dangerSoft : event.tone === 'warning' ? T.warningSoft : event.tone === 'success' ? T.successSoft : T.sunken;
  const icon = event.kind === 'artifact' ? 'file' : event.kind === 'retry' ? 'refresh' : important ? 'alert' : 'layers';
  return <div style={{ position: 'relative', display: 'grid', gridTemplateColumns: '18px minmax(0, 1fr)', gap: compact ? 7 : 10, padding: compact ? '7px 8px' : '11px 12px', borderRadius: T.rMd, border: `1px solid ${important ? tone + '44' : T.borderSubtle}`, background: important ? soft + '88' : T.sunken }}>
    <span style={{ width: 18, height: 18, borderRadius: '50%', display: 'grid', placeItems: 'center', background: important ? soft : T.raised, border: `1px solid ${tone}44` }}><Icon name={icon} size={10} color={tone} /></span>
    <div style={{ minWidth: 0 }}>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 7 }}><span style={{ font: `500 ${compact ? 9 : 10}px/1 ${T.mono}`, color: T.tertiary }}>{event.time}</span><b style={{ flex: 1, font: `600 ${compact ? 11.5 : 12.5}px/1.35 ${T.sans}`, color: T.fg }}>{event.label}</b>{event.meta && <span style={{ font: `500 9px/1 ${T.mono}`, color: T.tertiary }}>{event.meta}</span>}</div>
      {expanded && event.detail && <p style={{ margin: '5px 0 0', font: `400 ${compact ? 11 : 12}px/1.45 ${T.sans}`, color: T.secondary }}>{event.detail}</p>}
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginTop: event.detail || event.artifactId ? 6 : 0 }}>
        {event.detail && <button onClick={() => setExpanded((v) => !v)} style={{ border: 0, background: 'none', padding: 0, color: T.brandDeep, cursor: 'pointer', font: `600 10px/1 ${T.sans}` }}>{expanded ? 'Hide details' : 'Details'}</button>}
        {event.artifactId && <button onClick={() => onOpen && onOpen(event.artifactId)} style={{ border: 0, background: 'none', padding: 0, color: T.brandDeep, cursor: 'pointer', font: `600 10px/1 ${T.sans}` }}>Open output →</button>}
      </div>
    </div>
  </div>;
}

function FactoryActivity({ onOpen, actions }) {
  const attention = FACTORY_ACTIVITY.filter((event) => event.tone === 'warning' || event.tone === 'danger').length;
  return <section style={{ height: '100%', overflow: 'auto', border: `1px solid ${T.borderSubtle}`, borderRadius: T.rLg, background: T.raised }}>
    {actions && <div style={{ padding: 14, display: 'flex', flexDirection: 'column', gap: 12, borderBottom: `1px solid ${T.borderSubtle}`, background: T.bg }}><CategoryLabel>Current action items</CategoryLabel>{actions}</div>}
    <header style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '14px 16px', borderBottom: `1px solid ${T.borderSubtle}` }}><div><b style={{ display: 'block', font: `700 14px/1.2 ${T.display}`, color: T.fg }}>Run activity</b><span style={{ font: `400 11px/1.4 ${T.sans}`, color: T.tertiary }}>Every stage, retry, intervention, and output in occurrence order.</span></div><StatusPill tone="warning">{attention} need attention</StatusPill></header>
    <div style={{ position: 'relative', maxWidth: 760, padding: '16px 18px 24px 42px' }}><span style={{ position: 'absolute', left: 26, top: 24, bottom: 30, width: 1, background: T.borderDefault }} />
      <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>{FACTORY_ACTIVITY.map((event) => <div key={event.id} style={{ position: 'relative' }}><span style={{ position: 'absolute', left: -20, top: 16, width: 9, height: 9, borderRadius: '50%', background: event.tone === 'danger' ? T.danger : event.tone === 'warning' ? T.warning : event.tone === 'success' ? T.success : T.tertiary, boxShadow: `0 0 0 4px ${T.raised}` }} /><SystemEvent event={event} onOpen={onOpen} /></div>)}</div>
    </div>
  </section>;
}

function conciergeSeed(context, build, sourceContext) {
  if (context === 'build') {
    return build && build.allDone
      ? [{ who: 'agent', time: '12:35', text: `All ${build.total} tickets are green and the app is deployed. Want me to walk you through the live build?` }]
      : [{ who: 'agent', time: '12:16', text: `Build is underway — ${build ? build.done : 5}/${build ? build.total : 11} tickets done. I’ll keep the operational events in this conversation as they happen.` },
         ...FACTORY_ACTIVITY.slice(0, 3).map((event) => ({ kind: 'event', event })),
         { who: 'agent', time: '12:22', text: 'Playwright caught a tax-rounding bug on SF-11. Sonnet pulled it back into Building to fix.' },
         ...FACTORY_ACTIVITY.slice(3).map((event) => ({ kind: 'event', event }))];
  }
  if (context === 'brief') {
    return [{ who: 'agent', text: 'This is the Product Brief we created together. You can edit it directly, or tell me what you want changed in your own words — both paths update the same brief.' }];
  }
  if (context === 'outputs') {
    return [{ who: 'agent', text: 'These are the factory’s real outputs, organized by the stage that produced them. Pick one and I can explain the decision, connect it back to the brief, or help you steer what happens next.' }];
  }
  if (context === 'files' || context === 'docs') {
    return [{ who: 'agent', text: 'These are the source directories and files the factory works from. I read the generated directory summaries first, then narrow retrieval to the smallest relevant subtree before opening individual documents.' }];
  }
  if (context === 'maintenance') {
    return [{ who: 'agent', text: 'The product has shipped. I’m still here to help you understand what is running, describe a change, or start the next maintenance task.' }];
  }
  if (context === 'ingesting') {
    return [{ who: 'agent', text: 'I’m still processing your uploads in the background — I’ll keep this page updating as results land. You can pick up the interview whenever you’re ready.' }];
  }
  return [{ who: 'agent', text: 'I’m watching this project for you — 5 of 11 tickets done, 3 agents working, $4.20 spent. Ask me about progress, scope, or anything in your documents.' }];
}
function conciergeReply(context, text, sourceContext) {
  const t = text.toLowerCase();
  if (context === 'files' || context === 'docs') {
    if (sourceContext) {
      const source = sourceContext.type === 'file' ? sourceContext.name : sourceContext.type === 'directory' ? `the generated ${sourceContext.name} directory summary` : 'the generated source overview';
      const coverage = sourceContext.summary_status === 'Failed' || sourceContext.summary_status === 'failed' ? ' Its latest refresh failed, so I would keep the incomplete coverage visible rather than treating this as current.' : sourceContext.summary_status === 'Needs refresh' || sourceContext.summary_status === 'pending' ? ' It is awaiting refresh, so I would verify the underlying file before relying on it.' : '';
      return `From ${source}: ${sourceContext.summary_md}${coverage}`;
    }
    const docs = (window.PROJ_MATERIALS || []).map((m) => m.name);
    const hit = docs.find((n) => t.includes(n.split('.')[0].split('-')[0]) || t.includes(n.toLowerCase()));
    if (hit) return `From ${hit}: that’s covered there. I’ll cite the exact section once document citations ship — for now I can summarize what it contains.`;
    return 'I’ll start from the source overview, choose the most relevant directory summary, then narrow the search to that subtree.';
  }
  if (context === 'build') return 'On it — I’ve relayed that to the build team and flagged it on the board. I’ll surface any change here as the agents pick it up.';
  if (context === 'brief') return 'I can revise that in the Product Brief. Tell me the outcome you want, and I’ll keep the rest of the document consistent with it.';
  if (context === 'outputs') return 'I’ll relate that output to the Product Brief and the stage that produced it, then show you what would change downstream.';
  if (context === 'maintenance') return 'Tell me what should change in the delivered product, and I’ll turn it into a maintenance task without losing the project context.';
  return 'Got it. I’ll keep an eye on the build and surface anything relevant here.';
}

function ProjectConcierge({ context = 'overview', build, onOpen, docChips, selectedLabel, sourceContext, collapsed, onCollapsedChange }) {
  const chat = useConciergeChat(conciergeSeed(context, build, sourceContext), (text) => conciergeReply(context, text, sourceContext));
  const [localCollapsed, setLocalCollapsed] = React.useState(false);
  const savedScroll = React.useRef(0);
  const isCollapsed = typeof collapsed === 'boolean' ? collapsed : localCollapsed;
  const setCollapsed = (next) => { setLocalCollapsed(next); onCollapsedChange && onCollapsedChange(next); };
  React.useEffect(() => {
    if (!isCollapsed) requestAnimationFrame(() => { if (chat.scroller.current) chat.scroller.current.scrollTop = savedScroll.current; });
  }, [isCollapsed]);
  const priorContext = React.useRef(context);
  React.useEffect(() => {
    if (priorContext.current === context) return;
    priorContext.current = context;
    const next = conciergeSeed(context, build, sourceContext)[0];
    if (next) chat.push(next);
  }, [context]);
  const subtitle = context === 'build' ? (build && build.allDone ? 'Build complete' : 'Relaying the build')
    : context === 'brief' ? 'Working from your brief'
    : context === 'outputs' ? 'Across the factory’s work'
    : context === 'files' || context === 'docs' ? 'Across your source material'
    : context === 'maintenance' ? 'Supporting the shipped product'
    : context === 'ingesting' ? 'Processing in background'
    : 'Watching this project';
  const working = chat.thinking ? 'Thinking' : (context === 'build' && build && !build.allDone) ? 'Working' : (context === 'ingesting') ? 'Processing' : false;
  const suggestions = context === 'build' ? ['Summarize progress', 'What’s blocking the build?', 'Reprioritize a ticket']
    : context === 'brief' ? ['What is missing?', 'Make this more concise', 'Revise the selected section']
    : context === 'outputs' ? ['Explain this output', 'Relate it to the brief', 'What changed?']
    : context === 'files' || context === 'docs' ? (docChips && docChips.length ? docChips : ['What’s in the price book?', 'Summarize the SOP'])
    : context === 'maintenance' ? ['Summarize what shipped', 'Describe a change', 'Check current health']
    : ['How’s the build going?', 'What’s left to do?', 'Any blockers?'];

  if (isCollapsed) return <button onClick={() => setCollapsed(false)} title="Open Concierge" aria-label="Open Concierge" style={{ position: 'absolute', right: 18, bottom: 18, zIndex: 30, width: 44, height: 44, display: 'grid', placeItems: 'center', borderRadius: '50%', border: `1px solid ${T.brand}55`, background: T.raised, boxShadow: T.shadowMd, cursor: 'pointer' }}><Sparkle size={16} color={T.brand} />{working && <span style={{ position: 'absolute', right: 2, top: 2, width: 9, height: 9, borderRadius: '50%', background: T.success, boxShadow: `0 0 0 2px ${T.raised}`, animation: 'sfPulse 1.5s ease-in-out infinite' }} />}</button>;

  return (
    <div style={{ width: 340, flexShrink: 0, borderLeft: `1px solid ${T.borderSubtle}`, background: T.raised, display: 'flex', flexDirection: 'column', minHeight: 0, alignSelf: 'stretch' }}>
      <ConciergeHeader subtitle={subtitle} working={working} onCollapse={() => { savedScroll.current = chat.scroller.current ? chat.scroller.current.scrollTop : 0; setCollapsed(true); }} />
      <div ref={chat.scroller} style={{ flex: 1, overflow: 'auto', padding: '14px 16px', display: 'flex', flexDirection: 'column', gap: 12 }}>
        {chat.messages.map((m, i) => m.kind === 'event' ? <SystemEvent key={m.event.id} event={m.event} compact onOpen={onOpen} /> : <Message key={i} who={m.who} text={m.text} confidence={m.confidence} time={m.time} anim={i >= 1} />)}
        {!chat.thinking && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 7 }}>
            <CategoryLabel>{selectedLabel ? `Ask about ${selectedLabel}` : context === 'files' || context === 'docs' ? 'Ask about source material' : 'Try asking'}</CategoryLabel>
            <QuickReplies options={suggestions} onPick={(o) => chat.sendText(o)} />
          </div>
        )}
        {context === 'build' && !chat.thinking && (
          <div style={{ padding: 11, borderRadius: T.rLg, border: `1px solid ${T.brand}33`, background: T.brandSoft + '66' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 5 }}><Sparkle size={11} color={T.brandDeep} /><CategoryLabel tone="brand">Steer the build</CategoryLabel></div>
            <p style={{ font: `400 12px/1.5 ${T.sans}`, color: T.secondary, margin: 0 }}>Ask me to reprioritize a ticket, change scope, or pause an agent — I’ll pass it straight to the build team.</p>
          </div>
        )}
        {chat.thinking && <TypingIndicator label={chat.thinking} />}
      </div>
      <div style={{ flexShrink: 0, padding: '12px 16px', borderTop: `1px solid ${T.borderSubtle}` }}>
        <Composer placeholder={context === 'build' ? 'Ask or steer the build team…' : context === 'brief' ? 'Ask or revise the brief…' : context === 'outputs' ? 'Ask about this factory output…' : context === 'files' || context === 'docs' ? 'Ask about this directory or file…' : 'Ask the Concierge…'} value={chat.draft} onChange={chat.setDraft} onSend={() => chat.sendText()} />
      </div>
    </div>
  );
}

Object.assign(window, { useConciergeChat, ConciergeHeader, QuickReplies, ChoiceList, ProcessingScreen, InterviewRail, ProjectConcierge, FACTORY_ACTIVITY, SystemEvent, FactoryActivity });
