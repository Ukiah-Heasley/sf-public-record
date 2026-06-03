from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import duckdb
import httpx

from ..config import Settings
from ..db import connect

TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9-]{1,}")

DOMAIN_SYNONYMS = {
    "appeal": ("challenge", "objection"),
    "approval": ("approve", "authorization", "entitlement"),
    "delay": ("continuance", "continued", "postpone", "postponed"),
    "housing": ("dwelling", "residential", "unit", "units", "apartment"),
    "opposition": ("concern", "concerns", "objection", "comment", "neighbor"),
    "parking": ("garage", "vehicle", "vehicles", "car", "cars"),
    "project": ("proposal", "development"),
    "transit": ("muni", "bus", "rail", "station"),
}


class EmbeddingProvider(Protocol):
    provider_name: str
    model_name: str
    dimensions: int

    def embed_texts(self, texts: list[str], input_type: str = "document") -> list[list[float]]:
        """Embed texts as normalized vectors."""


@dataclass(frozen=True)
class PendingChunk:
    chunk_id: str
    text: str


@dataclass(frozen=True)
class EmbedChunksResult:
    chunk_count: int
    embedded_count: int
    skipped_count: int
    embedding_provider: str
    embedding_model: str
    embedding_dim: int


class LocalHashEmbeddingProvider:
    provider_name = "local_hash"

    def __init__(self, model_name: str = "local-hash-v1", dimensions: int = 384) -> None:
        self.model_name = model_name
        self.dimensions = dimensions

    def embed_texts(self, texts: list[str], input_type: str = "document") -> list[list[float]]:
        return [hash_embedding(text, dimensions=self.dimensions) for text in texts]


class SentenceTransformersEmbeddingProvider:
    provider_name = "sentence_transformers"

    def __init__(self, model_name: str, dimensions: int | None = None) -> None:
        self.model_name = model_name
        self._dimensions = dimensions
        self._model = None

    @property
    def dimensions(self) -> int:
        if self._dimensions is not None:
            return self._dimensions
        vectors = self.embed_texts(["dimension probe"])
        self._dimensions = len(vectors[0])
        return self._dimensions

    def embed_texts(self, texts: list[str], input_type: str = "document") -> list[list[float]]:
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise RuntimeError(
                "sentence-transformers is not installed. Use "
                "SF_PUBLIC_RECORD_EMBEDDING_PROVIDER=local_hash, "
                "or install the optional local model stack."
            ) from exc

        if self._model is None:
            self._model = SentenceTransformer(self.model_name)

        vectors = self._model.encode(
            texts,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return [list(map(float, vector)) for vector in vectors]


class OpenAIEmbeddingProvider:
    provider_name = "openai"

    def __init__(
        self,
        api_key: str,
        model_name: str = "text-embedding-3-small",
        dimensions: int | None = None,
    ) -> None:
        self.api_key = api_key
        self.model_name = model_name
        self._dimensions = dimensions or 1536

    @property
    def dimensions(self) -> int:
        return self._dimensions

    def embed_texts(self, texts: list[str], input_type: str = "document") -> list[list[float]]:
        payload: dict[str, object] = {
            "model": self.model_name,
            "input": texts,
            "encoding_format": "float",
        }
        if self._dimensions:
            payload["dimensions"] = self._dimensions

        with httpx.Client(timeout=60.0) as client:
            response = client.post(
                "https://api.openai.com/v1/embeddings",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json=payload,
            )
            response.raise_for_status()
            data = response.json()["data"]

        vectors = [item["embedding"] for item in sorted(data, key=lambda item: item["index"])]
        return [normalize_vector(vector) for vector in vectors]


class GoogleEmbeddingProvider:
    provider_name = "google"

    def __init__(
        self,
        api_key: str,
        model_name: str = "gemini-embedding-001",
        dimensions: int | None = None,
    ) -> None:
        self.api_key = api_key
        self.model_name = model_name
        self._dimensions = dimensions or 768

    @property
    def dimensions(self) -> int:
        return self._dimensions

    def embed_texts(self, texts: list[str], input_type: str = "document") -> list[list[float]]:
        task_type = "RETRIEVAL_QUERY" if input_type == "query" else "RETRIEVAL_DOCUMENT"
        endpoint = (
            "https://generativelanguage.googleapis.com/v1beta/"
            f"models/{self.model_name}:embedContent"
        )
        vectors: list[list[float]] = []
        with httpx.Client(timeout=60.0) as client:
            for text in texts:
                response = client.post(
                    endpoint,
                    params={"key": self.api_key},
                    json={
                        "content": {"parts": [{"text": text}]},
                        "taskType": task_type,
                    },
                )
                response.raise_for_status()
                vector = response.json()["embedding"]["values"]
                vectors.append(normalize_vector(vector[: self._dimensions]))
        return vectors


def embed_chunks(
    db_path: Path | str,
    settings: Settings,
    batch_size: int = 32,
    limit: int | None = None,
    force: bool = False,
) -> EmbedChunksResult:
    provider = embedding_provider_from_settings(settings)
    with connect(db_path) as conn:
        return embed_chunk_rows(
            conn=conn,
            provider=provider,
            batch_size=batch_size,
            limit=limit,
            force=force,
        )


def embed_chunk_rows(
    conn: duckdb.DuckDBPyConnection,
    provider: EmbeddingProvider,
    batch_size: int = 32,
    limit: int | None = None,
    force: bool = False,
) -> EmbedChunksResult:
    if force:
        conn.execute(
            """
            DELETE FROM chunk_embeddings
            WHERE embedding_provider = ? AND embedding_model = ?
            """,
            (provider.provider_name, provider.model_name),
        )

    chunks = list_chunks_for_embedding(conn, provider=provider, limit=limit)
    embedded_count = 0

    for offset in range(0, len(chunks), batch_size):
        batch = chunks[offset : offset + batch_size]
        vectors = provider.embed_texts([chunk.text for chunk in batch], input_type="document")
        rows = [
            (
                chunk.chunk_id,
                provider.provider_name,
                provider.model_name,
                len(vector),
                vector,
            )
            for chunk, vector in zip(batch, vectors, strict=True)
        ]
        conn.executemany(
            """
            INSERT INTO chunk_embeddings (
                chunk_id,
                embedding_provider,
                embedding_model,
                embedding_dim,
                embedding
            )
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT (chunk_id, embedding_provider, embedding_model) DO UPDATE SET
                embedding_dim = excluded.embedding_dim,
                embedding = excluded.embedding,
                embedded_at = now()
            """,
            rows,
        )
        embedded_count += len(rows)

    total_chunks = conn.execute("SELECT count(*) FROM chunks").fetchone()[0]
    return EmbedChunksResult(
        chunk_count=total_chunks,
        embedded_count=embedded_count,
        skipped_count=max(0, total_chunks - embedded_count),
        embedding_provider=provider.provider_name,
        embedding_model=provider.model_name,
        embedding_dim=provider.dimensions,
    )


def list_chunks_for_embedding(
    conn: duckdb.DuckDBPyConnection,
    provider: EmbeddingProvider,
    limit: int | None = None,
) -> list[PendingChunk]:
    query = """
        SELECT c.chunk_id, c.text
        FROM chunks c
        LEFT JOIN chunk_embeddings e
            ON e.chunk_id = c.chunk_id
            AND e.embedding_provider = ?
            AND e.embedding_model = ?
        WHERE e.chunk_id IS NULL
        ORDER BY c.document_id, c.chunk_index
    """
    params: list[object] = [provider.provider_name, provider.model_name]
    if limit is not None:
        query += " LIMIT ?"
        params.append(limit)

    rows = conn.execute(query, params).fetchall()
    return [PendingChunk(chunk_id=row[0], text=row[1]) for row in rows]


def embedding_provider_from_settings(settings: Settings) -> EmbeddingProvider:
    provider_name = settings.embedding_provider.lower().replace("-", "_")
    if provider_name in {"local_hash", "hash"}:
        return LocalHashEmbeddingProvider(
            model_name=settings.embedding_model,
            dimensions=settings.embedding_dimensions,
        )
    if provider_name in {"sentence_transformers", "sentence_transformer", "local"}:
        return SentenceTransformersEmbeddingProvider(
            model_name=settings.embedding_model,
            dimensions=settings.embedding_dimensions if settings.embedding_dimensions > 0 else None,
        )
    if provider_name == "openai":
        if not settings.openai_api_key:
            raise RuntimeError(
                "OPENAI_API_KEY is required for "
                "SF_PUBLIC_RECORD_EMBEDDING_PROVIDER=openai."
            )
        return OpenAIEmbeddingProvider(
            api_key=settings.openai_api_key,
            model_name=settings.embedding_model,
            dimensions=settings.embedding_dimensions if settings.embedding_dimensions > 0 else None,
        )
    if provider_name in {"google", "gemini"}:
        if not settings.google_api_key:
            raise RuntimeError(
                "GOOGLE_API_KEY is required for "
                "SF_PUBLIC_RECORD_EMBEDDING_PROVIDER=google."
            )
        return GoogleEmbeddingProvider(
            api_key=settings.google_api_key,
            model_name=settings.embedding_model,
            dimensions=settings.embedding_dimensions if settings.embedding_dimensions > 0 else None,
        )
    raise RuntimeError(f"Unknown embedding provider: {settings.embedding_provider}")


def hash_embedding(text: str, dimensions: int = 384) -> list[float]:
    vector = [0.0] * dimensions
    terms = expanded_terms(text)
    if not terms:
        return vector

    for term in terms:
        digest = hashlib.blake2b(term.encode(), digest_size=8).digest()
        bucket = int.from_bytes(digest[:4], "big") % dimensions
        sign = 1.0 if digest[4] % 2 == 0 else -1.0
        vector[bucket] += sign

    return normalize_vector(vector)


def expanded_terms(text: str) -> list[str]:
    terms = tokenize_terms(text)
    expanded: list[str] = []
    for term in terms:
        expanded.append(term)
        expanded.extend(DOMAIN_SYNONYMS.get(term, ()))
    return expanded


def tokenize_terms(text: str) -> list[str]:
    terms = [normalize_term(match.group(0)) for match in TOKEN_RE.finditer(text.lower())]
    return [term for term in terms if len(term) > 1]


def normalize_term(term: str) -> str:
    if len(term) > 4 and term.endswith("ies"):
        return f"{term[:-3]}y"
    if len(term) > 4 and term.endswith("s"):
        return term[:-1]
    return term


def normalize_vector(vector: list[float]) -> list[float]:
    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0:
        return [0.0 for _ in vector]
    return [float(value / norm) for value in vector]


def cosine_similarity(left: list[float] | None, right: list[float] | None) -> float:
    if not left or not right:
        return 0.0
    size = min(len(left), len(right))
    if size == 0:
        return 0.0
    return sum(left[index] * right[index] for index in range(size))
