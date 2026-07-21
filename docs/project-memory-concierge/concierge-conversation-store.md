# Concierge Conversation Store — Design

**Date:** 2026-06-30 · **Grounded in:** `main` @ `ded31ad` (Concierge conversation loop — FE + **mocked** backend).
**Replaces:** the in-memory mock `services/conversation.py` **and** the volume-only `chat.jsonl` (`ChatStore`) — both are data-loss / non-durable today.
**Goal:** one DB-backed conversation store whose rows carry everything needed to (a) render the UI, (b) telemeter cost, and (c) **replay the exact history to any model provider** (OpenAI / Anthropic / OpenRouter), including **image input, image retrieval, and images extracted from a document (with the source document + page)**.

---

## 0. What exists today (and why it can't stay)

| Surface | Route | Storage today | Problem |
|---|---|---|---|
| Factory Concierge | `POST /api/chat` (`chat_agent.py`) | `ChatMessage{role,content,msg_type,ts,metadata}` → **`chat.jsonl` on the /data volume** | lost if the volume is wiped (ARCHITECTURE §5/§6); not queryable; images stored as **names only** (`metadata["images"]=[name]`) |
| Onboarding Concierge | `POST /api/projects/{pid}/converse` (`conversation.py`) | **in-memory dict**, resets on restart | mock; scripted; no persistence, no provider replay |

The commit that added `/converse` says it plainly: *"the real agent + DB-backed chat history follow… swaps to the real agent + DB-backed history later with no route change."* This design is that store. The `turn()`/`history()` contract and the `/converse` + `/api/chat` routes stay; only `state.conversation_svc` / `ChatStore` are swapped for the DB-backed implementation.

---

## 1. The table — `conversation` (one row per message/turn)

Matches your column list, plus the few extras replay + telemetry need. Follows repo conventions: `models.py` `Table`, `Text` ids for project (flat-schema style), `_UUID` for identity, `JSONB` blobs, all DML through `dbshim`.

```python
conversation = Table(
    "conversation", metadata,
    Column("id", _UUID, primary_key=True, server_default=text("gen_random_uuid()")),   # = message_id (returned to FE)
    Column("session_id", _UUID, nullable=False),          # groups one conversation/thread (see §2)
    Column("seq", Integer, nullable=False),               # monotonic order within session (replay key)

    # --- scoping (denormalized onto every row: flat-schema; app-layer scope checks, not RLS) ---
    Column("user_id", _UUID, ForeignKey("users.id")),     # who sent it (null for agent/tool/system)
    Column("project_id", Text),                           # → projectstate; null for org-level chat
    Column("org_id", Text),                               # → organizations.id

    # --- the message ---
    Column("role", Text, nullable=False),                 # user | agent | tool | system
    Column("input", Text),                                # plaintext (denormalized from json_blob; display/search)
    Column("json_blob", JSONB, nullable=False,            # CANONICAL content blocks — source of truth (§3)
           server_default=text("'[]'::jsonb")),

    # --- tool turns (role='agent' emits tool_use; role='tool' carries the result) ---
    Column("tool_name", Text),
    Column("tool_call_id", Text),                         # correlates tool_use ↔ tool_result
    Column("tool_result", JSONB),                         # convenience mirror of the result block (query/telemetry)

    # --- references & provenance ---
    # NOTE (as shipped): this single referenced_artifact FK was deliberately NOT built — one prompt
    # can cite many artifacts, so artifact refs live as blocks inside json_blob, not a scalar column.

    # --- model attribution (assistant/tool turns) ---
    Column("model", Text),
    Column("provider", Text),                             # 'openai' | 'anthropic' | 'openrouter' | ...
    Column("input_tokens", Integer, server_default="0"),
    Column("output_tokens", Integer, server_default="0"),
    Column("cost_usd", Float, server_default="0"),

    # --- Concierge output (see concierge-agent-spec.md §3) — lives in json_blob on agent turns ---
    # suggested_responses: [{response, type: "single select"|"multi select"}]; empty ⇒ plain text.
    # No `choices`/`done` columns — the FE derives multi/single-select purely from json_blob.

    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    Column("updated_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    UniqueConstraint("session_id", "seq", name="uq_conversation_session_seq"),
)
```

Indexes (migration `0009_conversation`): `(session_id, seq)` unique already; `(project_id)`, `(org_id)`, `(user_id)` for scoped lookups + the admin history filters (§9).

**Output contract.** `ConverseOut` = `{ "response": str, "suggested_responses": [{"response": str, "type": "single select"|"multi select"}] }`. The `suggested_responses` array is stored inside the agent turn's `json_blob` (not a dedicated column), so the multiple-choice UI is a pure function of the stored message. `id` is the **message_id** returned to the FE; `session_id` is the thread. Full agent programming in `concierge-agent-spec.md`.

**Why `seq` in addition to `created_at`:** replay order must be deterministic; two messages in the same turn (assistant tool_use + tool result) can share a timestamp. `seq` is the authoritative order; `created_at`/`updated_at` are audit.

---

## 2. Session grouping — `session_id` (no second table required)

A project has several Concierge *contexts* (PRD §2.4b: `overview` / `build` / `docs` / `ingesting` / interview). Rather than a separate table, the **`session_id`** column groups a conversation's messages. Recommended minimal form: keep `session_id` on the row now; add a small `conversation_session(id, project_id, org_id, context, title, created_at)` **only if** the admin history UI (§9) needs to list/rename sessions cheaply. For onboarding there's exactly one session per draft, so a deterministic `session_id = uuid5(project_id, "onboarding")` works with zero extra rows.

---

## 3. `json_blob` — provider-agnostic content blocks (the source of truth)

Every row's `json_blob` is a **list of canonical content blocks**. This is the one representation the whole system reads; the flat `input`/`tool_result` columns are denormalized conveniences. Block shapes:

```jsonc
// text
{ "type": "text", "text": "In one line, what's the outcome?" }

// image  (ALWAYS references a blob; never inline bytes in the row)
{ "type": "image",
  "blob_id": 8123,                       // → blobs.id (bytes in Supabase Storage)
  "media_type": "image/png",
  "origin": {                            // where this image came from
    "kind": "upload" | "generated" | "doc_extract",
    "document_blob_id": 8100,            // present when kind = doc_extract
    "page": 4                            // 1-based source page/slide (doc_extract)
  } }

// tool call (role = 'agent')
{ "type": "tool_use", "id": "call_ab12", "name": "search_memory",
  "input": { "query": "pricing tiers", "k": 8 } }

// tool result (role = 'tool')
{ "type": "tool_result", "tool_use_id": "call_ab12", "is_error": false,
  "content": [ {"type":"text","text":"…"}, {"type":"image","blob_id":8130,"origin":{...}} ] }
```

Design rules:
- **Images are blobs, never inline.** A content block holds `blob_id` + `media_type` + `origin`; the bytes live in the existing Supabase Storage adapter (`storage.py`/`BlobStore`). This keeps rows small and reuses durable storage.
- **`origin` makes retrieval self-describing.** When the Concierge answers "show the wiring diagram from the spec," the returned image block already names its `document_blob_id` + `page`, so the UI can caption it ("p.4 of spec.pdf") and the model gets the provenance — exactly your requirement that a document-extracted image travels with its document + page.
- **Tool turns** are two rows (assistant `tool_use`, then `tool` `tool_result`) so provider replay is lossless; the `tool_result` column mirrors the result for cheap querying/telemetry.

---

## 4. Images & document-page provenance (where the link lives)

Images unify onto `blobs` (kind `image`). To record "extracted from document X, page N," add **provenance to `blobs`** so it's canonical, not just embedded in a message:

```python
# blobs table — add:
Column("source_blob_id", Integer, ForeignKey("blobs.id")),  # the document this asset came from
Column("source_page", Integer),                              # 1-based page/slide
Column("provenance", JSONB, server_default=text("'{}'::jsonb")),  # extractor, bbox, etc.
```

This dovetails with the **Project Memory ingestion** (the other design): `docx_extract.extract_with_images` already pulls images out of Word tables, and PDF pages can be rasterized on extract. Each extracted image becomes a `blobs` row with `source_blob_id`→the document and `source_page`. A message that surfaces such an image just references its `blob_id`; the doc+page ride along automatically.

Optional `message_asset(message_id, blob_id, direction)` join (mirrors `blob_uses`) if we want fast "all images in this thread" / reuse counts — defer until a screen needs it.

---

## 5. Provider replay — one adapter, many providers

`history(session_id)` → rows ordered by `seq` → assemble canonical messages → **`to_provider(messages, provider)`** renders the shape each SDK wants. This is the "easily fetched and made part of conversation history before being sent to a model provider" requirement.

- **Role map:** `user`→`user`; `agent`→`assistant`; `system`→`system`; `tool`→ *(Anthropic: a `user` message whose content is a `tool_result` block; OpenAI: a `tool` role message keyed by `tool_call_id`)*.
- **Images:** resolve `blob_id` → the storage adapter yields a signed URL or base64; emit the provider's image part (OpenAI `image_url`, Anthropic `image` source). `origin` is dropped from the provider payload (it's UI/context metadata) but can be prepended as a caption when useful.
- **Provider-agnostic canonical form in the DB; provider-specific only at the boundary.** Switching a project's model/provider never touches stored history.

Sketch:
```python
def to_provider(rows, provider):        # rows: canonical messages (json_blob per row)
    msgs = []
    for r in rows:
        blocks = [render_block(b, provider) for b in r["json_blob"]]
        msgs.append(map_role(r["role"], blocks, provider))
    return msgs
```

---

## 6. Swap the mock, keep the contracts

- `services/conversation.py` → `Conversation` keeps its `turn(project_id, message)` and `history(project_id)` signatures, now reading/writing `conversation` via a `ConversationStore` over `dbshim`. Its output shape moves to the new `ConverseOut` (`{response, suggested_responses}`) per `concierge-agent-spec.md` — storage swap in T1.3 (route + FE untouched), output-shape swap in T2.2 (FE updates then). `state.reset()` builds it exactly where `conversation_svc` is built today.
- `/api/chat` (`chat_agent.py`) stops writing `chat.jsonl`; it appends the same rows to `conversation` (role `user`/`agent`, `model`/`provider`/tokens filled from the run). `chat_history` reads from the table. `chat.jsonl` can stay as a debug mirror during migration, then retire.
- **Cost telemetry** already exists per-agent (`runtime_agents` table); assistant turns write `model`/`provider`/tokens/`cost_usd` so conversation cost reconciles with the run's ledger.

---

## 7. Migration & tests

- `0009_conversation.py`: create `conversation`; add `source_blob_id`/`source_page`/`provenance` to `blobs`; indexes. Follows the Alembic-owns-schema / `models.metadata.create_all`-in-tests invariant, so no drift.
- Unit tests mirror `tests/unit/test_conversation.py` (no DB) for the service contract; an integration test asserts round-trip persistence + `to_provider` output shape for OpenAI and Anthropic (incl. an image block and a tool_use/tool_result pair).

---

## 9. Admin history table (Tenexity OS)

One filterable, cross-tenant view of **all** conversation history — the store already carries every scope needed, so this is a query surface, not new data.

- **Endpoint:** `GET /api/admin/conversations` (staff-gated, `_staff_session`), filters: `org_id`, `project_id`, `user_id`, `session_id`, `role`, date range; paginated.
- **Two lenses:** a **sessions** roll-up (`session_id` + org + project + user + turn count + last activity) and a **messages** drill-down (role, `model`/`provider`, `cost_usd`, rendered `response`/`suggested_responses`). Clicking a session opens its full transcript.
- **Placement:** a history/observability screen in Tenexity OS, next to §5.4's produced-files index. Because agent rows store model/provider/tokens/cost, it doubles as per-conversation spend visibility.

---

## 8. Open decisions

1. **Session table now or later?** Recommend the `session_id` column only for now (deterministic `uuid5` for onboarding); add `conversation_session` when a session-list/rename UI needs it.
2. **Unify `/api/chat` onto this table in the same PR, or migrate `/converse` first?** Recommend `/converse` first (it's the mock you don't trust), then fold `/api/chat` off `chat.jsonl` in a follow-up so the blast radius is staged.
3. **Image bytes to the provider:** signed Storage URL (cheaper, needs public-ish URL) vs base64 inline (works everywhere, larger payloads). Recommend signed URL with base64 fallback.
4. **`user_id` type:** `users.id` is `_UUID`; the chat routes currently carry the owner **email** (`v[0]`). Either resolve email→`users.id` at write time (recommended, clean FK) or store email in a separate column. 
5. **Does conversation feed Project Memory?** On hand-off, the interview transcript + extracted `key_facts` are a natural `memory_note` / doc — recommend writing the finalized brief into memory so agents can retrieve "what the user said in onboarding."
```
