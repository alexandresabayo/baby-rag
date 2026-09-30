import asyncio
import json
import sqlite3

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from app.config import ensure_dirs, get_settings
from app.db import queries
from app.db.connection import connect, fts5_available, init_schema
from app.db.fts import ensure_fts_tokenizer
from app.runtime import get_store, startup_checks
from app.services import ingest as ingest_mod
from app.services.rag import chat_stream, do_search


class IngestBody(BaseModel):
    force: bool = False


class SearchBody(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    top_k: int | None = Field(default=None, ge=1, le=20)


class ChatBody(BaseModel):
    message: str = Field(min_length=1, max_length=8000)
    conversation_id: str | None = None
    top_k: int | None = Field(default=None, ge=1, le=20)


app = FastAPI(title="baby-rag", version="0.1.0")


@app.on_event("startup")
async def _startup():
    settings = get_settings()
    ensure_dirs(settings)
    conn = connect(settings)
    try:
        if not fts5_available(conn):
            raise RuntimeError("SQLite is not compiled with FTS5 support")
        init_schema(conn)
        ensure_fts_tokenizer(conn, settings)
    finally:
        conn.close()
    await startup_checks(settings)


app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origin_list,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _err(code: str, message: str, status: int) -> HTTPException:
    return HTTPException(status_code=status, detail={"code": code, "message": message})


def _db() -> sqlite3.Connection:
    return connect(get_settings())


@app.get("/api/health")
async def health():
    settings = get_settings()
    conn = _db()
    try:
        sqlite_count = queries.count_chunks(conn)
        ok, msg = ingest_mod.check_embedding_guard(conn, settings)
    finally:
        conn.close()
    try:
        store = get_store()
        chroma_count = store.count()
        chroma_ok = True
    except Exception as exc:
        chroma_count, chroma_ok, msg = -1, False, str(exc)
    return {
        "status": "ok" if (chroma_ok and sqlite_count == chroma_count and ok) else "degraded",
        "sqlite": {"ok": True, "chunks": sqlite_count},
        "chroma": {"ok": chroma_ok, "chunks": chroma_count},
        "counts_match": sqlite_count == chroma_count,
        "embedding_meta_ok": ok,
        "embedding_meta_message": msg,
    }


@app.get("/api/config")
async def config():
    s = get_settings()
    return {
        "llm_base_url": s.llm_base_url,
        "llm_model": s.llm_model,
        "embedding_base_url": s.embedding_base_url,
        "embedding_model": s.embedding_model,
        "embedding_dim": s.embedding_dim,
        "database_path": s.database_path,
        "chroma_mode": s.chroma_mode,
        "chroma_collection": s.chroma_collection,
        "corpus_dir": s.corpus_dir,
        "chunk_size": s.chunk_size,
        "chunk_overlap": s.chunk_overlap,
        "top_k": s.top_k,
        "candidate_k": s.candidate_k,
        "hybrid": s.hybrid,
        "rrf_k": s.rrf_k,
        "fake_providers": s.fake_providers_flag,
    }


def _list_documents_sync() -> list[dict]:
    conn = _db()
    try:
        return [dict(r) for r in queries.list_documents(conn)]
    finally:
        conn.close()


@app.get("/api/documents")
async def documents():
    return await asyncio.to_thread(_list_documents_sync)


@app.post("/api/ingest")
async def start_ingest(body: IngestBody):
    if ingest_mod.is_running():
        raise _err("ingest_running", "an ingestion job is already running", 409)
    from app.runtime import get_embedding_provider, get_store
    settings = get_settings()

    async def _run():
        await ingest_mod.run_ingest(settings, get_store(), get_embedding_provider(), body.force)

    import asyncio
    asyncio.create_task(_run())
    return {"status": "started"}


@app.get("/api/ingest/status")
async def ingest_status():
    job = ingest_mod.get_job()
    return job.to_dict() if job else {"state": "idle", "total": 0, "done": 0, "failed": 0,
                                      "chunks_written": 0, "error": None}


@app.post("/api/search")
async def search(body: SearchBody):
    results = await do_search(get_settings(), body.query, body.top_k)
    return {"results": results}


@app.post("/api/chat")
async def chat(body: ChatBody):
    settings = get_settings()

    async def event_gen():
        async for ev in chat_stream(settings, body.message, body.conversation_id, body.top_k):
            payload = ev["data"] if not isinstance(ev["data"], str) else ev["data"]
            data = payload if isinstance(payload, str) else json.dumps(payload)
            yield f"event: {ev['event']}\ndata: {data}\n\n"

    return StreamingResponse(event_gen(), media_type="text/event-stream")


@app.get("/api/conversations")
async def conversations():
    def _sync():
        conn = _db()
        try:
            return [dict(r) for r in queries.list_conversations(conn)]
        finally:
            conn.close()
    return await asyncio.to_thread(_sync)


@app.get("/api/conversations/{conv_id}")
async def conversation(conv_id: str):
    def _sync():
        conn = _db()
        try:
            conv = queries.get_conversation(conn, conv_id)
            if conv is None:
                raise _err("not_found", "conversation not found", 404)
            msgs = queries.list_messages(conn, conv_id)
            out = []
            for m in msgs:
                d = dict(m)
                d["sources"] = json.loads(d["sources"]) if d["sources"] else None
                out.append(d)
            return {"id": conv_id, "title": conv["title"], "created_at": conv["created_at"],
                    "messages": out}
        finally:
            conn.close()
    return await asyncio.to_thread(_sync)


@app.delete("/api/conversations/{conv_id}")
async def delete_conversation(conv_id: str):
    def _sync():
        conn = _db()
        try:
            conv = queries.get_conversation(conn, conv_id)
            if conv is None:
                raise _err("not_found", "conversation not found", 404)
            queries.delete_conversation(conn, conv_id)
            return {"status": "deleted"}
        finally:
            conn.close()
    return await asyncio.to_thread(_sync)


@app.exception_handler(RequestValidationError)
async def validation_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content={"error": {"code": "validation_error", "message": exc.errors()[0]["msg"]}},
    )


@app.exception_handler(HTTPException)
async def http_exc_handler(request: Request, exc: HTTPException):
    detail = exc.detail
    if isinstance(detail, dict) and "code" in detail:
        payload = detail
    else:
        payload = {"code": "error", "message": str(detail)}
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": payload},
    )
