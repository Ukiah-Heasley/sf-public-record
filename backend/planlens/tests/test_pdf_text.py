from __future__ import annotations

import pymupdf
from backend.planlens.crawl.supporting_pages import (
    make_source_document,
    upsert_source_documents,
)
from backend.planlens.db import connect, init_db
from backend.planlens.parse.pdf_text import (
    extract_pdf_pages,
    extraction_quality,
    parse_pdf_documents,
)


def test_extraction_quality_uses_char_count_thresholds() -> None:
    assert extraction_quality(500) == "good"
    assert extraction_quality(100) == "medium"
    assert extraction_quality(99) == "poor"


def test_extract_pdf_pages_reads_text_and_empty_pages(tmp_path) -> None:
    pdf_path = tmp_path / "sample.pdf"
    pdf = pymupdf.open()
    first_page = pdf.new_page()
    first_page.insert_textbox((72, 72, 540, 540), "Planning agenda " * 80)
    pdf.new_page()
    pdf.save(pdf_path)
    pdf.close()

    pages = extract_pdf_pages(document_id="doc-test", local_path=pdf_path)

    assert len(pages) == 2
    assert pages[0].page_id == "page-doc-test-0001"
    assert pages[0].document_id == "doc-test"
    assert pages[0].page_number == 1
    assert "Planning agenda" in pages[0].text
    assert pages[0].extraction_method == "pymupdf"
    assert pages[0].extraction_quality in {"medium", "good"}
    assert pages[1].page_number == 2
    assert pages[1].char_count == 0
    assert pages[1].extraction_quality == "poor"


def test_parse_pdf_documents_replaces_document_pages(tmp_path) -> None:
    db_path = tmp_path / "planlens.duckdb"
    pdf_path = tmp_path / "agenda.pdf"
    pdf = pymupdf.open()
    page = pdf.new_page()
    page.insert_text((72, 72), "1. 2025-000001CUA 123 Main Street")
    pdf.save(pdf_path)
    pdf.close()

    init_db(db_path)
    with connect(db_path) as conn:
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
            source_type="agenda",
            title="Agenda",
            url="https://sfplanning.org/agenda.pdf",
        )
        upsert_source_documents(conn, [document])
        conn.execute(
            """
            UPDATE source_documents
            SET local_path = ?, mime_type = 'application/pdf'
            WHERE document_id = ?
            """,
            (pdf_path.as_posix(), document.document_id),
        )

        first_result = parse_pdf_documents(conn)
        second_result = parse_pdf_documents(conn)
        rows = conn.execute(
            """
            SELECT document_id, page_number, extraction_method
            FROM pages
            WHERE document_id = ?
            """,
            (document.document_id,),
        ).fetchall()

    assert first_result.parsed_document_count == 1
    assert first_result.page_count == 1
    assert second_result.parsed_document_count == 1
    assert second_result.page_count == 1
    assert rows == [(document.document_id, 1, "pymupdf")]
