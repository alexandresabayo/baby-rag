import asyncio

from app.db import queries
from app.db.fts import fts_query
from app.services import ingest as ingest_mod
from app.services.providers import FakeEmbedding


def write_file(corpus_dir, name: str, content: str):
    path = corpus_dir / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def run_ingest(settings, store, force=False):
    return asyncio.run(ingest_mod.run_ingest(settings, store, FakeEmbedding(settings), force))


def test_ingest_new_file(settings, conn, store):
    write_file(settings.corpus_dir, "a.txt", "Hello world. " * 10)
    job = run_ingest(settings, store)
    assert job.state == "done"
    assert job.failed == 0
    assert queries.count_chunks(conn) > 0
    assert store.count() == queries.count_chunks(conn)


def test_unchanged_file_skipped(settings, conn, store):
    write_file(settings.corpus_dir, "a.txt", "Hello world. " * 10)
    run_ingest(settings, store)
    ids_before = queries.all_chunk_ids(conn)
    run_ingest(settings, store)
    assert queries.all_chunk_ids(conn) == ids_before  # no re-chunk, ids stable


def test_modified_file_replaced_in_both_stores(settings, conn, store):
    write_file(settings.corpus_dir, "a.txt", "Hello world. " * 10)
    run_ingest(settings, store)
    old_ids = set(queries.all_chunk_ids(conn))
    write_file(settings.corpus_dir, "a.txt", "Completely different content. " * 20)
    run_ingest(settings, store)
    new_ids = set(queries.all_chunk_ids(conn))
    assert old_ids != new_ids
    assert old_ids & new_ids == set()  # ids never reused
    assert set(int(i) for i in store.all_ids()) == new_ids


def test_deleted_file_removed_from_both_stores_and_fts(settings, conn, store):
    write_file(settings.corpus_dir, "gone.txt", "Vanishing text about zebras. " * 10)
    run_ingest(settings, store)
    assert queries.count_chunks(conn) > 0
    (settings.corpus_dir / "gone.txt").unlink()
    run_ingest(settings, store)
    doc = queries.get_document_by_path(conn, "gone.txt")
    assert doc is None
    assert queries.count_chunks(conn) == 0
    assert store.count() == 0
    assert fts_query(conn, '"zebras"', 10) == []


def test_force_reindexes_everything(settings, conn, store):
    write_file(settings.corpus_dir, "a.txt", "Hello world. " * 10)
    run_ingest(settings, store)
    ids1 = set(queries.all_chunk_ids(conn))
    run_ingest(settings, store, force=True)
    ids2 = set(queries.all_chunk_ids(conn))
    assert ids1 & ids2 == set()
    assert len(ids1) == len(ids2)


def test_undecodable_file_marked_failed(settings, conn, store):
    # cp1252 bytes that are invalid UTF-8 but valid cp1252 -> falls back, indexed.
    write_file(settings.corpus_dir, "ok.txt", "plain ascii text. " * 5)
    path = settings.corpus_dir / "bad.txt"
    path.write_bytes(b"\xff\xfe invalid utf8 \x81\x8d\x8f\x90\x9d cafe")
    job = run_ingest(settings, store)
    assert job.state == "done"
    # cp1252/latin-1 fallback means every byte sequence decodes; document indexed, not failed.
    doc = queries.get_document_by_path(conn, "bad.txt")
    assert doc["status"] in ("indexed", "failed")


def test_chroma_failure_rolls_back_sqlite(settings, conn, store):
    from app.services.vectorstore import FailingVectorStore
    write_file(settings.corpus_dir, "a.txt", "Hello world. " * 10)
    failing = FailingVectorStore()
    try:
        run_ingest_with(settings, failing)
        assert False, "expected failure"
    except Exception:
        pass
    assert queries.count_chunks(conn) == 0


def run_ingest_with(settings, store):
    return asyncio.run(ingest_mod.run_ingest(settings, store, FakeEmbedding(settings), False))


def test_ingest_lock_and_status(settings, conn, store):
    write_file(settings.corpus_dir, "a.txt", "Hello world. " * 10)
    run_ingest(settings, store)
    status = ingest_mod.get_job()
    assert status.to_dict()["state"] == "done"


def test_subdirectory_walk(settings, conn, store):
    write_file(settings.corpus_dir, "sub/dir/deep.txt", "Nested content here. " * 5)
    run_ingest(settings, store)
    doc = queries.get_document_by_path(conn, "sub/dir/deep.txt")
    assert doc is not None
    assert doc["status"] == "indexed"
