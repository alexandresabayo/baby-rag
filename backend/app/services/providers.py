import hashlib
import math
from collections.abc import AsyncIterator
from typing import Protocol

from openai import AsyncOpenAI

from app.config import Settings


class LLMProvider(Protocol):
    def stream(self, messages: list[dict]) -> AsyncIterator[str]: ...


class EmbeddingProvider(Protocol):
    async def embed(self, texts: list[str]) -> list[list[float]]: ...


def _stable_hash_embedding(text: str, dim: int) -> list[float]:
    """Deterministic offline embedding: bag-of-hashed-words projected into dim axes."""
    vec = [0.0] * dim
    for word in text.lower().split():
        h = hashlib.sha256(word.encode("utf-8")).digest()
        idx = int.from_bytes(h[:8], "big") % dim
        sign = 1.0 if h[8] % 2 == 0 else -1.0
        vec[idx] += sign
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


class FakeLLM:
    """Streams a canned answer quoting the top context block."""

    def __init__(self, settings: Settings):
        self.settings = settings

    async def stream(self, messages: list[dict]):
        system = messages[0]["content"] if messages and messages[0]["role"] == "system" else ""
        top = ""
        for line in system.split("\n"):
            if line.startswith("[1]"):
                top = line
                break
        answer = (
            f"[FAKE LLM] Based on the retrieved context: {top}\n\n"
            "This is a deterministic offline answer produced by FAKE_PROVIDERS=1; "
            "no API key or network access was used."
        )
        for token in answer.split(" "):
            yield token + " "


class FakeEmbedding:
    def __init__(self, settings: Settings):
        self.dim = settings.embedding_dim

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [_stable_hash_embedding(t, self.dim) for t in texts]


class OpenAILLM:
    def __init__(self, settings: Settings):
        self.client = AsyncOpenAI(
            base_url=settings.llm_base_url, api_key=settings.llm_api_key
        )
        self.model = settings.llm_model
        self.temperature = settings.llm_temperature
        self.max_tokens = settings.llm_max_tokens

    async def stream(self, messages: list[dict]):
        stream = await self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            stream=True,
        )
        async for event in stream:
            if event.choices and event.choices[0].delta.content:
                yield event.choices[0].delta.content


class OpenAIEmbedding:
    def __init__(self, settings: Settings):
        self.client = AsyncOpenAI(
            base_url=settings.embedding_base_url, api_key=settings.embedding_api_key
        )
        self.model = settings.embedding_model

    async def embed(self, texts: list[str]) -> list[list[float]]:
        resp = await self.client.embeddings.create(model=self.model, input=texts)
        return [d.embedding for d in resp.data]
