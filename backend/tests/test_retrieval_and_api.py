import asyncio
import json
import os

import pytest

from app.db import queries
from app.services import ingest as ingest_mod
from app.services.providers import FakeEmbedding
from app.services.retrieval import build_fts_query, fuse_rrf, retrieve


async def ingest(settings, store, force=False):
    return await ingest_mod.run_ingest(settings, store, FakeEmbedding(settings), force)


def write_file(corpus_dir, name, content):
    (corpus_dir / name).write_text(content, encoding="utf-8")


# ---- build_fts_query ----

@pytest.mark.parametrize("raw,expected", [
    ('hello world', '"hello" OR "world"'),
    ('"quoted" -minus:and AND', '"quoted" OR "minus" OR "and" OR "AND"'),
    ('', ''),
    ('   ', ''),
    ('!!!"', ''),
    ('привет мир', '"привет" OR "мир"'),
    ('café résumé', '"café" OR "résumé"'),
    ('a b a b', '"a" OR "b"'),
])
def test_build_fts_query(raw, expected):
    assert build_fts_query(raw) == expected


def test_fuse_rrf_order():
    a = fuse_rrf([[1, 2], [2, 3]], 60, 5)
    assert a[0]["chunk_id"] == 2  # found first-ish by both
    assert set(a[0]["retrievers"]) == {"fts", "vector"}


def test_fuse_rrf_vector_only():
    a = fuse_rrf([[5, 6], []], 60, 5)
    assert [x["chunk_id"] for x in a] == [5, 6]
    assert all(x["retrievers"] == ["vector"] for x in a)


# ---- retrieval through real stores ----

async def do_retrieve(settings, conn, store, query, top_k=None):
    return await retrieve(settings, conn, store, FakeEmbedding(settings), query, top_k)


async def test_vector_retrieval(settings, conn, store):
    write_file(settings.corpus_dir, "doc.txt",
               "The quick brown fox jumps over the lazy dog. " * 10)
    await ingest(settings, store)
    res = await do_retrieve(settings, conn, store, "quick brown fox")
    assert len(res) > 0
    assert res[0]["path"] == "doc.txt"
    assert "fox" in res[0]["text"]


async def test_hybrid_retrieval(settings, conn, store):
    write_file(settings.corpus_dir, "coffee.txt", "Coffee originated in Ethiopia. " * 5)
    write_file(settings.corpus_dir, "bikes.txt", "Bicycles were invented in Germany. " * 5)
    await ingest(settings, store)
    res = await do_retrieve(settings, conn, store, "coffee Ethiopia")
    assert res[0]["path"] == "coffee.txt"
    assert "vector" in res[0]["retrievers"] or "fts" in res[0]["retrievers"]


async def test_vector_only_mode(settings, conn, store, monkeypatch):
    monkeypatch.setattr(settings, "hybrid", False)
    write_file(settings.corpus_dir, "doc.txt", "Unique zebra stripe patterns. " * 10)
    await ingest(settings, store)
    res = await do_retrieve(settings, conn, store, "zebra")
    assert len(res) > 0


async def test_orphan_chroma_ids_ignored(settings, conn, store):
    write_file(settings.corpus_dir, "doc.txt", "Elephants never forget anything. " * 10)
    await ingest(settings, store)
    store.upsert(["999999"], [[0.1] * 32], [{"document_id": 1, "path": "x", "chunk_index": 0}])
    res = await do_retrieve(settings, conn, store, "elephants")
    assert all(r["chunk_id"] != 999999 for r in res)


async def test_top_k_limit(settings, conn, store):
    write_file(settings.corpus_dir, "doc.txt", "Alpha beta gamma delta epsilon. " * 50)
    await ingest(settings, store)
    res = await do_retrieve(settings, conn, store, "alpha beta", top_k=2)
    assert len(res) <= 2


# ---- SSE chat ----

async def test_chat_sse_event_sequence(settings, conn, store):
    write_file(settings.corpus_dir, "doc.txt", "Paris is the capital of France. " * 10)
    await ingest(settings, store)
    from app.services.rag import chat_stream

    events = []
    async for ev in chat_stream(settings, "What is the capital of France?", None, None):
        events.append(ev)
    names = [e["event"] for e in events]
    assert names[0] == "sources"
    assert names[-1] == "done"
    assert "token" in names
    assert "error" not in names
    assert events[-1]["data"]["conversation_id"]


async def test_chat_persists_messages(settings, conn, store):
    write_file(settings.corpus_dir, "doc.txt", "The sky is blue. " * 10)
    await ingest(settings, store)
    from app.services.rag import chat_stream

    conv_id = None
    async for ev in chat_stream(settings, "What colour is the sky?", None, None):
        if ev["event"] == "done":
            conv_id = ev["data"]["conversation_id"]
    conv = queries.get_conversation(conn, conv_id)
    assert conv is not None
    msgs = queries.list_messages(conn, conv_id)
    assert [m["role"] for m in msgs] == ["user", "assistant"]
    assert msgs[1]["sources"] is not None
    assert len(json.loads(msgs[1]["sources"])) > 0


async def test_chat_existing_conversation(settings, conn, store):
    write_file(settings.corpus_dir, "doc.txt", "Water boils at 100 degrees. " * 10)
    await ingest(settings, store)
    from app.services.rag import chat_stream

    conv_id = None
    async for ev in chat_stream(settings, "Boiling point of water?", None, None):
        if ev["event"] == "done":
            conv_id = ev["data"]["conversation_id"]
    async for ev in chat_stream(settings, "And freezing?", conv_id, None):
        pass
    assert queries.count_messages(conn, conv_id) == 4


# ---- embedding guard ----

async def test_embedding_mismatch_guard(settings, conn, store):
    write_file(settings.corpus_dir, "doc.txt", "Some content here. " * 5)
    await ingest(settings, store)
    ok, msg = ingest_mod.check_embedding_guard(conn, settings)
    assert ok
    settings.embedding_model = "other-model"
    ok, msg = ingest_mod.check_embedding_guard(conn, settings)
    assert not ok and "reindex" in msg


def test_tokenizer_change_rebuilds_fts(settings, conn):
    from app.db.fts import ensure_fts_tokenizer
    write_file(settings.corpus_dir, "doc.txt", "Running quickly jumps higher. " * 5)
    # simulate stored tokenizer change
    queries.set_meta(conn, "fts_tokenizer", "porter unicode61 remove_diacritics 2")
    settings.fts_tokenizer = "porter unicode61 remove_diacritics 2"
    ensure_fts_tokenizer(conn, settings)
    tok = queries.get_meta(conn, "fts_tokenizer")
    assert tok == "porter unicode61 remove_diacritics 2"


def store_obj(conn):
    return None


def test_schema_version_guard(settings, conn):
    conn.execute("PRAGMA user_version = 99")
    from app.db.connection import SCHEMA_VERSION, init_schema
    try:
        init_schema(conn)
        assert False
    except RuntimeError as e:
        assert "newer" in str(e)
    conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")


# ---- config ----

def test_config_invalid_chroma_mode(monkeypatch, tmp_path):
    monkeypatch.setenv("FAKE_PROVIDERS", "1")
    monkeypatch.setenv("CHROMA_MODE", "bogus")
    from app.config import Settings
    try:
        Settings()
        assert False
    except Exception:
        pass


def test_config_overlap_validation(monkeypatch):
    monkeypatch.setenv("FAKE_PROVIDERS", "1")
    monkeypatch.setenv("CHUNK_SIZE", "100")
    monkeypatch.setenv("CHUNK_OVERLAP", "100")
    from app.config import Settings
    try:
        Settings()
        assert False
    except Exception:
        pass


def test_fake_embedding_deterministic_and_dim(settings):
    e1 = asyncio.run(FakeEmbedding(settings).embed(["hello world"]))
    e2 = asyncio.run(FakeEmbedding(settings).embed(["hello world"]))
    assert e1 == e2
    assert len(e1[0]) == settings.embedding_dim
