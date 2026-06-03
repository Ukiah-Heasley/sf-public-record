from __future__ import annotations

from datetime import date

from backend.planlens.crawl.supporting_pages import make_source_document, upsert_source_documents
from backend.planlens.db import connect, init_db
from backend.planlens.parse.agenda_parser import (
    case_number_candidates,
    parse_agenda_documents,
    parse_agenda_items_from_text,
)

AGENDA_TEXT = """
REGULAR CALENDAR

1. 2025-000123CUA 123 Main Street
District 5
Planner: Jane Planner, jane.planner@sfgov.org, (415) 555-1212
Project Description: The proposal would construct 42 dwelling units near transit.
CEQA Status: Exempt
Preliminary Recommendation: Approve with Conditions
Conditional Use Authorization

2. Director's Report
No case number is listed for this informational item.
"""


def test_parse_agenda_items_from_text_extracts_core_fields() -> None:
    items = parse_agenda_items_from_text(AGENDA_TEXT, hearing_id="cpc-2025-12-18")

    assert len(items) == 2
    first = items[0]
    assert first.item_number == "1"
    assert first.section == "REGULAR CALENDAR"
    assert first.case_number == "2025-000123CUA"
    assert first.case_suffix == "CUA"
    assert first.address == "123 Main Street"
    assert first.district == "5"
    assert first.planner_name == "Jane Planner"
    assert first.planner_contact == "jane.planner@sfgov.org, (415) 555-1212"
    assert first.project_description == (
        "The proposal would construct 42 dwelling units near transit."
    )
    assert first.entitlement_type == "Conditional Use Authorization"
    assert first.ceqa_status == "Exempt"
    assert first.preliminary_recommendation == "Approve with Conditions"
    assert first.parser_confidence > 0.8

    second = items[1]
    assert second.item_number == "2"
    assert second.case_number is None
    assert "Director's Report" in second.raw_text
    assert second.parser_confidence > 0


def test_case_number_candidates_include_base_case_number() -> None:
    assert case_number_candidates("2025-000123CUA") == (
        "2025-000123CUA",
        "2025-000123",
    )


def test_parse_agenda_documents_upserts_items_and_links_matching_documents(tmp_path) -> None:
    db_path = tmp_path / "planlens.duckdb"
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
        agenda_document = make_source_document(
            hearing_id="cpc-2025-12-18",
            source_type="agenda",
            title="Agenda",
            url="https://sfplanning.org/agenda.pdf",
        )
        staff_report = make_source_document(
            hearing_id="cpc-2025-12-18",
            source_type="staff_report",
            title="2025-000123 Staff Report",
            url="https://sfplanning.org/docs/2025-000123-staff-report.pdf",
        )
        upsert_source_documents(conn, [agenda_document, staff_report])
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
                'page-agenda-0001',
                ?,
                1,
                ?,
                ?,
                'pymupdf',
                'good'
            )
            """,
            (agenda_document.document_id, AGENDA_TEXT, len(AGENDA_TEXT)),
        )

        first_result = parse_agenda_documents(conn)
        second_result = parse_agenda_documents(conn)
        agenda_rows = conn.execute(
            """
            SELECT item_number, case_number, raw_text
            FROM agenda_items
            ORDER BY item_number
            """
        ).fetchall()
        link_rows = conn.execute(
            """
            SELECT document_id, relationship, confidence
            FROM document_links
            """
        ).fetchall()

    assert first_result.agenda_item_count == 2
    assert first_result.linked_document_count == 1
    assert second_result.agenda_item_count == 2
    assert second_result.linked_document_count == 1
    assert agenda_rows[0][0] == "1"
    assert agenda_rows[0][1] == "2025-000123CUA"
    assert agenda_rows[1][0] == "2"
    assert "Director's Report" in agenda_rows[1][2]
    assert link_rows == [(staff_report.document_id, "case_number_match", 1.0)]


def test_parse_agenda_items_extracts_proposed_continuance_date() -> None:
    text = """
    REGULAR CALENDAR

    3. 2025-000456CUA 500 Market Street
    Continued from: November 6, 2025
    Proposed Continuance Date: December 18, 2025
    """

    items = parse_agenda_items_from_text(text, hearing_id="cpc-2025-12-18")

    assert items[0].continued_from == "November 6, 2025"
    assert items[0].proposed_continuance_date == date(2025, 12, 18)
