from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field


class HearingSummary(BaseModel):
    hearing_id: str
    hearing_date: date
    title: str | None = None
    status: str | None = None
    agenda_url: str | None = None
    minutes_url: str | None = None
    supporting_url: str | None = None
    document_count: int = 0
    agenda_item_count: int = 0


class SourceDocumentSummary(BaseModel):
    document_id: str
    hearing_id: str | None = None
    source_type: str
    title: str | None = None
    url: str
    local_path: str | None = None
    file_size_bytes: int | None = None
    downloaded_at: str | None = None


class AgendaItemSummary(BaseModel):
    agenda_item_id: str
    hearing_id: str
    item_number: str | None = None
    section: str | None = None
    case_number: str | None = None
    address: str | None = None
    district: str | None = None
    planner_name: str | None = None
    planner_contact: str | None = None
    project_description: str | None = None
    entitlement_type: str | None = None
    ceqa_status: str | None = None
    preliminary_recommendation: str | None = None
    raw_text: str | None = None
    parser_confidence: float | None = None


class HearingDetail(HearingSummary):
    source_url: str
    documents: list[SourceDocumentSummary] = Field(default_factory=list)
    agenda_items: list[AgendaItemSummary] = Field(default_factory=list)


class DashboardSummary(BaseModel):
    hearings_indexed: int
    pdfs_downloaded: int
    pages_parsed: int
    agenda_items_extracted: int
    staff_reports_linked: int
    chunks_indexed: int
    embeddings_indexed: int


class DocumentTypeCount(BaseModel):
    source_type: str
    count: int


class ExtractionHealth(BaseModel):
    extraction_quality: str
    page_count: int


class OppositionTheme(BaseModel):
    theme: str
    mention_count: int


class RecentActivityItem(BaseModel):
    hearing_id: str
    hearing_date: date
    title: str | None = None
    status: str | None = None
    document_count: int = 0
    page_count: int = 0
    agenda_item_count: int = 0


class DashboardResponse(BaseModel):
    summary: DashboardSummary
    recent_activity: list[RecentActivityItem]
    document_types: list[DocumentTypeCount]
    extraction_health: list[ExtractionHealth]
    opposition_themes: list[OppositionTheme]


class SearchRequest(BaseModel):
    query: str
    date_start: date | None = None
    date_end: date | None = None
    document_types: list[str] | None = None
    limit: int = 10
    lexical_only: bool = False


class SearchResultItem(BaseModel):
    chunk_id: str
    document_id: str
    title: str | None = None
    source_type: str
    hearing_date: date | None = None
    page_start: int | None = None
    page_end: int | None = None
    citation_label: str | None = None
    text: str
    score: float
    url: str


class SearchResponse(BaseModel):
    query: str
    answer_stub: str
    results: list[SearchResultItem]
