from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import duckdb

from ..config import Settings
from ..db import connect

AGENDA_ITEM_RE = re.compile(r"^\s*\d+[A-Za-z]?\.\s+")
CASE_RE = re.compile(r"\b20\d{2}-\d{6}[A-Z0-9-]*\b")
SPACE_RE = re.compile(r"\s+")
WORD_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9-]{1,}")

KNOWN_SECTION_HINTS = (
    "Agenda Item",
    "Background",
    "CEQA",
    "Executive Summary",
    "Issues and Other Considerations",
    "Planning Code Compliance",
    "Preliminary Recommendation",
    "Project Description",
    "Public Comment",
    "Recommendation",
    "Required Commission Action",
    "Site Description",
    "Staff Analysis",
    "Staff Report",
)

LOW_VALUE_PATTERNS = (
    re.compile(r"^\s*page\s+\d+\s*$", re.IGNORECASE),
    re.compile(r"^\s*\d+\s*$"),
)


@dataclass(frozen=True)
class PageText:
    document_id: str
    hearing_date: date | None
    source_type: str
    title: str | None
    page_number: int
    text: str
    extraction_quality: str | None


@dataclass(frozen=True)
class TextBlock:
    text: str
    page_start: int
    page_end: int
    section_hint: str | None


@dataclass(frozen=True)
class Chunk:
    chunk_id: str
    document_id: str
    page_start: int
    page_end: int
    chunk_index: int
    text: str
    token_estimate: int
    section_hint: str | None
    citation_label: str


@dataclass(frozen=True)
class ChunkDocumentsResult:
    document_count: int
    chunk_count: int


def chunk_documents(
    db_path: Path | str,
    settings: Settings,
    limit: int | None = None,
    document_id: str | None = None,
) -> ChunkDocumentsResult:
    with connect(db_path) as conn:
        return chunk_parsed_documents(
            conn=conn,
            settings=settings,
            limit=limit,
            document_id=document_id,
        )


def chunk_parsed_documents(
    conn: duckdb.DuckDBPyConnection,
    settings: Settings,
    limit: int | None = None,
    document_id: str | None = None,
) -> ChunkDocumentsResult:
    document_ids = list_parsed_document_ids(conn, limit=limit, document_id=document_id)
    chunk_count = 0

    for parsed_document_id in document_ids:
        pages = list_document_pages(conn, parsed_document_id)
        chunks = build_document_chunks(
            pages=pages,
            target_tokens=settings.chunk_target_tokens,
            max_tokens=settings.chunk_max_tokens,
            overlap_tokens=settings.chunk_overlap_tokens,
        )
        replace_document_chunks(conn, parsed_document_id, chunks)
        chunk_count += len(chunks)

    return ChunkDocumentsResult(document_count=len(document_ids), chunk_count=chunk_count)


def list_parsed_document_ids(
    conn: duckdb.DuckDBPyConnection,
    limit: int | None = None,
    document_id: str | None = None,
) -> list[str]:
    filters = ["p.text IS NOT NULL", "length(trim(p.text)) > 0"]
    params: list[object] = []

    if document_id:
        filters.append("d.document_id = ?")
        params.append(document_id)

    query = f"""
        SELECT d.document_id
        FROM source_documents d
        JOIN pages p ON p.document_id = d.document_id
        WHERE {" AND ".join(filters)}
        GROUP BY d.document_id
        ORDER BY d.document_id
    """
    if limit is not None:
        query += " LIMIT ?"
        params.append(limit)

    return [row[0] for row in conn.execute(query, params).fetchall()]


def list_document_pages(
    conn: duckdb.DuckDBPyConnection,
    document_id: str,
) -> list[PageText]:
    rows = conn.execute(
        """
        SELECT
            d.document_id,
            h.hearing_date,
            d.source_type,
            d.title,
            p.page_number,
            p.text,
            p.extraction_quality
        FROM source_documents d
        LEFT JOIN hearings h ON h.hearing_id = d.hearing_id
        JOIN pages p ON p.document_id = d.document_id
        WHERE d.document_id = ?
        ORDER BY p.page_number
        """,
        (document_id,),
    ).fetchall()

    return [
        PageText(
            document_id=row[0],
            hearing_date=row[1],
            source_type=row[2],
            title=row[3],
            page_number=row[4],
            text=row[5] or "",
            extraction_quality=row[6],
        )
        for row in rows
    ]


def build_document_chunks(
    pages: list[PageText],
    target_tokens: int = 1000,
    max_tokens: int = 1200,
    overlap_tokens: int = 120,
) -> list[Chunk]:
    if not pages:
        return []

    document_id = pages[0].document_id
    blocks = split_pages_into_blocks(pages=pages, max_tokens=max_tokens)
    chunks: list[Chunk] = []
    current_blocks: list[TextBlock] = []
    current_tokens = 0

    for block in blocks:
        block_tokens = estimate_tokens(block.text)
        current_section = current_blocks[-1].section_hint if current_blocks else None
        section_changed = (
            current_section is not None
            and block.section_hint is not None
            and block.section_hint != current_section
        )

        should_flush = bool(current_blocks) and (
            current_tokens + block_tokens > max_tokens
            or (section_changed and current_tokens >= max(16, target_tokens // 4))
        )

        if should_flush:
            chunks.append(
                make_chunk(
                    document_id=document_id,
                    chunk_index=len(chunks),
                    blocks=current_blocks,
                    page_context=pages[0],
                )
            )
            current_blocks = overlap_blocks_for_next(
                previous_blocks=current_blocks,
                next_block=block,
                overlap_tokens=overlap_tokens,
            )
            current_tokens = sum(estimate_tokens(existing.text) for existing in current_blocks)

        current_blocks.append(block)
        current_tokens += block_tokens

        if current_tokens >= target_tokens:
            chunks.append(
                make_chunk(
                    document_id=document_id,
                    chunk_index=len(chunks),
                    blocks=current_blocks,
                    page_context=pages[0],
                )
            )
            current_blocks = []
            current_tokens = 0

    if current_blocks:
        chunks.append(
            make_chunk(
                document_id=document_id,
                chunk_index=len(chunks),
                blocks=current_blocks,
                page_context=pages[0],
            )
        )

    return chunks


def split_pages_into_blocks(pages: list[PageText], max_tokens: int) -> list[TextBlock]:
    blocks: list[TextBlock] = []
    active_section: str | None = section_from_document_type(pages[0].source_type)

    for page in pages:
        if should_skip_page(page):
            continue

        paragraphs = split_page_paragraphs(page.text)
        for paragraph in paragraphs:
            section_hint = detect_section_hint(paragraph)
            if section_hint:
                active_section = section_hint

            block = TextBlock(
                text=paragraph,
                page_start=page.page_number,
                page_end=page.page_number,
                section_hint=active_section,
            )
            blocks.extend(split_large_block(block, max_tokens=max_tokens))

    return blocks


def split_page_paragraphs(text: str) -> list[str]:
    normalized = text.replace("\xa0", " ").replace("\r\n", "\n").replace("\r", "\n")
    raw_paragraphs = re.split(r"\n\s*\n", normalized)
    paragraphs: list[str] = []

    for raw_paragraph in raw_paragraphs:
        lines = [clean_line(line) for line in raw_paragraph.splitlines()]
        lines = [line for line in lines if line and not is_low_value_line(line)]
        if not lines:
            continue

        current: list[str] = []
        for line in lines:
            if is_standalone_heading(line) or AGENDA_ITEM_RE.match(line):
                if current:
                    paragraphs.append(clean_text(" ".join(current)))
                    current = []
                paragraphs.append(line)
                continue
            current.append(line)

        if current:
            paragraphs.append(clean_text(" ".join(current)))

    return [
        paragraph
        for paragraph in paragraphs
        if paragraph
        and (
            estimate_tokens(paragraph) >= 8
            or is_standalone_heading(paragraph)
            or AGENDA_ITEM_RE.match(paragraph)
        )
    ]


def split_large_block(block: TextBlock, max_tokens: int) -> list[TextBlock]:
    if estimate_tokens(block.text) <= max_tokens:
        return [block]

    words = block.text.split()
    target_chars = max_tokens * 4
    pieces: list[TextBlock] = []
    current_words: list[str] = []
    current_chars = 0

    for word in words:
        if current_words and current_chars + len(word) + 1 > target_chars:
            pieces.append(
                TextBlock(
                    text=clean_text(" ".join(current_words)),
                    page_start=block.page_start,
                    page_end=block.page_end,
                    section_hint=block.section_hint,
                )
            )
            current_words = []
            current_chars = 0
        current_words.append(word)
        current_chars += len(word) + 1

    if current_words:
        pieces.append(
            TextBlock(
                text=clean_text(" ".join(current_words)),
                page_start=block.page_start,
                page_end=block.page_end,
                section_hint=block.section_hint,
            )
        )

    return pieces


def make_chunk(
    document_id: str,
    chunk_index: int,
    blocks: list[TextBlock],
    page_context: PageText,
) -> Chunk:
    text = clean_text("\n\n".join(block.text for block in blocks))
    page_start = min(block.page_start for block in blocks)
    page_end = max(block.page_end for block in blocks)
    section_hint = most_recent_section_hint(blocks)
    return Chunk(
        chunk_id=f"chunk-{document_id}-{chunk_index:04d}",
        document_id=document_id,
        page_start=page_start,
        page_end=page_end,
        chunk_index=chunk_index,
        text=text,
        token_estimate=estimate_tokens(text),
        section_hint=section_hint,
        citation_label=citation_label(
            hearing_date=page_context.hearing_date,
            source_type=page_context.source_type,
            title=page_context.title,
            page_start=page_start,
            page_end=page_end,
        ),
    )


def overlap_blocks_for_next(
    previous_blocks: list[TextBlock],
    next_block: TextBlock,
    overlap_tokens: int,
) -> list[TextBlock]:
    if overlap_tokens <= 0 or not previous_blocks:
        return []

    previous_section = previous_blocks[-1].section_hint
    if next_block.section_hint and previous_section and next_block.section_hint != previous_section:
        return []

    overlap_chars = overlap_tokens * 4
    selected: list[TextBlock] = []
    selected_chars = 0
    for block in reversed(previous_blocks):
        if selected_chars >= overlap_chars:
            break
        if block.section_hint != previous_section:
            break
        selected.append(block)
        selected_chars += len(block.text)
    selected.reverse()

    return selected


def replace_document_chunks(
    conn: duckdb.DuckDBPyConnection,
    document_id: str,
    chunks: list[Chunk],
) -> None:
    existing_chunk_ids = [
        row[0]
        for row in conn.execute(
            "SELECT chunk_id FROM chunks WHERE document_id = ?",
            (document_id,),
        ).fetchall()
    ]
    if existing_chunk_ids:
        conn.executemany(
            "DELETE FROM chunk_embeddings WHERE chunk_id = ?",
            [(chunk_id,) for chunk_id in existing_chunk_ids],
        )
    conn.execute("DELETE FROM chunks WHERE document_id = ?", (document_id,))

    if not chunks:
        return

    conn.executemany(
        """
        INSERT INTO chunks (
            chunk_id,
            document_id,
            page_start,
            page_end,
            chunk_index,
            text,
            token_estimate,
            section_hint,
            citation_label
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                chunk.chunk_id,
                chunk.document_id,
                chunk.page_start,
                chunk.page_end,
                chunk.chunk_index,
                chunk.text,
                chunk.token_estimate,
                chunk.section_hint,
                chunk.citation_label,
            )
            for chunk in chunks
        ],
    )


def citation_label(
    hearing_date: date | None,
    source_type: str,
    title: str | None,
    page_start: int,
    page_end: int,
) -> str:
    date_label = (
        f"{hearing_date.strftime('%b')} {hearing_date.day}, {hearing_date.year}"
        if hearing_date
        else "Undated"
    )
    document_label = title if title else source_type.replace("_", " ").title()
    page_label = f"p. {page_start}" if page_start == page_end else f"pp. {page_start}-{page_end}"
    return f"{date_label} {document_label} - {page_label}"


def detect_section_hint(text: str) -> str | None:
    first_line = clean_line(text.splitlines()[0] if text.splitlines() else text)
    if AGENDA_ITEM_RE.match(first_line):
        match = CASE_RE.search(first_line)
        item_number = first_line.split(".", maxsplit=1)[0].strip()
        if match:
            return f"Agenda Item {item_number} - {match.group(0)}"
        return f"Agenda Item {item_number}"

    normalized = first_line.strip(":")
    lower = normalized.lower()
    for known_hint in KNOWN_SECTION_HINTS:
        if lower == known_hint.lower():
            return known_hint

    if is_standalone_heading(normalized):
        return normalized.title() if normalized.isupper() else normalized

    return None


def section_from_document_type(source_type: str) -> str | None:
    if source_type == "staff_report":
        return "Staff Report"
    if source_type == "agenda":
        return "Agenda"
    if source_type.startswith("correspondence"):
        return "Correspondence"
    return source_type.replace("_", " ").title() if source_type else None


def most_recent_section_hint(blocks: list[TextBlock]) -> str | None:
    for block in reversed(blocks):
        if block.section_hint:
            return block.section_hint
    return None


def should_skip_page(page: PageText) -> bool:
    text = clean_text(page.text)
    if not text:
        return True
    return page.extraction_quality == "poor" and estimate_tokens(text) < 20


def is_standalone_heading(line: str) -> bool:
    stripped = line.strip()
    if not stripped or len(stripped) > 90:
        return False
    if stripped.endswith(".") and not stripped.endswith(":"):
        return False
    if stripped.endswith(":"):
        return True
    words = WORD_RE.findall(stripped)
    if not words or len(words) > 10:
        return False
    alpha_chars = [char for char in stripped if char.isalpha()]
    if not alpha_chars:
        return False
    uppercase_ratio = sum(1 for char in alpha_chars if char.isupper()) / len(alpha_chars)
    return uppercase_ratio >= 0.75


def is_low_value_line(line: str) -> bool:
    return any(pattern.match(line) for pattern in LOW_VALUE_PATTERNS)


def estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


def chunk_content_hash(text: str) -> str:
    return hashlib.sha256(clean_text(text).encode()).hexdigest()


def clean_line(value: str) -> str:
    return SPACE_RE.sub(" ", value.replace("\xa0", " ")).strip()


def clean_text(value: str) -> str:
    return SPACE_RE.sub(" ", value.replace("\xa0", " ")).strip()
