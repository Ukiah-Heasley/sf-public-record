from __future__ import annotations

import hashlib
import re
import time
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from urllib.parse import urljoin

import duckdb
import httpx
from bs4 import BeautifulSoup
from bs4.element import Tag

from ..config import Settings
from ..db import connect
from .models import ArchiveHearing

ARCHIVE_URL = "https://sfplanning.org/cpc-hearing-archives"

MONTH_RE = r"January|February|March|April|May|June|July|August|September|October|November|December"
DATE_RE = re.compile(rf"\b({MONTH_RE})\s+(\d{{1,2}})[,\.\s]+(\d{{4}})\b", re.IGNORECASE)
CANCELLED_RE = re.compile(r"\b(cancelled|canceled|cancellation)\b", re.IGNORECASE)
QUALIFIER_RE = re.compile(r"\(([^)]+)\)")
SLUG_RE = re.compile(r"[^a-z0-9]+")


@dataclass(frozen=True)
class CrawlArchiveResult:
    snapshot_path: Path
    parsed_count: int
    upserted_count: int


def crawl_archive(
    db_path: Path | str,
    settings: Settings,
    source_url: str = ARCHIVE_URL,
    since: date | None = None,
    limit: int | None = 50,
    include_future: bool = False,
) -> CrawlArchiveResult:
    html = fetch_archive_html(source_url=source_url, user_agent=settings.user_agent)
    snapshot_path = save_html_snapshot(html, settings.html_dir)
    until = None if include_future else date.today()
    hearings = parse_archive_html(
        html=html,
        source_url=source_url,
        since=since,
        until=until,
        limit=limit,
    )

    with connect(db_path) as conn:
        upsert_archive_hearings(conn, hearings)

    if settings.crawl_delay_seconds > 0:
        time.sleep(settings.crawl_delay_seconds)

    return CrawlArchiveResult(
        snapshot_path=snapshot_path,
        parsed_count=len(hearings),
        upserted_count=len(hearings),
    )


def fetch_archive_html(source_url: str = ARCHIVE_URL, user_agent: str | None = None) -> str:
    headers = {"User-Agent": user_agent or Settings.user_agent}
    with httpx.Client(headers=headers, follow_redirects=True, timeout=30.0) as client:
        response = client.get(source_url)
        response.raise_for_status()
        return response.text


def save_html_snapshot(html: str, html_dir: Path) -> Path:
    html_dir.mkdir(parents=True, exist_ok=True)
    content_hash = hashlib.sha256(html.encode("utf-8")).hexdigest()[:16]
    path = html_dir / f"cpc_archive_{content_hash}.html"
    if not path.exists():
        path.write_text(html, encoding="utf-8")
    return path


def parse_archive_html(
    html: str,
    source_url: str = ARCHIVE_URL,
    since: date | None = None,
    until: date | None = None,
    limit: int | None = None,
) -> list[ArchiveHearing]:
    soup = BeautifulSoup(html, "html.parser")
    hearings: list[ArchiveHearing] = []

    for row in soup.find_all("tr"):
        if not isinstance(row, Tag):
            continue
        hearing = _parse_table_row(row, source_url)
        if hearing is None:
            continue
        if since and hearing.hearing_date < since:
            continue
        if until and hearing.hearing_date > until:
            continue
        hearings.append(hearing)
        if limit and len(hearings) >= limit:
            break

    return hearings


def upsert_archive_hearings(
    conn: duckdb.DuckDBPyConnection,
    hearings: list[ArchiveHearing],
) -> None:
    if not hearings:
        return

    rows = [
        (
            hearing.hearing_id,
            hearing.hearing_date,
            hearing.title,
            hearing.status,
            hearing.agenda_url,
            hearing.minutes_url,
            hearing.supporting_url,
            hearing.source_url,
        )
        for hearing in hearings
    ]

    conn.executemany(
        """
        INSERT INTO hearings (
            hearing_id,
            hearing_date,
            title,
            status,
            agenda_url,
            minutes_url,
            supporting_url,
            source_url
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (hearing_id) DO UPDATE SET
            hearing_date = excluded.hearing_date,
            title = excluded.title,
            status = excluded.status,
            agenda_url = excluded.agenda_url,
            minutes_url = excluded.minutes_url,
            supporting_url = excluded.supporting_url,
            source_url = excluded.source_url,
            crawled_at = now()
        """,
        rows,
    )


def _parse_table_row(row: Tag, source_url: str) -> ArchiveHearing | None:
    cells = row.find_all(["td", "th"], recursive=False)
    if len(cells) < 2:
        return None

    first_cell_text = _clean_text(cells[0].get_text(" ", strip=True))
    if first_cell_text.lower().startswith("hearing date"):
        return None

    hearing_date = _parse_date(first_cell_text)
    if hearing_date is None:
        return None

    row_text = _clean_text(row.get_text(" ", strip=True))
    status = "cancelled" if CANCELLED_RE.search(row_text) else "scheduled"
    title = _title_from_date_text(first_cell_text)

    agenda_url = _extract_column_link(cells, 1, "agenda", source_url)
    minutes_url = _extract_column_link(cells, 2, "minutes", source_url)
    supporting_url = _extract_column_link(cells, 3, "supporting", source_url)

    return ArchiveHearing(
        hearing_id=_hearing_id(hearing_date, title),
        hearing_date=hearing_date,
        title=title,
        status=status,
        agenda_url=agenda_url,
        minutes_url=minutes_url,
        supporting_url=supporting_url,
        source_url=source_url,
    )


def _parse_date(text: str) -> date | None:
    match = DATE_RE.search(text)
    if not match:
        return None
    month, day, year = match.groups()
    return datetime.strptime(f"{month} {int(day)} {year}", "%B %d %Y").date()


def _title_from_date_text(text: str) -> str:
    qualifiers = [
        _clean_text(match.group(1))
        for match in QUALIFIER_RE.finditer(text)
        if not CANCELLED_RE.search(match.group(1))
    ]

    suffix = _clean_text(" ".join(qualifiers))
    if suffix:
        return f"Planning Commission - {suffix}"
    return "Planning Commission"


def _hearing_id(hearing_date: date, title: str) -> str:
    suffix = title.removeprefix("Planning Commission").strip(" -")
    if not suffix:
        return f"cpc-{hearing_date.isoformat()}"
    slug = SLUG_RE.sub("-", suffix.lower()).strip("-")
    return f"cpc-{hearing_date.isoformat()}-{slug}"


def _extract_column_link(
    cells: list[Tag],
    index: int,
    expected_label: str,
    base_url: str,
) -> str | None:
    if index >= len(cells):
        return None

    cell = cells[index]
    cell_text = _clean_text(cell.get_text(" ", strip=True)).lower()
    if not cell_text or cell_text in {"n/a", "na"}:
        return None

    links = [link for link in cell.find_all("a", href=True) if isinstance(link, Tag)]
    for link in links:
        link_text = _clean_text(link.get_text(" ", strip=True)).lower()
        if expected_label in link_text:
            return urljoin(base_url, str(link["href"]))

    if expected_label in cell_text and links:
        return urljoin(base_url, str(links[0]["href"]))
    return None


def _clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value.replace("\xa0", " ")).strip()
