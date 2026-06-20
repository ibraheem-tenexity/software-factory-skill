import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import { BriefForm } from "./BriefForm";

type Msg = { role: string; content: string; msg_type?: string; ts?: number };

// A message arrives twice — once in the POST /api/chat response, once echoed over the SSE
// stream (the server _push_sse's the same reply so other watchers see it). Dedup on a stable
// identity so the caller's own client doesn't render each reply twice.
const keyOf = (m: Msg) => `${m.ts ?? ""}|${m.role}|${m.content}`;
function mergeMsgs(prev: Msg[], incoming: Msg[]): Msg[] {
  const seen = new Set(prev.map(keyOf));
  const fresh: Msg[] = [];
  for (const m of incoming) {
    const k = keyOf(m);
    if (seen.has(k)) continue;
    seen.add(k);
    fresh.push(m);
  }
  return fresh.length ? [...prev, ...fresh] : prev;
}

export function ChatPanel({ projectId, onProjectCreated }: { projectId: string | null; onProjectCreated: (id: string) => void }) {
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!projectId) { setMsgs([]); return; }
    api.chatHistory(projectId).then((d) => setMsgs(d.messages || [])).catch(() => setMsgs([]));
    // live updates: SSE stream of new messages for this run
    const es = new EventSource(`/api/chat/${projectId}/stream`, { withCredentials: true } as any);
    es.onmessage = (e) => {
      try {
        const m = JSON.parse(e.data);
        const arr = Array.isArray(m) ? m : [m];
        setMsgs((prev) => mergeMsgs(prev, arr));
      } catch { /* heartbeat */ }
    };
    return () => es.close();
  }, [projectId]);

  useEffect(() => { endRef.current?.scrollIntoView({ behavior: "smooth" }); }, [msgs]);

  const send = async () => {
    const message = text.trim();
    if (!message || busy) return;
    setText("");
    setBusy(true);
    setMsgs((prev) => [...prev, { role: "user", content: message }]);
    try {
      const r = await api.chat({ project_id: projectId, message });
      if (!projectId && r.project_id) onProjectCreated(r.project_id);
      setMsgs((prev) => mergeMsgs(prev, r.messages || []));
    } catch {
      setMsgs((prev) => [...prev, { role: "system", content: "(chat error)" }]);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="chat-panel">
      <div className="messages">
        {msgs.length === 0 && (
          <div className="empty">Tell me what you'd like to build — I'll interview you to build a complete brief.</div>
        )}
        {msgs.map((m, i) => (
          <div key={i} className={"msg " + (m.role || "assistant")}>{m.content}</div>
        ))}
        <div ref={endRef} />
      </div>
      {projectId && <BriefForm projectId={projectId} />}
      <div className="compose">
        <textarea
          value={text}
          placeholder="Message the concierge…"
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); } }}
        />
        <button onClick={send} disabled={busy}>Send</button>
      </div>
    </div>
  );
}
