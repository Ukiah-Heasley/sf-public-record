from __future__ import annotations

import hashlib
import re
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urljoin, urlparse

import duckdb
import httpx
from bs4 import BeautifulSoup
from bs4.element import Tag

from ..config import Settings
from ..db import connect
from .models import SourceDocument

DOCUMENT_SOURCE_TYPES = {
    "agenda",
    "minutes",
    "staff_report",
    "presentation",
    "correspondence_pre_hearing",
    "correspondence_at_hearing",
    "notice",
    "other",
}

GENERIC_LINK_TITLES = {
    "",
    "download",
    "download pdf",
    "pdf",
    "view",
    "view document",
    "view pdf",
}

PDF_URL_RE = re.compile(r"\.pdf(?:$|[?#])", re.IGNORECASE)
SECTION_LABEL_TAGS = {"h1", "h2", "h3", "h4", "h5", "h6", "strong", "b", "th"}
LINK_CONTEXT_TAGS = ["li", "p", "tr", "td", "div", "section"]


@dataclass(frozen=True)
class HearingDocumentLinks:
    hearing_id: str
    agenda_url: str | None
    minutes_url: str | None
    supporting_url: str | None


@dataclass(frozen=True)
class CrawlSupportingResult:
    hearing_count: int
    parsed_document_count: int
    upserted_document_count: int
    snapshot_paths: tuple[Path, ...]


def crawl_supporting_pages(
    db_path: Path | str,
    settings: Settings,
    limit: int | None = 50,
    hearing_id: str | None = None,
) -> CrawlSupportingResult:
    """Fetch supporting pages and register source documents for known hearings."""
    with connect(db_path) as conn:
        hearings = list_hearing_document_links(conn, limit=limit, hearing_id=hearing_id)

    documents: list[SourceDocument] = []
    snapshot_paths: list[Path] = []

    for hearing in hearings:
        documents.extend(documents_from_archive_links(hearing))

        if hearing.supporting_url:
            html = fetch_supporting_page_html(
                source_url=hearing.supporting_url,
                user_agent=settings.user_agent,
            )
            snapshot_paths.append(
                save_supporting_html_snapshot(
                    html=html,
                    html_dir=settings.html_dir,
                    hearing_id=hearing.hearing_id,
                )
            )
            documents.extend(
                parse_supporting_page(
                    html=html,
                    source_url=hearing.supporting_url,
                    hearing_id=hearing.hearing_id,
                )
            )

            if settings.crawl_delay_seconds > 0:
                time.sleep(settings.crawl_delay_seconds)

    documents = dedupe_source_documents(documents)

    with connect(db_path) as conn:
        upsert_source_documents(conn, documents)

    return CrawlSupportingResult(
        hearing_count=len(hearings),
        parsed_document_count=len(documents),
        upserted_document_count=len(documents),
        snapshot_paths=tuple(snapshot_paths),
    )


def list_hearing_document_links(
    conn: duckdb.DuckDBPyConnection,
    limit: int | None = 50,
    hearing_id: str | None = None,
) -> list[HearingDocumentLinks]:
    filters = [
        "(agenda_url IS NOT NULL OR minutes_url IS NOT NULL OR supporting_url IS NOT NULL)"
    ]
    params: list[object] = []

    if hearing_id:
        filters.append("hearing_id = ?")
        params.append(hearing_id)

    query = f"""
        SELECT hearing_id, agenda_url, minutes_url, supporting_url
        FROM hearings
        WHERE {" AND ".join(filters)}
        ORDER BY hearing_date DESC, hearing_id
    """
    if limit is not None:
        query += " LIMIT ?"
        params.append(limit)

    rows = conn.execute(query, params).fetchall()
    return [
        HearingDocumentLinks(
            hearing_id=row[0],
            agenda_url=row[1],
            minutes_url=row[2],
            supporting_url=row[3],
        )
        for row in rows
    ]


def fetch_supporting_page_html(source_url: str, user_agent: str | None = None) -> str:
    headers = {"User-Agent": user_agent or Settings.user_agent}
    with httpx.Client(headers=headers, follow_redirects=True, timeout=30.0) as client:
        response = client.get(source_url)
        response.raise_for_status()
        return response.text


def save_supporting_html_snapshot(html: str, html_dir: Path, hearing_id: str) -> Path:
    html_dir.mkdir(parents=True, exist_ok=True)
    content_hash = hashlib.sha256(html.encode("utf-8")).hexdigest()[:16]
    path = html_dir / f"supporting_{hearing_id}_{content_hash}.html"
    if not path.exists():
        path.write_text(html, encoding="utf-8")
    return path


def documents_from_archive_links(hearing: HearingDocumentLinks) -> list[SourceDocument]:
    documents: list[SourceDocument] = []
    if hearing.agenda_url:
        documents.append(
            make_source_document(
                hearing_id=hearing.hearing_id,
                source_type="agenda",
                title="Agenda",
                url=hearing.agenda_url,
            )
        )
    if hearing.minutes_url:
        documents.append(
            make_source_document(
                hearing_id=hearing.hearing_id,
                source_type="minutes",
                title="Minutes",
                url=hearing.minutes_url,
            )
        )
    return documents


def parse_supporting_page(
    html: str,
    source_url: str,
    hearing_id: str,
) -> list[SourceDocument]:
    soup = BeautifulSoup(html, "html.parser")
    current_source_type = "other"
    documents: list[SourceDocument] = []
    seen_urls: set[str] = set()

    for element in soup.find_all(True):
        if not isinstance(element, Tag) or element.name is None:
            continue

        if element.name in SECTION_LABEL_TAGS:
            section_source_type = classify_source_type(element.get_text(" ", strip=True))
            if section_source_type != "other":
                current_source_type = section_source_type

        if element.name != "a" or not element.has_attr("href"):
            continue

        url = canonicalize_url(urljoin(source_url, str(element["href"])))
        if not is_document_link(url, element.get_text(" ", strip=True)):
            continue
        if url in seen_urls:
            continue

        context = element.find_parent(LINK_CONTEXT_TAGS)
        context_text = clean_text(context.get_text(" ", strip=True)) if context else ""
        link_text = clean_text(element.get_text(" ", strip=True))
        source_type = classify_source_type(" ".join([context_text, link_text, url]))
        if source_type == "other":
            source_type = current_source_type

        documents.append(
            make_source_document(
                hearing_id=hearing_id,
                source_type=source_type,
                title=document_title(link=element, context_text=context_text, url=url),
                url=url,
            )
        )
        seen_urls.add(url)

    return documents


def upsert_source_documents(
    conn: duckdb.DuckDBPyConnection,
    documents: list[SourceDocument],
) -> None:
    if not documents:
        return

    rows = [
        (
            document.document_id,
            document.hearing_id,
            document.source_type,
            document.title,
            document.url,
        )
        for document in dedupe_source_documents(documents)
    ]

    conn.executemany(
        """
        INSERT INTO source_documents (
            document_id,
            hearing_id,
            source_type,
            title,
            url
        )
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT (document_id) DO UPDATE SET
            hearing_id = excluded.hearing_id,
            source_type = excluded.source_type,
            title = excluded.title,
            url = excluded.url
        """,
        rows,
    )


def dedupe_source_documents(documents: list[SourceDocument]) -> list[SourceDocument]:
    by_id: dict[str, SourceDocument] = {}
    for document in documents:
        existing = by_id.get(document.document_id)
        if existing is None:
            by_id[document.document_id] = document
            continue

        if existing.source_type == "other" and document.source_type != "other":
            by_id[document.document_id] = document
            continue

        if existing.title is None and document.title is not None:
            by_id[document.document_id] = document

    return list(by_id.values())


def make_source_document(
    hearing_id: str,
    source_type: str,
    title: str | None,
    url: str,
) -> SourceDocument:
    if source_type not in DOCUMENT_SOURCE_TYPES:
        source_type = "other"
    canonical_url = canonicalize_url(url)
    return SourceDocument(
        document_id=document_id_for(hearing_id=hearing_id, url=canonical_url),
        hearing_id=hearing_id,
        source_type=source_type,
        title=clean_text(title or "") or None,
        url=canonical_url,
    )


def document_id_for(hearing_id: str, url: str) -> str:
    digest = hashlib.sha256(f"{hearing_id}|{canonicalize_url(url)}".encode()).hexdigest()
    return f"doc-{digest[:20]}"


def classify_source_type(text: str) -> str:
    normalized = clean_text(text).lower()

    if "correspondence" in normalized:
        if any(
            phrase in normalized
            for phrase in (
                "at hearing",
                "at the hearing",
                "during hearing",
                "during the hearing",
            )
        ):
            return "correspondence_at_hearing"
        if any(
            phrase in normalized
            for phrase in (
                "before hearing",
                "before the hearing",
                "pre-hearing",
                "pre hearing",
                "prior to hearing",
                "prior to the hearing",
                "received prior",
            )
        ):
            return "correspondence_pre_hearing"
        return "correspondence_pre_hearing"

    if "staff report" in normalized:
        return "staff_report"
    if "presentation" in normalized:
        return "presentation"
    if "agenda" in normalized:
        return "agenda"
    if "minutes" in normalized:
        return "minutes"
    if "notice" in normalized:
        return "notice"

    return "other"


def is_document_link(url: str, link_text: str) -> bool:
    if PDF_URL_RE.search(url):
        return True

    normalized_text = clean_text(link_text).lower()
    return normalized_text.endswith("pdf") or " pdf" in normalized_text


def document_title(link: Tag, context_text: str, url: str) -> str:
    link_text = clean_text(link.get_text(" ", strip=True))
    if link_text.lower() not in GENERIC_LINK_TITLES:
        return link_text

    context = clean_text(context_text)
    if context and context.lower() not in GENERIC_LINK_TITLES:
        return context

    path = urlparse(url).path.rstrip("/")
    filename = path.rsplit("/", maxsplit=1)[-1]
    return filename or url


def canonicalize_url(url: str) -> str:
    return url.strip()


def clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value.replace("\xa0", " ")).strip()
