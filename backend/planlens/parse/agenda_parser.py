from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

import duckdb

from ..db import connect

CASE_RE = re.compile(r"\b20\d{2}-\d{6}[A-Z0-9-]*\b")
ITEM_RE = re.compile(r"(?m)^\s*(\d+[a-zA-Z]?)\.\s+")
PHONE_RE = re.compile(r"\(?\d{3}\)?[-.\s]\d{3}[-.\s]\d{4}")
EMAIL_RE = re.compile(r"[\w.-]+@sfgov\.org", re.IGNORECASE)
RECOMMENDATION_RE = re.compile(
    r"Preliminary Recommendation:\s*(.+)",
    re.IGNORECASE,
)
DISTRICT_RE = re.compile(r"\bDistrict\s+(\d+)\b", re.IGNORECASE)
ADDRESS_RE = re.compile(
    r"\b\d{1,6}\s+[A-Z][A-Za-z0-9 .'-]+?"
    r"(?:Street|St|Avenue|Ave|Boulevard|Blvd|Road|Rd|Drive|Dr|Lane|Ln|"
    r"Way|Court|Ct|Place|Pl|Terrace|Ter)\b",
    re.IGNORECASE,
)
CEQA_RE = re.compile(r"CEQA(?:\s+(?:Status|Determination))?:\s*(.+)", re.IGNORECASE)
CONTINUED_FROM_RE = re.compile(r"Continued\s+from:\s*(.+)", re.IGNORECASE)
PROPOSED_CONTINUANCE_RE = re.compile(
    r"Proposed\s+Continuance\s+Date:\s*(.+)",
    re.IGNORECASE,
)
PLANNER_RE = re.compile(
    r"(?:Planner|Staff Contact|Contact):\s*"
    r"([A-Z][A-Za-z .'-]+?)(?=,|\s+-|\s+[\w.-]+@|\s+\(?\d{3}|\n|$)",
    re.IGNORECASE,
)
PROJECT_DESCRIPTION_RE = re.compile(
    r"Project Description:\s*(.+?)"
    r"(?=\n(?:CEQA|Preliminary Recommendation|Planner|Staff Contact|Contact|"
    r"Continued|Proposed Continuance|District)\b|\Z)",
    re.IGNORECASE | re.DOTALL,
)
MONTH_RE = (
    "January|February|March|April|May|June|July|August|September|October|"
    "November|December"
)
DATE_RE = re.compile(rf"\b({MONTH_RE})\s+(\d{{1,2}}),?\s+(\d{{4}})\b", re.IGNORECASE)

ENTITLEMENT_TERMS = (
    "Conditional Use Authorization",
    "Large Project Authorization",
    "Downtown Project Authorization",
    "Office Development Authorization",
    "Variance",
    "Planned Unit Development",
    "General Plan Amendment",
    "Planning Code Text Amendment",
    "Discretionary Review",
    "Informational Presentation",
)


@dataclass(frozen=True)
class AgendaDocumentText:
    document_id: str
    hearing_id: str
    text: str


@dataclass(frozen=True)
class ParsedAgendaItem:
    agenda_item_id: str
    hearing_id: str
    item_number: str
    section: str | None
    case_number: str | None
    case_suffix: str | None
    address: str | None
    district: str | None
    planner_name: str | None
    planner_contact: str | None
    project_description: str | None
    entitlement_type: str | None
    ceqa_status: str | None
    preliminary_recommendation: str | None
    continued_from: str | None
    proposed_continuance_date: date | None
    raw_text: str
    parser_confidence: float


@dataclass(frozen=True)
class ParseAgendasResult:
    document_count: int
    parsed_document_count: int
    agenda_item_count: int
    linked_document_count: int


def parse_agendas(
    db_path: Path | str,
    limit: int | None = None,
    hearing_id: str | None = None,
    document_id: str | None = None,
    link_documents: bool = True,
) -> ParseAgendasResult:
    with connect(db_path) as conn:
        return parse_agenda_documents(
            conn=conn,
            limit=limit,
            hearing_id=hearing_id,
            document_id=document_id,
            link_documents=link_documents,
        )


def parse_agenda_documents(
    conn: duckdb.DuckDBPyConnection,
    limit: int | None = None,
    hearing_id: str | None = None,
    document_id: str | None = None,
    link_documents: bool = True,
) -> ParseAgendasResult:
    documents = list_agenda_document_texts(
        conn=conn,
        limit=limit,
        hearing_id=hearing_id,
        document_id=document_id,
    )

    items_by_hearing: dict[str, list[ParsedAgendaItem]] = {}
    parsed_document_count = 0
    for document in documents:
        items = parse_agenda_items_from_text(document.text, hearing_id=document.hearing_id)
        items_by_hearing.setdefault(document.hearing_id, []).extend(items)
        parsed_document_count += 1

    agenda_item_count = 0
    hearing_ids = tuple(items_by_hearing)
    for parsed_hearing_id, items in items_by_hearing.items():
        replace_hearing_agenda_items(conn, parsed_hearing_id, items)
        agenda_item_count += len(items)

    linked_document_count = 0
    if link_documents and hearing_ids:
        linked_document_count = link_documents_to_agenda_items(conn, hearing_ids=hearing_ids)

    return ParseAgendasResult(
        document_count=len(documents),
        parsed_document_count=parsed_document_count,
        agenda_item_count=agenda_item_count,
        linked_document_count=linked_document_count,
    )


def list_agenda_document_texts(
    conn: duckdb.DuckDBPyConnection,
    limit: int | None = None,
    hearing_id: str | None = None,
    document_id: str | None = None,
) -> list[AgendaDocumentText]:
    filters = ["source_type = 'agenda'"]
    params: list[object] = []

    if hearing_id:
        filters.append("hearing_id = ?")
        params.append(hearing_id)
    if document_id:
        filters.append("document_id = ?")
        params.append(document_id)

    query = f"""
        SELECT document_id, hearing_id
        FROM source_documents
        WHERE {" AND ".join(filters)}
        ORDER BY document_id
    """
    if limit is not None:
        query += " LIMIT ?"
        params.append(limit)

    documents = conn.execute(query, params).fetchall()
    agenda_documents: list[AgendaDocumentText] = []
    for agenda_document_id, agenda_hearing_id in documents:
        page_rows = conn.execute(
            """
            SELECT page_number, text
            FROM pages
            WHERE document_id = ?
            ORDER BY page_number
            """,
            (agenda_document_id,),
        ).fetchall()
        text = "\n\n".join(
            f"--- page {page_number} ---\n{page_text or ''}"
            for page_number, page_text in page_rows
        )
        agenda_documents.append(
            AgendaDocumentText(
                document_id=agenda_document_id,
                hearing_id=agenda_hearing_id,
                text=text,
            )
        )

    return agenda_documents


def parse_agenda_items_from_text(text: str, hearing_id: str) -> list[ParsedAgendaItem]:
    matches = list(ITEM_RE.finditer(text))
    items: list[ParsedAgendaItem] = []

    for index, match in enumerate(matches):
        block_start = match.start()
        block_end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        raw_text = clean_block(text[block_start:block_end])
        if not raw_text:
            continue

        item_number = match.group(1)
        section = section_hint_from_prefix(text[:block_start])
        items.append(
            parse_agenda_item_block(
                raw_text=raw_text,
                hearing_id=hearing_id,
                item_number=item_number,
                section=section,
            )
        )

    return items


def parse_agenda_item_block(
    raw_text: str,
    hearing_id: str,
    item_number: str,
    section: str | None,
) -> ParsedAgendaItem:
    case_number = first_match(CASE_RE, raw_text)
    case_suffix = extract_case_suffix(case_number)
    address = first_match(ADDRESS_RE, raw_text)
    district = first_group(DISTRICT_RE, raw_text)
    planner_name = first_group(PLANNER_RE, raw_text)
    planner_contact = extract_planner_contact(raw_text)
    project_description = extract_project_description(raw_text)
    entitlement_type = extract_entitlement_type(raw_text)
    ceqa_status = first_group(CEQA_RE, raw_text)
    preliminary_recommendation = first_group(RECOMMENDATION_RE, raw_text)
    continued_from = first_group(CONTINUED_FROM_RE, raw_text)
    proposed_continuance_date = extract_proposed_continuance_date(raw_text)

    return ParsedAgendaItem(
        agenda_item_id=agenda_item_id_for(
            hearing_id=hearing_id,
            item_number=item_number,
            case_number=case_number,
            raw_text=raw_text,
        ),
        hearing_id=hearing_id,
        item_number=item_number,
        section=section,
        case_number=case_number,
        case_suffix=case_suffix,
        address=normalize_optional(address),
        district=normalize_optional(district),
        planner_name=normalize_optional(planner_name),
        planner_contact=normalize_optional(planner_contact),
        project_description=normalize_optional(project_description),
        entitlement_type=normalize_optional(entitlement_type),
        ceqa_status=normalize_optional(ceqa_status),
        preliminary_recommendation=normalize_optional(preliminary_recommendation),
        continued_from=normalize_optional(continued_from),
        proposed_continuance_date=proposed_continuance_date,
        raw_text=raw_text,
        parser_confidence=parser_confidence(
            [
                item_number,
                case_number,
                address,
                district,
                planner_name,
                planner_contact,
                project_description,
                entitlement_type,
                ceqa_status,
                preliminary_recommendation,
            ]
        ),
    )


def replace_hearing_agenda_items(
    conn: duckdb.DuckDBPyConnection,
    hearing_id: str,
    items: list[ParsedAgendaItem],
) -> None:
    existing_item_ids = [
        row[0]
        for row in conn.execute(
            "SELECT agenda_item_id FROM agenda_items WHERE hearing_id = ?",
            (hearing_id,),
        ).fetchall()
    ]
    if existing_item_ids:
        conn.executemany(
            "DELETE FROM document_links WHERE agenda_item_id = ?",
            [(agenda_item_id,) for agenda_item_id in existing_item_ids],
        )
    conn.execute("DELETE FROM agenda_items WHERE hearing_id = ?", (hearing_id,))

    if not items:
        return

    conn.executemany(
        """
        INSERT INTO agenda_items (
            agenda_item_id,
            hearing_id,
            item_number,
            section,
            case_number,
            case_suffix,
            address,
            district,
            planner_name,
            planner_contact,
            project_description,
            entitlement_type,
            ceqa_status,
            preliminary_recommendation,
            continued_from,
            proposed_continuance_date,
            raw_text,
            parser_confidence
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                item.agenda_item_id,
                item.hearing_id,
                item.item_number,
                item.section,
                item.case_number,
                item.case_suffix,
                item.address,
                item.district,
                item.planner_name,
                item.planner_contact,
                item.project_description,
                item.entitlement_type,
                item.ceqa_status,
                item.preliminary_recommendation,
                item.continued_from,
                item.proposed_continuance_date,
                item.raw_text,
                item.parser_confidence,
            )
            for item in items
        ],
    )


def link_documents_to_agenda_items(
    conn: duckdb.DuckDBPyConnection,
    hearing_ids: tuple[str, ...] | None = None,
) -> int:
    filters: list[str] = []
    params: list[object] = []
    if hearing_ids:
        placeholders = ", ".join("?" for _ in hearing_ids)
        filters.append(f"hearing_id IN ({placeholders})")
        params.extend(hearing_ids)

    where_clause = f"WHERE {' AND '.join(filters)}" if filters else ""
    item_rows = conn.execute(
        f"""
        SELECT agenda_item_id, hearing_id, case_number
        FROM agenda_items
        {where_clause}
        """,
        params,
    ).fetchall()

    if not item_rows:
        return 0

    item_ids = [row[0] for row in item_rows]
    conn.executemany(
        """
        DELETE FROM document_links
        WHERE relationship = 'case_number_match' AND agenda_item_id = ?
        """,
        [(agenda_item_id,) for agenda_item_id in item_ids],
    )

    links: list[tuple[str, str, str, str, float]] = []
    for agenda_item_id, item_hearing_id, case_number in item_rows:
        if not case_number:
            continue

        document_rows = conn.execute(
            """
            SELECT document_id, title, url
            FROM source_documents
            WHERE hearing_id = ? AND source_type <> 'agenda'
            """,
            (item_hearing_id,),
        ).fetchall()
        candidates = case_number_candidates(case_number)
        for document_id, title, url in document_rows:
            haystack = f"{title or ''} {url or ''}".upper()
            if any(candidate.upper() in haystack for candidate in candidates):
                links.append(
                    (
                        link_id_for(agenda_item_id=agenda_item_id, document_id=document_id),
                        agenda_item_id,
                        document_id,
                        "case_number_match",
                        1.0,
                    )
                )

    if not links:
        return 0

    conn.executemany(
        """
        INSERT INTO document_links (
            link_id,
            agenda_item_id,
            document_id,
            relationship,
            confidence
        )
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT (link_id) DO UPDATE SET
            agenda_item_id = excluded.agenda_item_id,
            document_id = excluded.document_id,
            relationship = excluded.relationship,
            confidence = excluded.confidence
        """,
        links,
    )
    return len(links)


def agenda_item_id_for(
    hearing_id: str,
    item_number: str,
    case_number: str | None,
    raw_text: str,
) -> str:
    fallback = clean_text(raw_text)[:160]
    key = f"{hearing_id}|{item_number}|{case_number or ''}|{fallback}"
    digest = hashlib.sha256(key.encode()).hexdigest()
    return f"agenda-{digest[:20]}"


def link_id_for(agenda_item_id: str, document_id: str) -> str:
    digest = hashlib.sha256(f"{agenda_item_id}|{document_id}".encode()).hexdigest()
    return f"link-{digest[:20]}"


def section_hint_from_prefix(prefix: str) -> str | None:
    for line in reversed(prefix.splitlines()[-16:]):
        cleaned = clean_text(line).strip(":")
        if not cleaned or cleaned.startswith("--- page"):
            continue
        if len(cleaned) > 90 or ITEM_RE.match(cleaned):
            continue
        lower = cleaned.lower()
        if any(
            keyword in lower
            for keyword in (
                "calendar",
                "hearing",
                "discretionary review",
                "general public comment",
            )
        ):
            return cleaned
        if cleaned.isupper() and len(cleaned.split()) <= 8:
            return cleaned.title()
    return None


def extract_case_suffix(case_number: str | None) -> str | None:
    if not case_number:
        return None
    match = re.match(r"20\d{2}-\d{6}([A-Z0-9-]+)$", case_number)
    return match.group(1) if match else None


def extract_planner_contact(text: str) -> str | None:
    contacts = []
    email = first_match(EMAIL_RE, text)
    phone = first_match(PHONE_RE, text)
    if email:
        contacts.append(email)
    if phone:
        contacts.append(phone)
    return ", ".join(contacts) or None


def extract_project_description(text: str) -> str | None:
    match = PROJECT_DESCRIPTION_RE.search(text)
    if not match:
        return None
    return clean_multiline(match.group(1))


def extract_entitlement_type(text: str) -> str | None:
    lower = text.lower()
    matches = [term for term in ENTITLEMENT_TERMS if term.lower() in lower]
    return "; ".join(matches) or None


def extract_proposed_continuance_date(text: str) -> date | None:
    match = PROPOSED_CONTINUANCE_RE.search(text)
    if not match:
        return None
    return parse_written_date(match.group(1))


def parse_written_date(text: str) -> date | None:
    match = DATE_RE.search(text)
    if not match:
        return None
    month, day, year = match.groups()
    return datetime.strptime(f"{month} {int(day)} {year}", "%B %d %Y").date()


def case_number_candidates(case_number: str) -> tuple[str, ...]:
    candidates = [case_number]
    base_match = re.match(r"(20\d{2}-\d{6})", case_number)
    if base_match and base_match.group(1) != case_number:
        candidates.append(base_match.group(1))
    return tuple(candidates)


def parser_confidence(fields: list[object | None]) -> float:
    present_count = sum(1 for field in fields if field)
    return round(min(1.0, present_count / 10), 2)


def first_match(pattern: re.Pattern[str], text: str) -> str | None:
    match = pattern.search(text)
    return clean_text(match.group(0)) if match else None


def first_group(pattern: re.Pattern[str], text: str) -> str | None:
    match = pattern.search(text)
    return clean_text(match.group(1)) if match else None


def normalize_optional(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = clean_multiline(value)
    return cleaned or None


def clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value.replace("\xa0", " ")).strip()


def clean_multiline(value: str) -> str:
    return "\n".join(
        clean_text(line)
        for line in value.replace("\xa0", " ").splitlines()
        if clean_text(line)
    ).strip()


def clean_block(value: str) -> str:
    lines = [clean_text(line) for line in value.splitlines()]
    return "\n".join(line for line in lines if line).strip()
