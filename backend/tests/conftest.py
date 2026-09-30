import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


@pytest.fixture()
def settings(tmp_path, monkeypatch):
    monkeypatch.setenv("FAKE_PROVIDERS", "1")
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("CHROMA_MODE", "persistent")
    monkeypatch.setenv("CHROMA_PATH", str(tmp_path / "chroma"))
    monkeypatch.setenv("CORPUS_DIR", str(tmp_path / "corpus"))
    monkeypatch.setenv("EMBEDDING_DIM", "32")
    monkeypatch.setenv("EMBEDDING_BATCH_SIZE", "4")
    monkeypatch.setenv("LOG_LEVEL", "WARNING")
    (tmp_path / "corpus").mkdir(exist_ok=True)

    from app.config import Settings, reset_settings
    reset_settings()
    from app import runtime
    runtime.reset_runtime()
    s = Settings()
    yield s
    reset_settings()
    runtime.reset_runtime()


@pytest.fixture()
def conn(settings):
    from app.db.connection import connect, init_schema
    from app.db.fts import ensure_fts_tokenizer
    c = connect(settings)
    init_schema(c)
    ensure_fts_tokenizer(c, settings)
    yield c
    c.close()


@pytest.fixture()
def store(settings):
    from app.services.vectorstore import ChromaStore
    return ChromaStore(settings)


@pytest.fixture()
def embedding(settings):
    from app.services.providers import FakeEmbedding
    return FakeEmbedding(settings)
