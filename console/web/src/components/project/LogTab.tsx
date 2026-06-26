// LogTab.tsx — live build-log tail for a running (or finished) project.
// Polls GET /api/projects/{id}/log every 3s; auto-scrolls to bottom on new output.
// Shows a truncation banner when the tail is capped (log > 20 KB), plus a download link.
import { useEffect, useRef, useState } from "react";
import { api } from "../../api";
import { T } from "../onboarding/design";

function fmtBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1048576) return `${Math.round(n / 1024)} KB`;
  return `${(n / 1048576).toFixed(1)} MB`;
}

export function LogTab({ projectId }: { projectId: string }) {
  const [log, setLog] = useState<string | null>(null);
  const [capped, setCapped] = useState(false);
  const [totalBytes, setTotalBytes] = useState(0);
  const bottomRef = useRef<HTMLDivElement>(null);
  const atBottomRef = useRef(true);

  useEffect(() => {
    let live = true;
    const poll = () => {
      api.projectLog(projectId).then((d) => {
        if (!live) return;
        setLog(d.log);
        setCapped(d.capped);
        setTotalBytes(d.total_bytes);
      }).catch(() => {});
    };
    poll();
    const h = setInterval(poll, 3000);
    return () => { live = false; clearInterval(h); };
  }, [projectId]);

  // Auto-scroll: only follow the bottom if the user hasn't scrolled up.
  useEffect(() => {
    if (atBottomRef.current) {
      bottomRef.current?.scrollIntoView({ behavior: "smooth" });
    }
  }, [log]);

  const handleScroll = (e: React.UIEvent<HTMLDivElement>) => {
    const el = e.currentTarget;
    atBottomRef.current = el.scrollHeight - el.scrollTop - el.clientHeight < 40;
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", minHeight: 0 }}>
      {/* toolbar */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between",
        padding: "10px 20px", borderBottom: `1px solid ${T.borderSubtle}`, flexShrink: 0,
        background: T.raised }}>
        <span style={{ font: `600 13px/1 ${T.display}`, color: T.fg }}>Build log</span>
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          {totalBytes > 0 && (
            <span style={{ font: `400 11px/1 ${T.mono}`, color: T.tertiary }}>
              {fmtBytes(totalBytes)} total
            </span>
          )}
          <a href={`/api/projects/${projectId}/log?full=1`} download={`${projectId}.log`}
            style={{ font: `500 11.5px/1 ${T.sans}`, color: T.brand, textDecoration: "none" }}>
            Download full log
          </a>
        </div>
      </div>

      {/* truncation banner */}
      {capped && (
        <div style={{ padding: "7px 20px", background: "#2d2a1a", borderBottom: `1px solid #4a4218`,
          font: `400 11.5px/1 ${T.mono}`, color: "#c9b44a", flexShrink: 0 }}>
          Showing last {fmtBytes(20000)} of {fmtBytes(totalBytes)} — download for the full log.
        </div>
      )}

      {/* log body */}
      <div onScroll={handleScroll} style={{ flex: 1, minHeight: 0, overflowY: "auto",
        background: "#0d0d10", padding: "14px 20px" }}>
        {log === null ? (
          <span style={{ font: `400 12px/1.5 ${T.mono}`, color: "#555" }}>Loading…</span>
        ) : log === "" ? (
          <span style={{ font: `400 12px/1.5 ${T.mono}`, color: "#555" }}>No log output yet — the build agent will write here once it starts.</span>
        ) : (
          <pre style={{ margin: 0, font: `400 11.5px/1.6 ${T.mono}`, color: "#d4d4d4",
            whiteSpace: "pre-wrap", wordBreak: "break-word" }}>{log}</pre>
        )}
        <div ref={bottomRef} />
      </div>
    </div>
  );
}
