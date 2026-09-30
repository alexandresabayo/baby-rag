"""Process-wide singletons: providers and the vector store (created once)."""

import logging

from app.config import Settings
from app.db.connection import connect
from app.services import ingest as ingest_mod
from app.services.providers import (
    FakeEmbedding,
    FakeLLM,
    OpenAIEmbedding,
    OpenAILLM,
)
from app.services.vectorstore import ChromaStore

logger = logging.getLogger("babyrag.runtime")

_store = None
_llm = None
_embedding = None


def get_store() -> ChromaStore:
    global _store
    if _store is None:
        _store = ChromaStore(get_settings_ref())
    return _store


def get_settings_ref() -> Settings:
    from app.config import get_settings
    return get_settings()


def get_llm_provider():
    global _llm
    if _llm is None:
        s = get_settings_ref()
        _llm = FakeLLM(s) if s.fake_providers_flag else OpenAILLM(s)
    return _llm


def get_embedding_provider():
    global _embedding
    if _embedding is None:
        s = get_settings_ref()
        _embedding = FakeEmbedding(s) if s.fake_providers_flag else OpenAIEmbedding(s)
    return _embedding


def reset_runtime() -> None:
    global _store, _llm, _embedding
    _store, _llm, _embedding = None, None, None


async def startup_checks(settings: Settings) -> None:
    """Fail fast on invalid config; warn (not crash) on embedding-model mismatch."""
    settings.validate_for_run()
    get_store()
    get_llm_provider()
    get_embedding_provider()
    conn = connect(settings)
    try:
        ok, msg = ingest_mod.check_embedding_guard(conn, settings)
        if not ok:
            logger.warning("Embedding model changed: %s", msg)
    finally:
        conn.close()
