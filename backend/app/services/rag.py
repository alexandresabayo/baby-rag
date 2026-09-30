import asyncio
import sqlite3
import uuid
from collections.abc import AsyncIterator

from app.config import Settings
from app.prompts import SYSTEM_PROMPT, build_messages
from app.services.retrieval import retrieve

MAX_MESSAGE_CHARS = 8000
CONTEXT_CHAR_BUDGET = 24000


def _search_sync(settings: Settings, query: str, top_k: int | None,
                 store, embedding_provider) -> list[dict]:
    from app.db.connection import connect
    conn = connect(settings)
    try:
        return asyncio.run(retrieve(settings, conn, store, embedding_provider, query, top_k))
    finally:
        conn.close()


async def do_search(settings: Settings, query: str, top_k: int | None) -> list[dict]:
    from app.runtime import get_embedding_provider, get_store
    return await asyncio.to_thread(
        _search_sync, settings, query, top_k, get_store(), get_embedding_provider()
    )


def _prepare_chat_sync(settings: Settings, message: str, conversation_id: str | None,
                       history_turns: int) -> tuple:
    """Runs in a worker thread: open conn, resolve/create conversation, persist user
    message, return (conn, conversation_id, history_rows)."""
    from app.db import queries
    from app.db.connection import connect
    conn = connect(settings)
    try:
        if conversation_id:
            conv = queries.get_conversation(conn, conversation_id)
            if conv is None:
                conversation_id = None
        if not conversation_id:
            conversation_id = str(uuid.uuid4())
            queries.create_conversation(conn, conversation_id, message[:60] or "New conversation")
        queries.add_message(conn, conversation_id, "user", message, None)
        history = [
            {"role": r["role"], "content": r["content"]}
            for r in queries.last_messages(conn, conversation_id, (history_turns + 1) * 2)
        ][:-1]  # drop the just-added question
        history = history[-history_turns * 2:]
        return conn, conversation_id, history
    except Exception:
        conn.close()
        raise


def _search_with_conn_sync(settings: Settings, conn: sqlite3.Connection, query: str,
                           top_k: int | None, store, embedding_provider) -> list[dict]:
    return asyncio.run(retrieve(settings, conn, store, embedding_provider, query, top_k))


def _persist_assistant_sync(conn: sqlite3.Connection, conversation_id: str,
                            content: str, sources: list) -> int:
    from app.db import queries
    return queries.add_message(conn, conversation_id, "assistant", content, sources)


async def chat_stream(settings: Settings, message: str, conversation_id: str | None,
                      top_k: int | None) -> AsyncIterator[dict]:
    """Yield SSE events: sources, token*, error?, done."""
    from app.runtime import get_embedding_provider, get_llm_provider, get_store

    if not message or len(message) > MAX_MESSAGE_CHARS:
        yield {"event": "error", "data": {"message": "message is empty or too long"}}
        return

    conn, conversation_id, history = await asyncio.to_thread(
        _prepare_chat_sync, settings, message, conversation_id, settings.history_turns
    )
    try:
        store = get_store()
        embed = get_embedding_provider()
        results = await asyncio.to_thread(
            _search_with_conn_sync, settings, conn, message, top_k, store, embed
        )

        sources = [
            {
                "n": i + 1,
                "chunk_id": r["chunk_id"],
                "path": r["path"],
                "chunk_index": r["chunk_index"],
                "text": r["text"],
                "start_char": r["start_char"],
                "end_char": r["end_char"],
                "score": r["score"],
                "retrievers": r["retrievers"],
            }
            for i, r in enumerate(results)
        ]
        yield {"event": "sources", "data": sources}

        blocks = []
        budget = CONTEXT_CHAR_BUDGET
        for s in sources:
            if budget - len(s["text"]) < 0:
                break
            blocks.append({"path": s["path"], "text": s["text"]})
            budget -= len(s["text"])

        messages = build_messages(SYSTEM_PROMPT, blocks, history, message)
        llm = get_llm_provider()

        full = []
        try:
            async for token in llm.stream(messages):
                full.append(token)
                yield {"event": "token", "data": token}
        except Exception as exc:
            yield {"event": "error", "data": {"message": f"LLM error: {exc}"}}

        msg_id = await asyncio.to_thread(
            _persist_assistant_sync, conn, conversation_id, "".join(full), sources
        )
        yield {"event": "done", "data": {"message_id": msg_id, "conversation_id": conversation_id}}
    finally:
        await asyncio.to_thread(conn.close)
