from __future__ import annotations

import duckdb
from backend.planlens.crawl.supporting_pages import (
    HearingDocumentLinks,
    documents_from_archive_links,
    parse_supporting_page,
    upsert_source_documents,
)

SUPPORTING_HTML = """
<html>
  <body>
    <h2>Staff Report</h2>
    <ul>
      <li><a href="/docs/staff-report.pdf">Staff Report - 123 Main Street</a></li>
    </ul>

    <h2>Presentation(s)</h2>
    <p><a href="presentation.pdf">Planning Department Presentation</a></p>

    <h2>Correspondence Received Before Hearing</h2>
    <p><a href="/docs/pre-correspondence.pdf">Public Correspondence</a></p>

    <h2>Correspondence Received At Hearing</h2>
    <p><a href="/docs/at-hearing-correspondence.pdf">At Hearing Correspondence</a></p>

    <h2>Other</h2>
    <p><a href="/docs/notice.pdf">Public Notice</a></p>
    <p><a href="/about">About the department</a></p>
  </body>
</html>
"""


def test_parse_supporting_page_classifies_document_sections() -> None:
    documents = parse_supporting_page(
        html=SUPPORTING_HTML,
        source_url="https://sfplanning.org/hearings/2025-12-18/supporting",
        hearing_id="cpc-2025-12-18",
    )

    by_url = {document.url: document for document in documents}

    assert len(documents) == 5
    assert (
        by_url["https://sfplanning.org/docs/staff-report.pdf"].source_type == "staff_report"
    )
    assert (
        by_url[
            "https://sfplanning.org/hearings/2025-12-18/presentation.pdf"
        ].source_type
        == "presentation"
    )
    assert (
        by_url["https://sfplanning.org/docs/pre-correspondence.pdf"].source_type
        == "correspondence_pre_hearing"
    )
    assert (
        by_url["https://sfplanning.org/docs/at-hearing-correspondence.pdf"].source_type
        == "correspondence_at_hearing"
    )
    assert by_url["https://sfplanning.org/docs/notice.pdf"].source_type == "notice"


def test_documents_from_archive_links_registers_agenda_and_minutes() -> None:
    documents = documents_from_archive_links(
        HearingDocumentLinks(
            hearing_id="cpc-2025-12-18",
            agenda_url="https://sfplanning.org/agenda.pdf",
            minutes_url="https://sfplanning.org/minutes.pdf",
            supporting_url=None,
        )
    )

    assert [(document.source_type, document.title) for document in documents] == [
        ("agenda", "Agenda"),
        ("minutes", "Minutes"),
    ]


def test_upsert_source_documents_is_idempotent() -> None:
    documents = parse_supporting_page(
        html=SUPPORTING_HTML,
        source_url="https://sfplanning.org/hearings/2025-12-18/supporting",
        hearing_id="cpc-2025-12-18",
    )
    conn = duckdb.connect(":memory:")
    conn.execute(
        """
        CREATE TABLE hearings (
            hearing_id VARCHAR PRIMARY KEY,
            hearing_date DATE NOT NULL,
            title VARCHAR,
            status VARCHAR,
            agenda_url VARCHAR,
            minutes_url VARCHAR,
            supporting_url VARCHAR,
            source_url VARCHAR NOT NULL,
            crawled_at TIMESTAMP DEFAULT current_timestamp
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE source_documents (
            document_id VARCHAR PRIMARY KEY,
            hearing_id VARCHAR,
            source_type VARCHAR NOT NULL,
            title VARCHAR,
            url VARCHAR NOT NULL,
            local_path VARCHAR,
            sha256 VARCHAR,
            mime_type VARCHAR,
            file_size_bytes BIGINT,
            downloaded_at TIMESTAMP
        )
        """
    )
    conn.execute(
        """
        INSERT INTO hearings (
            hearing_id,
            hearing_date,
            title,
            status,
            source_url
        )
        VALUES ('cpc-2025-12-18', DATE '2025-12-18', 'Planning Commission', 'scheduled', 'x')
        """
    )

    upsert_source_documents(conn, documents)
    upsert_source_documents(conn, documents)

    assert conn.execute("SELECT count(*) FROM source_documents").fetchone()[0] == 5
