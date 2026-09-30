import logging
import os
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Chat model
    llm_base_url: str = "https://api.mistral.ai/v1"
    llm_api_key: str = ""
    llm_model: str = "mistral-small-latest"
    llm_temperature: float = 0.2
    llm_max_tokens: int = 1024

    # Embeddings
    embedding_base_url: str = "https://api.mistral.ai/v1"
    embedding_api_key: str = ""
    embedding_model: str = "mistral-embed"
    embedding_dim: int = 1024
    embedding_batch_size: int = 32

    # SQLite
    database_path: str = "./data/babyrag.db"

    # Chroma
    chroma_mode: str = "persistent"  # persistent | http
    chroma_path: str = "./data/chroma"
    chroma_host: str = "localhost"
    chroma_port: int = 8001
    chroma_collection: str = "baby_rag_chunks"

    # Corpus and chunking
    corpus_dir: Path = Path("./corpus")
    chunk_size: int = 1000
    chunk_overlap: int = 150

    # Retrieval
    top_k: int = 5
    candidate_k: int = 20
    hybrid: bool = True
    fts_tokenizer: str = "unicode61 remove_diacritics 2"
    rrf_k: int = 60

    # App
    cors_origins: str = "http://localhost:5173,http://localhost:8080"
    fake_providers: bool = False
    log_level: str = "INFO"
    history_turns: int = 6

    @field_validator("chroma_mode")
    @classmethod
    def _mode(cls, v: str) -> str:
        v = v.strip().lower()
        if v not in ("persistent", "http"):
            raise ValueError("CHROMA_MODE must be 'persistent' or 'http'")
        return v

    @field_validator("chunk_size", "chunk_overlap", "top_k", "candidate_k", "rrf_k",
                     "embedding_dim", "embedding_batch_size", "llm_max_tokens", "history_turns")
    @classmethod
    def _positive(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("must be > 0")
        return v

    @field_validator("chunk_overlap")
    @classmethod
    def _overlap(cls, v: int, info) -> int:
        size = info.data.get("chunk_size", 1000)
        if v >= size:
            raise ValueError("CHUNK_OVERLAP must be smaller than CHUNK_SIZE")
        return v

    @field_validator("fts_tokenizer")
    @classmethod
    def _tokenizer(cls, v: str) -> str:
        if not v.strip() or any(c in v for c in "();'\""):
            raise ValueError("FTS_TOKENIZER must be a valid FTS5 tokenizer spec")
        return v.strip()

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def fake_providers_flag(self) -> bool:
        # Accept both FAKE_PROVIDERS=1/true and the env var directly.
        raw = os.environ.get("FAKE_PROVIDERS")
        if raw is not None:
            return raw.strip().lower() in ("1", "true", "yes", "on")
        return self.fake_providers

    def validate_for_run(self) -> None:
        if not self.fake_providers_flag:
            missing = [n for n, v in (
                ("LLM_API_KEY", self.llm_api_key),
                ("EMBEDDING_API_KEY", self.embedding_api_key),
            ) if not v or v == "changeme"]
            if missing:
                raise ValueError(
                    f"Invalid configuration: {', '.join(missing)} not set. "
                    "Set real keys in .env or use FAKE_PROVIDERS=1."
                )


_settings: Settings | None = None
logger = logging.getLogger("babyrag.config")


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
        logging.basicConfig(level=_settings.log_level.upper())
    return _settings


def reset_settings() -> None:
    global _settings
    _settings = None


def ensure_dirs(settings: Settings) -> None:
    Path(settings.database_path).parent.mkdir(parents=True, exist_ok=True)
    if settings.chroma_mode == "persistent":
        Path(settings.chroma_path).mkdir(parents=True, exist_ok=True)
