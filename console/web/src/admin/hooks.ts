import React from "react";

export function useAdminFetch<T>(fn: () => Promise<T>) {
  const [data, setData] = React.useState<T | null>(null);
  const [loading, setLoading] = React.useState(true);
  const [rev, setRev] = React.useState(0);
  const fnRef = React.useRef(fn);
  fnRef.current = fn;
  React.useEffect(() => {
    let active = true;
    setLoading(true);
    fnRef
      .current()
      .then((d) => { if (active) { setData(d); setLoading(false); } })
      .catch(() => { if (active) { setData(null); setLoading(false); } });
    return () => {
      active = false;
    };
  }, [rev]);
  return { data, loading, refetch: () => setRev((r) => r + 1) };
}

export function toolKind(config: Record<string, unknown>): "MCP" | "HTTP" | "API" {
  if (config?.kind === "api") return "API";
  if (config?.type === "http") return "HTTP";
  return "MCP";
}

export function fmtRel(updated?: number | string): string {
  if (!updated) return "—";
  if (typeof updated === "string") return updated;
  const ts = updated > 1e10 ? updated : updated * 1000;
  const diff = Math.max(0, Date.now() - ts);
  const sec = Math.floor(diff / 1000);
  if (sec < 60) return `${sec}s ago`;
  const min = Math.floor(sec / 60);
  if (min < 60) return `${min}m ago`;
  const hr = Math.floor(min / 60);
  if (hr < 24) return `${hr}h ago`;
  const day = Math.floor(hr / 24);
  if (day < 30) return `${day}d ago`;
  const month = Math.floor(day / 30);
  return `${month}mo ago`;
}
