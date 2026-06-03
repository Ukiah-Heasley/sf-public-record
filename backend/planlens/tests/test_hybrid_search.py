from __future__ import annotations

from backend.planlens.config import Settings
from backend.planlens.crawl.supporting_pages import make_source_document, upsert_source_documents
from backend.planlens.db import connect, init_db
from backend.planlens.embed.embeddings import LocalHashEmbeddingProvider, embed_chunk_rows
from backend.planlens.search.hybrid import hybrid_search, lexical_search


def test_hybrid_search_ranks_planning_evidence_with_embeddings(tmp_path) -> None:
    db_path = tmp_path / "planlens.duckdb"
    settings = Settings(
        db_path=db_path,
        raw_dir=tmp_path / "raw",
        embedding_provider="local_hash",
        embedding_model="local-hash-v1",
        embedding_dimensions=64,
    )
    init_db(db_path)

    with connect(db_path) as conn:
        seed_search_chunks(conn)
        embed_chunk_rows(conn, provider=LocalHashEmbeddingProvider(dimensions=64))

    response = hybrid_search(
        db_path=db_path,
        settings=settings,
        query="parking opposition near transit",
        limit=2,
    )

    assert len(response.results) == 2
    assert response.results[0].chunk_id == "chunk-doc-staff-0000"
    assert response.results[0].score > response.results[1].score
    assert response.results[0].citation_label == "Dec 18, 2025 Staff Report - p. 2"


def test_lexical_search_works_without_embeddings(tmp_path) -> None:
    db_path = tmp_path / "planlens.duckdb"
    init_db(db_path)

    with connect(db_path) as conn:
        seed_search_chunks(conn)

    response = lexical_search(
        db_path=db_path,
        query="CEQA shadow",
        document_types=["staff_report"],
        limit=1,
    )

    assert len(response.results) == 1
    assert response.results[0].chunk_id == "chunk-doc-staff-0001"
    assert response.results[0].vector_score == 0


def seed_search_chunks(conn) -> None:
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
    staff_report = make_source_document(
        hearing_id="cpc-2025-12-18",
        source_type="staff_report",
        title="Staff Report 2025-000123",
        url="https://sfplanning.org/docs/2025-000123-staff-report.pdf",
    )
    upsert_source_documents(conn, [staff_report])
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
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                "chunk-doc-staff-0000",
                staff_report.document_id,
                2,
                2,
                0,
                "Neighbors raised concerns about reduced parking near the Muni station.",
                18,
                "Public Comment",
                "Dec 18, 2025 Staff Report - p. 2",
            ),
            (
                "chunk-doc-staff-0001",
                staff_report.document_id,
                4,
                4,
                1,
                "The CEQA analysis found no significant shadow impacts.",
                14,
                "CEQA",
                "Dec 18, 2025 Staff Report - p. 4",
            ),
        ],
    )
