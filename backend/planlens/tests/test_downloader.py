from __future__ import annotations

import hashlib

import httpx
from backend.planlens.config import Settings
from backend.planlens.crawl.downloader import download_pdf_documents
from backend.planlens.crawl.supporting_pages import (
    make_source_document,
    upsert_source_documents,
)
from backend.planlens.db import connect, init_db


def test_download_pdf_documents_stores_metadata_and_skips_existing(tmp_path) -> None:
    db_path = tmp_path / "planlens.duckdb"
    raw_dir = tmp_path / "raw"
    settings = Settings(db_path=db_path, raw_dir=raw_dir, crawl_delay_seconds=0)
    init_db(db_path)

    pdf_content = b"%PDF-1.7\nexample pdf\n%%EOF"
    request_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal request_count
        request_count += 1
        assert str(request.url) == "https://sfplanning.org/docs/staff-report.pdf"
        return httpx.Response(
            200,
            headers={"content-type": "application/pdf"},
            content=pdf_content,
        )

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
        upsert_source_documents(
            conn,
            [
                make_source_document(
                    hearing_id="cpc-2025-12-18",
                    source_type="staff_report",
                    title="Staff Report",
                    url="https://sfplanning.org/docs/staff-report.pdf",
                )
            ],
        )

        client = httpx.Client(transport=httpx.MockTransport(handler))
        first_result = download_pdf_documents(
            conn=conn,
            settings=settings,
            client=client,
            sleep=lambda _: None,
        )
        second_result = download_pdf_documents(
            conn=conn,
            settings=settings,
            client=client,
            sleep=lambda _: None,
        )
        client.close()

        row = conn.execute(
            """
            SELECT local_path, sha256, mime_type, file_size_bytes
            FROM source_documents
            """
        ).fetchone()

    assert first_result.downloaded_count == 1
    assert first_result.skipped_count == 0
    assert second_result.downloaded_count == 0
    assert second_result.skipped_count == 1
    assert request_count == 1

    local_path, sha256, mime_type, file_size_bytes = row
    assert (tmp_path / "raw" / "pdfs").joinpath(local_path.rsplit("/", maxsplit=1)[-1]).exists()
    assert sha256 == hashlib.sha256(pdf_content).hexdigest()
    assert mime_type == "application/pdf"
    assert file_size_bytes == len(pdf_content)
