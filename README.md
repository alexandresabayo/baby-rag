# baby-rag

A small, complete, provider-agnostic RAG (retrieval-augmented generation) web app.
Drop `.txt` files into `corpus/` (or upload them from the browser), index them, chat with
them, inspect exactly what was retrieved and why, tune the pipeline live from the UI, and
come back later to a searchable history of everything you asked.

> **This README is the full specification.** It is written to be read by a coding agent that
> builds the whole repository from it. Read it end to end before writing any code.

---

## 0. Instructions for the building agent

1. **Work autonomously. Do not ask clarifying questions.** Where this spec is silent or
   ambiguous, choose the simplest reasonable option and record it in `docs/DECISIONS.md`
   (one line: decision + reason). The same file records any deviation from this spec.
2. **Build in the phase order of section 12.** Finish and verify each phase before the next.
3. **Priorities:** `MUST` items are required, `SHOULD` items are expected, `STRETCH` items
   only if everything else is done and green. Never sacrifice a MUST for a STRETCH.
4. **Verify your work by running it.** Run the tests, start the backend, hit the endpoints,
   build the frontend. Do not claim something works without having executed it.
5. **Commit in small logical commits** with clear messages. No secrets, no `.env`, no
   `node_modules`, no build output, no `data/` in git.
6. **Finish by updating section 13 (Status)** of this README: tick what is done, and list
   honestly what is not done or not verified, and how you verified the rest.
7. **Pin nothing blindly.** Use current stable versions of every dependency and record the
   resolved versions in `pyproject.toml` / `package.json` (lockfiles committed). For ChromaDB
   in particular, follow the documentation of the version you install (its API has changed
   between releases).
8. **No containers.** This project does not use Docker: do not create Dockerfiles, Compose files
   or nginx configs. Everything runs as plain local processes (section 11). Use
   `FAKE_PROVIDERS=1` (section 6.4) so nothing needs an API key to be tested.
9. **Design is not yours to decide.** This spec contains no visual design. Before writing any
   frontend markup or CSS, invoke the skills listed in section 7.1 and follow them. If a skill
   is not available in your environment, say so in `docs/DECISIONS.md` and ship neutral,
   unstyled-but-usable CSS behind the single theme file; do not invent a look.
10. **Architecture is graded.** Section 3 contains rules that are enforced by an automated
    test. Read them before creating the first file, not after.

---

## 1. Goal, scope and how this project will be judged

**Goal:** the most complete *backbone* of a RAG application: ingestion, retrieval,
generation, history, API, UI, tests, packaging. Correct, inspectable and extensible over
feature-rich.

**In scope:** local single-user use, plain-text corpus, OpenAI-compatible LLM and embedding
endpoints, hybrid retrieval, streaming chat with citations, persistent searchable history,
live tuning of the RAG pipeline from the web interface.

**Out of scope (v1):** authentication and multi-user, PDF/Word parsing, agents/tool-calling,
fine-tuning, cloud deployment, Docker/containers, ORMs and schema-migration tooling. The API is meant to be
bound to localhost.

### 1.1 Evaluation lenses

The result will be reviewed by a developer through three lenses. Each one has a concrete,
demonstrable acceptance path; the building agent must make each path work and describe it in
the Status section (13).

| # | Lens | What the reviewer looks for | Where specified | Demo path |
|---|---|---|---|---|
| 1 | **Web architecture trinity** (Frontend, Backend, Database) | Each tier has a clear job and the database visibly matters to the user: data survives restarts, can be browsed, searched and deleted from the UI | 3.1, 5, 6.6, 7 | Chat, restart backend, open **History**: the conversation is there, is full-text searchable, shows its sources and retrieval trace, can be renamed and deleted |
| 2 | **Codebase architecture is solid** | Layering, dependency direction, dependency injection, swappable interfaces, pure core, tests that enforce the rules | 3.2 to 3.5 | `make test` runs `test_architecture.py`; `docs/ARCHITECTURE.md` explains how to add a provider, a retriever, a setting |
| 3 | **RAG is manipulable from the web interface** | Every meaningful knob and every intermediate artifact (chunks, candidates, scores, final prompt) can be seen and changed without touching files or restarting | 6.5, 6.2, 7 (Lab page) | Open **Lab**, change `top_k`, toggle hybrid, edit the system prompt, filter by document, and watch retrieved chunks and the answer change |

---

## 2. Stack

| Layer | Language / standard | Open-source framework / tool |
|---|---|---|
| Frontend UI | JavaScript (ES2022) | Vue 3 (Composition API, `<script setup>`), Vite, Pinia, Vue Router, `marked`, DOMPurify |
| Backend / API | Python 3.12 | FastAPI, Uvicorn, Pydantic v2 |
| Application database | SQL | **SQLite** (single file, WAL mode) with **FTS5** for full-text search (chunks **and** message history) |
| Vector database | Embeddings + similarity search | **ChromaDB** (`chromadb` Python client, embedded/persistent mode) |
| DB access | Python | **Standard-library `sqlite3` only**: plain SQL, no ORM, no migration tool |
| LLM (chat) | OpenAI-compatible HTTP API (`/v1/chat/completions`) | `openai` Python SDK (`AsyncOpenAI`), any provider |
| Embeddings | OpenAI-compatible HTTP API (`/v1/embeddings`) | same SDK, **separate endpoint config** |
| Visual design | delegated | Claude skills listed in section 7.1 (nothing is specified here) |
| Run / packaging | Single local process | Uvicorn serves the API and the built UI on one port (`make start`); Vite dev server for development |
| Tests | Python / JavaScript | pytest, Vitest |
| Lint / format | | ruff (Python), ESLint + Prettier (JS) |

**Two stores, two clear roles:**
- **SQLite = source of truth.** Documents, chunk text and offsets, the full-text indexes,
  conversations, messages (with sources and retrieval traces), ingestion job history,
  runtime settings, metadata.
- **ChromaDB = derived vector index only.** It holds one embedding per chunk, keyed by the
  chunk id from SQLite. It can be wiped and rebuilt at any time from SQLite (`make reindex`).

Other notes:
- Chat and embeddings are configured independently because not every provider offers both
  (or offers them with the same base URL).
- Frontend is plain JavaScript (not TypeScript). JSDoc comments are welcome.
- There is deliberately **no data-access layer** beyond small plain functions: no SQLAlchemy,
  no Alembic, no repository framework. SQL lives as plain strings in `app/db/`.
- SQLite must be compiled with FTS5 (true for practically every Python build). The app checks
  this at startup and fails fast with a clear message otherwise.

---

## 3. Architecture

### 3.1 The trinity and what each tier owns

```
┌──────────────────────┐   HTTP / JSON / SSE   ┌─────────────────────────────┐        ┌──────────────────────────┐
│ FRONTEND (Vue 3)     │ ────────────────────► │ BACKEND (FastAPI)           │ ─────► │ DATABASE                 │
│ Chat · History · Lab │ ◄──────────────────── │ api → services → db/vector  │ ◄───── │ SQLite  (source of truth)│
│ Corpus · Status      │                       │ providers: LLM, embeddings  │        │ ChromaDB (derived index) │
└──────────────────────┘                       └─────────────────────────────┘        └──────────────────────────┘
```

| Tier | Owns | Must NOT |
|---|---|---|
| Frontend | Presentation, interaction state, SSE consumption, rendering of traces | Contain retrieval or prompt logic; call the LLM; hold data that is not also persisted server-side |
| Backend | Validation, business rules, retrieval, prompt assembly, streaming, orchestration of the two stores | Render anything; import UI concepts; let routers contain SQL |
| Database | Durable state: corpus, chunks, conversations, messages + traces, settings, job history, both full-text indexes; vectors in Chroma | Hold business logic beyond constraints, triggers for FTS sync, and indexes |

**The database must be a user-visible feature, not plumbing.** The UI exposes it through:
the **History** page (persisted, searchable conversations; section 6.6), the **Corpus** page
(documents, chunks, job history), the **Lab** page (stored settings and stored traces), and
the **Status** page (store health and counts). Anything a user would reasonably expect to
survive a restart must be in SQLite.

### 3.2 Data flow

```
 corpus/*.txt ──► ingest ──► chunk ──► embed ──┬─► SQLite:   documents, chunks (text, offsets) + FTS5 index
   ▲ (upload)                                  └─► ChromaDB: one vector per chunk (id = chunk id)

 Browser (Vue) ──► FastAPI ──► effective settings = request overrides > saved settings > registry defaults
        ▲             │       ──► retrieve: ChromaDB (vector) + SQLite FTS5 (full-text) ──► RRF fusion ──► top-k
        │             │                                                                        │
        └── SSE ◄─────┴──── build prompt (context + history + question) ──► LLM ◄─────────────┘
                      └──► persist user + assistant message, sources and full trace in SQLite
```

### 3.3 Backend layering (enforced)

`api/` (HTTP only) → `services/` (business logic) → `db/` (connection helper, schema, plain SQL
functions) and `services/vectorstore.py` (the only module that imports `chromadb`).

Rules. Each one is checked by `backend/tests/test_architecture.py`, which parses the source
with `ast` and fails with a readable message naming the offending file and import:

1. **Dependency direction is one-way:** `api → services → db`. `db/` imports nothing from
   `services/` or `api/`. `services/` never imports from `api/`. No cycles.
2. **Import confinement:** `sqlite3` only inside `app/db/`; `chromadb` only in
   `services/vectorstore.py`; `openai` only inside `services/providers/`; `fastapi` /
   `starlette` only inside `api/` and `main.py`.
3. **Routers are thin:** a route handler validates input (Pydantic), calls one service
   function, returns a schema. No SQL, no retrieval logic, no prompt text in `api/`.
4. **Composition root + dependency injection:** `main.py` exposes `create_app(settings, paths)` (both default to the real ones for `uvicorn app.main:create_app --factory`).
   Everything a handler needs (settings, paths, DB connection, providers, vector store, ingestion
   lock) is obtained through FastAPI `Depends` in `api/deps.py`. No module-level singletons
   or mutable globals (a logger is fine). Tests swap implementations through
   `app.dependency_overrides`, never by monkeypatching.
5. **Interfaces are `typing.Protocol`s:** `LLMProvider`, `EmbeddingProvider`, `VectorStore`.
   Real and fake implementations both conform; a shared contract test-suite is run against
   every implementation.
6. **Pure core:** `chunking`, `build_fts_query`, `rrf_fuse`, prompt building, and settings
   resolution/validation are pure functions (no I/O, no clock, no randomness) and have the
   densest unit tests.
7. **Two kinds of models:** Pydantic models live only in `api/schemas.py` (wire format);
   services exchange plain `dataclass`es. Services never see HTTP types.
8. **Typed and linted:** type hints on all public functions; ruff clean (include rules
   `B`, `UP`, `I`, `S`); a type checker (mypy or pyright) is a SHOULD.
9. **Errors are domain errors:** services raise small domain exceptions
   (`NotFound`, `Conflict`, `InvalidInput`, `IndexNotReady`, `ProviderError`); a single handler
   in `api/errors.py` maps them to the JSON error shape.
10. **Extension is additive:** adding a provider, a retriever or a setting must not require
    editing existing routers or unrelated services (see 3.5).

### 3.4 Frontend layering (enforced)

`views/` → `stores/` (Pinia) → `api/` (the **only** place that calls `fetch`).
`components/` are presentational: props in, events out, no store access, no `fetch`.
`api/sse.js` is a pure parser (string chunks in, events out). Server state is owned by stores;
views do not keep private copies of it. ESLint `no-restricted-imports` enforces: components
cannot import `api/` or `stores/`; views cannot import `api/` directly.

### 3.5 Documentation of the architecture

`docs/ARCHITECTURE.md` (MUST, short): the diagram of 3.1/3.2, the layer rules, a request
walkthrough for (a) a chat turn, (b) an ingestion run, (c) a history search, and a
"how do I add..." recipe for: a new LLM/embedding provider, a new retriever, a new runtime
setting (see 6.5: it is one registry entry), a new API resource.

### 3.6 SQLite access rules (`app/db/`)

- `sqlite3` is synchronous. API handlers call DB functions through `asyncio.to_thread`
  (or Starlette's `run_in_threadpool`) so the event loop is never blocked.
- One short-lived connection per request / per ingestion run, opened by a single helper that sets
  `PRAGMA journal_mode=WAL`, `PRAGMA foreign_keys=ON`, `PRAGMA busy_timeout=5000`, uses
  `sqlite3.Row` as row factory, and `isolation_level=None` (autocommit) so transactions are
  explicit (`BEGIN IMMEDIATE` … `COMMIT`/`ROLLBACK`). Never share a connection between threads.
- Always use `?` parameters; never build SQL with string formatting from user input. The one
  exception is the FTS5 tokenizer in DDL, which must come from an allow-list (see 6.5).
- Run a **single Uvicorn worker**. The database file must live on a local disk (not a network
  share).

---

## 4. Configuration (`backend/.env`)

Configuration is deliberately minimal and split in three, by *who decides*:

| Kind | Examples | Where it lives |
|---|---|---|
| **Environment** (secrets, endpoints, things that differ per machine) | API keys, base URLs, model names | `backend/.env` |
| **Application layout** (structure of the project, same for everyone) | database file, Chroma folder, corpus folder, collection name, embedding batch size | **code constants** in `config.py` (`AppPaths`), injectable in tests |
| **RAG tuning** | `top_k`, chunk size, temperature, system prompt | **runtime settings** (6.5): registry defaults in code, changed from the web UI, saved in SQLite |

Only the first kind is an environment variable. Paths and the Chroma collection name are not
configuration: nobody needs to move them, and putting them in `.env` only adds ways to break the
app. Log level is not app configuration either: it is passed to Uvicorn by the Makefile
(`--log-level`).

**Where and how `backend/.env` is loaded**
- The file is **`backend/.env`** (template: `backend/.env.example`). The backend is the only
  consumer of configuration and secrets; the frontend has no env file and never holds a secret.
- Loaded with `pydantic-settings` (`BaseSettings`). Real environment variables override the file.
- The `.env` path is resolved from `config.py`'s own location, never from the current working
  directory, so `make`, pytest and IDEs all behave the same.
- **Required = a field with no default.** Missing required variables must produce one readable
  message listing every missing name and how to fix it (or use `FAKE_PROVIDERS=1`), then exit
  non-zero; never a raw Pydantic traceback. There are **no fallbacks between variables**: the
  chat and embedding endpoints are configured explicitly and independently.
- The only conditional rule lives in one `model_validator`: the six required variables are waived
  when `FAKE_PROVIDERS=1`.

| Variable | Required? | Default | Meaning |
|---|---|---|---|
| `LLM_BASE_URL` | **yes** (unless fake) | none | OpenAI-compatible chat endpoint |
| `LLM_API_KEY` | **yes** (unless fake) | none | |
| `LLM_MODEL` | **yes** (unless fake) | none | also the default of the `llm_model` runtime setting |
| `EMBEDDING_BASE_URL` | **yes** (unless fake) | none | OpenAI-compatible embeddings endpoint |
| `EMBEDDING_API_KEY` | **yes** (unless fake) | none | |
| `EMBEDDING_MODEL` | **yes** (unless fake) | none | |
| `EMBEDDING_DIM` | no | unset = model's native size | for models that accept a `dimensions` parameter (e.g. OpenAI `text-embedding-3-*`); when set it is sent with every embeddings request and the returned vectors must match |
| `FAKE_PROVIDERS` | no | `0` | `1` = offline deterministic fakes, nothing else required |

`backend/.env.example` is exactly this (required uncommented, optional commented out with their defaults):

```dotenv
# --- Required (unless FAKE_PROVIDERS=1) ---
LLM_BASE_URL=https://api.mistral.ai/v1
LLM_API_KEY=changeme
LLM_MODEL=mistral-small-latest
EMBEDDING_BASE_URL=https://api.mistral.ai/v1
EMBEDDING_API_KEY=changeme
EMBEDDING_MODEL=mistral-embed

# --- Optional (shown with their defaults; uncomment to override) ---
# EMBEDDING_DIM=        # unset = model's native size; set only for models that support a "dimensions" parameter
# FAKE_PROVIDERS=0
```

**Application layout (`AppPaths`)** is a frozen dataclass in `config.py`, built from the location of
`config.py` (never from the cwd) and passed into `create_app(settings, paths=AppPaths.default())`:

| Field | Value |
|---|---|
| `database` | `<repo>/data/babyrag.db` |
| `chroma_dir` | `<repo>/data/chroma` |
| `corpus_dir` | `<repo>/corpus` (uploads go to `corpus/uploads/`) |
| `CHROMA_COLLECTION` (module constant) | `baby_rag_chunks` |
| `EMBEDDING_BATCH_SIZE` (module constant) | `32` |
| `FAKE_EMBEDDING_DIM` (module constant) | `256` |

Tests build `AppPaths` pointing at a temporary directory and pass it in; they never touch the real
`data/` or `corpus/` and never set environment variables for paths. The same object is the only
source of paths for the ingestion lock, the CLI and the API.

**Tests and `.env`:** tests never read the real `.env`: they build `Settings(_env_file=None, ...)`
explicitly and pass it to `create_app`.

Provider examples to document in `.env.example` as comments:

| Provider | `*_BASE_URL` | Chat model example | Embedding model (dimension) |
|---|---|---|---|
| Mistral API | `https://api.mistral.ai/v1` | `mistral-small-latest` | `mistral-embed` (1024) |
| OpenAI | `https://api.openai.com/v1` | (any chat model) | `text-embedding-3-small` (1536) |
| Ollama (local) | `http://localhost:11434/v1` | (any pulled model) | `nomic-embed-text` (768) |
| vLLM / LM Studio / OpenRouter | their `/v1` URL | their model id | their embedding model |

**Chroma:** only the embedded `persistent` client (folder `AppPaths.chroma_dir`) is implemented. It sits
behind the `VectorStore` protocol, so a server mode could be added later without touching other
code. An embedded store must not be opened by several processes: run **a single Uvicorn worker**,
and use the server lock below.

**Server lock (CLI xor server):** the server takes an exclusive OS file lock on
`<database file>.server.lock` at startup and holds it for its whole life. The CLI commands
(`ingest`, `reindex`, `verify`) try to take the same lock without waiting; if it is held they
exit non-zero with: *"The server is running. Stop it first, then re-run this command."* The same
lock makes a second server refuse to start. So at any time either the server or the CLI owns the
stores, never both.

**Embedding model rule:** store the embedding model name and dimension in the SQLite `meta` table
and in the Chroma collection metadata at first ingest.
- **`EMBEDDING_DIM` unset (default):** no `dimensions` parameter is sent, so providers that reject
  it (e.g. Mistral) work; the dimension is detected from the first embedding returned.
- **`EMBEDDING_DIM` set:** it is passed as `dimensions` in every embeddings request (the provider
  receives it through its constructor, `dimensions: int | None`), and the returned vector length
  must equal it, otherwise the call fails with a clear message (the model probably does not
  support the parameter).
- The fake provider uses `EMBEDDING_DIM` when set, else `FAKE_EMBEDDING_DIM`.

On startup, if the configured model or a set `EMBEDDING_DIM` differs from `meta`, refuse to serve
retrieval and print: *"Embedding model changed; run `make reindex`."* Every embedding call also
checks the returned vector length against the stored dimension and fails with the same message on a
mismatch.
`make reindex` deletes and recreates the Chroma collection and re-embeds every chunk stored in
SQLite (no re-chunking needed). Embedding model, endpoints and API keys are **never** editable from
the web UI.

**Tokenizer rule:** store the active FTS tokenizer in `meta`. If it changes (from the UI, see 6.5),
the app drops and recreates both FTS5 tables (`chunks_fts`, `messages_fts`) and their triggers and
rebuilds them from `chunks` / `messages` (cheap, no re-embedding).

---

## 5. Data model

### 5.1 SQLite (plain SQL, no migration tool)

The schema lives in `backend/app/db/schema.sql` and is applied at every startup with
`CREATE TABLE IF NOT EXISTS`. The schema version is kept in `PRAGMA user_version` (currently `1`):
if the file has a **newer** version than the code, refuse to start with a clear message. There
is no upgrade machinery in v1: a schema change means deleting the database file and re-ingesting
(record it in `docs/DECISIONS.md`; conversations are lost, which is acceptable for v1).

Types follow SQLite conventions: timestamps are ISO-8601 UTC strings, UUIDs are `TEXT`, JSON
is `TEXT`.

```sql
CREATE TABLE IF NOT EXISTS documents (
  id             INTEGER PRIMARY KEY AUTOINCREMENT,
  path           TEXT NOT NULL UNIQUE,       -- relative to the corpus dir, POSIX separators
  content_hash   TEXT NOT NULL,              -- sha256 of file bytes
  n_chars        INTEGER NOT NULL,
  n_chunks       INTEGER NOT NULL DEFAULT 0,
  chunk_size     INTEGER NOT NULL,           -- chunking parameters used for this document
  chunk_overlap  INTEGER NOT NULL,
  status         TEXT NOT NULL CHECK (status IN ('indexed', 'failed')),
  error          TEXT,
  indexed_at     TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE TABLE IF NOT EXISTS chunks (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,   -- also the ChromaDB id (as a string)
  document_id   INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  chunk_index   INTEGER NOT NULL,
  content       TEXT NOT NULL,
  start_char    INTEGER NOT NULL,
  end_char      INTEGER NOT NULL,
  UNIQUE (document_id, chunk_index)
);
-- AUTOINCREMENT is required: chunk ids must never be reused, otherwise a stale Chroma id
-- could collide with a newer chunk.

CREATE TABLE IF NOT EXISTS conversations (
  id          TEXT PRIMARY KEY,              -- UUID4
  title       TEXT NOT NULL,                 -- auto: first 60 chars of first question; renamable
  created_at  TEXT NOT NULL,
  updated_at  TEXT NOT NULL                  -- bumped on every new message; list order
);
CREATE INDEX IF NOT EXISTS idx_conversations_updated ON conversations(updated_at DESC);

CREATE TABLE IF NOT EXISTS messages (
  id               INTEGER PRIMARY KEY AUTOINCREMENT,
  conversation_id  TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
  role             TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
  content          TEXT NOT NULL,
  sources          TEXT,                     -- JSON: citations shown for an assistant message
  trace            TEXT,                     -- JSON: full retrieval + prompt trace (6.3), assistant messages only
  created_at       TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_messages_conv ON messages(conversation_id, id);

CREATE TABLE IF NOT EXISTS ingest_jobs (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  started_at      TEXT NOT NULL,
  finished_at     TEXT,
  state           TEXT NOT NULL CHECK (state IN ('running', 'done', 'failed', 'interrupted')),
  forced          INTEGER NOT NULL DEFAULT 0,
  source          TEXT NOT NULL CHECK (source IN ('api', 'cli')),
  files_total     INTEGER NOT NULL DEFAULT 0,
  files_done      INTEGER NOT NULL DEFAULT 0,
  files_failed    INTEGER NOT NULL DEFAULT 0,
  chunks_written  INTEGER NOT NULL DEFAULT 0,
  error           TEXT
);
-- At startup, any job still 'running' from a previous process is marked 'interrupted'.

CREATE TABLE IF NOT EXISTS settings (        -- saved runtime settings (6.5); only overridden keys are stored
  key         TEXT PRIMARY KEY,
  value       TEXT NOT NULL,                 -- JSON scalar
  updated_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS meta ( key TEXT PRIMARY KEY, value TEXT NOT NULL );
-- keys: embedding_model, embedding_dim, fts_tokenizer
```

**Full-text indexes (FTS5, external-content).** Created by code rather than `schema.sql`, because
the tokenizer is configurable. One index over chunks (retrieval), one over messages (history search):

```sql
CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
  content, content='chunks', content_rowid='id', tokenize='<FTS_TOKENIZER>'
);
CREATE TRIGGER IF NOT EXISTS chunks_ai AFTER INSERT ON chunks BEGIN
  INSERT INTO chunks_fts(rowid, content) VALUES (new.id, new.content);
END;
CREATE TRIGGER IF NOT EXISTS chunks_ad AFTER DELETE ON chunks BEGIN
  INSERT INTO chunks_fts(chunks_fts, rowid, content) VALUES ('delete', old.id, old.content);
END;

CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts USING fts5(
  content, content='messages', content_rowid='id', tokenize='<FTS_TOKENIZER>'
);
CREATE TRIGGER IF NOT EXISTS messages_ai AFTER INSERT ON messages BEGIN
  INSERT INTO messages_fts(rowid, content) VALUES (new.id, new.content);
END;
CREATE TRIGGER IF NOT EXISTS messages_ad AFTER DELETE ON messages BEGIN
  INSERT INTO messages_fts(messages_fts, rowid, content) VALUES ('delete', old.id, old.content);
END;
```

Chunks and messages are never updated in place (a changed document has its chunks deleted and
re-inserted; renaming a conversation touches only `conversations`), so no update triggers are
needed. Deleting a document cascades to its chunks, and deleting a conversation cascades to its
messages; those deletes fire the triggers. Tests must prove both FTS indexes have no rows left
after such deletions. `verify` also runs FTS5's `integrity-check` command on both.

### 5.2 ChromaDB

- One collection, named by the `CHROMA_COLLECTION` constant (`baby_rag_chunks`), configured for **cosine distance**.
- Items: `id = str(chunks.id)`, `embedding = <vector>`, `metadata = {document_id, path, chunk_index}`.
- **Always pass embeddings explicitly** and create the collection with no embedding function
  (`embedding_function=None` or the equivalent for your Chroma version), so Chroma never
  downloads or runs its own default embedding model.
- Do not duplicate chunk text in Chroma; SQLite holds it.
- Vector search must support an optional `document_id IN (...)` filter (Chroma `where`).

---

## 6. Backend behavior

### 6.1 Ingestion (MUST)
- Walk the corpus directory recursively for `*.txt` (case-insensitive). Document identity = relative path.
- Read as UTF-8 (accept a BOM). If decoding fails, fall back to cp1252 then latin-1 and log a warning.
- **Idempotent and incremental:** a document is skipped only if its `content_hash` **and** its
  stored `chunk_size` / `chunk_overlap` equal the current effective values; otherwise it is
  re-chunked and re-embedded (so changing chunk settings in the UI and pressing "Sync" re-chunks
  exactly the stale documents). **Delete** documents whose file no longer exists (from both
  stores). `force=true` re-indexes everything.
- **Chunking** (`services/chunking.py`, pure functions, heavily unit-tested): split on
  paragraphs, then sentences, then hard-cut at `chunk_size`; overlap of `chunk_overlap`
  characters; never emit empty chunks; keep `start_char`/`end_char` offsets into the original
  text; deterministic output.
- **Keeping the two stores consistent** (per document, SQLite is authoritative). Embedding is
  the slow and failure-prone step, so it happens **before** the write transaction is opened;
  this keeps SQLite's single write lock held only briefly, so chat persistence is never blocked
  by a long ingestion:
  1. chunk the text and embed the chunk texts (batched); nothing has been written yet;
  2. open a write transaction (`BEGIN IMMEDIATE`); remember the ids of the document's old
     chunks (if any), delete those rows, insert the new chunk rows and obtain their ids;
  3. upsert the vectors into Chroma with those ids;
  4. `COMMIT`;
  5. only after a successful commit, delete the *old* chunk ids of a replaced or removed
     document from Chroma.

  If step 1 fails, nothing was written. If step 2 or 3 fails, `ROLLBACK` (and delete any ids
  already written to Chroma). If step 4 fails, delete the ids written in step 3. Retrieval must
  ignore any Chroma id that has no SQLite row, so an interrupted run can never surface phantom
  results.
- Embed in batches of `EMBEDDING_BATCH_SIZE` (constant, 32) with retry and exponential backoff on 429/5xx and
  timeouts. One bad file marks that document `failed` with the error and does **not** abort the run.
- Only one ingestion runs at a time: an in-process lock, and `POST /api/ingest` answers 409 while
  one runs (the CLI cannot overlap with the server, see the server lock in section 4). Ingestion runs
  as a background task (in a worker thread, with its own connection). Every run is recorded in
  `ingest_jobs` and progress is exposed via `GET /api/ingest/status` (current or last job) and
  `GET /api/ingest/jobs` (history).
- **Corpus management from the web** (MUST): upload one or more `.txt` files
  (`POST /api/documents/upload`, stored under `corpus/uploads/`; sanitize the filename, reject
  path separators / `..`, non-`.txt`, empty files, and files over a size limit) and delete a document
  (`DELETE /api/documents/{id}` removes the file if it is inside the corpus directory and both stores'
  entries). Neither triggers ingestion by itself; the UI offers "Sync" right after.
- CLI: `python -m app.cli ingest [--force]`, `python -m app.cli reindex`,
  `python -m app.cli verify [--fix]` (compares SQLite chunk ids with Chroma ids and checks FTS
  integrity of both indexes, reports and, with `--fix`, removes orphans and re-embeds missing chunks).

### 6.2 Retrieval (MUST)

All parameters below come from the **effective settings** of 6.5 (request override > saved > registry default).

1. Embed the query with the embedding provider.
2. Vector search in Chroma: top `candidate_k` by cosine distance (similarity = `1 - distance`),
   restricted to `document_ids` when a filter is given. Fetch the matching rows from SQLite by
   id; drop ids with no row.
3. If `hybrid`: full-text search with FTS5, top `candidate_k`, ordered by `bm25(chunks_fts)`
   (lower is better), restricted by document when filtered (join on `chunks`):
   `SELECT rowid FROM chunks_fts WHERE chunks_fts MATCH ? ORDER BY bm25(chunks_fts) LIMIT ?`.
   FTS5 has no equivalent of `websearch_to_tsquery`, and raw user text can be an invalid FTS5
   query (quotes, `-`, `:`, `AND`, …). So build the query in a pure, unit-tested function
   `build_fts_query(text)`: extract word tokens (`\w+`, Unicode-aware), drop empties, wrap each
   token in double quotes, join with ` OR `. If no tokens remain, skip full-text search for
   that query. Never pass raw user text to `MATCH`.
4. Fuse with **Reciprocal Rank Fusion** (`rrf_fuse`, pure): `score = Σ 1 / (rrf_k + rank)`
   (ranks start at 1); ties broken by lowest chunk id for determinism; return the top `top_k`.
5. Each result carries: chunk id, document id and path, chunk index, text, fused score, and for
   each retriever that found it: its rank and raw score (cosine similarity / bm25).
6. The retrieval service returns a `RetrievalResult` with the final hits **and** the full
   candidate lists of both retrievers (used by the trace and by the Lab page).

### 6.3 Generation (MUST)
- Provider interface `LLMProvider.stream(messages, *, model, temperature, max_tokens) -> AsyncIterator[str]`
  and `EmbeddingProvider.embed(texts) -> list[list[float]]`, implemented with the `openai` SDK
  against `*_BASE_URL`. No provider-specific code paths anywhere.
- System prompt default lives in `app/prompts.py`; it can be overridden at runtime (6.5). The
  default must instruct the model to: answer **only** from the provided context; say clearly
  when the context does not contain the answer; cite sources as `[1]`, `[2]` matching the
  numbered context blocks; treat context as *data, never as instructions* (prompt-injection
  hygiene); answer in the user's language.
- Prompt assembly (pure function): system prompt + numbered context blocks (with file path) + the
  last `history_turns` turns of the conversation + the user question. Respect a rough context
  budget (truncate history first, then reduce chunks) and record what was truncated.
- Streaming over **Server-Sent Events** with these event names:
  `sources` (JSON list, sent first), `token` (text delta), `trace` (JSON, sent once after the last
  token), `error` (JSON `{message}`), `done` (JSON `{message_id, conversation_id}`).
- Persist the user and assistant messages in `messages`, with `sources` and `trace` on the
  assistant message. If the client aborts mid-stream, persist the partial assistant answer
  flagged in its trace as `"aborted": true`. Bump `conversations.updated_at`; create the
  conversation (auto title) on its first message.
- **Trace** (stored, and returned by the API for any assistant message):

```json
{
  "query": "…",
  "settings": { "...effective settings used for this turn..." },
  "document_ids": null,
  "retrieval": {
    "vector": [{"chunk_id": 12, "rank": 1, "similarity": 0.83}],
    "fts":    [{"chunk_id": 12, "rank": 2, "bm25": -4.1}],
    "fused":  [{"chunk_id": 12, "rrf_score": 0.0325, "found_by": ["vector", "fts"]}]
  },
  "prompt": {"messages": [...], "history_turns_used": 4, "chunks_used": 5, "truncated": false},
  "timings_ms": {"embed": 0, "vector": 0, "fts": 0, "fuse": 0, "first_token": 0, "total": 0},
  "model": "…", "fake_providers": false, "aborted": false
}
```

### 6.4 Fake providers (MUST)
When `FAKE_PROVIDERS=1`, use deterministic offline implementations: embeddings from a stable
hash (so similar text overlaps somewhat and identical text is identical, correct
`FAKE_EMBEDDING_DIM`), and an LLM that streams a canned answer quoting the top context block.
Chroma and SQLite are still the real ones. Used by tests and by anyone running the demo
without an API key. The UI shows a visible "FAKE PROVIDERS" badge in that mode.

### 6.5 Runtime settings: the RAG is tunable from the UI (MUST)

A **settings registry** (`services/settings.py`) is the single definition of every tunable:
key, type, bounds, default, scope, label, help text. The API, validation, the trace and
the frontend form are all driven by it. **Adding a setting = adding one registry entry.**

| Key | Type / bounds | Scope | Notes |
|---|---|---|---|
| `top_k` | int 1–50 | query | chunks sent to the LLM |
| `candidate_k` | int 1–200, ≥ `top_k` | query | candidates per retriever |
| `hybrid` | bool | query | false = vector only |
| `rrf_k` | int 1–1000 | query | |
| `history_turns` | int 0–20 | query | |
| `llm_model` | string, non-empty | query | model id sent to the chat endpoint; default = `LLM_MODEL` |
| `temperature` | float 0–2 | query | |
| `max_tokens` | int 16–8192 | query | |
| `system_prompt` | string ≤ 8000 chars | query | empty/absent = default from `prompts.py` |
| `chunk_size` | int 200–8000 | **index** | documents become "stale" until synced |
| `chunk_overlap` | int 0 to < `chunk_size` | **index** | same |
| `fts_tokenizer` | one of an allow-list | **index** | see below; applied immediately by rebuilding both FTS tables |

- **Scope `query`** settings take effect on the next request. **Scope `index`** settings change
  how data is stored: the UI must say so, and show how many documents are stale (indexed with
  other chunk parameters) with a one-click "Sync" (incremental ingest, 6.1).
- **`fts_tokenizer` allow-list:** `unicode61 remove_diacritics 2`,
  `porter unicode61 remove_diacritics 2`, `trigram`. Anything else is rejected. The value is
  interpolated into DDL, so it must never come from free text.
- **Defaults live in the registry (in code)**, not in `.env` (the one exception is `llm_model`,
  whose default is the required `LLM_MODEL`). Precedence:
  `per-request override` > `saved setting (SQLite)` > `registry default`.
- **Resolution** is a pure function: `resolve(registry_defaults, saved, request_overrides) ->
  EffectiveSettings` with cross-field validation. Endpoints, API keys, embedding model and
  dimension are **not** in the registry and cannot be changed from the UI.
- Saved settings live in the `settings` table (only keys that differ from the registry defaults). Every
  chat turn and search stores the effective settings it used in its trace, so any past answer
  can be reproduced and compared.
- `POST /api/search` and `POST /api/chat` accept an optional `overrides` object (same keys,
  `query` scope only) that applies to that request only and is never saved.

### 6.6 Conversation history (MUST)

History is a first-class feature backed by SQLite, not a side effect of chatting.
- Conversations and messages (with `sources` and `trace`) persist across restarts.
- **List + search:** `GET /api/conversations?q=&limit=&offset=` returns conversations ordered by
  `updated_at` desc. With `q`, matching uses `messages_fts` through the same `build_fts_query`,
  returns the conversations containing matches, each with up to 3 `matches`
  (`message_id`, `role`, `snippet` from FTS5 `snippet()` using plain `[[` `]]` markers, never HTML).
- **Rename:** `PATCH /api/conversations/{id}` `{ "title" }`.
- **Open:** `GET /api/conversations/{id}` returns all messages with sources and traces.
- **Export (SHOULD):** `GET /api/conversations/{id}/export` returns a JSON (or Markdown) file download.
- **Delete:** `DELETE /api/conversations/{id}` cascades to messages and to `messages_fts`.
- **Replay:** the trace contains everything needed to re-run a question with the same settings;
  the frontend uses it to prefill the Lab page (7).

### 6.7 API (MUST)

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/health` | liveness; SQLite and Chroma reachable; chunk counts match; embedding meta match; stale-document count; row counts (documents, chunks, conversations, messages); DB file size |
| GET | `/api/config` | redacted effective config (no keys), fake-mode flag |
| GET | `/api/settings` | registry + per-key `{value, default, source: default\|saved, scope, min, max, choices, label, help}` |
| PUT | `/api/settings` | partial update of saved settings, validated; returns the same payload as GET |
| DELETE | `/api/settings` | reset all saved settings (or `?key=` for one) |
| GET | `/api/documents` | list documents with status, chunk count, chunk params, stale flag, indexed_at |
| GET | `/api/documents/{id}` | one document |
| GET | `/api/documents/{id}/chunks` | its chunks (text + offsets) |
| GET | `/api/chunks/{id}` | one chunk with its document path |
| POST | `/api/documents/upload` | multipart `.txt` upload(s) into `corpus/uploads/` |
| DELETE | `/api/documents/{id}` | remove document (file, SQLite rows, Chroma vectors, FTS rows) |
| POST | `/api/chunking/preview` (SHOULD) | body `{ "text" \| "document_id", "chunk_size?", "chunk_overlap?" }` → chunks with offsets, nothing persisted |
| POST | `/api/ingest` | body `{ "force": false }` → starts a job; 409 if one is running |
| GET | `/api/ingest/status` | current/last job progress |
| GET | `/api/ingest/jobs` | job history from `ingest_jobs` |
| POST | `/api/search` | body `{ "query", "document_ids?", "overrides?" }` → fused hits **plus** both candidate lists (no LLM) |
| POST | `/api/chat` | body `{ "message", "conversation_id?", "document_ids?", "overrides?" }` → SSE stream |
| GET | `/api/conversations` | list / search (6.6) |
| GET | `/api/conversations/{id}` | messages with sources and traces |
| PATCH | `/api/conversations/{id}` | rename |
| GET | `/api/conversations/{id}/export` | download (SHOULD) |
| DELETE | `/api/conversations/{id}` | delete |

Auto-generated OpenAPI docs at `/docs`. Consistent JSON error shape
`{ "error": { "code", "message" } }`. Validate input with Pydantic; sensible limits
(message length, upload size, page size).

---

## 7. Frontend behavior (MUST unless noted)

Vue 3 + Vite + Pinia + Vue Router, responsive, following the layering of 3.4. Pages:

- **Chat:** compact conversation list (new, switch, delete); message list; input box;
  streaming answer rendered token by token; **citation chips `[1]`** that open a side panel
  showing the source file path and the exact chunk text; stop button (abort the stream);
  optional document filter; a per-message "inspect" action that opens that message's trace
  (candidates, scores, final prompt, timings); clear error and empty states.
- **History:** the window onto the database. Search box (full-text over all past messages with
  highlighted snippets), paginated list of conversations with dates and message counts, open a
  conversation read-only or continue it in Chat, rename, delete (with confirmation), export (SHOULD), and
  "Replay in Lab" on any question. Must show content persisted before the last restart.
- **Lab (RAG playground):** one screen to manipulate and inspect the pipeline without chatting:
  - a query box and a **schema-driven settings panel** generated from `GET /api/settings`
    (sliders/toggles/selects/text areas per registry entry; index-scope settings are visually
    separated and labelled as requiring a sync); "apply for this run only" vs "save";
  - **Search** mode (retrieval only): side-by-side columns *Vector candidates*, *Full-text
    candidates*, *Fused result*, each with rank, score and expandable chunk text; the
    `found_by` badges make the effect of `hybrid`, `rrf_k`, `candidate_k` visible;
  - **Ask** mode: same, plus the streamed answer and the exact prompt that was sent;
  - system-prompt editor with "reset to default";
  - **chunking preview (SHOULD):** pick a document or paste text, change size/overlap, see the resulting
    chunks and offsets before committing to a re-index;
  - document filter; "Replay" prefill from a history trace.
- **Corpus:** table of documents (path, status, chunks, chunk params, stale flag, indexed_at,
  error) with expandable chunk view; upload `.txt` files; delete a document; "Sync corpus" and
  "Force re-index" buttons; live progress from `/api/ingest/status` (polling); ingestion job
  history from `/api/ingest/jobs`.
- **Status:** health checks for SQLite and Chroma (including the chunk-count comparison, stale
  documents, and row counts per table), redacted effective config, "FAKE PROVIDERS" badge.

Also required:
- Render assistant answers as Markdown with `marked` and **sanitize with DOMPurify** (no raw
  HTML injection). Search snippets use the `[[ ]]` markers and are rendered as text + `<mark>`
  built by the frontend, never as injected HTML.
- Consume SSE with `fetch` + `ReadableStream` (POST body needed); handle the `trace` event.
- The frontend always calls the relative base `/api` (no frontend env variable). In development the Vite dev server proxies `/api` to `localhost:8000`; in production the backend serves the built UI from the same origin, so no CORS configuration exists anywhere.
- Component/unit tests with Vitest for: SSE parser, chat store, citation rendering, history search
  snippet rendering, settings form generation from the registry. (SHOULD)

### 7.1 Visual design: delegated to skills (no design is specified in this README)

Everything visual is the responsibility of the following skills, invoked **before** any
frontend markup or CSS is written, and applied to all pages above:

1. **`frontend-design`**: layout, aesthetic direction,
   component styling, quality bar for the UI.
2. **`theme-factory`** with the **Forest Canopy** theme: the **accent colours** only.
3. **`brand-guidelines`**: everything else it covers (base palette and neutrals, typography, brand rules).

Conflicts: Forest Canopy decides accent colours (primary actions, citation chips, links, active,
info and success states); `brand-guidelines` decides the rest of what it covers (backgrounds,
text, neutrals, typography); `frontend-design` decides layout and craft. Record any conflict and
how it was resolved in `docs/DECISIONS.md`.

Only structural constraints are imposed here, independent of the look: all colours, fonts and
spacing are CSS variables in a single `src/styles/theme.css` (no hard-coded values elsewhere);
states such as `failed` or error are conveyed with text or an icon, not colour alone; everything
is keyboard-reachable.

---

## 8. Repository layout

```
baby-rag/
├── README.md                 # this file
├── Makefile
├── .gitignore
├── corpus/                   # user's .txt files; 2-3 tiny sample-*.txt files are committed
├── data/                     # local runtime data (SQLite file, Chroma folder); git-ignored
├── docs/
│   ├── DECISIONS.md
│   └── ARCHITECTURE.md
├── scripts/
│   └── eval_retrieval.py         # SHOULD: hit@k over eval/questions.jsonl
├── eval/
│   └── questions.jsonl           # SHOULD: question + expected source path, matching samples
├── backend/
│   ├── .env.example          # the only env template; copy to backend/.env
│   ├── pyproject.toml
│   ├── app/
│   │   ├── main.py               # create_app(settings, paths): composition root
│   │   ├── config.py             # Settings (env, pydantic-settings) + AppPaths (code constants)
│   │   ├── prompts.py            # default system prompt
│   │   ├── cli.py
│   │   ├── api/
│   │   │   ├── deps.py           # FastAPI dependencies (DI)
│   │   │   ├── errors.py         # domain error -> JSON shape
│   │   │   ├── schemas.py        # Pydantic wire models
│   │   │   ├── sse.py
│   │   │   ├── static.py         # serves frontend/dist + SPA fallback when it exists
│   │   │   └── routers/          # health, settings, documents, ingest, search, chat, conversations
│   │   ├── services/
│   │   │   ├── chunking.py       # pure
│   │   │   ├── settings.py       # registry + pure resolve/validate
│   │   │   ├── ingest.py
│   │   │   ├── retrieval.py      # build_fts_query, rrf_fuse (pure) + orchestration
│   │   │   ├── rag.py            # prompt assembly (pure) + chat orchestration
│   │   │   ├── history.py        # conversations/messages use-cases
│   │   │   ├── vectorstore.py    # only module importing chromadb
│   │   │   └── providers/        # protocols, openai-compatible impls, fakes
│   │   └── db/                   # connection.py, schema.sql, fts.py, and plain-SQL modules:
│   │                             # documents.py, chunks.py, conversations.py, messages.py,
│   │                             # jobs.py, settings.py, meta.py
│   └── tests/                    # includes test_architecture.py
└── frontend/
    ├── package.json
    ├── vite.config.js        # dev proxy /api -> localhost:8000
    └── src/
        ├── main.js, App.vue
        ├── router/
        ├── api/              # only place that calls fetch: client.js, sse.js, one module per resource
        ├── stores/           # Pinia: chat, history, settings, corpus, status
        ├── styles/theme.css  # produced under the skills of 7.1
        ├── views/            # ChatView, HistoryView, LabView, CorpusView, StatusView
        └── components/       # presentational only
```

`.gitignore`: `backend/.env`, `node_modules`, `dist`, `__pycache__`, `.venv`, `data/`, `corpus/*.txt`
**except** `corpus/sample-*.txt`, and `corpus/uploads/`.

The corpus folder must be writable by the backend (UI uploads and deletes).

---

## 9. Makefile targets (MUST)

`make help` (default, lists targets) · `make install` (backend venv + frontend deps) ·
`make backend-dev` · `make frontend-dev` · `make build` (build the UI) ·
`make start` (build the UI if needed, then serve API + UI on one port) · `make ingest` ·
`make reindex` · `make verify` · `make test` (backend + frontend, including the architecture test) ·
`make lint` · `make fmt` · `make demo` (SHOULD: `FAKE_PROVIDERS=1`, sample corpus, ingest, start)

There is no `make migrate`, no `make up`/`down` and no service to start: the SQLite schema is applied
automatically at startup and Chroma runs embedded.

Ports: backend (and, with `make start`, the UI) 8000; Vite dev server 5173.

---

## 10. Testing (MUST)

- **Backend (pytest), runs offline** with `FAKE_PROVIDERS=1` against a real SQLite file in a
  temporary directory and a temporary Chroma persistent directory (no services required). Cover at minimum:
  - **architecture:** `test_architecture.py` enforcing the rules of 3.3 (dependency direction, import
    confinement, no SQL / prompt text in `api/`, no module-level singletons);
  - chunking (edge cases: empty file, one huge paragraph, unicode, exact-size boundaries);
  - ingestion (new, unchanged → skipped, modified → replaced in both stores, changed chunk
    settings → only stale docs re-chunked, deleted → removed from both stores including the FTS
    index, undecodable file → `failed`, job rows recorded, stale `running` job → `interrupted`);
  - **store consistency** (Chroma write failure rolls back SQLite; orphan Chroma ids are ignored
    by retrieval; `verify --fix` repairs drift; chunk ids are never reused after deletes);
  - retrieval (vector, full-text, fusion order and tie-break, vector-only mode, document filter,
    candidate lists present, `build_fts_query` with hostile input such as quotes, `-`, `:`,
    `AND`, empty string and non-Latin text);
  - **settings** (registry validation and bounds, resolution precedence request > saved > env,
    cross-field rules, tokenizer allow-list rejects injection attempts, tokenizer change rebuilds
    both FTS tables, index-scope change marks documents stale, overrides are not persisted);
  - **history** (conversation and messages survive re-opening the app on the same DB file; search
    via `messages_fts` with hostile input; snippets; rename; export (SHOULD); deleting a conversation
    leaves no rows in `messages` or `messages_fts`; partial answer persisted on abort);
  - corpus management (upload accepts `.txt`, rejects traversal / wrong extension / oversize /
    empty; delete removes file, rows, vectors and FTS entries);
  - chat SSE event sequence (`sources` → `token`* → `trace` → `done`) and trace content;
  - config: missing required variables produce one readable error; optional defaults apply; `FAKE_PROVIDERS=1` waives the six required variables; the `.env` path and `AppPaths` are independent of the cwd; tests inject a temporary `AppPaths`; embedding-model and dimension mismatch guard; `EMBEDDING_DIM` set → `dimensions` sent in the request and length checked, unset → not sent (verified with a mock HTTP transport); schema-version guard; API error shapes;
  - **server lock:** the CLI refuses with the documented message while the lock is held; a second server refuses to start;
  - `VectorStore` and provider contract tests run against every implementation.
- **Frontend (Vitest):** see section 7.
- **CI (SHOULD):** a GitHub Actions workflow running lint + both test suites. No services are needed.

---

## 11. Running locally

Local processes are the only supported path.
- SQLite is a file (`data/babyrag.db`, created on first start) and Chroma runs **embedded** (folder
  `data/chroma`), so no extra service or install step is needed.
- **Development:** `make backend-dev` (port 8000) and `make frontend-dev` (port 5173, proxies `/api`).
- **Single-process run:** `make start` builds the UI and serves it, together with the API, from
  Uvicorn on port 8000 (one worker). SSE needs no proxy tuning since there is no proxy.
- `make test` works with no `.env` at all.
- **Server or CLI, never both:** `make ingest`, `make reindex` and `make verify` require the server to
  be stopped (enforced by the server lock of section 4). While the server runs, use the "Sync corpus"
  and "Force re-index" buttons in the UI.

---

## 12. Build phases

1. **Skeleton:** repo layout, Makefile, `backend/.env.example`, config (required/optional rules of section 4), SQLite connection helper + schema, Chroma wrapper, `create_app` + DI wiring, `/api/health`, `test_architecture.py` (green from the first commit and kept green), `docs/ARCHITECTURE.md` first draft.
2. **Ingestion:** chunking, providers (real + fake), incremental ingest with the two-store consistency protocol, FTS5 index, job history, upload/delete, CLI (`ingest`, `reindex`, `verify`), tests.
3. **Settings + retrieval + chat + history:** settings registry and resolution, hybrid retrieval with candidate lists and document filter, prompts, SSE chat with traces, persistence, `messages_fts`, conversation search/rename/delete (export: SHOULD), tests.
4. **Frontend:** invoke the skills of 7.1 first; then the five pages (Chat, History, Lab, Corpus, Status), SSE client, citations panel, trace inspector, schema-driven settings panel, sanitization, tests.
5. **Single-process run:** static mount of the built UI, `make build` / `make start` verified end to end on one port.
6. **Polish:** finish `docs/ARCHITECTURE.md` and `docs/DECISIONS.md`, eval script, CI, lint clean, walk through the three demo paths of 1.1 and record them.
7. **STRETCH:** reranking hook (a new `Reranker` protocol applied after fusion, toggled by a setting), side-by-side comparison of two settings profiles in the Lab.

---

## 13. Definition of done and status

The project is done when **all MUST items** below are true and demonstrated by commands you ran.

**MUST**
- [ ] `make start` → UI reachable on http://localhost:8000, `/api/health` all green (SQLite and Chroma)
- [ ] **Minimal config:** the app starts with only the six required variables in `backend/.env` (or with only `FAKE_PROVIDERS=1`); every optional variable has a default defined in code, and no path or log level is an environment variable
- [ ] `make ingest` indexes `corpus/`; re-running it skips unchanged files; edits and deletions are reflected in **both** stores (and in the FTS index)
- [ ] Chat streams an answer with clickable citations to the exact source chunk
- [ ] **Trinity / history:** a conversation survives a backend restart; History page lists it, finds it by a word from an old message, shows its sources and trace, and can rename and delete it
- [ ] **Architecture:** `test_architecture.py` passes; `docs/ARCHITECTURE.md` exists with the walkthroughs and "how do I add…" recipes
- [ ] **Manipulable from the UI:** in the Lab page, changing `top_k`, `hybrid`, `rrf_k`, the document filter and the system prompt visibly changes retrieval and/or the answer without restart; upload and delete of a `.txt` work from the Corpus page
- [ ] Every chat turn stores its effective settings and candidate lists in the trace, viewable in the UI
- [ ] Works with `FAKE_PROVIDERS=1` and no API key; works with a real OpenAI-compatible endpoint via `.env` only
- [ ] Embedding model/dimension change is detected and `make reindex` recreates the Chroma collection
- [ ] `make verify` detects and `--fix` repairs SQLite/Chroma drift
- [ ] `make test` passes offline; `make lint` is clean
- [ ] No secret in git; `backend/.env.example` documents every variable
- [ ] Assistant Markdown and history snippets are sanitized in the UI
- [ ] Visual design produced through the skills of 7.1 (or the fallback recorded in `docs/DECISIONS.md`)
- [ ] No ORM or migration dependency: only stdlib `sqlite3` for SQL access

**SHOULD**
- [ ] Vitest tests · [ ] CI workflow · [ ] `eval_retrieval.py` with sample questions · [ ] consistent error shapes and input limits · [ ] `docs/DECISIONS.md` filled in · [ ] type checker clean · [ ] `make demo` · [ ] conversation export · [ ] chunking preview (endpoint + Lab panel)

**STRETCH**
- [ ] reranking hook · [ ] settings-profile comparison in the Lab

### Status (the building agent fills this in at the end)

- Done:
- Not done / not verified:
- How it was verified (commands run, results), including the three demo paths of section 1.1:
- Known issues and next steps:

---

## 14. Quickstart (the building agent completes and verifies this section)

```bash
make install
cp backend/.env.example backend/.env   # set the 6 required variables, or use FAKE_PROVIDERS=1 to try it offline
# put your .txt files in ./corpus (or upload them from the Corpus page)
make start                             # http://localhost:8000, then press "Sync corpus" (or stop the server first and run `make ingest`)
```