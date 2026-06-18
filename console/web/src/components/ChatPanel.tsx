import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import { BriefForm } from "./BriefForm";

type Msg = { role: string; content: string; msg_type?: string };

export function ChatPanel({ runId, onRunCreated }: { runId: string | null; onRunCreated: (id: string) => void }) {
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!runId) { setMsgs([]); return; }
    api.chatHistory(runId).then((d) => setMsgs(d.messages || [])).catch(() => setMsgs([]));
    // live updates: SSE stream of new messages for this run
    const es = new EventSource(`/api/chat/${runId}/stream`, { withCredentials: true } as any);
    es.onmessage = (e) => {
      try {
        const m = JSON.parse(e.data);
        const arr = Array.isArray(m) ? m : [m];
        setMsgs((prev) => [...prev, ...arr]);
      } catch { /* heartbeat */ }
    };
    return () => es.close();
  }, [runId]);

  useEffect(() => { endRef.current?.scrollIntoView({ behavior: "smooth" }); }, [msgs]);

  const send = async () => {
    const message = text.trim();
    if (!message || busy) return;
    setText("");
    setBusy(true);
    setMsgs((prev) => [...prev, { role: "user", content: message }]);
    try {
      const r = await api.chat({ run_id: runId, message });
      if (!runId && r.run_id) onRunCreated(r.run_id);
      setMsgs((prev) => [...prev, ...(r.messages || [])]);
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
      {runId && <BriefForm runId={runId} />}
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
