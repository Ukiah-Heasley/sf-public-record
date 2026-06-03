from __future__ import annotations

from backend.planlens.db import connect, init_db
from backend.planlens.embed.embeddings import (
    LocalHashEmbeddingProvider,
    embed_chunk_rows,
    hash_embedding,
)


def test_hash_embedding_is_deterministic_and_normalized() -> None:
    first = hash_embedding("parking opposition near transit", dimensions=16)
    second = hash_embedding("parking opposition near transit", dimensions=16)

    assert first == second
    assert len(first) == 16
    assert abs(sum(value * value for value in first) - 1.0) < 0.0001


def test_embed_chunk_rows_populates_and_skips_existing_embeddings(tmp_path) -> None:
    db_path = tmp_path / "planlens.duckdb"
    init_db(db_path)
    provider = LocalHashEmbeddingProvider(dimensions=16)

    with connect(db_path) as conn:
        seed_chunks(conn)

        first_result = embed_chunk_rows(conn, provider=provider, batch_size=2)
        second_result = embed_chunk_rows(conn, provider=provider, batch_size=2)
        rows = conn.execute(
            """
            SELECT embedding_provider, embedding_model, embedding_dim, len(embedding)
            FROM chunk_embeddings
            ORDER BY chunk_id
            """
        ).fetchall()

    assert first_result.embedded_count == 2
    assert first_result.skipped_count == 0
    assert second_result.embedded_count == 0
    assert second_result.skipped_count == 2
    assert rows == [
        ("local_hash", "local-hash-v1", 16, 16),
        ("local_hash", "local-hash-v1", 16, 16),
    ]


def seed_chunks(conn) -> None:
    conn.execute(
        """
        INSERT INTO hearings (
            hearing_id,
            hearing_date,
            title,
            status,
            source_url
        )
        VALUES (
            'cpc-2025-12-18',
            DATE '2025-12-18',
            'Planning Commission',
            'scheduled',
            'https://sfplanning.org/cpc-hearing-archives'
        )
        """
    )
    conn.execute(
        """
        INSERT INTO source_documents (
            document_id,
            hearing_id,
            source_type,
            title,
            url
        )
        VALUES (
            'doc-test',
            'cpc-2025-12-18',
            'staff_report',
            'Staff Report',
            'https://sfplanning.org/doc-test.pdf'
        )
        """
    )
    conn.executemany(
        """
        INSERT INTO chunks (
            chunk_id,
            document_id,
            page_start,
            page_end,
            chunk_index,
            text,
            token_estimate,
            section_hint,
            citation_label
        )
        VALUES (?, 'doc-test', 1, 1, ?, ?, 20, 'Staff Report', 'Citation')
        """,
        [
            ("chunk-doc-test-0000", 0, "Parking concerns near transit"),
            ("chunk-doc-test-0001", 1, "CEQA analysis and shadow findings"),
        ],
    )
