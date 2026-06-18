import { useEffect, useState } from "react";
import { api, BRIEF_SECTIONS, Brief } from "../api";

// The structured brief, editable alongside the chat interview — both write the same brief
// (PUT /api/runs/{id}/brief). A filled dot marks a covered section.
export function BriefForm({ runId }: { runId: string }) {
  const [brief, setBrief] = useState<Brief>({});
  const [coverage, setCoverage] = useState<Record<string, boolean>>({});
  const [dirty, setDirty] = useState<Record<string, boolean>>({});

  useEffect(() => {
    let live = true;
    const load = () => api.brief(runId).then((d) => {
      if (!live) return;
      setBrief((prev) => {
        const next = { ...d.brief };
        // don't clobber fields the user is actively editing
        for (const k of Object.keys(dirty)) if (dirty[k]) next[k] = prev[k] ?? "";
        return next;
      });
      setCoverage(d.coverage);
    }).catch(() => {});
    load();
    const h = setInterval(load, 4000);
    return () => { live = false; clearInterval(h); };
  }, [runId]);

  const save = async (key: string) => {
    const d = await api.putBrief(runId, { [key]: brief[key] || "" });
    setCoverage(d.coverage);
    setDirty((p) => ({ ...p, [key]: false }));
  };

  return (
    <div className="brief">
      <h3>Project brief</h3>
      {BRIEF_SECTIONS.map(({ key, label }) => (
        <div className="brief-field" key={key}>
          <label><span className={"dot" + (coverage[key] ? " on" : "")} /> {label}</label>
          <textarea
            value={brief[key] || ""}
            placeholder={`Add ${label.toLowerCase()}…`}
            onChange={(e) => { setBrief((p) => ({ ...p, [key]: e.target.value })); setDirty((p) => ({ ...p, [key]: true })); }}
            onBlur={() => dirty[key] && save(key)}
          />
        </div>
      ))}
    </div>
  );
}
