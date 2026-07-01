# Project Memory — Design

**Status:** Draft for review · **Owner:** Ibraheem · **Date:** 2026-06-30
**Scope:** The per-project knowledge layer that ingests user-uploaded documents and project context, then exposes it to Software Factory agents through hybrid search and a hierarchical summary tree. Backed by Supabase Postgres + pgvector.

---

## 1. Purpose & where it sits

When a user creates a project they upload documents and describe what they're building. The concierge interview adds more. Today that context is fragmented; agents downstream (PRD, architecture, build, research, design, maintenance) have no reliable, queryable way to pull it back. **Project Memory** is the durable, searchable store of everything known about a project, scoped to that project and accessible to every agent in the factory through a small set of tools.

It lives one level below the existing tenant/org knowledge base:

```
Org / tenant context  (company-wide: AI policy, Cortex, industry research)
        │
        └── Project  (one build effort)
                └── Project Memory   ← this design
                        ├── Hierarchical summary tree (project → doc → section)
                        └── Chunk store with hybrid (dense + sparse) search
```

Agents read project memory constantly; they write to it rarely (the concierge writes the brief; the maintenance agent appends learnings). The default posture is **read-optimized**.

---

## 2. Design principles

1. **Coarse-to-fine retrieval.** An agent should be able to get a 2,000-ft view (project overview), zoom to a document summary, and only then pull the exact chunks it needs. This keeps token budgets small and grounds the agent before it dives in.
2. **Hybrid by default.** Every retrieval runs dense (semantic) *and* sparse (lexical/learned-sparse) search and fuses the results. Distribution docs are full of part numbers, SKUs, API names, and acronyms — exactly where pure-dense embeddings underperform and sparse retrieval wins.
3. **One store, strong isolation.** Everything is in the existing `software-factory-state` Postgres. Every row carries `project_id`/`org_id`, and isolation is enforced the way the rest of the factory does it — **app-layer scope checks** (`authorize_project`, ownership on every route) plus the fact that **agents hold no DB credential** and reach memory only through a scope-scoped MCP. (Not Postgres RLS — this system isolates at the app layer; see ARCHITECTURE §7.) No separate vector DB to operate or keep in sync.
4. **Summaries are first-class data, not derived on the fly.** The hierarchy is computed once at ingest and stored, so reads are cheap and deterministic.
5. **Tool surface is tiny and stable.** Agents see ~6 tools, not a database. The schema can evolve underneath without changing agent prompts.

---

## 3. Data model (Postgres + pgvector)

Extensions: `vector` (pgvector ≥ 0.7, for both `vector` and `sparsevec` types) and Postgres native full-text (`tsvector`) as a keyword fallback.

```
project
  id              uuid pk
  org_id          uuid            -- tenant scope
  name            text
  status          text
  created_at      timestamptz

project_brief                      -- the concierge-synthesized brief (one live row per project)
  project_id      uuid pk fk
  brief_md        text             -- structured: goal, users, constraints, success criteria
  source          text             -- 'concierge' | 'manual'
  embedding       vector(1024)     -- so the brief is itself searchable
  updated_at      timestamptz

document                           -- one uploaded file or pasted context blob
  id              uuid pk
  project_id      uuid fk
  title           text
  source_type     text             -- 'upload' | 'paste' | 'web_research' | 'transcript'
  mime_type       text
  storage_path    text             -- Supabase Storage object
  status          text             -- 'pending'|'parsing'|'chunking'|'summarizing'|'ready'|'failed'
  content_hash    text             -- dedupe + change detection
  version         int default 1
  created_at      timestamptz

doc_summary                        -- the per-document "2,000-ft view"
  document_id     uuid pk fk
  summary_md      text             -- map-reduce summary of the whole doc
  key_facts       jsonb            -- extracted entities: systems, APIs, constraints, decisions
  outline         jsonb            -- section titles + one-line gist each (the mid tier)
  embedding       vector(1024)
  token_count     int

chunk                              -- the leaf level
  id              uuid pk
  document_id     uuid fk
  project_id      uuid fk          -- denormalized for fast project-scoped filtering
  ordinal         int              -- position within doc
  section_path    text             -- e.g. "2 / 2.3 Auth" for hierarchical navigation
  content         text
  dense           vector(1024)     -- semantic embedding
  sparse          sparsevec(30522) -- learned-sparse (SPLADE) OR built from tsvector terms
  fts             tsvector         -- generated from content, exact-keyword fallback
  token_count     int
  created_at      timestamptz

memory_note                        -- agent/maintenance-appended learnings (write path)
  id              uuid pk
  project_id      uuid fk
  author          text             -- agent name or 'user'
  body_md         text
  embedding       vector(1024)
  created_at      timestamptz
```

**Indexes**

```sql
-- dense: cosine HNSW
create index on chunk using hnsw (dense vector_cosine_ops);
-- sparse: inner-product HNSW on sparsevec
create index on chunk using hnsw (sparse sparsevec_ip_ops);
-- lexical fallback
create index on chunk using gin (fts);
-- scope filters
create index on chunk (project_id);
create index on document (project_id, status);
```

**Why `sparsevec` for the sparse index.** pgvector's `sparsevec` type stores high-dimensional sparse vectors natively. We populate it from a learned-sparse model (SPLADE-style), which gives true term-importance weighting rather than raw counts — this is the "sparse vector index" half of the hybrid. If we want to defer running a SPLADE model, the `fts`/`tsvector` column gives a working lexical channel on day one, and we upgrade to `sparsevec` later without schema churn.

---

## 4. The hierarchical summary tree (the "2,000-ft view")

Three tiers, all stored, so an agent can navigate top-down:

| Tier | Stored in | Granularity | Typical use |
|---|---|---|---|
| **Project overview** | `project_brief` + a rollup of `doc_summary` | whole project, ~1 page | First thing an orchestrator reads. "What is this project, what exists, what matters." |
| **Document summary** | `doc_summary.summary_md` + `outline` | one doc, ~1–2 paragraphs + section outline | Decide *which* documents are relevant before pulling chunks. |
| **Chunk** | `chunk.content` | ~300–500 tokens | The exact passage to ground a claim or copy a spec. |

Summaries are built with **map-reduce** at ingest: summarize each chunk → reduce per section → reduce per document (`doc_summary.summary_md`) → the project overview is a reduce over all `doc_summary` rows (recomputed when documents are added/removed). `key_facts` is a structured extraction pass (systems, APIs, constraints, decisions, glossary terms) that the PRD and architecture agents can read directly without search.

**The per-document AI summary is a first-class, customer-visible feature — not just agent fuel.** It is exactly the intake **"Auto-summarize" / "Regenerate"** action on each uploaded file (see the Materials screen): on upload we generate `summary_md` and pre-fill the file's description; the user can **Regenerate** to re-run it. The same `summary_md` feeds the project-overview rollup, the Documents view, and the interview's "What I learned." One summarization pass, three surfaces.

**No confidence scores — references instead.** Per the corrected product spec, we do **not** attach an (unreliable) confidence band to inferred facts. Every entry in `key_facts` instead carries an explicit **source reference** — `{fact, document_blob_id, section_path, page?}` — so the customer sees *where* a fact came from and can judge it directly. A fact with no supporting reference is not stored as a fact; it becomes an interview question. This is honest grounding, not calibrated guessing.

This means a typical agent flow is: **read project overview (cheap) → search for the 2–3 relevant docs → read their summaries → fetch only the chunks that matter.** Coarse-to-fine, small token footprint.

---

## 5. Ingestion pipeline

Triggered on upload or when the concierge finalizes context. Runs as a background job (Supabase Edge Function or a worker), advancing `document.status`:

```
upload → store object + content_hash
      → parse (pdf/docx/md/html/transcript → clean text + structure)
      → chunk (structure-aware: respect headings; ~400 tok, ~50 overlap; keep section_path)
      → embed dense  (batch → vector(1024))
      → embed sparse (SPLADE → sparsevec)  + generate fts
      → summarize (map-reduce → doc_summary, key_facts, outline)
      → recompute project overview rollup
      → status = ready
```

Notes:
- **Dedup/change detection** via `content_hash`; re-uploading an unchanged file is a no-op, a changed file bumps `version` and re-ingests.
- **Transcripts** (Fireflies) and **web-research** outputs flow through the same pipeline with `source_type` set accordingly, so meeting context and research are searchable alongside uploads.
- **Failure isolation:** a doc that fails parsing is marked `failed` and surfaced in the project view; it doesn't block the others.

---

## 6. Hybrid search & fusion

A single retrieval does dense + sparse in parallel, fuses with **Reciprocal Rank Fusion (RRF)**, optionally reranks. RRF needs no score normalization across the two very different scoring scales, which is what makes it robust here.

```sql
-- conceptually, wrapped in an RPC: project_memory_search(project_id, query_dense, query_sparse, k)
with dense as (
  select id, row_number() over (order by dense <=> $query_dense) as rnk
  from chunk where project_id = $pid order by dense <=> $query_dense limit 50
),
sparse as (
  select id, row_number() over (order by sparse <#> $query_sparse) as rnk
  from chunk where project_id = $pid order by sparse <#> $query_sparse limit 50
)
select c.*,
       coalesce(1.0/(60 + d.rnk), 0) + coalesce(1.0/(60 + s.rnk), 0) as rrf_score
from chunk c
left join dense  d on d.id = c.id
left join sparse s on s.id = c.id
where d.id is not null or s.id is not null
order by rrf_score desc
limit $k;
```

Pipeline around the RPC: embed the query (dense + sparse) → RRF over top-50 from each channel → optional cross-encoder/Voyage rerank of the top ~20 → return top `k` (default 8) with document title, `section_path`, and a link back to the source. The reranker is optional and behind a flag — RRF alone is a strong baseline.

---

## 7. Agent-facing tools

Exposed via the factory's tool/MCP registry. All are project-scoped automatically from the agent's run context — agents never pass `org_id` or see other projects.

| Tool | Input | Returns | When agents use it |
|---|---|---|---|
| `get_project_overview` | – | project brief + rollup summary + `key_facts` digest | First call in almost every run; sets the frame. |
| `list_documents` | optional filter (`source_type`, query) | doc titles, summaries, status | To see what context exists. |
| `get_document_summary` | `document_id` | `summary_md`, `outline`, `key_facts` | After deciding a doc is relevant. |
| `search_memory` | `query`, `k?`, `source_type?` | top-k chunks (content, title, `section_path`, score) | The workhorse — hybrid retrieval. |
| `get_chunk` | `chunk_id`, `window?` | chunk + N neighbors by `ordinal` | Expand context around a hit. |
| `add_memory_note` | `body_md` | note id | Maintenance/concierge agents append learnings. |

Example `search_memory` schema:

```json
{
  "name": "search_memory",
  "description": "Hybrid (semantic + keyword) search over this project's documents, brief, transcripts, and research. Returns the most relevant passages with their source document and section.",
  "input_schema": {
    "type": "object",
    "properties": {
      "query": { "type": "string", "description": "Natural-language or keyword query." },
      "k": { "type": "integer", "default": 8, "description": "Number of passages to return." },
      "source_type": { "type": "string", "enum": ["upload","paste","web_research","transcript"], "description": "Optional filter." }
    },
    "required": ["query"]
  }
}
```

Prompt guidance baked into the tool descriptions nudges agents toward coarse-to-fine: overview → summaries → search → expand. This keeps retrieval grounded and cheap without hard-coding the flow.

---

## 8. Multi-tenancy, security & "DB pollution"

The meeting flagged agents doing unintended DB edits. Project Memory mitigates this structurally:

- **App-layer scope enforcement (not RLS).** Consistent with ARCHITECTURE §7: every memory read/write goes through a service method that filters by the caller's authorized scope (reuse `authorize_project`), and the memory MCP resolves `scope_id` from a **project-scoped token** — so an agent can only ever address its own project's memory (+ inherited org docs via `blob_uses`). The DB itself is reached by one service identity through the pooler; tenancy is enforced above it, everywhere, the way the rest of the system already works.
- **Read vs. write separation.** The six tools are the *only* write path agents have into memory, and only `add_memory_note` writes. Agents hold **no Supabase credential at all** (ARCHITECTURE §1); ingestion runs console-side under the service identity. Build agents structurally cannot `UPDATE`/`DELETE` chunks or summaries.
- **Provenance.** Every chunk links back to its `document` (`blobs.id`) and `section_path`, and every `key_fact` carries an explicit source **reference** (document + page/section), so any agent or interview claim traces to a source.

---

## 9. Lifecycle: updates, versioning, freshness

- Adding/removing a document recomputes only that document's summary plus the project rollup — incremental, not a full rebuild.
- `version` on `document` keeps history; retrieval reads the latest by default.
- The **maintenance agent** appends `memory_note` rows over the project's life (logs reviewed, feedback ingested, patches applied), so the project's memory compounds — directly supporting the "ongoing build" vision rather than one-off builds.
- A periodic job can re-summarize stale rollups if upstream models improve.

---

## 10. Build phases

1. **MVP** — `document` + `chunk` with dense `vector` + `tsvector`; ingestion (parse/chunk/embed/summarize); `search_memory`, `get_project_overview`, `get_document_summary`. RRF over dense + FTS. Proves the loop end-to-end.
2. **Sparse upgrade** — add `sparsevec` (SPLADE), swap the lexical channel into true learned-sparse, add optional reranker.
3. **Compounding memory** — `memory_note` write path, maintenance-agent integration, transcript + web-research ingestion, freshness jobs.

---

## 11. Open questions

- **Embedding model & dims.** 1024 assumed (Voyage-style); confirm provider, given the Claude/OpenRouter dual-harness setup. Affects `vector(N)` and cost.
- **SPLADE hosting.** Run our own sparse-embedding endpoint, or stay on `tsvector` longer? Drives the phase-2 timeline.
- **Chunk size** by `source_type` — transcripts and PRDs may want different chunking than spec PDFs.
- **Rerank budget.** Cross-encoder rerank improves precision but adds latency/cost per search; decide default on/off.
- **Org-level memory.** Should `search_memory` optionally fall back to org/industry context when a project has thin documents? (Likely yes, behind a flag.)
```
