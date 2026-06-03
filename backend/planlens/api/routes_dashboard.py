from __future__ import annotations

from fastapi import APIRouter

from ..db import connect
from .deps import SettingsDep
from .schemas import (
    DashboardResponse,
    DashboardSummary,
    DocumentTypeCount,
    ExtractionHealth,
    OppositionTheme,
    RecentActivityItem,
)

router = APIRouter(tags=["dashboard"])

THEMES = {
    "parking": ("parking", "garage", "vehicle", "traffic"),
    "delay": ("continued", "continuance", "delay", "postpone"),
    "housing": ("housing", "dwelling", "residential", "unit", "units"),
    "ceqa": ("ceqa", "environmental", "shadow"),
    "transit": ("transit", "muni", "bus", "rail", "station"),
    "opposition": ("opposition", "concern", "objection", "neighbor", "comment"),
}


@router.get("/dashboard/summary", response_model=DashboardSummary)
def get_dashboard_summary(settings: SettingsDep) -> DashboardSummary:
    with connect(settings.db_path) as conn:
        return dashboard_summary(conn)


@router.get("/dashboard/recent-activity", response_model=list[RecentActivityItem])
def get_recent_activity(settings: SettingsDep, limit: int = 8) -> list[RecentActivityItem]:
    with connect(settings.db_path) as conn:
        return recent_activity(conn, limit=limit)


@router.get("/dashboard/opposition-themes", response_model=list[OppositionTheme])
def get_opposition_themes(settings: SettingsDep) -> list[OppositionTheme]:
    with connect(settings.db_path) as conn:
        return opposition_themes(conn)


@router.get("/dashboard", response_model=DashboardResponse)
def get_dashboard(settings: SettingsDep) -> DashboardResponse:
    with connect(settings.db_path) as conn:
        return DashboardResponse(
            summary=dashboard_summary(conn),
            recent_activity=recent_activity(conn),
            document_types=document_types(conn),
            extraction_health=extraction_health(conn),
            opposition_themes=opposition_themes(conn),
        )


def dashboard_summary(conn) -> DashboardSummary:
    row = conn.execute(
        """
        SELECT
            (SELECT count(*) FROM hearings),
            (SELECT count(*) FROM source_documents WHERE local_path IS NOT NULL),
            (SELECT count(*) FROM pages),
            (SELECT count(*) FROM agenda_items),
            (
                SELECT count(*)
                FROM document_links l
                JOIN source_documents d ON d.document_id = l.document_id
                WHERE d.source_type = 'staff_report'
            ),
            (SELECT count(*) FROM chunks),
            (SELECT count(*) FROM chunk_embeddings)
        """
    ).fetchone()
    return DashboardSummary(
        hearings_indexed=row[0],
        pdfs_downloaded=row[1],
        pages_parsed=row[2],
        agenda_items_extracted=row[3],
        staff_reports_linked=row[4],
        chunks_indexed=row[5],
        embeddings_indexed=row[6],
    )


def recent_activity(conn, limit: int = 8) -> list[RecentActivityItem]:
    rows = conn.execute(
        """
        SELECT
            h.hearing_id,
            h.hearing_date,
            h.title,
            h.status,
            count(DISTINCT d.document_id) AS document_count,
            count(DISTINCT p.page_id) AS page_count,
            count(DISTINCT a.agenda_item_id) AS agenda_item_count
        FROM hearings h
        LEFT JOIN source_documents d ON d.hearing_id = h.hearing_id
        LEFT JOIN pages p ON p.document_id = d.document_id
        LEFT JOIN agenda_items a ON a.hearing_id = h.hearing_id
        GROUP BY h.hearing_id, h.hearing_date, h.title, h.status
        ORDER BY h.hearing_date DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    return [
        RecentActivityItem(
            hearing_id=row[0],
            hearing_date=row[1],
            title=row[2],
            status=row[3],
            document_count=row[4],
            page_count=row[5],
            agenda_item_count=row[6],
        )
        for row in rows
    ]


def document_types(conn) -> list[DocumentTypeCount]:
    rows = conn.execute(
        """
        SELECT source_type, count(*)
        FROM source_documents
        GROUP BY source_type
        ORDER BY count(*) DESC, source_type
        """
    ).fetchall()
    return [DocumentTypeCount(source_type=row[0], count=row[1]) for row in rows]


def extraction_health(conn) -> list[ExtractionHealth]:
    rows = conn.execute(
        """
        SELECT coalesce(extraction_quality, 'unknown'), count(*)
        FROM pages
        GROUP BY coalesce(extraction_quality, 'unknown')
        ORDER BY count(*) DESC
        """
    ).fetchall()
    return [ExtractionHealth(extraction_quality=row[0], page_count=row[1]) for row in rows]


def opposition_themes(conn) -> list[OppositionTheme]:
    rows = conn.execute("SELECT lower(text) FROM chunks").fetchall()
    text = "\n".join(row[0] or "" for row in rows)
    themes: list[OppositionTheme] = []
    for theme, terms in THEMES.items():
        count = sum(text.count(term) for term in terms)
        themes.append(OppositionTheme(theme=theme, mention_count=count))
    themes.sort(key=lambda item: item.mention_count, reverse=True)
    return themes
