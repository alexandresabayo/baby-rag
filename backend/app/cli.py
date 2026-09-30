import asyncio
import json
import sys

from app.config import ensure_dirs, get_settings
from app.db import queries
from app.db.connection import connect, init_schema
from app.db.fts import ensure_fts_tokenizer
from app.runtime import get_embedding_provider, get_store


def main() -> None:
    args = sys.argv[1:]
    if not args or args[0] in ("-h", "--help", "help"):
        print(__doc__)
        return
    cmd = args[0]
    settings = get_settings()
    ensure_dirs(settings)
    conn = connect(settings)
    try:
        init_schema(conn)
        ensure_fts_tokenizer(conn, settings)
    finally:
        conn.close()

    if cmd == "ingest":
        force = "--force" in args
        from app.services.ingest import run_ingest
        job = asyncio.run(run_ingest(settings, get_store(), get_embedding_provider(), force))
        print(json.dumps(job.to_dict()))
    elif cmd == "reindex":
        run_reindex(settings)
    elif cmd == "verify":
        run_verify(settings, fix="--fix" in args)
    else:
        print(f"unknown command: {cmd}", file=sys.stderr)
        sys.exit(2)


def run_reindex(settings) -> None:
    """Drop and recreate the Chroma collection; re-embed every chunk in SQLite."""
    store = get_store()
    store.reset_collection()
    conn = connect(settings)
    try:
        rows = queries.list_documents(conn)
        embed = get_embedding_provider()
        for row in rows:
            if row["status"] != "indexed":
                continue
            chunks = queries.chunks_for_document(conn, row["id"])
            if not chunks:
                continue
            vectors = asyncio.run(embed.embed([c["content"] for c in chunks]))
            ids = [str(c["id"]) for c in chunks]
            metas = [{"document_id": row["id"], "path": row["path"], "chunk_index": c["chunk_index"]}
                     for c in chunks]
            store.upsert(ids, vectors, metas)
        queries.set_meta(conn, "embedding_model", settings.embedding_model)
        queries.set_meta(conn, "embedding_dim", str(settings.embedding_dim))
        print(f"reindexed {store.count()} chunks")
    finally:
        conn.close()


def run_verify(settings, fix: bool = False) -> None:
    """Compare SQLite chunk ids with Chroma ids; check FTS integrity; repair with --fix."""
    store = get_store()
    conn = connect(settings)
    try:
        sqlite_ids = set(queries.all_chunk_ids(conn))
        chroma_ids = set(int(i) for i in store.all_ids())
        orphans = sorted(chroma_ids - sqlite_ids)
        missing = sorted(sqlite_ids - chroma_ids)
        fts_ids = {r[0] for r in conn.execute("SELECT rowid FROM chunks_fts").fetchall()}
        fts_missing = sorted(sqlite_ids - fts_ids)
        print(f"sqlite chunks: {len(sqlite_ids)}, chroma chunks: {len(chroma_ids)}")
        print(f"chroma orphans: {len(orphans)}, missing from chroma: {len(missing)}")
        print(f"fts missing: {len(fts_missing)}")
        if fix:
            if orphans:
                store.delete([str(i) for i in orphans])
                print(f"deleted {len(orphans)} orphan vectors")
            if missing:
                embed = get_embedding_provider()
                for doc in queries.list_documents(conn):
                    if doc["status"] != "indexed":
                        continue
                    for c in queries.chunks_for_document(conn, doc["id"]):
                        if c["id"] in missing:
                            vec = asyncio.run(embed.embed([c["content"]]))
                            store.upsert([str(c["id"])], vec, [{
                                "document_id": doc["id"], "path": doc["path"],
                                "chunk_index": c["chunk_index"]}])
                            print(f"re-embedded chunk {c['id']}")
            if fts_missing:
                from app.db.fts import rebuild_fts
                conn.execute("BEGIN IMMEDIATE")
                try:
                    rebuild_fts(conn, settings.fts_tokenizer)
                    conn.execute("COMMIT")
                except Exception:
                    conn.execute("ROLLBACK")
                    raise
                print(f"rebuilt FTS index ({len(fts_missing)} missing rows)")
        else:
            ok = not orphans and not missing and not fts_missing
            print("OK" if ok else "DRIFT DETECTED (run with --fix to repair)")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
