"""Text embeddings for retrieval: fastembed (ONNX, CPU, no API) behind a small protocol, plus a
deterministic fake for tests so the suite never downloads a model."""

from __future__ import annotations

import hashlib
import math
from typing import Any, Protocol

from fieldwise.db.models import EMBEDDING_DIM

MODEL_NAME = "BAAI/bge-small-en-v1.5"  # 384 dimensions, ~130 MB, downloaded once


class Embedder(Protocol):
    name: str

    def embed(self, texts: list[str]) -> list[list[float]]: ...


class FastEmbedder:
    name = MODEL_NAME

    def __init__(self) -> None:
        self._model: Any = None

    def _get_model(self) -> Any:
        if self._model is None:
            from fastembed import TextEmbedding  # noqa: PLC0415 — heavy import, on first use

            self._model = TextEmbedding(model_name=MODEL_NAME)
        return self._model

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        vectors = self._get_model().embed(texts, batch_size=16)
        return [[float(x) for x in vector] for vector in vectors]


class FakeEmbedder:
    """Bag-of-hashed-words vectors: similar texts get similar vectors, deterministically."""

    name = "fake"

    def embed(self, texts: list[str]) -> list[list[float]]:
        out: list[list[float]] = []
        for text in texts:
            vector = [0.0] * EMBEDDING_DIM
            for token in text.lower().split():
                index = int(hashlib.sha256(token.encode()).hexdigest(), 16) % EMBEDDING_DIM
                vector[index] += 1.0
            norm = math.sqrt(sum(v * v for v in vector)) or 1.0
            out.append([v / norm for v in vector])
        return out
