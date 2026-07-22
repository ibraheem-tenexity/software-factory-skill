// recipes.tsx — Tenexity OS "Recipes" library (CBT-9 admin authoring UI, closes the gap: the
// admin CRUD routes have been live since PR #390 with no UI consuming them). Internal-only editor
// for the reusable build blueprints customers pick from during intake (RecipePicker in
// OnboardingScreen.tsx already reads the Published/light half of this data via api.listRecipes()).
//
// Backend contract (console/routers/admin_os.py + src/software_factory/recipes/store.py):
//   name, tagline, category, capabilities (customer-facing), body_md (internal notes/brief input),
//   repo_url (single linked GitHub repo — the build seed), images ({url, public, caption?}),
//   status (draft|published|archived, DB CHECK constraint).
// NOTE: the design mock (design/recipes.jsx) also sketches a per-recipe "systems" tag list and a
// multi-repo editor; neither has a backing column (migrations/versions/0029_recipes_table.py has
// no `systems` field and RecipeIn.repo_url is a single string) — both are left out here rather
// than built as client-only state that silently doesn't persist.
//
// Save can reject with HTTP 400 whose `.detail` is the store's verbatim reason (e.g. "...has no
// AGENTS.md or CLAUDE.md at the repo root..." — see RecipeValidationError). That exact text is
// rendered inline, never a generic "save failed".
import React from "react";
import { T } from "./tokens";
import { AdminBtn, ColHead, Mono } from "./views";
import { Icon, StatusPill } from "./primitives";
import { Chips } from "../components/onboarding/design";
import { api } from "../api";
import type { AdminRecipe, RecipeImage, ApiError } from "../api";

const RECIPE_CATEGORIES = ["Sales & Quoting", "Integrations", "Inventory", "Customer", "Finance", "Operations"];
const STATUS_ORDER = ["draft", "published", "archived"] as const;
const STATUS_TONE: Record<string, "warning" | "success" | "neutral"> = { draft: "warning", published: "success", archived: "neutral" };

function blank(): AdminRecipe {
  return { id: "", name: "Untitled recipe", tagline: "", category: "", capabilities: [], body_md: "", repo_url: "", images: [], status: "draft" };
}

// ── small tag editor (capabilities) ─────────────────────────────────────────────────────────

function TagEditor({ tags, onChange, placeholder }: { tags: string[]; onChange: (v: string[]) => void; placeholder?: string }) {
  const [text, setText] = React.useState("");
  const commit = () => {
    const t = text.trim();
    if (t && !tags.includes(t)) onChange([...tags, t]);
    setText("");
  };
  return (
    <div style={{ display: "flex", flexWrap: "wrap", gap: 7 }}>
      {tags.map((t) => (
        <span key={t} style={{ display: "inline-flex", alignItems: "center", gap: 5, padding: "5px 6px 5px 11px", borderRadius: 9999, border: `1px solid ${T.borderDefault}`, background: T.raised, font: `500 12.5px/1 ${T.sans}`, color: T.fg }}>
          {t}
          <button onClick={() => onChange(tags.filter((x) => x !== t))} title="Remove" style={{ width: 18, height: 18, display: "grid", placeItems: "center", border: "none", borderRadius: "50%", background: T.sunken, color: T.tertiary, cursor: "pointer" }}>
            <Icon name="x" size={10} color={T.tertiary} />
          </button>
        </span>
      ))}
      <span style={{ display: "inline-flex", alignItems: "center", gap: 4, padding: "3px 4px 3px 11px", borderRadius: 9999, border: `1px dashed ${T.borderDefault}`, background: T.raised }}>
        <input
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); commit(); } }}
          placeholder={placeholder || "Add…"}
          style={{ width: 150, border: "none", outline: "none", background: "transparent", font: `500 12.5px/1 ${T.sans}`, color: T.fg }}
        />
        <button onMouseDown={(e) => e.preventDefault()} onClick={commit} title="Add"
          style={{ width: 22, height: 22, flexShrink: 0, display: "grid", placeItems: "center", borderRadius: "50%", border: "none", background: T.brand, cursor: "pointer" }}>
          <Icon name="plus" size={12} color="#fff" />
        </button>
      </span>
    </div>
  );
}

// ── image entries (Public/Internal toggle) ──────────────────────────────────────────────────

function ImageEditor({ images, onChange }: { images: RecipeImage[]; onChange: (v: RecipeImage[]) => void }) {
  const add = () => onChange([...images, { url: "", public: false, caption: "" }]);
  const patch = (i: number, p: Partial<RecipeImage>) => onChange(images.map((im, j) => (j === i ? { ...im, ...p } : im)));
  const remove = (i: number) => onChange(images.filter((_, j) => j !== i));
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
      {images.map((im, i) => (
        <div key={i} style={{ display: "flex", alignItems: "flex-start", gap: 10, padding: "11px 12px", borderRadius: T.rMd, border: `1px solid ${T.borderSubtle}`, background: T.sunken }}>
          <div style={{ flex: 1, minWidth: 0, display: "flex", flexDirection: "column", gap: 6 }}>
            <input value={im.url} onChange={(e) => patch(i, { url: e.target.value })} placeholder="https://…/screenshot.png"
              style={{ width: "100%", boxSizing: "border-box", border: "none", outline: "none", background: "transparent", font: `500 12.5px/1.3 ${T.mono}`, color: T.fg }} />
            <input value={im.caption || ""} onChange={(e) => patch(i, { caption: e.target.value })} placeholder="caption (internal)…"
              style={{ width: "100%", boxSizing: "border-box", border: "none", outline: "none", background: "transparent", font: `400 12px/1.3 ${T.sans}`, color: T.secondary }} />
          </div>
          <button onClick={() => patch(i, { public: !im.public })} title="Public images are shown to the customer; Internal stays OS-side"
            style={{ display: "inline-flex", alignItems: "center", gap: 5, flexShrink: 0, border: `1px solid ${im.public ? T.brand + "66" : T.borderSubtle}`, background: im.public ? T.brandSoft : T.raised, borderRadius: 9999, padding: "5px 10px", cursor: "pointer" }}>
            <span style={{ font: `600 9.5px/1 ${T.mono}`, letterSpacing: "0.05em", textTransform: "uppercase", color: im.public ? T.brandDeep : T.tertiary }}>{im.public ? "Public" : "Internal"}</span>
          </button>
          <button onClick={() => remove(i)} title="Remove image"
            style={{ width: 26, height: 26, flexShrink: 0, display: "grid", placeItems: "center", border: `1px solid ${T.borderSubtle}`, borderRadius: 6, background: T.raised, color: T.tertiary, cursor: "pointer" }}>
            <Icon name="x" size={13} color={T.tertiary} />
          </button>
        </div>
      ))}
      <button onClick={add} style={{ alignSelf: "flex-start", display: "inline-flex", alignItems: "center", gap: 6, font: `500 12.5px/1 ${T.sans}`, padding: "8px 13px", borderRadius: T.rMd, cursor: "pointer", border: `1px dashed ${T.borderDefault}`, background: T.raised, color: T.secondary }}>
        <Icon name="plus" size={14} color={T.tertiary} /> Add image
      </button>
    </div>
  );
}

// ── minimal markdown preview (headers/lists/paragraphs — the description is internal notes, not
//    a rendered deliverable, so this deliberately stays lighter than the full artifact renderer) ──

function inlineRender(text: string): React.ReactNode {
  const parts = text.split(/(\*\*[^*]+\*\*|`[^`]+`)/g);
  return parts.map((p, i) => {
    if (p.startsWith("**") && p.endsWith("**")) return <strong key={i}>{p.slice(2, -2)}</strong>;
    if (p.startsWith("`") && p.endsWith("`")) return <code key={i} style={{ font: `500 12px/1 ${T.mono}`, background: T.sunken, padding: "1px 4px", borderRadius: 3 }}>{p.slice(1, -1)}</code>;
    return p;
  });
}

function MarkdownPreview({ content }: { content: string }) {
  const lines = content.split("\n");
  const blocks: React.ReactNode[] = [];
  let i = 0, key = 0;
  while (i < lines.length) {
    const line = lines[i];
    const hm = line.match(/^(#{1,3})\s+(.+)/);
    if (hm) {
      const level = hm[1].length;
      const sizes = ["", "18px", "15px", "13px"];
      blocks.push(<div key={key++} style={{ margin: `${level === 1 ? 20 : 14}px 0 6px`, font: `700 ${sizes[level]}/1.3 ${T.display}`, color: T.fg }}>{inlineRender(hm[2].trim())}</div>);
      i++; continue;
    }
    if (/^[-*]\s/.test(line)) {
      const items: string[] = [];
      while (i < lines.length && /^[-*]\s/.test(lines[i])) { items.push(lines[i].replace(/^[-*]\s/, "")); i++; }
      blocks.push(
        <ul key={key++} style={{ margin: "6px 0", paddingLeft: 18, display: "flex", flexDirection: "column", gap: 3 }}>
          {items.map((it, ii) => <li key={ii} style={{ font: `400 13px/1.5 ${T.sans}`, color: T.fg }}>{inlineRender(it)}</li>)}
        </ul>
      );
      continue;
    }
    if (!line.trim()) { i++; continue; }
    const para: string[] = [];
    while (i < lines.length && lines[i].trim() && !lines[i].startsWith("#") && !/^[-*]\s/.test(lines[i])) { para.push(lines[i]); i++; }
    if (para.length) blocks.push(<p key={key++} style={{ margin: "6px 0", font: `400 13px/1.6 ${T.sans}`, color: T.secondary }}>{inlineRender(para.join(" "))}</p>);
    else i++;
  }
  return <div>{blocks}</div>;
}

// ── section wrapper ──────────────────────────────────────────────────────────────────────────

function EditorSection({ title, sub, children, right }: { title: string; sub?: string; children: React.ReactNode; right?: React.ReactNode }) {
  return (
    <section style={{ borderTop: `1px solid ${T.borderSubtle}`, padding: "16px 20px" }}>
      <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 12, marginBottom: 12 }}>
        <div>
          <div style={{ font: `600 13.5px/1.2 ${T.sans}`, color: T.fg }}>{title}</div>
          {sub && <div style={{ font: `400 11.5px/1.4 ${T.sans}`, color: T.tertiary, marginTop: 3 }}>{sub}</div>}
        </div>
        {right}
      </div>
      {children}
    </section>
  );
}

// ── RecipesManagement ────────────────────────────────────────────────────────────────────────

export function RecipesManagement() {
  const [recipes, setRecipes] = React.useState<AdminRecipe[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [selected, setSelected] = React.useState<AdminRecipe | null>(null);
  const [isNew, setIsNew] = React.useState(false);

  const [name, setName] = React.useState("");
  const [tagline, setTagline] = React.useState("");
  const [category, setCategory] = React.useState("");
  const [capabilities, setCapabilities] = React.useState<string[]>([]);
  const [repoUrl, setRepoUrl] = React.useState("");
  const [images, setImages] = React.useState<RecipeImage[]>([]);
  const [bodyMd, setBodyMd] = React.useState("");
  const [status, setStatus] = React.useState("draft");
  const [mode, setMode] = React.useState<"write" | "split" | "preview">("split");
  const [saving, setSaving] = React.useState(false);
  const [dirty, setDirty] = React.useState(false);
  const [saveError, setSaveError] = React.useState<string | null>(null);

  const loadList = React.useCallback(() => {
    api.adminListRecipes().then((r) => setRecipes(r.recipes)).catch(() => {}).finally(() => setLoading(false));
  }, []);
  React.useEffect(() => { loadList(); }, [loadList]);

  const populate = (r: AdminRecipe) => {
    setName(r.name);
    setTagline(r.tagline || "");
    setCategory(r.category || "");
    setCapabilities(r.capabilities || []);
    setRepoUrl(r.repo_url || "");
    setImages(r.images || []);
    setBodyMd(r.body_md || "");
    setStatus(r.status);
    setSaveError(null);
    setDirty(false);
  };

  const selectRecipe = (r: AdminRecipe) => {
    setSelected(r);
    setIsNew(false);
    populate(r);
  };

  const startNew = () => {
    setSelected(null);
    setIsNew(true);
    populate(blank());
    setMode("split");
  };

  const cycleStatus = () => {
    setStatus((s) => STATUS_ORDER[(STATUS_ORDER.indexOf(s as any) + 1) % STATUS_ORDER.length]);
    setDirty(true);
  };

  const save = async () => {
    setSaving(true);
    setSaveError(null);
    const payload = {
      name: name.trim() || "Untitled recipe",
      tagline: tagline || undefined,
      category: category || undefined,
      capabilities,
      body_md: bodyMd || undefined,
      repo_url: repoUrl.trim() || undefined,
      images,
      status,
    };
    try {
      if (isNew) {
        const row = await api.adminCreateRecipe(payload);
        setRecipes((prev) => [row, ...prev]);
        setSelected(row);
        setIsNew(false);
        populate(row);
      } else if (selected) {
        const row = await api.adminPatchRecipe(selected.id, payload);
        setRecipes((prev) => prev.map((r) => (r.id === row.id ? row : r)));
        setSelected(row);
        populate(row);
      }
    } catch (e) {
      const err = e as ApiError;
      setSaveError(typeof err?.detail === "string" ? err.detail : err?.message || "Failed to save recipe.");
    } finally {
      setSaving(false);
    }
  };

  const hasEditor = isNew || selected !== null;

  return (
    <div style={{ display: "flex", gap: 16, alignItems: "flex-start" }}>
      {/* master list */}
      <div style={{ width: 280, flexShrink: 0, border: `1px solid ${T.borderSubtle}`, borderRadius: T.rLg, overflow: "hidden", background: T.raised }}>
        <div style={{ padding: "10px 14px", borderBottom: `1px solid ${T.borderSubtle}`, background: T.sunken, display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <ColHead>All recipes</ColHead>
          <AdminBtn primary onClick={startNew}><Icon name="plus" size={13} /> New recipe</AdminBtn>
        </div>
        <div style={{ maxHeight: 640, overflowY: "auto" }}>
          {loading && <div style={{ padding: "20px 16px" }}><Mono style={{ color: T.tertiary }}>Loading…</Mono></div>}
          {!loading && recipes.length === 0 && (
            <div style={{ padding: "32px 16px", textAlign: "center" }}>
              <Mono style={{ fontSize: 12, color: T.tertiary }}>No recipes yet. Create one to get started.</Mono>
            </div>
          )}
          {recipes.map((r) => {
            const on = selected?.id === r.id && !isNew;
            return (
              <button key={r.id} onClick={() => selectRecipe(r)}
                style={{ textAlign: "left", cursor: "pointer", width: "100%", border: "none", borderBottom: `1px solid ${T.borderSubtle}`, borderLeft: `3px solid ${on ? T.brand : "transparent"}`, background: on ? T.brandSoft : "transparent", padding: "12px 13px", display: "flex", flexDirection: "column", gap: 7 }}>
                <span style={{ font: `600 13px/1.25 ${T.sans}`, color: T.fg, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{r.name}</span>
                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <StatusPill tone={STATUS_TONE[r.status] || "neutral"}>{r.status}</StatusPill>
                  {r.category && <Mono style={{ fontSize: 10, color: T.tertiary, flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{r.category}</Mono>}
                </div>
              </button>
            );
          })}
        </div>
      </div>

      {/* editor */}
      {hasEditor ? (
        <div style={{ flex: 1, minWidth: 0, border: `1px solid ${T.borderSubtle}`, borderRadius: T.rLg, overflow: "hidden", background: T.raised, display: "flex", flexDirection: "column" }}>
          <div style={{ padding: "16px 20px", borderBottom: `1px solid ${T.borderSubtle}` }}>
            <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 10 }}>
              <input value={name} onChange={(e) => { setName(e.target.value); setDirty(true); }}
                style={{ flex: 1, minWidth: 0, border: "none", outline: "none", background: "transparent", font: `400 22px/1.2 ${T.display}`, letterSpacing: "-0.01em", color: T.fg }} />
              <button onClick={cycleStatus} title="Cycle status" style={{ border: "none", background: "transparent", cursor: "pointer", padding: 0 }}>
                <StatusPill tone={STATUS_TONE[status] || "neutral"}>{status}</StatusPill>
              </button>
            </div>
            <input value={tagline} onChange={(e) => { setTagline(e.target.value); setDirty(true); }} placeholder="Customer-facing one-liner shown in the picker…"
              style={{ width: "100%", boxSizing: "border-box", border: "none", outline: "none", background: "transparent", font: `400 13.5px/1.4 ${T.sans}`, color: T.secondary }} />
          </div>

          <div style={{ maxHeight: 640, overflowY: "auto" }}>
            <EditorSection title="Classification" sub="Category shown to the customer in the picker.">
              <Chips options={RECIPE_CATEGORIES} value={category} onChange={(v) => { setCategory(v); setDirty(true); }} />
            </EditorSection>

            <EditorSection title="What the customer gets" sub="The plain-language capability list shown in the recipe picker.">
              <TagEditor tags={capabilities} onChange={(v) => { setCapabilities(v); setDirty(true); }} placeholder="Add a capability…" />
            </EditorSection>

            <EditorSection title="Linked GitHub repo" sub="Internal only — the build seed. The factory forks and extends this repo instead of building greenfield; it must document its architecture with an AGENTS.md or CLAUDE.md at the root.">
              <input value={repoUrl} onChange={(e) => { setRepoUrl(e.target.value); setDirty(true); }} placeholder="https://github.com/org/repo"
                style={{ width: "100%", boxSizing: "border-box", height: 36, padding: "0 11px", borderRadius: T.rMd, border: `1px solid ${T.borderDefault}`, background: T.bg, font: `500 13px/1 ${T.mono}`, color: T.fg, outline: "none" }} />
            </EditorSection>

            <EditorSection title="Image artifacts" sub="Internal reference screens & diagrams. Public images may surface to the customer; Internal stays OS-side.">
              <ImageEditor images={images} onChange={(v) => { setImages(v); setDirty(true); }} />
            </EditorSection>

            <EditorSection title="Description" sub="Internal markdown notes — also the concierge/stage-1 input when this recipe drives a build."
              right={
                <div style={{ display: "inline-flex", padding: 2, borderRadius: T.rMd, background: T.sunken, border: `1px solid ${T.borderSubtle}` }}>
                  {(["write", "split", "preview"] as const).map((m) => (
                    <button key={m} onClick={() => setMode(m)}
                      style={{ font: `600 10.5px/1 ${T.mono}`, letterSpacing: "0.05em", padding: "5px 9px", borderRadius: 5, cursor: "pointer", border: "none", background: mode === m ? T.fg : "transparent", color: mode === m ? "#fff" : T.tertiary, textTransform: "uppercase" }}>
                      {m}
                    </button>
                  ))}
                </div>
              }>
              <div style={{ display: "flex", minHeight: 260, border: `1px solid ${T.borderSubtle}`, borderRadius: T.rMd, overflow: "hidden" }}>
                {(mode === "write" || mode === "split") && (
                  <textarea value={bodyMd} onChange={(e) => { setBodyMd(e.target.value); setDirty(true); }} spellCheck={false}
                    placeholder="# Recipe — …"
                    style={{ flex: 1, minWidth: 0, resize: "none", border: "none", outline: "none", padding: "14px 16px", background: T.bg, color: T.fg, font: `400 13px/1.7 ${T.mono}`, borderRight: mode === "split" ? `1px solid ${T.borderSubtle}` : "none" }} />
                )}
                {(mode === "preview" || mode === "split") && (
                  <div style={{ flex: 1, minWidth: 0, overflowY: "auto", padding: "14px 18px", background: T.raised }}>
                    {bodyMd.trim() ? <MarkdownPreview content={bodyMd} /> : <Mono style={{ color: T.tertiary, fontSize: 12 }}>Nothing to preview yet.</Mono>}
                  </div>
                )}
              </div>
            </EditorSection>
          </div>

          <div style={{ display: "flex", flexDirection: "column", gap: 8, padding: "12px 20px", borderTop: `1px solid ${T.borderSubtle}`, background: T.sunken }}>
            {saveError && (
              <div style={{ padding: "8px 11px", borderRadius: T.rMd, background: T.dangerSoft, color: T.danger, font: `500 12px/1.5 ${T.sans}` }}>
                {saveError}
              </div>
            )}
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12 }}>
              <ColHead style={{ color: dirty ? T.warning : T.tertiary }}>
                {isNew ? "Unsaved · new recipe" : dirty ? "Unsaved changes" : selected ? `Recipe · ${selected.id}` : ""}
              </ColHead>
              <AdminBtn primary onClick={save} disabled={saving || (!dirty && !isNew)}>
                {saving ? "Saving…" : "Save"}
              </AdminBtn>
            </div>
          </div>
        </div>
      ) : (
        <div style={{ flex: 1, display: "grid", placeItems: "center", height: 320, border: `1px solid ${T.borderSubtle}`, borderRadius: T.rLg, background: T.raised }}>
          <Mono style={{ fontSize: 12, color: T.tertiary }}>Select a recipe to edit, or create a new one.</Mono>
        </div>
      )}
    </div>
  );
}
