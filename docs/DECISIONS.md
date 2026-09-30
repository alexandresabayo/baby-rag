# Decisions and deviations

One line per decision: what was chosen and why. Deviations from the README spec are
marked **deviation**.

1. **Chunk offsets are computed against newline-normalized text** (`\r\n`/`\r` → `\n`),
   because the spec normalizes decoding but not line endings; offsets stay exact for
   Unix and Windows files alike.
2. **Fallback decoding (cp1252 → latin-1) means files rarely fail to decode**: latin-1
   accepts any byte sequence, so an "undecodable" file is indexed via fallback with a
   warning rather than marked `failed`. The `failed` status still exists for genuinely
   broken files (e.g. unreadable, empty of text).
3. **Ingestion progress is a module-level job object**, not a DB table: single-process
   Uvicorn keeps it in memory; the cross-process file lock (`<db>.ingest.lock`, `fcntl`
   where available) prevents CLI/API overlap.
4. **Chroma `embedding_function=None`** with explicit embeddings, per spec; tested
   against chromadb 1.5.x client API (`get_or_create_collection`, `upsert`, `query`).
5. **`FAKE_PROVIDERS` accepts 1/true/yes/on** and is also read directly from the env
   var so tests and Docker can toggle it without a `.env` file.
6. **Persistent-mode caveat (deviation, documented)**: with `CHROMA_MODE=persistent`
   the embedded store must be opened by one process at a time. The CLI refuses nothing,
   but the safe path is: stop the backend before `make ingest`/`reindex`/`verify`, or
   use the "Sync corpus" button in the UI (which runs ingestion inside the backend
   process). This is the exact behavior recommended by the spec; recorded here as the
   spec asks.
7. **CORS**: read once at startup from settings; the Vite dev proxy and nginx handle
   it in dev/prod, CORS_ORIGINS covers direct-access cases.
8. **`/api/chat` SSE `done` event** also returns `conversation_id` so the UI can
   continue an existing conversation after the first turn.
9. **Sandbox has no Docker**: the no-Docker path (section 11) is the verified one;
   Compose files are provided and follow the spec but were not executed end-to-end.
10. **Frontend typeface self-hosting** via `@fontsource/*` packages per spec; no
    external font CDN requests.
11. **Backend dev environment**: a repo-root `.venv` is used in this sandbox; the
    Makefile falls back to `python3`/`uv` when absent.
12. **Chunk-id reuse guard**: SQLite `AUTOINCREMENT` on `chunks` guarantees ids are
    never reused after deletes; a test proves it.
13. **Eval questions** cover the three committed sample files only, so
    `scripts/eval_retrieval.py` runs against a fresh ingest of `corpus/`.
