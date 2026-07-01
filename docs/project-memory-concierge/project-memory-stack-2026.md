# Project Memory — Lean Stack (2026)

**Companion to** `project-memory-design.md` · **Date:** 2026-06-30
**Goal:** the smallest set of current, proven libraries that delivers the hierarchical + hybrid design — and an explicit list of what *not* to pull in. The anti-bloat thesis below is the whole point.

---

## Decision: embeddings go through OpenRouter (dense) + Postgres for sparse

We're accessing models via **OpenRouter**. That's one API key for the whole model fleet — but it changes the hybrid design in one specific way worth stating up front:

**OpenRouter's embeddings endpoint is OpenAI-format and returns *dense* vectors only.** None of its embedding models (Gemini Embedding 2, Qwen3-Embedding, Mistral Embed) hand back a sparse/learned-lexical vector. So the "one model → dense + sparse" trick (BGE-M3, Cohere embed-v4) is **not** available through OpenRouter. ([OpenRouter embeddings](https://openrouter.ai/docs/api/reference/embeddings))

The clean answer: get the **dense** vector from a best-in-class model via OpenRouter, and get the **sparse** channel from **Postgres native full-text (`tsvector`)** — no extra model, no BM25 extension, no GPU. Both live in the same Supabase table; you fuse them with a ~15-line SQL RRF query. For distribution docs full of SKUs, part numbers, and API names, `tsvector` exact-keyword matching covers the lexical job well.

That collapses "vector store + sparse index + fusion" into: **one OpenRouter call + Postgres + one SQL query.** Even leaner than the two-vector version, at the cost of learned-sparse (SPLADE-quality) matching — which we can add later via a direct Cohere call if evals show we need it.

> **Trade-off in one line:** OpenRouter buys us model flexibility and zero embedding infra; the price is that the sparse channel is BM25-style keyword (`tsvector`), not learned-sparse.

---

## Recommended stack

| Layer | Pick | Why this one (2026) |
|---|---|---|
| **Store + both indexes** | **Supabase Postgres + pgvector 0.8** (`vector` HNSW) + **`tsvector`** GIN | Already your DB. Dense vectors in pgvector; sparse/keyword via native full-text. `sparsevec` column stays reserved for a future learned-sparse upgrade. Included on all plans, no extra infra. ([Supabase pgvector](https://supabase.com/docs/guides/database/extensions/pgvector)) |
| **Dense embeddings (via OpenRouter)** | **Gemini Embedding 2** (multimodal) or **Qwen3-Embedding** (top MTEB) | One OpenRouter key. Gemini Embedding 2 maps text **and images** into one space (great for PDF pages/screenshots, 8k ctx); Qwen3-Embedding leads pure-text MTEB (~70.6). Both return dense only. ([OpenRouter embedding models](https://openrouter.ai/collections/embedding-models)) |
| **Sparse / keyword channel** | **Postgres `tsvector` + `ts_rank_cd`** | No model, no extension. Handles exact matches on SKUs, part numbers, API names. Fused with dense via RRF. Upgrade path: swap in learned-sparse later without schema change. |
| **Learned-sparse / multimodal upgrade (direct API, not OpenRouter)** | **Cohere embed-v4** | If `tsvector` isn't enough: one call returns dense **and** learned-sparse, and vectorizes PDF screenshots/tables/figures directly. Served via Cohere/Bedrock/Azure — a second key outside OpenRouter. ([Cohere Embed v4](https://docs.cohere.com/changelog/embed-multimodal-v4)) |
| **Chunking / ingestion** | **Chonkie** | 505 KB, "install only what you need," no dependency tree. Ships `RecursiveChunker` (structure-aware, what you want for docs), `CodeChunker`, and `LateChunker`. This replaces LlamaIndex/LangChain ingestion entirely. ([Chonkie](https://github.com/chonkie-inc/chonkie)) |
| **Retrieval quality booster** | **Anthropic Contextual Retrieval** (prepend LLM-generated context to each chunk before embedding) | Highest-ROI technique, not a library: ~35% fewer retrieval failures; with reranking, error dropped 5.7%→1.9% in Anthropic's tests. A prompt + cheap model call at ingest — no new dependency. ([Anthropic](https://www.anthropic.com/news/contextual-retrieval)) |
| **Reranker (optional, flagged)** | **Voyage rerank-2.5** or **Cohere Rerank 4** (direct API); **bge-reranker-v2-m3** if self-hosting | Rerank endpoints are direct-API (not OpenRouter's embeddings route). Top rerankers sit within 1–3 NDCG points of each other; pick on latency/cost. Only rerank the top ~20 fused hits. ([reranker leaderboard](https://agentset.ai/rerankers)) |
| **Glue** | **Vanilla Python + OpenRouter client (OpenAI-compatible) + `psycopg`/`vecs`** | No orchestration framework. One OpenRouter base URL for embeddings + summarization LLM calls; plain SQL RPCs for retrieval. Skip LangChain, import only what you call. ([vecs](https://github.com/supabase/vecs)) |

---

## What NOT to build (the anti-bloat list)

- **No LangChain.** For a fixed ingest→search→rerank path it's dependency hell for zero benefit; the 2026 guidance is explicitly to avoid it for simple RAG. If you ever want graphs, reach for `langgraph` alone — not the metapackage.
- **No separate vector database** (Pinecone/Weaviate/Qdrant). pgvector in the DB you already run is enough at your scale, and it keeps `project_id` scoping in one place (enforced at the app layer, consistent with the rest of the system — not RLS). Revisit only if a single project exceeds tens of millions of chunks.
- **No BM25 extension.** VectorChord-BM25 / ParadeDB `pg_search` are excellent but **not available on managed Supabase** as of mid-2026. Native `tsvector` + `ts_rank_cd` covers the keyword channel with zero added infra.
- **No self-hosted embedding model** to start. OpenRouter gives dense from a top model with one key and no GPU. Revisit only if we decide learned-sparse (Cohere embed-v4 direct, or a self-hosted SPLADE) is worth the added dependency.
- **No custom chunker.** Chonkie's `RecursiveChunker` is better than anything worth hand-rolling.
- **No agent framework for retrieval.** The six tools in the design are thin functions over SQL RPCs.

---

## How the pieces map to the design doc

- §3 data model: `chunk.dense vector` is populated by the **OpenRouter embedding call**; the sparse channel is the generated **`fts tsvector`** column. `sparse sparsevec` stays in the schema, unused for now, reserved for a learned-sparse upgrade.
- §4 summaries: the contextual-retrieval blurb per chunk is generated in the same map pass that builds `doc_summary` (also an OpenRouter LLM call) — no extra stage.
- §5 ingestion: Chonkie does parse+chunk → OpenRouter embeds dense → `to_tsvector` builds sparse → contextual context is prepended before embedding.
- §6 hybrid search: RRF SQL fuses dense (`<=>`) and `ts_rank_cd`; reranker is the optional, flagged tail.

---

## Suggested first slice (proves it lean)

1. Supabase + pgvector 0.8, tables from §3 (dense `vector` + generated `fts tsvector`).
2. Chonkie `RecursiveChunker` → OpenRouter embed (Gemini Embedding 2 or Qwen3) → insert; `fts` auto-generated.
3. One RRF RPC (`project_memory_search`) fusing `dense` (`<=>`) and `ts_rank_cd(fts, query)`.
4. `search_memory` + `get_project_overview` tools.
5. Add contextual-retrieval prepend (biggest quality jump for least code).
6. Add reranker (direct API) only if eval shows it's needed; consider Cohere embed-v4 for learned-sparse if `tsvector` underperforms.

Everything above is ~a few hundred lines and three dependencies (OpenRouter client, Chonkie, psycopg), not a framework.

---

## Sources

- [pgvector 0.8.0 (PGXN)](https://pgxn.org/dist/vector/0.8.0/) · [Supabase pgvector docs](https://supabase.com/docs/guides/database/extensions/pgvector) · [Supabase vecs client](https://github.com/supabase/vecs)
- [OpenRouter embeddings API](https://openrouter.ai/docs/api/reference/embeddings) · [OpenRouter embedding models](https://openrouter.ai/collections/embedding-models)
- [Cohere Embed v4 (multimodal, dense+sparse)](https://docs.cohere.com/changelog/embed-multimodal-v4)
- [BGE-M3 model card](https://huggingface.co/BAAI/bge-m3) · [BGE-M3 docs](https://bge-model.com/bge/bge_m3.html)
- [Embedding leaderboard 2026 (Milvus)](https://milvus.io/blog/choose-embedding-model-rag-2026.md)
- [Chonkie chunking library](https://github.com/chonkie-inc/chonkie)
- [Anthropic Contextual Retrieval](https://www.anthropic.com/news/contextual-retrieval)
- [Reranker leaderboard (Agentset)](https://agentset.ai/rerankers)
- [VectorChord-BM25 (context on why it's not on Supabase yet)](https://github.com/orgs/supabase/discussions/18061)
