// recipes.jsx — Recipes, two surfaces:
//
//  • RecipeLibrary  (Tenexity OS · internal) — the master list the internal team
//    curates. Operators edit the customer-facing summary AND attach the internal
//    build assets: linked GitHub repos and image artifacts. Markdown description
//    with live preview + "Open in viewer".
//  • RecipePicker  (customer · onboarding) — a light chooser shown during intake.
//    The customer sees only name / tagline / category / "what you get" — never the
//    repos, images or internal notes. "No recipe" is always an option.
//
// Reuses OS helpers (AdminBtn, PageTitle, ColHead, Mono) + Markdown + openArtifact
// + RECIPES / RECIPE_STATUS / RECIPE_CATEGORIES + shared T / Icon / Chips.

function RecipeStatusPill({ status }) {
  const s = (typeof RECIPE_STATUS !== 'undefined' && RECIPE_STATUS[status]) || { label: status, tone: 'neutral' };
  const tones = { neutral: [T.sunken, T.secondary], info: [T.brandSoft, T.brandDeep], warning: [T.warningSoft, T.warning], success: [T.successSoft, T.success] };
  const c = tones[s.tone] || tones.neutral;
  return <span style={{ font: `600 9.5px/1 ${T.mono}`, letterSpacing: '0.05em', textTransform: 'uppercase', color: c[1], background: c[0], border: `1px solid ${c[1]}22`, padding: '4px 7px', borderRadius: 4 }}>{s.label}</span>;
}

// A small comma-free tag editor: existing tags as removable chips + an inline add.
function TagEditor({ tags, onChange, placeholder }) {
  const [text, setText] = React.useState('');
  const commit = () => { const t = text.trim(); if (t && !tags.includes(t)) onChange([...tags, t]); setText(''); };
  return (
    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 7 }}>
      {tags.map((t) => (
        <span key={t} style={{ display: 'inline-flex', alignItems: 'center', gap: 5, padding: '5px 6px 5px 11px', borderRadius: 9999, border: `1px solid ${T.borderDefault}`, background: T.raised, font: `500 12.5px/1 ${T.sans}`, color: T.fg }}>
          {t}
          <button onClick={() => onChange(tags.filter((x) => x !== t))} title="Remove" style={{ width: 18, height: 18, display: 'grid', placeItems: 'center', border: 'none', borderRadius: '50%', background: T.sunken, color: T.tertiary, cursor: 'pointer' }}><Icon name="x" size={10} color={T.tertiary} /></button>
        </span>
      ))}
      <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4, padding: '3px 4px 3px 11px', borderRadius: 9999, border: `1px dashed ${T.borderDefault}`, background: T.raised }}>
        <input value={text} onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); commit(); } }}
          placeholder={placeholder || 'Add…'}
          style={{ width: 150, border: 'none', outline: 'none', background: 'transparent', font: `500 12.5px/1 ${T.sans}`, color: T.fg }} />
        <button onMouseDown={(e) => e.preventDefault()} onClick={commit} title="Add" style={{ width: 22, height: 22, flexShrink: 0, display: 'grid', placeItems: 'center', borderRadius: '50%', border: 'none', background: T.brand, color: '#fff', cursor: 'pointer' }}><Icon name="plus" size={12} color="#fff" /></button>
      </span>
    </div>
  );
}

// Linked GitHub repos editor (internal only).
function RepoEditor({ repos, onChange }) {
  const add = () => onChange([...repos, { name: '', url: '', desc: '' }]);
  const patch = (i, p) => onChange(repos.map((r, j) => j === i ? { ...r, ...p } : r));
  const remove = (i) => onChange(repos.filter((_, j) => j !== i));
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
      {repos.map((r, i) => (
        <div key={i} style={{ display: 'flex', alignItems: 'flex-start', gap: 10, padding: '11px 12px', borderRadius: T.rMd, border: `1px solid ${T.borderSubtle}`, background: T.sunken }}>
          <span style={{ width: 30, height: 30, flexShrink: 0, borderRadius: 7, display: 'grid', placeItems: 'center', background: T.ink }}><Icon name="github" size={15} color="#fff" /></span>
          <div style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column', gap: 6 }}>
            <input value={r.name} onChange={(e) => patch(i, { name: e.target.value })} placeholder="owner/repo"
              style={{ width: '100%', border: 'none', outline: 'none', background: 'transparent', font: `600 13px/1.2 ${T.mono}`, color: T.fg }} />
            <input value={r.url} onChange={(e) => patch(i, { url: e.target.value })} placeholder="github.com/owner/repo"
              style={{ width: '100%', border: 'none', outline: 'none', background: 'transparent', font: `400 11.5px/1.2 ${T.mono}`, color: T.brandDeep }} />
            <input value={r.desc} onChange={(e) => patch(i, { desc: e.target.value })} placeholder="What this repo seeds…"
              style={{ width: '100%', border: 'none', outline: 'none', background: 'transparent', font: `400 12px/1.3 ${T.sans}`, color: T.secondary }} />
          </div>
          <button onClick={() => remove(i)} title="Unlink repo" style={{ width: 26, height: 26, flexShrink: 0, display: 'grid', placeItems: 'center', border: `1px solid ${T.borderSubtle}`, borderRadius: 6, background: T.raised, color: T.tertiary, cursor: 'pointer' }}><Icon name="trash" size={13} color={T.tertiary} /></button>
        </div>
      ))}
      <button onClick={add} style={{ alignSelf: 'flex-start', display: 'inline-flex', alignItems: 'center', gap: 6, font: `500 12.5px/1 ${T.sans}`, padding: '8px 13px', borderRadius: T.rMd, cursor: 'pointer', border: `1px dashed ${T.borderDefault}`, background: T.raised, color: T.secondary }}>
        <Icon name="github" size={14} color={T.tertiary} /> Link a GitHub repo
      </button>
    </div>
  );
}

// Linked image artifacts editor (internal only). Uses striped placeholders — the
// operator names each slot; the actual asset is dropped in later.
function ImageEditor({ images, onChange }) {
  const add = () => onChange([...images, { name: 'new-image.png', note: '' }]);
  const patch = (i, p) => onChange(images.map((r, j) => j === i ? { ...r, ...p } : r));
  const remove = (i) => onChange(images.filter((_, j) => j !== i));
  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(150px, 1fr))', gap: 10 }}>
      {images.map((im, i) => (
        <div key={i} style={{ border: `1px solid ${T.borderSubtle}`, borderRadius: T.rMd, overflow: 'hidden', background: T.raised }}>
          <div style={{ position: 'relative', height: 84, background: `repeating-linear-gradient(45deg, ${T.sunken}, ${T.sunken} 7px, ${T.bg} 7px, ${T.bg} 14px)`, display: 'grid', placeItems: 'center' }}>
            <Icon name="image" size={20} color={T.tertiary} />
            <button onClick={() => remove(i)} title="Remove image" style={{ position: 'absolute', top: 5, right: 5, width: 22, height: 22, display: 'grid', placeItems: 'center', border: 'none', borderRadius: '50%', background: 'rgba(0,0,0,0.5)', color: '#fff', cursor: 'pointer' }}><Icon name="x" size={11} color="#fff" /></button>
          </div>
          <div style={{ padding: '8px 9px', display: 'flex', flexDirection: 'column', gap: 4 }}>
            <input value={im.name} onChange={(e) => patch(i, { name: e.target.value })} placeholder="file.png"
              style={{ border: 'none', outline: 'none', background: 'transparent', font: `600 11px/1.2 ${T.mono}`, color: T.fg }} />
            <input value={im.note} onChange={(e) => patch(i, { note: e.target.value })} placeholder="caption…"
              style={{ border: 'none', outline: 'none', background: 'transparent', font: `400 11px/1.3 ${T.sans}`, color: T.tertiary }} />
          </div>
        </div>
      ))}
      <button onClick={add} style={{ minHeight: 130, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 6, border: `1px dashed ${T.borderDefault}`, borderRadius: T.rMd, background: T.raised, color: T.secondary, cursor: 'pointer', font: `500 12px/1 ${T.sans}` }}>
        <Icon name="plus" size={16} color={T.tertiary} /> Add image
      </button>
    </div>
  );
}

function EditorSection({ title, sub, children, right }) {
  return (
    <section style={{ borderTop: `1px solid ${T.borderSubtle}`, padding: '18px 20px' }}>
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 12, marginBottom: 13 }}>
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

function RecipeLibrary() {
  const [recipes, setRecipes] = React.useState(() => (typeof RECIPES !== 'undefined' ? RECIPES.map((r) => ({ ...r, repos: r.repos.map((x) => ({ ...x })), images: r.images.map((x) => ({ ...x })), includes: [...r.includes], systems: [...r.systems] })) : []));
  const [activeId, setActiveId] = React.useState(recipes[0] && recipes[0].id);
  const [mode, setMode] = React.useState('split'); // write | preview | split
  const [saved, setSaved] = React.useState(false);
  const savedTimer = React.useRef(null);

  const idx = recipes.findIndex((r) => r.id === activeId);
  const r = recipes[idx];
  const patch = (p) => setRecipes((rs) => rs.map((x) => x.id === activeId ? { ...x, ...p } : x));
  const nameDict = useDictation(r && r.name, (v) => patch({ name: v }));
  const contentDict = useDictation(r && r.content, (v) => patch({ content: v }));

  const flash = () => { setSaved(true); clearTimeout(savedTimer.current); savedTimer.current = setTimeout(() => setSaved(false), 1800); };
  const save = () => { if (typeof registerArtifacts === 'function' && r) registerArtifacts({ [r.id]: { ...(ART[r.id] || {}), content: r.content, name: r.id + '.md', updated: 'just now', type: 'md', project: 'Recipes', node: r.category, agent: 'Proposal Lead · ' + r.owner } }); patch({ updated: 'just now' }); flash(); };
  const newRecipe = () => {
    const id = 'recipe-' + Date.now();
    const d = { id, name: 'Untitled recipe', tagline: '', category: 'Operations', status: 'draft', builds: 0, updated: 'just now', owner: 'TENDER', includes: [], systems: [], repos: [], images: [], content: '# Recipe — Untitled\n\nDescribe what this recipe produces.\n' };
    setRecipes((rs) => [d, ...rs]); setActiveId(id); setMode('split');
  };
  const cycleStatus = () => { const order = ['draft', 'published', 'archived']; patch({ status: order[(order.indexOf(r.status) + 1) % order.length] }); };

  return (
    <React.Fragment>
      <PageTitle title="Recipes" sub="Reusable build blueprints the team curates. Attach GitHub repos & images; customers pick from these during intake and see only the summary."
        actions={<AdminBtn primary onClick={newRecipe}>+ New recipe</AdminBtn>} />

      <div style={{ display: 'flex', gap: 16, alignItems: 'flex-start' }}>
        {/* master list */}
        <div style={{ width: 290, flexShrink: 0, border: `1px solid ${T.borderSubtle}`, borderRadius: T.rLg, overflow: 'hidden', background: T.raised }}>
          <div style={{ padding: '10px 14px', borderBottom: `1px solid ${T.borderSubtle}`, background: T.sunken, display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <ColHead>All recipes</ColHead><Mono style={{ fontSize: 10.5 }}>{recipes.length}</Mono>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column' }}>
            {recipes.map((d, i) => {
              const on = d.id === activeId;
              return (
                <button key={d.id} onClick={() => setActiveId(d.id)} style={{ textAlign: 'left', cursor: 'pointer', border: 'none', borderTop: i ? `1px solid ${T.borderSubtle}` : 'none', borderLeft: `3px solid ${on ? T.brand : 'transparent'}`,
                  background: on ? T.brandSoft + '55' : T.raised, padding: '12px 13px', display: 'flex', flexDirection: 'column', gap: 7 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 7 }}>
                    <Icon name="book" size={13} color={T.tertiary} />
                    <span style={{ flex: 1, minWidth: 0, font: `600 13px/1.25 ${T.sans}`, color: T.fg, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{d.name}</span>
                  </div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <RecipeStatusPill status={d.status} />
                    <Mono style={{ fontSize: 10, color: T.tertiary, flex: 1, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{d.category}</Mono>
                    <Mono style={{ fontSize: 10, color: T.tertiary }}>{d.builds} builds</Mono>
                  </div>
                </button>
              );
            })}
          </div>
        </div>

        {/* editor */}
        {r ? (
          <div style={{ flex: 1, minWidth: 0, border: `1px solid ${T.borderSubtle}`, borderRadius: T.rLg, overflow: 'hidden', background: T.raised, display: 'flex', flexDirection: 'column' }}>
            {/* header */}
            <div style={{ padding: '16px 20px', borderBottom: `1px solid ${T.borderSubtle}` }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 10 }}>
                <input value={r.name} onChange={(e) => patch({ name: e.target.value })}
                  style={{ flex: 1, minWidth: 0, border: 'none', outline: 'none', background: 'transparent', font: `400 22px/1.2 ${T.display}`, letterSpacing: '-0.01em', color: T.fg }} />
                {nameDict.supported && <MicButton size={28} listening={nameDict.listening} onClick={nameDict.toggle} title="Dictate name" />}
                <button onClick={cycleStatus} title="Cycle status" style={{ border: 'none', background: 'transparent', cursor: 'pointer', padding: 0 }}><RecipeStatusPill status={r.status} /></button>
              </div>
              <input value={r.tagline} onChange={(e) => patch({ tagline: e.target.value })} placeholder="Customer-facing one-liner shown in the picker…"
                style={{ width: '100%', border: 'none', outline: 'none', background: 'transparent', font: `400 13.5px/1.4 ${T.sans}`, color: T.secondary }} />
            </div>

            <div style={{ maxHeight: 640, overflow: 'auto' }}>
              {/* classification */}
              <EditorSection title="Classification" sub="Category + the systems this recipe knows how to connect (both shown to the customer).">
                <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
                  <div>
                    <CategoryLabel style={{ display: 'block', marginBottom: 7 }}>Category</CategoryLabel>
                    <Chips options={RECIPE_CATEGORIES} value={r.category} onChange={(v) => patch({ category: v })} />
                  </div>
                  <div>
                    <CategoryLabel style={{ display: 'block', marginBottom: 7 }}>Systems</CategoryLabel>
                    <TagEditor tags={r.systems} onChange={(v) => patch({ systems: v })} placeholder="e.g. Epicor" />
                  </div>
                </div>
              </EditorSection>

              {/* what the customer gets */}
              <EditorSection title="What the customer gets" sub="The plain-language capability list shown in the recipe picker.">
                <TagEditor tags={r.includes} onChange={(v) => patch({ includes: v })} placeholder="Add a capability…" />
              </EditorSection>

              {/* internal build assets */}
              <EditorSection title="Linked GitHub repos" sub="Internal only — seeds the build. Never shown to the customer.">
                <RepoEditor repos={r.repos} onChange={(v) => patch({ repos: v })} />
              </EditorSection>

              <EditorSection title="Image artifacts" sub="Internal only — reference screens & diagrams attached to this recipe.">
                <ImageEditor images={r.images} onChange={(v) => patch({ images: v })} />
              </EditorSection>

              {/* description */}
              <EditorSection title="Description" sub="Internal markdown notes. Opens in the artifact viewer."
                right={
                  <div style={{ display: 'inline-flex', padding: 2, borderRadius: T.rMd, background: T.sunken, border: `1px solid ${T.borderSubtle}` }}>
                    {[['write', 'Write'], ['split', 'Split'], ['preview', 'Preview']].map(([id, label]) => (
                      <button key={id} onClick={() => setMode(id)} style={{ font: `600 10.5px/1 ${T.mono}`, letterSpacing: '0.04em', padding: '6px 10px', borderRadius: 6, cursor: 'pointer', border: 'none', background: mode === id ? T.brand : 'transparent', color: mode === id ? '#fff' : T.secondary }}>{label}</button>
                    ))}
                  </div>
                }>
                <div style={{ display: 'flex', minHeight: 300, border: `1px solid ${T.borderSubtle}`, borderRadius: T.rMd, overflow: 'hidden' }}>
                  {(mode === 'write' || mode === 'split') && (
                    <div style={{ flex: 1, minWidth: 0, position: 'relative', display: 'flex', borderRight: mode === 'split' ? `1px solid ${T.borderSubtle}` : 'none' }}>
                      <textarea value={r.content} onChange={(e) => patch({ content: e.target.value })} spellCheck={false}
                        style={{ flex: 1, minWidth: 0, resize: 'none', border: 'none', outline: 'none', padding: '16px 18px', background: T.raised, color: T.fg, font: `400 13px/1.7 ${T.mono}` }} />
                      {contentDict.supported && <span style={{ position: 'absolute', right: 10, top: 10 }}><MicButton size={26} listening={contentDict.listening} onClick={contentDict.toggle} title="Dictate description" /></span>}
                    </div>
                  )}
                  {(mode === 'preview' || mode === 'split') && (
                    <div style={{ flex: 1, minWidth: 0, overflow: 'auto', padding: '18px 22px', background: mode === 'split' ? T.bg : T.raised }}>
                      {typeof Markdown !== 'undefined' ? <Markdown source={r.content} /> : <pre>{r.content}</pre>}
                    </div>
                  )}
                </div>
              </EditorSection>
            </div>

            {/* footer */}
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12, padding: '12px 20px', borderTop: `1px solid ${T.borderSubtle}`, background: T.sunken }}>
              <span style={{ font: `400 11px/1 ${T.mono}`, color: saved ? T.success : T.tertiary }}>{saved ? '✓ saved' : 'edited ' + r.updated}</span>
              <div style={{ display: 'flex', alignItems: 'center', gap: 9 }}>
                <AdminBtn onClick={() => openArtifact(r.id)} title="Open this recipe in the artifact viewer (new tab)">Open in viewer ↗</AdminBtn>
                <AdminBtn primary onClick={save}>Save</AdminBtn>
              </div>
            </div>
          </div>
        ) : (
          <div style={{ flex: 1, display: 'grid', placeItems: 'center', height: 320, border: `1px solid ${T.borderSubtle}`, borderRadius: T.rLg, background: T.raised }}>
            <span style={{ font: `400 14px/1.5 ${T.sans}`, color: T.tertiary }}>Select a recipe to edit, or create a new one.</span>
          </div>
        )}
      </div>
    </React.Fragment>
  );
}

// ---------- customer-facing picker (onboarding) ----------
// Shows only the light fields. "No recipe" is always available. value = recipe id
// or null; onChange(idOrNull).
function RecipePicker({ value, onChange }) {
  const all = (typeof RECIPES !== 'undefined' ? RECIPES : []).filter((r) => r.status === 'published');
  const card = (sel, onClick, children, key) => (
    <button key={key} onClick={onClick} style={{ textAlign: 'left', display: 'flex', flexDirection: 'column', gap: 9, padding: '15px 16px', borderRadius: T.rLg, cursor: 'pointer',
      border: `1.5px solid ${sel ? T.brand : T.borderSubtle}`, background: sel ? T.brandSoft : T.raised, transition: 'all .12s', position: 'relative' }}>
      {sel && <span style={{ position: 'absolute', top: 12, right: 12, width: 20, height: 20, borderRadius: '50%', background: T.brand, display: 'grid', placeItems: 'center' }}><Icon name="check" size={12} color="#fff" /></span>}
      {children}
    </button>
  );
  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))', gap: 11 }}>
      {all.map((r) => {
        const sel = value === r.id;
        return card(sel, () => onChange(sel ? null : r.id), (
          <React.Fragment>
            <CategoryLabel tone={sel ? 'brand' : 'tertiary'}>{r.category}</CategoryLabel>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, paddingRight: 24 }}>
              <span style={{ width: 26, height: 26, flexShrink: 0, borderRadius: 7, display: 'grid', placeItems: 'center', background: sel ? T.brand : T.sunken }}><Icon name="book" size={14} color={sel ? '#fff' : T.tertiary} /></span>
              <span style={{ font: `700 15px/1.2 ${T.display}`, letterSpacing: '-0.01em', color: T.fg }}>{r.name}</span>
            </div>
            <span style={{ font: `400 12.5px/1.5 ${T.sans}`, color: T.secondary }}>{r.tagline}</span>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 5, marginTop: 2 }}>
              {r.includes.slice(0, 3).map((c) => (
                <span key={c} style={{ font: `500 10.5px/1 ${T.sans}`, color: T.secondary, background: sel ? '#fff' : T.sunken, border: `1px solid ${T.borderSubtle}`, padding: '4px 7px', borderRadius: 9999 }}>{c}</span>
              ))}
              {r.includes.length > 3 && <span style={{ font: `500 10.5px/1 ${T.mono}`, color: T.tertiary, padding: '4px 3px' }}>+{r.includes.length - 3}</span>}
            </div>
          </React.Fragment>
        ), r.id);
      })}
      {/* No recipe */}
      {card(value === null, () => onChange(null), (
        <React.Fragment>
          <CategoryLabel tone={value === null ? 'brand' : 'tertiary'}>No template</CategoryLabel>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <span style={{ width: 26, height: 26, flexShrink: 0, borderRadius: 7, display: 'grid', placeItems: 'center', background: T.sunken }}><Icon name="x" size={14} color={T.tertiary} /></span>
            <span style={{ font: `700 15px/1.2 ${T.display}`, letterSpacing: '-0.01em', color: T.fg }}>No recipe</span>
          </div>
          <span style={{ font: `400 12.5px/1.5 ${T.sans}`, color: T.secondary }}>Start from a blank build — the factory works only from your brief and materials.</span>
        </React.Fragment>
      ), '__none')}
    </div>
  );
}

Object.assign(window, { RecipeLibrary, RecipeStatusPill, RecipePicker });
