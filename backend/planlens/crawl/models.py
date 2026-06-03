from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class ArchiveHearing:
    hearing_id: str
    hearing_date: date
    title: str
    status: str
    agenda_url: str | None
    minutes_url: str | None
    supporting_url: str | None
    source_url: str


@dataclass(frozen=True)
class SourceDocument:
    document_id: str
    hearing_id: str
    source_type: str
    title: str | None
    url: str
