import logging
from typing import Protocol

import chromadb
from chromadb.config import Settings as ChromaSettings

from app.config import Settings

logger = logging.getLogger("babyrag.vectorstore")


class VectorStore(Protocol):
    def upsert(self, ids: list[str], embeddings: list[list[float]],
               metadatas: list[dict]) -> None: ...
    def query(self, embedding: list[float], k: int) -> list[str]: ...
    def delete(self, ids: list[str]) -> None: ...
    def count(self) -> int: ...
    def all_ids(self) -> list[str]: ...
    def collection_metadata(self) -> dict: ...
    def reset_collection(self) -> None: ...


class ChromaStore:
    """The only module that imports chromadb, per the architecture rules."""

    def __init__(self, settings: Settings):
        self.settings = settings
        if settings.chroma_mode == "http":
            self.client = chromadb.HttpClient(
                host=settings.chroma_host, port=settings.chroma_port
            )
        else:
            self.client = chromadb.PersistentClient(
                path=settings.chroma_path,
                settings=ChromaSettings(anonymized_telemetry=False, allow_reset=True),
            )
        self.collection = self._get_or_create()

    def _get_or_create(self):
        return self.client.get_or_create_collection(
            name=self.settings.chroma_collection,
            metadata={"hnsw:space": "cosine"},
            embedding_function=None,
        )

    def upsert(self, ids, embeddings, metadatas) -> None:
        if not ids:
            return
        self.collection.upsert(
            ids=ids, embeddings=embeddings, metadatas=metadatas
        )

    def query(self, embedding: list[float], k: int) -> list[str]:
        res = self.collection.query(
            query_embeddings=[embedding],
            n_results=min(k, max(self.count(), 1)),
            include=["metadatas", "distances"],
        )
        return [str(i) for i in res["ids"][0]]

    def distances(self, embedding: list[float], k: int):
        res = self.collection.query(
            query_embeddings=[embedding],
            n_results=min(k, max(self.count(), 1)),
            include=["distances"],
        )
        ids = res["ids"][0]
        dists = res["distances"][0]
        return [(str(i), 1.0 - d) for i, d in zip(ids, dists, strict=False)]

    def delete(self, ids: list[str]) -> None:
        if not ids:
            return
        self.collection.delete(ids=ids)

    def count(self) -> int:
        return self.collection.count()

    def all_ids(self) -> list[str]:
        if self.count() == 0:
            return []
        res = self.collection.get(include=[])
        return [str(i) for i in res["ids"]]

    def collection_metadata(self) -> dict:
        col = self.client.get_collection(self.settings.chroma_collection)
        return dict(col.metadata or {})

    def reset_collection(self) -> None:
        try:
            self.client.delete_collection(self.settings.chroma_collection)
        except Exception:
            logger.warning("Collection did not exist during reset")
        self.collection = self._get_or_create()


class FailingVectorStore:
    """Test double whose writes always fail, to prove SQLite rollback."""

    def __init__(self, *args, **kwargs):
        self.deleted: list[str] = []

    def upsert(self, ids, embeddings, metadatas):
        raise RuntimeError("simulated Chroma failure")

    def query(self, embedding, k):
        return []

    def delete(self, ids):
        self.deleted.extend(ids)

    def count(self) -> int:
        return 0

    def all_ids(self) -> list[str]:
        return []

    def collection_metadata(self) -> dict:
        return {}

    def reset_collection(self) -> None:
        pass
