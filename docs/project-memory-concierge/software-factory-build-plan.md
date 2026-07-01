# Software Factory — Build Plan (the Concierge + Project Memory milestone)

**Date:** 2026-06-30 · **Owner:** Ibraheem · **Source of truth for status:** Linear project *Software Factory* (team SOF).
**Grounds:** `docs/product-spec-software-factory.md`, `docs/ARCHITECTURE.md`, repo `main` @ `ded31ad`, and the design set (`project-memory-design.md`, `project-memory-stack-2026.md`, `project-memory-integration.md`, `concierge-conversation-store.md`).

---

## 1. What we're building now (one paragraph)

The **trust spine** of the product: make the Concierge real and durable, and make the system actually *understand uploaded materials* before it spends money building. Concretely — (1) a durable, provider-agnostic **conversation store** replacing the in-memory mock and the volume-only `chat.jsonl`; (2) **one context-parameterized Concierge agent** (kills the two-implementation split); (3) **Project Memory ingestion** that produces **AI document summaries** and **reference-backed key facts** feeding the processing/interview reflection step; (4) **coarse retrieval** so the build agents are grounded in the customer's materials; all with (5) **ingestion spend charged to the project cap** under the existing stop-at-ceiling brake. This is the spec's P0 (§4.4–§4.6) plus the §4.5 reflection step, which is the single biggest trust risk in the product.

### Locked decisions (do not relitigate)
- Isolation = **app-layer scope checks + credential-scoped MCP + agents hold no DB credential** (ARCHITECTURE §7). **Not** Postgres RLS.
- **No confidence scores.** `key_facts` carry **source references** (`document_blob_id` + `section_path`/`page`). Unreferenced ⇒ becomes an interview question, never a stated fact.
- **AI per-document summaries are a first-class P0 feature** (the Auto-summarize / Regenerate button).
- **Ingestion spend (embed + summarize + extract) is charged to the project cap**; budget model = **stop-at-ceiling + raise-to-resume** (no pre-flight reservation).
- Reuse `blobs` as the document layer; **no** second vector DB; embeddings via **OpenRouter** (dense) + Postgres `tsvector` (sparse).

### Explicitly deferred (build the schema hooks, not the feature)
RRF tuning, Anthropic contextual-retrieval prepend, cross-encoder reranker, learned-sparse (Cohere embed-v4), **inline document-citation Q&A** (spec §7), and the image-source **caption/retrieval UX**. We *do* capture image provenance columns now (one-way door), but ship none of the precision-retrieval or citation surfaces until the doc-Q&A milestone.

---

## 2. Architecture deltas (the whole change surface)

| Area | Change | File(s) |
|---|---|---|
| Schema | `conversation` table; `doc_summary` + `chunk` tables; `blobs` gains `source_blob_id`/`source_page`/`provenance`; `CREATE EXTENSION vector` | `src/software_factory/models.py`, `migrations/versions/0008_project_memory.py`, `0009_conversation.py`, `conftest.py` |
| Cost seam | record ingestion/LLM/embedding spend to the project ledger so stop-at-ceiling includes it | `budget.py`, `agents.py` (reuse), new `memory/cost.py` helper |
| New package | `memory/` — embed, chunker, store, ingest, search, mcp_server | `src/software_factory/memory/*` |
| Conversation | `ConversationStore` (`session_id` + `message_id`) + content-block model + `to_provider` adapter; swap the mock; admin history query | `src/software_factory/conversation_store.py` (or `services/conversation.py` rewrite), `console/state.py`, `console/routers/chat.py`, `admin_os.py` |
| Concierge | **rip out** OpenAI-Agents-SDK + 14 tools; rebuild as **LangChain** agent (system prompt + tools + `ConciergeTurn` structured output). New dep: `langchain`/`langgraph` | `chat_agent.py`, `agent_prompts.py`, `console/schemas.py` |
| Agent tools | console-hosted memory MCP added to every stage workspace | `workspace_setup.py` (`mcp_config`), `console/app.py` mount, seed `mcp_tools` |
| Ingest hook | write-through on project-scope blob upload + real progress to `ProcessingScreen` | `input_pipeline.py`, blob-upload path, SSE (`console/state.py`), FE `concierge.jsx`/onboarding |
| Feature flags | `SF_MEMORY=1`, `SF_CONVERSATION_DB=1` (env-gated like `notify`/`storage`) | `env.py`, `state.py` |

---

## 3. Phases, tickets, and acceptance criteria

Each ticket states **Goal** and **Acceptance** (per CLAUDE.md §5). Do the work in a worktree off `~/software-factory-skill-bare`; open a PR; poll it to merge.

### Phase 0 — Foundations (schema + cost seam)  ·  *blocks everything*

**T0.1 — Migrations + models for memory & conversation**
- *Goal:* add the three tables + `blobs` provenance columns + pgvector extension, defined once in `models.py`, owned by Alembic, buildable by `create_all` in tests.
- *Files:* `models.py`; `0008_project_memory.py` (doc_summary, chunk, `CREATE EXTENSION IF NOT EXISTS vector`, HNSW + GIN + scope indexes, `blobs` alters); `0009_conversation.py` (conversation + indexes); `conftest.py` (enable `vector` on the test DB).
- *Acceptance:* `alembic upgrade head` succeeds on a clean DB; `models.metadata.create_all` builds the same schema in tests (no drift); `pytest` green; a smoke test inserts + reads a `Vector(1024)` and a `to_tsvector` row.

**T0.2 — Ingestion cost seam**
- *Goal:* one helper records embedding/summarization/extraction spend to the project's ledger so the poller's stop-at-ceiling brake counts it.
- *Files:* `memory/cost.py`, reuse `budget.py`/`agents.py` accounting.
- *Acceptance:* ingesting a fixture doc writes a cost row attributable to the project; a project whose cap is exceeded *by ingestion* trips the existing `budget` blocker; unit test asserts the ledger delta.

### Phase 1 — Conversation store (P0)  ·  *needs T0.1*

**T1.1 — `ConversationStore` + content-block model**
- *Goal:* durable store over `dbshim`; `json_blob` holds canonical blocks (`text`/`image`/`tool_use`/`tool_result`); `input`/`tool_result`/`choices`/`done` denormalized; `seq` ordering.
- *Acceptance:* append + `history(session_id)` round-trips ordered by `seq`; image blocks reference a `blobs.id` (never inline bytes); unit tests with no DB for the block model, one integration test for persistence.

**T1.2 — `to_provider` adapter (OpenAI + Anthropic)**
- *Goal:* render stored history to each SDK's message shape; role map (`agent`→assistant, `tool`→ provider-specific tool result); images resolved from storage to URL/base64.
- *Acceptance:* golden-file tests for a transcript containing a text turn, an image turn, and a `tool_use`/`tool_result` pair → valid OpenAI *and* Anthropic payloads.

**T1.3 — Swap the mock; keep the contract**
- *Goal:* `Conversation.turn()/history()` unchanged signature, now DB-backed; `state.reset()` builds it; `/api/projects/{pid}/converse` untouched.
- *Acceptance:* existing `tests/unit/test_conversation.py` contract still passes; a restart no longer loses a transcript; blank message still 400s.

**T1.4 (follow-up) — Fold `/api/chat` off `chat.jsonl`**
- *Goal:* `chat_agent.py` appends to `conversation`; `chat_history` reads from it; `chat.jsonl` kept as debug mirror behind a flag, then retired.
- *Acceptance:* a chat turn persists to the table with `model`/`provider`/token/cost fields set; history endpoint reads identical content to the old JSONL for a migrated project.

**T1.5 — Admin history table (Tenexity OS)**
- *Goal:* one filterable cross-tenant view of all conversation history — `GET /api/admin/conversations` (staff-gated) filterable by `org_id`/`project_id`/`user_id`/`session_id`/role/date, with a sessions roll-up and a messages drill-down; a Tenexity OS screen beside the produced-files index.
- *Files:* `console/routers/admin_os.py` (or new), FE admin screen; query over `conversation`.
- *Acceptance:* staff can filter to one org/project/user/session and open a full transcript; non-staff get 403; the view shows per-turn model/provider/cost.

### Phase 2 — One Concierge agent (P0)  ·  *needs T1.1–T1.3* · *full spec: `concierge-agent-spec.md`*

**T2.0 — Rip out the old Concierge**
- *Goal:* delete the OpenAI-Agents-SDK runtime (`Agent`/`Runner`) and **all 14 tools** in `make_tools()`, plus the scripted mock in `services/conversation.py`. No porting — they don't work and we don't want them.
- *Files:* `chat_agent.py`, `services/conversation.py`.
- *Acceptance:* the 14 tools and `agents`-SDK imports are gone; the app still boots (behind the flag); no test references the removed tools.

**T2.1 — LangChain Concierge = system prompt + agent + tools**
- *Goal:* a single **LangChain** tool-calling agent (system prompt + bound tools + reason/act loop), context-parameterized (`intake`|`overview`|`build`|`docs`|`ingesting`) — same identity, different focus (spec Principle 2, §4.6). **Tool belt starts empty**; only reality-backed tools get bound later (§5 of the spec). No multi-agent graphs or chains — the loop and nothing more.
- *Files:* `chat_agent.py` (LangChain agent), `agent_prompts.py` (one editable `CONCIERGE` prompt + per-context framing, existing override cache).
- *Acceptance:* the same agent answers across all five contexts; runs with an empty tool belt; prompt edits in Tenexity OS drive the next session; a voice-consistency eval passes a rubric.

**T2.2 — Structured output contract**
- *Goal:* every turn to the human is `ConciergeTurn` = `{response: str (required), suggested_responses: [{response: str, type: "single select"|"multi select"}]}`, enforced via Pydantic `with_structured_output`. New `ConverseOut` mirrors it. **No `done`/`choices`** — the FE derives multi/single-select purely from `suggested_responses` (empty ⇒ plain text). Stored in the agent row's `json_blob`.
- *Files:* `chat_agent.py`, `console/schemas.py`, FE `ChoiceList`/onboarding.
- *Acceptance:* empty `suggested_responses` renders a text turn; `single select` renders radios (click submits), `multi select` renders checkboxes (+Confirm); a parse failure retries once then falls back to `{response, []}` without 500; the FE receives `message_id` + `session_id`.

### Phase 3 — Project Memory ingestion, summaries & grounded facts (P0)  ·  *needs T0.1, T0.2*

**T3.1 — `memory/` core: embed + chunk + store**
- *Goal:* `embed.py` (OpenRouter dense, chosen model), `chunker.py` (Chonkie `RecursiveChunker` or zero-dep splitter), `store.py` (CRUD over dbshim).
- *Acceptance:* a markdown doc → ordered chunks with `section_path`; `embed_texts` returns `Vector(1024)`; stored + retrievable by `blob_id`.

**T3.2 — Ingestion pipeline + write-through + real progress**
- *Goal:* on project-scope blob upload: parse (reuse `pdf_extract`/`docx_extract`) → chunk → embed → `to_tsvector` → summarize (map-reduce) → `key_facts` with references → recompute overview rollup; advance `doc_summary.status`; **cost recorded (T0.2)**; stream real progress into `ProcessingScreen` (replace mock `INGEST_STEPS`), incl. "continue in background".
- *Acceptance:* uploading N docs produces N `doc_summary` + chunks; the processing screen shows real per-file progress over SSE; ingestion spend appears on the project ledger; a doc that fails to parse is marked `failed` and doesn't block the others.

**T3.3 — AI document summaries (first-class feature)**
- *Goal:* `summary_md` generated on upload pre-fills the file description; an **Auto-summarize / Regenerate** endpoint re-runs it.
- *Files:* new route (e.g. `POST /api/projects/{pid}/documents/{blob_id}/summarize`), FE wiring on the Materials file tiles.
- *Acceptance:* an uploaded file shows a generated description; Regenerate produces a fresh summary; summary is persisted and visible on the Documents view.

**T3.4 — Reflection step: reference-backed "What I learned"**
- *Goal:* `key_facts` → the interview's "What I learned" rows, each with its **source reference** (document + section/page); facts lacking a reference are **converted to interview questions**, not shown as facts (spec §4.5, Risk 1).
- *Acceptance (the trust test):* an **injected fact with no supporting span never renders as a stated fact** — it appears as an unconfirmed question; every displayed learned-fact links to a real source; building cannot start until outstanding questions are answered/confirmed.

### Phase 4 — Coarse retrieval for the build agents (P0/P1)  ·  *needs T3.1–T3.2*

**T4.1 — Hybrid (dense + tsvector) search RPC**
- *Goal:* `search.py` runs the RRF query (dense `<=>` + `ts_rank_cd`) via dbshim; returns `content` + `document` + `section_path` + score, scope-filtered.
- *Acceptance:* `search_memory("<known fact>")` returns the right chunk with correct document + section_path; org docs imported via `blob_uses` are retrievable from the project.

**T4.2 — Console-hosted Memory MCP + tool exposure**
- *Goal:* `memory/mcp_server.py` mounted in `console/app.py`; add `_MEMORY` HTTP server to `workspace_setup.mcp_config()` (both runtimes); resolve `scope_id` from a project-scoped token; seed a `mcp_tools` row. Tools: `get_project_overview`, `list_documents`, `get_document_summary`, `search_memory`, `get_chunk`, `add_memory_note` (only the last writes).
- *Acceptance:* a stage agent lists the memory tools; an agent scoped to project A cannot read project B's memory; agents still carry **no** Supabase creds.

**T4.3 — Point Stage-1/Stage-2 at memory + graceful fallback**
- *Goal:* update stage SKILL prompts to consult `get_project_overview`/`search_memory`; on MCP error the stage **falls back to `context.txt`** and continues (preserves resilience, Principle 5 / §4.8).
- *Acceptance:* a Stage-1 run cites a fact that exists only in an upload; with the memory MCP forced down, the same run still completes using `context.txt` (no wedge).

---

## 4. Dependency / sequencing graph

```
T0.1 ─┬─► T1.1 ─► T1.2 ─► T1.3 ─► T2.1        (Concierge track)
      │                    └─► T1.4 (follow-up)
      └─► T0.2 ─► T3.1 ─► T3.2 ─┬─► T3.3
                                ├─► T3.4        (reflection / trust test)
                                └─► T4.1 ─► T4.2 ─► T4.3   (agent grounding)
```

The two tracks (Conversation/Concierge and Memory/ingestion) parallelize after Phase 0. **T3.4 is the milestone gate** — the reflection trust test is the thing that makes spend safe.

---

## 5. Cross-cutting requirements (apply to every ticket)

- **No drift:** `models.py` is the only table definition; every schema change is an Alembic revision *and* builds under `create_all` in tests; touching schema means updating `docs/ARCHITECTURE.md` + `docs/schema-erd.{md,svg}` (CLAUDE.md §6).
- **Feature-flagged rollout:** `SF_MEMORY` and `SF_CONVERSATION_DB` gate the new paths (mirror `notify`/`storage` env-gating) so `main` stays shippable and tests stay hermetic.
- **Cost & telemetry:** assistant/ingestion turns record `model`/`provider`/tokens/`cost_usd`; reconcile with the `agents` ledger and Langfuse traces.
- **Security invariants:** agents hold no DB credential; memory reached only via the scope-scoped MCP; app-layer `authorize_project` on every route.
- **PR loop:** integrator leaves review comments; the build agent polls its own PR to merge and addresses every comment (CLAUDE.md PR Review Loop). Linear reflects status.
- **Loading/never-blank (spec Principle 1):** any new data-bound surface (Documents summaries, processing log) ships with skeleton/placeholder states.

---

## 6. Definition of done for this milestone (maps to spec P0)

1. A customer can create a project, upload materials, watch **real** ingestion progress, see an **AI summary per file**, and review **reference-backed** learned facts — with unreferenced inferences shown as questions, and no build starting on unconfirmed assumptions (§4.4–§4.5).
2. The Concierge is **one identity** across intake/overview/build/docs, DB-durable, resumable after restart (Principle 2 & 5).
3. Build agents are **grounded** in the project's materials via memory tools, and a memory outage **degrades gracefully** (§4.8).
4. **Ingestion spend counts against the cap** and the stop-at-ceiling brake fires on it.
5. The injected-unreferenced-fact **trust test passes** (T3.4).

---

## 7. Still-open decisions (defaults chosen so work isn't blocked)

| # | Decision | Default we'll build unless you say otherwise |
|---|---|---|
| 1 | Dense embedding model on OpenRouter | **Gemini Embedding 2** (multimodal headroom for PDF/wireframe pages) |
| 2 | Memory tool transport | **Console-hosted HTTP MCP** (secrets stay console-side) |
| 3 | Chunker | **Chonkie `RecursiveChunker`** (add dep) |
| 4 | Overview rollup storage | In **`projectstate.data`** (no new table) |
| 5 | pgvector on CI Postgres | Enable `CREATE EXTENSION vector` in `conftest.py` — **confirm CI image allows it** |
| 6 | `user_id` on conversation | Resolve chat-route **email → `users.id`** at write time (clean FK) |

---

## 8. First PRs to open (week 1)

1. **T0.1** migrations + models (unblocks both tracks).
2. **T0.2** cost seam (small, unblocks in-cap ingestion).
3. **T1.1 + T1.2** conversation store + provider adapter (the piece you don't trust today, made real).
4. **T3.1 + T3.2** memory core + ingestion write-through with real processing progress.

Everything else sequences off those per §4.
