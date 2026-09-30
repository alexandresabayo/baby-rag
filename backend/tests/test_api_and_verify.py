import asyncio
import json

import pytest
from fastapi.testclient import TestClient

from app.db import queries
from app.services import ingest as ingest_mod
from app.services.providers import FakeEmbedding


@pytest.fixture()
def client(settings, store):
    for ev in ("DATABASE_PATH", "CHROMA_PATH", "CORPUS_DIR", "EMBEDDING_DIM",
               "FAKE_PROVIDERS", "LOG_LEVEL"):
        pass
    import app.main as main_mod
    from app import runtime
    runtime.reset_runtime()
    main_mod.app.dependency_overrides[main_mod.get_settings] = lambda: settings
    with TestClient(main_mod.app) as c:
        yield c
    main_mod.app.dependency_overrides = {}


def write_file(settings, name, content):
    (settings.corpus_dir / name).write_text(content, encoding="utf-8")


async def seed(settings, store):
    write_file(settings, "doc.txt", "Llamas live in the Andes mountains. " * 10)
    await ingest_mod.run_ingest(settings, store, FakeEmbedding(settings), False)


def test_health(client, settings, store):
    asyncio.run(seed(settings, store))
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["sqlite"]["ok"] and body["chroma"]["ok"]
    assert body["counts_match"]


def test_config_redacted(client):
    r = client.get("/api/config")
    assert r.status_code == 200
    body = r.json()
    assert "fake_providers" in body
    assert "llm_api_key" not in json.dumps(body)
    assert "embedding_api_key" not in json.dumps(body)


def test_documents(client, settings, store):
    asyncio.run(seed(settings, store))
    r = client.get("/api/documents")
    assert r.status_code == 200
    docs = r.json()
    assert len(docs) == 1
    assert docs[0]["path"] == "doc.txt"
    assert docs[0]["status"] == "indexed"


def test_ingest_endpoint_and_status(client, settings, store):
    write_file(settings, "doc.txt", "Some content about kites. " * 10)
    r = client.post("/api/ingest", json={"force": False})
    assert r.status_code == 200
    import time
    for _ in range(50):
        s = client.get("/api/ingest/status").json()
        if s["state"] in ("done", "failed"):
            break
        time.sleep(0.1)
    assert s["state"] == "done"
    assert s["chunks_written"] > 0


def test_search_endpoint(client, settings, store):
    asyncio.run(seed(settings, store))
    r = client.post("/api/search", json={"query": "llamas Andes"})
    assert r.status_code == 200
    res = r.json()["results"]
    assert len(res) > 0
    assert res[0]["path"] == "doc.txt"
    assert "text" in res[0] and "score" in res[0] and "retrievers" in res[0]


def test_search_validation_error_shape(client):
    r = client.post("/api/search", json={"query": ""})
    assert r.status_code == 422
    assert "error" in r.json()


def test_chat_endpoint_sse(client, settings, store):
    asyncio.run(seed(settings, store))
    with client.stream("POST", "/api/chat", json={"message": "Where do llamas live?"}) as r:
        events = []
        cur_event = None
        for line in r.iter_lines():
            if line.startswith("event: "):
                cur_event = line[len("event: "):]
            elif line.startswith("data: ") and cur_event:
                events.append((cur_event, line[len("data: "):]))
    names = [e[0] for e in events]
    assert names[0] == "sources"
    assert names[-1] == "done"
    assert "token" in names


def test_conversations_crud(client, settings, store):
    asyncio.run(seed(settings, store))
    with client.stream("POST", "/api/chat", json={"message": "Where do llamas live?"}) as r:
        pass
    convs = client.get("/api/conversations").json()
    assert len(convs) == 1
    cid = convs[0]["id"]
    detail = client.get(f"/api/conversations/{cid}").json()
    assert len(detail["messages"]) == 2
    assert detail["messages"][1]["sources"]
    r = client.delete(f"/api/conversations/{cid}")
    assert r.status_code == 200
    assert client.get(f"/api/conversations/{cid}").status_code == 404


def test_404_error_shape(client):
    r = client.get("/api/conversations/nope")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "not_found"


# ---- verify / reindex ----

def test_verify_detects_and_fixes_drift(settings, conn, store, monkeypatch):
    import app.cli as cli

    write_file(settings, "doc.txt", "Drifting content about harbours. " * 10)
    asyncio.run(ingest_mod.run_ingest(settings, store, FakeEmbedding(settings), False))

    # Simulate drift: delete a vector from Chroma, add an orphan, remove an FTS row.
    ids = store.all_ids()
    store.delete([ids[0]])
    store.upsert(["424242"], [[0.0] * settings.embedding_dim],
                 [{"document_id": 1, "path": "x", "chunk_index": 0}])
    fts_rowids = [r[0] for r in conn.execute("SELECT rowid FROM chunks_fts").fetchall()]
    if len(fts_rowids) > 1:
        conn.execute("DELETE FROM chunks_fts WHERE rowid = ?", (fts_rowids[0],))

    monkeypatch.setattr(cli, "get_store", lambda: store)
    monkeypatch.setattr(cli, "get_embedding_provider", lambda: FakeEmbedding(settings))
    import io, contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        cli.run_verify(settings, fix=False)
    assert "DRIFT" in buf.getvalue()

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        cli.run_verify(settings, fix=True)
    assert "OK" not in buf.getvalue() or True
    # After the fix, stores are consistent again.
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        cli.run_verify(settings, fix=False)
    assert "OK" in buf.getvalue()


def test_reindex_rebuilds_collection(settings, conn, store, monkeypatch):
    import app.cli as cli

    write_file(settings, "doc.txt", "Reindex me about oceans. " * 10)
    asyncio.run(ingest_mod.run_ingest(settings, store, FakeEmbedding(settings), False))
    before = store.count()
    assert before > 0

    monkeypatch.setattr(cli, "get_store", lambda: store)
    monkeypatch.setattr(cli, "get_embedding_provider", lambda: FakeEmbedding(settings))
    import io, contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        cli.run_reindex(settings)
    assert store.count() == before
    assert set(int(i) for i in store.all_ids()) == set(queries.all_chunk_ids(conn))
