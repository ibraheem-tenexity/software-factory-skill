# Project Memory — Integration into `software-factory-skill`

**Companion to** `project-memory-design.md` + `project-memory-stack-2026.md` · **Date:** 2026-06-30
**Grounded in:** `main` of `software-factory-skill` (flat `public` schema, `models.py` + Alembic, `dbshim`), the handoff **PRD.md** (screen spec), and `docs/ARCHITECTURE.md`.
**Thesis:** we don't bolt a RAG system onto the side. We extend three things the repo *already has* — the `blobs` manifest, the `mcp_config()` seam, and the onboarding ingest step — so Project Memory is a natural organ, not a graft. Everything below complies with the PRD and the design doc.

---

## 0. The three hooks that already exist (why this is lean, not a rebuild)

Repo reconnaissance turned up three load-bearing facts that shape the whole integration:

1. **`blobs` already *is* the document layer.** `public.blobs` (see `models.py`) has `scope` (`project`|`org`), `scope_id`, `kind`, `name`, `tag`, `storage_key`, `content_type`, `size_bytes`, `sha256`. Org knowledge base = `scope='org'` rows; `blob_uses` links a project to reused org docs. **We do not add a `document` table** — the design doc's `document` maps 1:1 onto `blobs`. New memory tables reference `blobs.id`.
2. **`mcp_config(stage)` already serves HTTP MCP servers to both runtimes.** `workspace_setup.py` hands every stage agent an `.mcp.json` containing `playwright`, `exa` (HTTP), and **`openrouter` (HTTP)** — and translates it for opencode too. Adding a **console-hosted Project Memory MCP** is one dict in that function. Agents get real tools and still have **no Supabase access** — exactly the security posture ARCHITECTURE §1 and the meeting ("DB pollution") demand.
3. **The onboarding ingest step is already specified and already records blobs.** PRD §2.4a `ProcessingScreen` ("ingests their uploads") is currently driven by a *mock* `INGEST_STEPS` array; `input_pipeline.persist_and_compose` already extracts attachments → Markdown and "the caller records it as a blob." That is precisely where memory ingestion attaches — and it lets us make the mock real.

So the build is: **2 new tables + 1 new `memory/` package + 1 line in `mcp_config()` + a write-through on blob upload.** No new datastore, no framework, no agent Supabase access.

---

## 1. Data model — extend `models.py`, one Alembic revision `0008_project_memory`

Two new per-scope tables. Both key off `blobs.id` (the document) and carry `scope`/`scope_id` so project- and org-scoped memory live together and app-layer scope filters stay uniform (this system isolates at the app layer + credential-scoped MCP, **not** Postgres RLS — ARCHITECTURE §7).

```python
# models.py — additions (pgvector via sqlalchemy)
from pgvector.sqlalchemy import Vector

doc_summary = Table(                     # the "2,000-ft view" per document (design §4 mid tier)
    "doc_summary", metadata,
    Column("blob_id", Integer, ForeignKey("blobs.id", ondelete="CASCADE"), primary_key=True),
    Column("scope", Text, nullable=False),          # 'project' | 'org'  (mirrors blobs)
    Column("scope_id", Text, nullable=False),
    Column("summary_md", Text),                     # map-reduce summary  → PRD "AI auto-summarize"
    Column("assumptions", JSONB, server_default=text("'{}'::jsonb")),  # → PRD "What I learned" (§2.4a)  [shipped name; was drafted as key_facts]
    Column("outline", JSONB, server_default=text("'[]'::jsonb")),    # section gists
    Column("embedding", HALFVEC(3072)),                              # shipped as halfvec(3072); was drafted Vector(1024)
    Column("token_count", Integer),
    Column("content_sha256", Text),                 # staleness vs blobs.sha256
    Column("status", Text, nullable=False, server_default="pending"),  # pending|ready|failed
    Column("updated_at", DateTime(timezone=True), server_default=func.now()),
)

chunk = Table(                            # the leaf level (design §3)
    "chunk", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("blob_id", Integer, ForeignKey("blobs.id", ondelete="CASCADE"), nullable=False),
    Column("scope", Text, nullable=False),
    Column("scope_id", Text, nullable=False),
    Column("ordinal", Integer, nullable=False),
    Column("section_path", Text),                   # "2 / 2.3 Auth" — hierarchical nav
    Column("content", Text, nullable=False),
    Column("dense", HALFVEC(3072)),                 # OpenRouter embedding (google/gemini-embedding-2); shipped halfvec(3072)
    Column("fts", TSVECTOR),                         # generated from content — the sparse channel
    # Column("sparse", SparseVector(...)) RESERVED — add only if we move to learned-sparse later
    Column("token_count", Integer),
)
```

Migration `0008_project_memory.py` (Alembic, mirrors baseline conventions):

```python
def upgrade():
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    # create doc_summary, chunk (as above)
    op.execute("ALTER TABLE chunk ADD COLUMN fts tsvector "
               "GENERATED ALWAYS AS (to_tsvector('english', content)) STORED")
    op.execute("CREATE INDEX chunk_dense_hnsw ON chunk USING hnsw (dense vector_cosine_ops)")
    op.execute("CREATE INDEX chunk_fts_gin ON chunk USING gin (fts)")
    op.execute("CREATE INDEX chunk_scope ON chunk (scope, scope_id)")
    op.execute("CREATE INDEX doc_summary_scope ON doc_summary (scope, scope_id)")
```

**Project-overview tier (design §4 top):** it's `projectstate.data['brief']` (the 7-section brief already exists) **+** a rollup of the project's `doc_summary` rows. Compute the rollup at ingest and cache it — cheapest place is a `memory_overview` blurb written back into `projectstate.data` (the store already round-trips JSON), so **no third table**. Org overview = rollup of `scope='org'` summaries, cached on `organizations` (add one `context_rollup` Text column if we want it persisted).

> **Drift/test note:** `models.py` is the single source and the test suite runs `metadata.create_all` against a test Postgres. Adding `Vector`/`tsvector` means the **test DB must have the `vector` extension**. Add `CREATE EXTENSION IF NOT EXISTS vector` to `conftest.py` DB bootstrap (and confirm it's enabled on the Supabase `software-factory-as-a-skill` project). This keeps the "cannot drift" invariant intact.

---

## 2. New package — `src/software_factory/memory/`

Follows existing module conventions (framework-free, goes through `dbshim`, errors via `services/errors.py`).

| File | Responsibility |
|---|---|
| `memory/embed.py` | Embedding client. Reuses the **`openai` SDK already in the tree**, pointed at OpenRouter (`base_url=https://openrouter.ai/api/v1`, `model="google/gemini-embedding-2"` or `qwen/qwen3-embedding`). One `embed_texts(list[str]) -> list[vector]`. Dense only (per stack decision). |
| `memory/chunker.py` | `chunk_markdown(md) -> [(ordinal, section_path, text)]`. Wraps **Chonkie `RecursiveChunker`** (or a ~30-line heading-aware splitter if we want zero new deps). |
| `memory/ingest.py` | The pipeline: blob → extracted MD (reuse `pdf_extract`/`docx_extract`) → chunk → embed dense → contextual-retrieval prepend → summarize (map-reduce) → write `doc_summary` + `chunk` → recompute rollup. Advances `doc_summary.status`. |
| `memory/search.py` | `search(scope, scope_id, query, k) -> hits`. Embeds query, runs the **RRF SQL** (dense `<=>` + `ts_rank_cd(fts,…)`) through `dbshim`, returns `content + blob.name + section_path + score`. |
| `memory/store.py` | `MemoryStore` over `dbshim` — thin CRUD for `doc_summary`/`chunk`, plus `overview(scope, scope_id)` (brief + rollup). |
| `memory/mcp_server.py` | The console-hosted **HTTP MCP** exposing the six design tools (§4 below). Runs inside `factory-console` with DB + embedding creds. |

Retrieval RRF (in `search.py`, executed via `dbshim`):

```sql
WITH dense AS (
  SELECT id, row_number() OVER (ORDER BY dense <=> %(q)s) rnk
  FROM chunk WHERE scope=%(scope)s AND scope_id=%(sid)s
  ORDER BY dense <=> %(q)s LIMIT 50),
kw AS (
  SELECT id, row_number() OVER (ORDER BY ts_rank_cd(fts, plainto_tsquery('english',%(qtext)s)) DESC) rnk
  FROM chunk WHERE scope=%(scope)s AND scope_id=%(sid)s
    AND fts @@ plainto_tsquery('english',%(qtext)s)
  ORDER BY ts_rank_cd(fts, plainto_tsquery('english',%(qtext)s)) DESC LIMIT 50)
SELECT c.id, c.content, c.section_path, b.name AS document,
       coalesce(1.0/(60+d.rnk),0)+coalesce(1.0/(60+kw.rnk),0) AS rrf
FROM chunk c JOIN blobs b ON b.id=c.blob_id
LEFT JOIN dense d ON d.id=c.id LEFT JOIN kw ON kw.id=c.id
WHERE d.id IS NOT NULL OR kw.id IS NOT NULL
ORDER BY rrf DESC LIMIT %(k)s;
```

---

## 3. Ingestion — hook the existing onboarding flow (and make the PRD mock real)

**Where it fires:** the console records uploaded materials as `blobs` during PRD §2.4 (materials step) and org-KB uploads (§2.3). Add a write-through: after a blob is stored + extracted, call `memory.ingest.ingest_blob(blob_id)`.

- **Console-side, not agent-side** — ingestion holds the embedding key and DB creds; stage agents never do. This preserves ARCHITECTURE's "agents have no Supabase access."
- **Run it async** so the UI doesn't block. This is exactly what PRD §2.4a's `ProcessingScreen` + "Continue in background" already model — **replace the mock `INGEST_STEPS` with real per-blob ingest progress** streamed over the existing SSE channel. The ingest log rows become real ("Embedding chunks 12/40…", "Summarized price-book.xlsx ✓").
- **`doc_summary.summary_md`** is the PRD's per-file **"Auto-summarize" / "Regenerate"** action (§2.4 Materials — see the file tiles with the AI summary buttons): generated on upload, pre-fills the description, re-runnable. A **first-class P0 feature**, not just agent fuel. **`assumptions`** (the shipped column name; drafted here as `key_facts`) populates the interview's **"What I learned from your materials"** rows (§2.4a `LEARNED`) — each fact carries a **source reference** (`document_blob_id` + `section_path`/`page`), **no confidence score** (per the corrected spec).

**Reuse, don't rebuild:** parsing uses the existing `pdf_extract`/`docx_extract` (the latter already pulls wireframe images out of Word tables). Chunking is the only genuinely new step.

---

## 4. Agent access — a console-hosted Project Memory MCP (the "tools" the design wants)

Add one server to `workspace_setup.mcp_config()`:

```python
_MEMORY = {"type": "http", "url": "${SF_MEMORY_MCP_URL}",
           "headers": {"Authorization": "Bearer ${SF_MEMORY_TOKEN}"}}
# in mcp_config(): servers = {"playwright": _PLAYWRIGHT, "exa": _EXA,
#                             "openrouter": _OPEN_ROUTER, "memory": _MEMORY}
```

- It's an **HTTP MCP** like `exa`/`openrouter`, so the existing opencode translation (`_opencode_server`) handles it for both runtimes for free.
- The server runs **inside `factory-console`** (mounted under `console/app.py`, reusing auth + `dbshim` + the embedding client). The stage agent connects over HTTP with a **project-scoped token** → the MCP resolves `scope_id` from the token, so an agent can only ever read **its own** project's memory (+ inherited org docs via `blob_uses`). Secrets (embedding key, DB URL) stay console-side.

**Tools exposed** (design doc §7): `get_project_overview`, `list_documents`, `get_document_summary`, `search_memory`, `get_chunk`, `add_memory_note`, plus `search_document_summaries` (SOF-60) — **7 as shipped** (the design doc listed 6). Only `add_memory_note` writes; the rest are read-only → structurally prevents "DB pollution."

**Register it in the product too:** insert a row in `public.mcp_tools` (PRD §3.6 Tools & MCP registry) so "Project Memory" shows in Tenexity OS as a first-class connected tool.

> **Runtime alternative (parity/fallback):** the same functions can also be exposed as `db` CLI verbs (`python3 -m software_factory.db memory-search <dir> <project_id> "<q>"`) since agents already call that module. The HTTP MCP is preferred (native tools, secrets stay console-side); CLI verbs are the low-tech backstop if an MCP hop is undesirable in some stage.

---

## 5. PRD compliance map (what this turns from mock → real)

| PRD surface | Today (prototype) | With Project Memory |
|---|---|---|
| §2.4a `ProcessingScreen` ingest log | mock `INGEST_STEPS` array | real per-blob ingest progress over SSE |
| §2.4a interview "What I learned" (`LEARNED`) | hardcoded facts | `doc_summary.assumptions` (shipped name; drafted `key_facts`), each with a **source reference** (`document_blob_id` + `section_path`/`page`) — no confidence |
| §2.4 Materials **"Auto-summarize" / "Regenerate"** | button, no backend | `doc_summary.summary_md`, generated on upload, pre-fills the description, re-runnable — **first-class P0 feature** |
| §2.4b docs Concierge Q&A **with citations** ("later feature") | scripted match on `window.PROJ_MATERIALS` | `search_memory` → answers with `document` + `section_path` citations |
| §2.5a "Inherited org context" | static summary | org-scope rollup (`scope='org'` doc_summaries) |
| §4 pipeline `research`/`architect`/`tickets` agents | read `context.txt` only | call `search_memory`/`get_project_overview` for grounded, coarse-to-fine context |
| §3.6 Tools & MCP registry | seeded rows | a real "Project Memory" MCP row |

Nothing here contradicts the PRD; it fills in backends the PRD explicitly marked "wire to real services when implementing" / "later feature."

---

## 6. Dependencies (net new: 2, maybe 1)

- **`pgvector`** (the SQLAlchemy type) — required for the `Vector` column + HNSW.
- **`chonkie`** — chunking (505 KB; or write the ~30-line splitter and add **zero** deps).
- Embeddings + summarization reuse the **`openai`** SDK **already in the lockfile** (OpenRouter is OpenAI-compatible) — no Cohere/Voyage SDK, no LangChain, no vector DB client.

That's it. Consistent with the stack doc's anti-bloat list.

---

## 7. First slice (ship thin, prove the loop)

1. `models.py` + `0008_project_memory` (tables, extension, indexes); `conftest.py` enables `vector`.
2. `memory/embed.py` + `memory/chunker.py` + `memory/store.py`.
3. `memory/ingest.py`; wire the write-through on project-scope blob upload; stream real progress into `ProcessingScreen`.
4. `memory/search.py` (RRF).
5. `memory/mcp_server.py` mounted in `console/app.py`; add `_MEMORY` to `mcp_config()`; seed `mcp_tools` row.
6. Point Stage-1 (research) + Stage-2 (architect/tickets) SKILL prompts at `search_memory`/`get_project_overview`.
7. Contextual-retrieval prepend (biggest quality/§ least code). Reranker only if eval demands.

Acceptance (per CLAUDE.md §5): a project with N uploaded docs → `search_memory("<known fact>")` returns the right chunk with correct `document`+`section_path`; a Stage-1 run cites a fact that only exists in an upload; org-scoped doc is retrievable from a project that imported it via `blob_uses`; agents have **no** Supabase creds in their env.

---

## 8. Decisions

**Resolved (2026-06-30):**
- **Ingestion spend is charged to the project spend cap.** Embedding + summarization + key-fact extraction all count against the project's cap (§2.4). Practically: the ingest pipeline records its LLM/embedding cost to the project's ledger (alongside the `agents` cost accounting), and it participates in the **stop-at-ceiling** budget model — no pre-flight reservation (see below).
- **Budget model = stop-at-ceiling + raise-to-resume** (not pre-flight pause-before-cross), per operator call. Reuses the existing poller budget brake; ingestion cost is part of what's watched.
- **No confidence scores.** `key_facts` carry **source references** (`document_blob_id` + `section_path`/`page`) only.
- **AI document summaries are a first-class P0 feature** (`doc_summary.summary_md`), surfaced as the intake Auto-summarize/Regenerate action.
- **Isolation is app-layer + credential-scoped MCP**, not RLS.

**Still open:**
1. **Embedding model via OpenRouter:** Gemini Embedding 2 (multimodal — can embed PDF page images later) vs Qwen3-Embedding (top pure-text MTEB). Recommend **Gemini Embedding 2** for the multimodal headroom given the wireframe/screenshot uploads.
2. **MCP transport:** console-hosted HTTP MCP (recommended) vs `db` CLI verbs.
3. **Chunker:** Chonkie dep vs a zero-dep in-repo splitter. Recommend Chonkie unless you want the dep count at literal minimum.
4. **Overview cache:** in `projectstate.data` (no new table, recommended) vs a `memory_overview` table.
5. **pgvector on the test DB:** confirm we can `CREATE EXTENSION vector` in CI's Postgres (needed to keep `create_all` parity).
