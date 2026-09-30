# Testing guide for baby-rag

This guide verifies everything the build agent ran, from scratch, on a clean machine.
The only requirements are **Python 3.12** and **Node.js 22** — every command runs fully
offline with `FAKE_PROVIDERS=1`, so no API key is needed.

You can test either from the PR branch directly, or by applying `baby-rag.patch`
(see "Testing from the patch" at the end).

---

## 0. Setup

```bash
git clone https://github.com/alexandresabayo/baby-rag
cd baby-rag
git checkout vibe/build-baby-rag-app   # or apply baby-rag.patch (see bottom)

cp .env.example .env
# for the offline path, set in .env:
#   FAKE_PROVIDERS=1
#   EMBEDDING_DIM=1024

python3 -m venv .venv
.venv/bin/pip install -e "backend[dev]"

cd frontend && npm install && cd ..
```

> Why `FAKE_PROVIDERS=1`? It swaps the LLM and embedding providers for deterministic
> offline fakes (hash-based embeddings, canned LLM answers). SQLite, Chroma, FTS5 and
> the whole two-store machinery stay real. To test with a real provider later, put real
> keys in `.env` and set `FAKE_PROVIDERS=0` — nothing else changes.

---

## 1. Unit tests (must be green, offline)

```bash
# Backend: 54 tests
cd backend && FAKE_PROVIDERS=1 ../.venv/bin/python -m pytest tests/ -q
# expected: "54 passed"

# Frontend: 14 tests
cd ../frontend && npm test
# expected: "Test Files 3 passed, Tests 14 passed"
cd ..
```

What these cover:

| Area | Proven by |
|---|---|
| Chunking | empty file, huge paragraph, unicode, exact-size boundary, overlap, determinism, exact offsets into the original text |
| Ingestion | new file, unchanged → skipped, modified → replaced in **both** stores, deleted → removed from both stores **and the FTS index**, force re-index, subdirectories, undecodable bytes |
| Store consistency | Chroma write failure → SQLite rolled back, orphan Chroma ids ignored by retrieval, chunk ids never reused after deletes |
| Retrieval | vector search, hybrid search, vector-only mode, RRF fusion order, `build_fts_query` against quotes / `-` / `:` / `AND` / empty / non-Latin input, top-k limit |
| Chat | SSE event sequence `sources → token* → done`, message persistence with sources, multi-turn conversation continuity |
| Guards | embedding model/dimension mismatch, tokenizer change rebuilds FTS, newer schema version refuses to start, config validation |
| API | error shapes `{"error": {code, message}}`, 404s, 409 on concurrent ingest, input limits, redacted `/api/config` |
| CLI | `verify` detects drift, `verify --fix` repairs it, `reindex` recreates the collection |
| Frontend | SSE parser (tokens, JSON events, multiline data, comments), chat store (streaming, errors, conversation ids), citation chips, XSS sanitization |

## 2. Lint and build

```bash
cd backend && ../.venv/bin/ruff check app        # expected: "All checks passed!"
cd ../frontend
npx eslint src                                  # expected: "0 errors"
npm run build                                   # expected: "✓ built in ...s"
cd ..
```

---

## 3. Live end-to-end test (the interesting part)

Run the backend and exercise the real API. In one terminal:

```bash
make backend-dev          # serves http://localhost:8000
```

In a second terminal, run through the flow:

```bash
BASE=http://localhost:8000

# 3.1 Ingest the corpus via the API
curl -s -X POST $BASE/api/ingest -H 'content-type: application/json' -d '{"force": false}'
curl -s $BASE/api/ingest/status
# expected: {"state":"done","total":3,"done":3,"failed":0,"chunks_written":12,...}

# 3.2 Health: SQLite and Chroma counts must match
curl -s $BASE/api/health
# expected: "status":"ok", "counts_match":true

# 3.3 Documents are listed
curl -s $BASE/api/documents
# expected: 3 documents, status "indexed"

# 3.4 Hybrid search (no LLM involved)
curl -s -X POST $BASE/api/search -H 'content-type: application/json' \
  -d '{"query":"who invented the pneumatic tyre"}'
# expected: top result path "sample-bicycles.txt", "retrievers":["fts","vector"]

# 3.5 Streaming chat over SSE
curl -s -N -X POST $BASE/api/chat -H 'content-type: application/json' \
  -d '{"message":"Who built the lighthouse of Alexandria?"}'
# expected event sequence: first "event: sources" (JSON with paths + chunk texts),
# then many "event: token" lines, finally "event: done" with a conversation_id.

# 3.6 The conversation was persisted with its sources
curl -s $BASE/api/conversations | python3 -m json.tool     # note the id
curl -s $BASE/api/conversations/<id> | python3 -m json.tool
# expected: 2 messages (user + assistant), assistant has "sources" with paths

# 3.7 Validation and error shapes
curl -s -X POST $BASE/api/search -H 'content-type: application/json' -d '{"query":""}'
# expected: 422 {"error":{"code":"validation_error",...}}
```

Then point your browser at the UI:

```bash
make frontend-dev         # http://localhost:5173 (proxies /api to :8000)
```

Checklist in the browser:

- [ ] **Chat**: ask "Where was coffee discovered?" — the answer streams token by token,
      orange chips `[1] [2] …` appear under it; clicking one opens a side panel with the
      exact file path and chunk text.
- [ ] **Stop button** aborts a stream mid-answer.
- [ ] **New chat / delete** work in the sidebar; reopening a conversation shows history
      with its citations.
- [ ] **Corpus page**: shows 3 documents; edit a file in `corpus/`, click "Sync corpus",
      watch the live progress, then refresh — the chunk count changes.
- [ ] **Settings page**: all health rows green (SQLite, Chroma, counts match), the
      redacted config is shown, and the blue "FAKE PROVIDERS" badge is visible
      (also in the sidebar on every page).
- [ ] Dark mode follows your OS setting; no raw HTML renders in answers
      (assistant content is sanitized).

## 4. Ingestion edge cases (the spec's core promise)

With the backend stopped (important: the embedded Chroma store must be opened by one
process at a time):

```bash
cd backend

# 4.1 Idempotency: re-run skips unchanged files (chunks written = 0)
../.venv/bin/python -m app.cli ingest

# 4.2 Modify a file, re-ingest: it is re-chunked in both stores
echo "extra line" >> ../corpus/sample-coffee.txt
../.venv/bin/python -m app.cli ingest    # chunks_written > 0 for that file

# 4.3 Delete a file, re-ingest: gone from both stores and the FTS index
rm ../corpus/sample-coffee.txt
../.venv/bin/python -m app.cli ingest

# 4.4 Consistency check
../.venv/bin/python -m app.cli verify    # expected: "OK"

# 4.5 Drift repair: stop everything, delete the Chroma folder, then
../.venv/bin/python -m app.cli verify --fix   # re-embeds missing chunks
../.venv/bin/python -m app.cli verify         # "OK" again

# 4.6 Reindex from scratch (as required after an embedding-model change)
../.venv/bin/python -m app.cli reindex
```

Restore the sample afterwards: `git checkout -- corpus/` then re-run ingest.

## 5. Retrieval quality

With the backend running again:

```bash
../.venv/bin/python ../scripts/eval_retrieval.py --api http://localhost:8000
# expected: 6 lines, each "hit", and "hit@3: 6/6 = 100.0%"
```

## 6. Docker path (if you have Docker)

```bash
make up        # http://localhost:8080 (frontend), 8000 (API), 8001 (Chroma)
# then use "Sync corpus" in the UI, or: docker compose exec backend python -m app.cli ingest
make down
```

Note: this path was not executed in the build sandbox (no Docker available); the
no-Docker path above is the fully verified one.

---

## Testing from the patch

`baby-rag.patch` at the branch root contains the whole change as a plain diff
(~8000 lines, the zip binary excluded). On a checkout of `main`:

```bash
git apply --check baby-rag.patch   # dry-run first
git apply baby-rag.patch
```

Then follow the guide from section 0's install steps (skip the checkout line).

## Quick expected-results summary

| Check | Expected |
|---|---|
| Backend tests | 54 passed |
| Frontend tests | 14 passed |
| `ruff check app` | All checks passed |
| `eslint src` | 0 errors |
| `vite build` | ✓ built |
| `ingest` on sample corpus | 3 files, 12 chunks |
| Re-run `ingest` | chunks_written = 0 (skipped) |
| `verify` | OK |
| `/api/health` | status ok, counts_match true |
| Chat SSE | sources → tokens → done |
| Retrieval eval | hit@3 = 6/6 |
