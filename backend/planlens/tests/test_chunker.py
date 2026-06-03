from __future__ import annotations

from backend.planlens.config import Settings
from backend.planlens.crawl.supporting_pages import make_source_document, upsert_source_documents
from backend.planlens.db import connect, init_db
from backend.planlens.parse.chunker import build_document_chunks, chunk_parsed_documents


def test_build_document_chunks_preserves_sections_and_citations(tmp_path) -> None:
    db_path = tmp_path / "planlens.duckdb"
    init_db(db_path)

    with connect(db_path) as conn:
        document_id = seed_staff_report(conn)
        pages = conn.execute(
            """
            SELECT
                d.document_id,
                h.hearing_date,
                d.source_type,
                d.title,
                p.page_number,
                p.text,
                p.extraction_quality
            FROM source_documents d
            JOIN hearings h ON h.hearing_id = d.hearing_id
            JOIN pages p ON p.document_id = d.document_id
            WHERE d.document_id = ?
            ORDER BY p.page_number
            """,
            (document_id,),
        ).fetchall()

    from backend.planlens.parse.chunker import PageText

    chunks = build_document_chunks(
        pages=[
            PageText(
                document_id=row[0],
                hearing_date=row[1],
                source_type=row[2],
                title=row[3],
                page_number=row[4],
                text=row[5],
                extraction_quality=row[6],
            )
            for row in pages
        ],
        target_tokens=60,
        max_tokens=90,
        overlap_tokens=10,
    )

    assert chunks
    assert chunks[0].document_id == document_id
    assert chunks[0].citation_label.startswith("Dec 18, 2025 Staff Report - p")
    assert any(chunk.section_hint == "Project Description" for chunk in chunks)
    assert any(chunk.section_hint == "Public Comment" for chunk in chunks)


def test_chunk_parsed_documents_is_idempotent_and_clears_stale_embeddings(tmp_path) -> None:
    db_path = tmp_path / "planlens.duckdb"
    settings = Settings(
        db_path=db_path,
        raw_dir=tmp_path / "raw",
        chunk_target_tokens=70,
        chunk_max_tokens=90,
        chunk_overlap_tokens=10,
    )
    init_db(db_path)

    with connect(db_path) as conn:
        document_id = seed_staff_report(conn)

        first_result = chunk_parsed_documents(conn, settings=settings)
        first_chunk_ids = [
            row[0]
            for row in conn.execute(
                "SELECT chunk_id FROM chunks ORDER BY chunk_id"
            ).fetchall()
        ]
        conn.execute(
            """
            INSERT INTO chunk_embeddings (
                chunk_id,
                embedding_provider,
                embedding_model,
                embedding_dim,
                embedding
            )
            VALUES (?, 'local_hash', 'local-hash-v1', 2, [1.0, 0.0])
            """,
            (first_chunk_ids[0],),
        )

        second_result = chunk_parsed_documents(conn, settings=settings)
        second_chunk_ids = [
            row[0]
            for row in conn.execute(
                "SELECT chunk_id FROM chunks ORDER BY chunk_id"
            ).fetchall()
        ]
        stale_embedding_count = conn.execute("SELECT count(*) FROM chunk_embeddings").fetchone()[0]

    assert first_result.document_count == 1
    assert first_result.chunk_count > 0
    assert second_result.chunk_count == first_result.chunk_count
    assert second_chunk_ids == first_chunk_ids
    assert stale_embedding_count == 0
    assert all(chunk_id.startswith(f"chunk-{document_id}-") for chunk_id in second_chunk_ids)


def seed_staff_report(conn) -> str:
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
    document = make_source_document(
        hearing_id="cpc-2025-12-18",
        source_type="staff_report",
        title="Staff Report",
        url="https://sfplanning.org/docs/2025-000123-staff-report.pdf",
    )
    upsert_source_documents(conn, [document])
    conn.executemany(
        """
        INSERT INTO pages (
            page_id,
            document_id,
            page_number,
            text,
            char_count,
            extraction_method,
            extraction_quality
        )
        VALUES (?, ?, ?, ?, ?, 'pymupdf', 'good')
        """,
        [
            (
                "page-staff-0001",
                document.document_id,
                1,
                """
                PROJECT DESCRIPTION

                The project would add 42 dwelling units near a Muni rail station.
                It requests Conditional Use Authorization and includes reduced parking.

                STAFF ANALYSIS

                The proposal advances housing policy goals and improves the site design.
                """,
                360,
            ),
            (
                "page-staff-0002",
                document.document_id,
                2,
                """
                PUBLIC COMMENT

                Neighbors raised concerns about parking, loading, and traffic near transit.
                Staff recommends approval with conditions.
                """,
                180,
            ),
        ],
    )
    return document.document_id
