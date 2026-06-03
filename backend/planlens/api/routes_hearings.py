from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..db import connect
from .deps import SettingsDep
from .schemas import AgendaItemSummary, HearingDetail, HearingSummary, SourceDocumentSummary

router = APIRouter(tags=["hearings"])


@router.get("/hearings", response_model=list[HearingSummary])
def list_hearings(settings: SettingsDep, limit: int = 50) -> list[HearingSummary]:
    with connect(settings.db_path) as conn:
        rows = conn.execute(
            """
            SELECT
                h.hearing_id,
                h.hearing_date,
                h.title,
                h.status,
                h.agenda_url,
                h.minutes_url,
                h.supporting_url,
                count(DISTINCT d.document_id) AS document_count,
                count(DISTINCT a.agenda_item_id) AS agenda_item_count
            FROM hearings h
            LEFT JOIN source_documents d ON d.hearing_id = h.hearing_id
            LEFT JOIN agenda_items a ON a.hearing_id = h.hearing_id
            GROUP BY
                h.hearing_id,
                h.hearing_date,
                h.title,
                h.status,
                h.agenda_url,
                h.minutes_url,
                h.supporting_url
            ORDER BY h.hearing_date DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

    return [
        HearingSummary(
            hearing_id=row[0],
            hearing_date=row[1],
            title=row[2],
            status=row[3],
            agenda_url=row[4],
            minutes_url=row[5],
            supporting_url=row[6],
            document_count=row[7],
            agenda_item_count=row[8],
        )
        for row in rows
    ]


@router.get("/hearings/{hearing_id}", response_model=HearingDetail)
def get_hearing(hearing_id: str, settings: SettingsDep) -> HearingDetail:
    with connect(settings.db_path) as conn:
        hearing = conn.execute(
            """
            SELECT
                hearing_id,
                hearing_date,
                title,
                status,
                agenda_url,
                minutes_url,
                supporting_url,
                source_url
            FROM hearings
            WHERE hearing_id = ?
            """,
            (hearing_id,),
        ).fetchone()
        if hearing is None:
            raise HTTPException(status_code=404, detail="Hearing not found.")

        documents = get_source_documents(conn, hearing_id)
        agenda_items = get_agenda_items_for_hearing(conn, hearing_id)

    return HearingDetail(
        hearing_id=hearing[0],
        hearing_date=hearing[1],
        title=hearing[2],
        status=hearing[3],
        agenda_url=hearing[4],
        minutes_url=hearing[5],
        supporting_url=hearing[6],
        source_url=hearing[7],
        document_count=len(documents),
        agenda_item_count=len(agenda_items),
        documents=documents,
        agenda_items=agenda_items,
    )


@router.get(
    "/hearings/{hearing_id}/agenda-items",
    response_model=list[AgendaItemSummary],
)
def list_hearing_agenda_items(
    hearing_id: str,
    settings: SettingsDep,
) -> list[AgendaItemSummary]:
    with connect(settings.db_path) as conn:
        exists = conn.execute(
            "SELECT 1 FROM hearings WHERE hearing_id = ?",
            (hearing_id,),
        ).fetchone()
        if exists is None:
            raise HTTPException(status_code=404, detail="Hearing not found.")
        return get_agenda_items_for_hearing(conn, hearing_id)


@router.get("/agenda-items/{agenda_item_id}", response_model=AgendaItemSummary)
def get_agenda_item(agenda_item_id: str, settings: SettingsDep) -> AgendaItemSummary:
    with connect(settings.db_path) as conn:
        row = conn.execute(
            """
            SELECT
                agenda_item_id,
                hearing_id,
                item_number,
                section,
                case_number,
                address,
                district,
                planner_name,
                planner_contact,
                project_description,
                entitlement_type,
                ceqa_status,
                preliminary_recommendation,
                raw_text,
                parser_confidence
            FROM agenda_items
            WHERE agenda_item_id = ?
            """,
            (agenda_item_id,),
        ).fetchone()

    if row is None:
        raise HTTPException(status_code=404, detail="Agenda item not found.")
    return agenda_item_from_row(row)


def get_source_documents(conn, hearing_id: str) -> list[SourceDocumentSummary]:
    rows = conn.execute(
        """
        SELECT
            document_id,
            hearing_id,
            source_type,
            title,
            url,
            local_path,
            file_size_bytes,
            downloaded_at
        FROM source_documents
        WHERE hearing_id = ?
        ORDER BY source_type, title NULLS LAST, document_id
        """,
        (hearing_id,),
    ).fetchall()
    return [
        SourceDocumentSummary(
            document_id=row[0],
            hearing_id=row[1],
            source_type=row[2],
            title=row[3],
            url=row[4],
            local_path=row[5],
            file_size_bytes=row[6],
            downloaded_at=row[7].isoformat() if row[7] else None,
        )
        for row in rows
    ]


def get_agenda_items_for_hearing(conn, hearing_id: str) -> list[AgendaItemSummary]:
    rows = conn.execute(
        """
        SELECT
            agenda_item_id,
            hearing_id,
            item_number,
            section,
            case_number,
            address,
            district,
            planner_name,
            planner_contact,
            project_description,
            entitlement_type,
            ceqa_status,
            preliminary_recommendation,
            raw_text,
            parser_confidence
        FROM agenda_items
        WHERE hearing_id = ?
        ORDER BY
            try_cast(regexp_extract(item_number, '^[0-9]+') AS INTEGER) NULLS LAST,
            item_number
        """,
        (hearing_id,),
    ).fetchall()
    return [agenda_item_from_row(row) for row in rows]


def agenda_item_from_row(row) -> AgendaItemSummary:
    return AgendaItemSummary(
        agenda_item_id=row[0],
        hearing_id=row[1],
        item_number=row[2],
        section=row[3],
        case_number=row[4],
        address=row[5],
        district=row[6],
        planner_name=row[7],
        planner_contact=row[8],
        project_description=row[9],
        entitlement_type=row[10],
        ceqa_status=row[11],
        preliminary_recommendation=row[12],
        raw_text=row[13],
        parser_confidence=row[14],
    )
