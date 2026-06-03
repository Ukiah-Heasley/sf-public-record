from __future__ import annotations

from backend.planlens.api.main import create_app
from backend.planlens.config import Settings
from backend.planlens.crawl.supporting_pages import make_source_document, upsert_source_documents
from backend.planlens.db import connect
from fastapi.testclient import TestClient


def test_api_health_dashboard_hearing_and_search(tmp_path) -> None:
    db_path = tmp_path / "planlens.duckdb"
    settings = Settings(db_path=db_path, raw_dir=tmp_path / "raw")
    app = create_app(settings)
    seed_api_data(db_path)

    client = TestClient(app)

    assert client.get("/health").json() == {"status": "ok"}

    dashboard = client.get("/dashboard").json()
    assert dashboard["summary"]["hearings_indexed"] == 1
    assert dashboard["summary"]["pages_parsed"] == 1
    assert dashboard["summary"]["agenda_items_extracted"] == 1
    assert dashboard["document_types"] == [{"source_type": "staff_report", "count": 1}]

    hearings = client.get("/hearings").json()
    assert len(hearings) == 1
    assert hearings[0]["hearing_id"] == "cpc-2025-12-18"
    assert hearings[0]["document_count"] == 1

    hearing = client.get("/hearings/cpc-2025-12-18").json()
    assert hearing["agenda_item_count"] == 1
    assert hearing["documents"][0]["source_type"] == "staff_report"
    assert hearing["agenda_items"][0]["case_number"] == "2025-000123CUA"

    agenda_items = client.get("/hearings/cpc-2025-12-18/agenda-items").json()
    assert agenda_items[0]["item_number"] == "1"

    search = client.post(
        "/search",
        json={
            "query": "parking opposition near transit",
            "limit": 1,
            "lexical_only": True,
        },
    ).json()
    assert search["query"] == "parking opposition near transit"
    assert search["answer_stub"] == "Answer generation not implemented yet."
    assert search["results"][0]["chunk_id"] == "chunk-doc-api-0000"


def test_api_returns_404_for_missing_hearing(tmp_path) -> None:
    settings = Settings(db_path=tmp_path / "planlens.duckdb", raw_dir=tmp_path / "raw")
    client = TestClient(create_app(settings))

    response = client.get("/hearings/missing")

    assert response.status_code == 404


def seed_api_data(db_path) -> None:
    with connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO hearings (
                hearing_id,
                hearing_date,
                title,
                status,
                agenda_url,
                source_url
            )
            VALUES (
                'cpc-2025-12-18',
                DATE '2025-12-18',
                'Planning Commission',
                'scheduled',
                'https://sfplanning.org/agenda.pdf',
                'https://sfplanning.org/cpc-hearing-archives'
            )
            """
        )
        document = make_source_document(
            hearing_id="cpc-2025-12-18",
            source_type="staff_report",
            title="Staff Report 2025-000123",
            url="https://sfplanning.org/docs/2025-000123-staff-report.pdf",
        )
        upsert_source_documents(conn, [document])
        conn.execute(
            """
            UPDATE source_documents
            SET local_path = 'data/raw/pdfs/doc-api.pdf',
                mime_type = 'application/pdf',
                file_size_bytes = 100,
                downloaded_at = now()
            WHERE document_id = ?
            """,
            (document.document_id,),
        )
        conn.execute(
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
            VALUES (
                'page-doc-api-0001',
                ?,
                1,
                'Parking concerns near transit.',
                30,
                'pymupdf',
                'poor'
            )
            """,
            (document.document_id,),
        )
        conn.execute(
            """
            INSERT INTO agenda_items (
                agenda_item_id,
                hearing_id,
                item_number,
                case_number,
                raw_text,
                parser_confidence
            )
            VALUES (
                'agenda-api-1',
                'cpc-2025-12-18',
                '1',
                '2025-000123CUA',
                '1. 2025-000123CUA 123 Main Street',
                0.4
            )
            """
        )
        conn.execute(
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
            VALUES (
                'chunk-doc-api-0000',
                ?,
                1,
                1,
                0,
                'Neighbors raised parking opposition near transit.',
                12,
                'Public Comment',
                'Dec 18, 2025 Staff Report - p. 1'
            )
            """,
            (document.document_id,),
        )
