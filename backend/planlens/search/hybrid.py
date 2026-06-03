from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import duckdb

from ..config import Settings
from ..db import connect
from ..embed.embeddings import (
    cosine_similarity,
    embedding_provider_from_settings,
    expanded_terms,
    tokenize_terms,
)


@dataclass(frozen=True)
class ChunkSearchRow:
    chunk_id: str
    document_id: str
    title: str | None
    source_type: str
    hearing_date: date | None
    page_start: int | None
    page_end: int | None
    citation_label: str | None
    text: str
    url: str
    section_hint: str | None
    embedding: list[float] | None


@dataclass(frozen=True)
class SearchResult:
    chunk_id: str
    document_id: str
    title: str | None
    source_type: str
    hearing_date: date | None
    page_start: int | None
    page_end: int | None
    citation_label: str | None
    text: str
    score: float
    vector_score: float
    lexical_score: float
    metadata_boost: float
    url: str


@dataclass(frozen=True)
class HybridSearchResponse:
    query: str
    answer_stub: str
    results: tuple[SearchResult, ...]


def hybrid_search(
    db_path: Path | str,
    settings: Settings,
    query: str,
    date_start: date | None = None,
    date_end: date | None = None,
    document_types: list[str] | None = None,
    limit: int = 10,
) -> HybridSearchResponse:
    provider = embedding_provider_from_settings(settings)
    query_embedding = provider.embed_texts([query], input_type="query")[0]

    with connect(db_path) as conn:
        rows = list_searchable_chunks(
            conn=conn,
            embedding_provider=provider.provider_name,
            embedding_model=provider.model_name,
            date_start=date_start,
            date_end=date_end,
            document_types=document_types,
        )

    results = rank_chunks(
        query=query,
        query_embedding=query_embedding,
        rows=rows,
        limit=limit,
    )
    return HybridSearchResponse(
        query=query,
        answer_stub="Answer generation not implemented yet.",
        results=tuple(results),
    )


def lexical_search(
    db_path: Path | str,
    query: str,
    date_start: date | None = None,
    date_end: date | None = None,
    document_types: list[str] | None = None,
    limit: int = 10,
) -> HybridSearchResponse:
    with connect(db_path) as conn:
        rows = list_searchable_chunks(
            conn=conn,
            embedding_provider=None,
            embedding_model=None,
            date_start=date_start,
            date_end=date_end,
            document_types=document_types,
        )

    results = rank_chunks(
        query=query,
        query_embedding=None,
        rows=rows,
        limit=limit,
    )
    return HybridSearchResponse(
        query=query,
        answer_stub="Answer generation not implemented yet.",
        results=tuple(results),
    )


def list_searchable_chunks(
    conn: duckdb.DuckDBPyConnection,
    embedding_provider: str | None,
    embedding_model: str | None,
    date_start: date | None = None,
    date_end: date | None = None,
    document_types: list[str] | None = None,
) -> list[ChunkSearchRow]:
    params: list[object] = []
    embedding_join = ""
    if embedding_provider and embedding_model:
        embedding_join = """
            LEFT JOIN chunk_embeddings e
                ON e.chunk_id = c.chunk_id
                AND e.embedding_provider = ?
                AND e.embedding_model = ?
        """
        params.extend([embedding_provider, embedding_model])
    else:
        embedding_join = "LEFT JOIN chunk_embeddings e ON false"

    filters: list[str] = []
    if date_start:
        filters.append("h.hearing_date >= ?")
        params.append(date_start)
    if date_end:
        filters.append("h.hearing_date <= ?")
        params.append(date_end)
    if document_types:
        placeholders = ", ".join("?" for _ in document_types)
        filters.append(f"d.source_type IN ({placeholders})")
        params.extend(document_types)

    where_clause = f"WHERE {' AND '.join(filters)}" if filters else ""
    rows = conn.execute(
        f"""
        SELECT
            c.chunk_id,
            c.document_id,
            d.title,
            d.source_type,
            h.hearing_date,
            c.page_start,
            c.page_end,
            c.citation_label,
            c.text,
            d.url,
            c.section_hint,
            e.embedding
        FROM chunks c
        JOIN source_documents d ON d.document_id = c.document_id
        LEFT JOIN hearings h ON h.hearing_id = d.hearing_id
        {embedding_join}
        {where_clause}
        ORDER BY h.hearing_date DESC NULLS LAST, c.document_id, c.chunk_index
        """,
        params,
    ).fetchall()

    return [
        ChunkSearchRow(
            chunk_id=row[0],
            document_id=row[1],
            title=row[2],
            source_type=row[3],
            hearing_date=row[4],
            page_start=row[5],
            page_end=row[6],
            citation_label=row[7],
            text=row[8],
            url=row[9],
            section_hint=row[10],
            embedding=row[11],
        )
        for row in rows
    ]


def rank_chunks(
    query: str,
    query_embedding: list[float] | None,
    rows: list[ChunkSearchRow],
    limit: int = 10,
) -> list[SearchResult]:
    query_terms = expanded_terms(query)
    document_frequencies = chunk_document_frequencies(rows)
    scored: list[SearchResult] = []

    for row in rows:
        lexical = lexical_score(
            query_terms=query_terms,
            text=row.text,
            document_frequencies=document_frequencies,
            corpus_size=len(rows),
        )
        vector = vector_score(query_embedding=query_embedding, row_embedding=row.embedding)
        metadata = metadata_boost(query_terms=query_terms, row=row)
        hybrid = (0.55 * vector) + (0.35 * lexical) + (0.10 * metadata)

        if hybrid <= 0:
            continue

        scored.append(
            SearchResult(
                chunk_id=row.chunk_id,
                document_id=row.document_id,
                title=row.title,
                source_type=row.source_type,
                hearing_date=row.hearing_date,
                page_start=row.page_start,
                page_end=row.page_end,
                citation_label=row.citation_label,
                text=row.text,
                score=round(hybrid, 4),
                vector_score=round(vector, 4),
                lexical_score=round(lexical, 4),
                metadata_boost=round(metadata, 4),
                url=row.url,
            )
        )

    scored.sort(key=lambda result: result.score, reverse=True)
    return scored[:limit]


def lexical_score(
    query_terms: list[str],
    text: str,
    document_frequencies: dict[str, int],
    corpus_size: int,
) -> float:
    if not query_terms:
        return 0.0

    chunk_terms = tokenize_terms(text)
    if not chunk_terms:
        return 0.0

    term_counts: dict[str, int] = {}
    for term in chunk_terms:
        term_counts[term] = term_counts.get(term, 0) + 1

    unique_query_terms = list(dict.fromkeys(query_terms))
    score = 0.0
    max_possible = 0.0
    for term in unique_query_terms:
        idf = math.log((corpus_size + 1) / (document_frequencies.get(term, 0) + 1)) + 1
        max_possible += idf
        if term in term_counts:
            score += min(1.0, term_counts[term] / 3) * idf

    if max_possible == 0:
        return 0.0
    return min(1.0, score / max_possible)


def vector_score(
    query_embedding: list[float] | None,
    row_embedding: list[float] | None,
) -> float:
    if not query_embedding or not row_embedding:
        return 0.0
    similarity = cosine_similarity(query_embedding, row_embedding)
    return max(0.0, min(1.0, (similarity + 1.0) / 2.0))


def metadata_boost(query_terms: list[str], row: ChunkSearchRow) -> float:
    metadata = " ".join(
        value
        for value in (
            row.title or "",
            row.source_type,
            row.section_hint or "",
            row.citation_label or "",
            row.url,
        )
        if value
    )
    metadata_terms = set(tokenize_terms(metadata))
    if not query_terms or not metadata_terms:
        return 0.0

    unique_query_terms = set(query_terms)
    overlap = len(unique_query_terms & metadata_terms)
    return min(1.0, overlap / max(1, len(unique_query_terms)))


def chunk_document_frequencies(rows: list[ChunkSearchRow]) -> dict[str, int]:
    frequencies: dict[str, int] = {}
    for row in rows:
        for term in set(tokenize_terms(row.text)):
            frequencies[term] = frequencies.get(term, 0) + 1
    return frequencies
