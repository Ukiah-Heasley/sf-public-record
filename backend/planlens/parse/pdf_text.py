from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import duckdb

from ..db import connect


@dataclass(frozen=True)
class PendingPdfParseDocument:
    document_id: str
    local_path: Path


@dataclass(frozen=True)
class ExtractedPage:
    page_id: str
    document_id: str
    page_number: int
    text: str
    char_count: int
    extraction_method: str
    extraction_quality: str


@dataclass(frozen=True)
class PdfParseFailure:
    document_id: str
    local_path: Path
    error: str


@dataclass(frozen=True)
class ParsePdfsResult:
    document_count: int
    parsed_document_count: int
    page_count: int
    failed_count: int
    failures: tuple[PdfParseFailure, ...]


def parse_pdfs(
    db_path: Path | str,
    limit: int | None = None,
    document_id: str | None = None,
) -> ParsePdfsResult:
    with connect(db_path) as conn:
        return parse_pdf_documents(conn=conn, limit=limit, document_id=document_id)


def parse_pdf_documents(
    conn: duckdb.DuckDBPyConnection,
    limit: int | None = None,
    document_id: str | None = None,
) -> ParsePdfsResult:
    documents = list_downloaded_pdf_documents(conn, limit=limit, document_id=document_id)
    parsed_document_count = 0
    page_count = 0
    failures: list[PdfParseFailure] = []

    for document in documents:
        try:
            pages = extract_pdf_pages(
                document_id=document.document_id,
                local_path=document.local_path,
            )
        except Exception as exc:  # noqa: BLE001 - keep parsing independent documents.
            failures.append(
                PdfParseFailure(
                    document_id=document.document_id,
                    local_path=document.local_path,
                    error=str(exc),
                )
            )
            continue

        replace_document_pages(conn, document.document_id, pages)
        parsed_document_count += 1
        page_count += len(pages)

    return ParsePdfsResult(
        document_count=len(documents),
        parsed_document_count=parsed_document_count,
        page_count=page_count,
        failed_count=len(failures),
        failures=tuple(failures),
    )


def list_downloaded_pdf_documents(
    conn: duckdb.DuckDBPyConnection,
    limit: int | None = None,
    document_id: str | None = None,
) -> list[PendingPdfParseDocument]:
    filters = [
        "local_path IS NOT NULL",
        "(mime_type = 'application/pdf' OR lower(local_path) LIKE '%.pdf')",
    ]
    params: list[object] = []

    if document_id:
        filters.append("document_id = ?")
        params.append(document_id)

    query = f"""
        SELECT document_id, local_path
        FROM source_documents
        WHERE {" AND ".join(filters)}
        ORDER BY document_id
    """
    if limit is not None:
        query += " LIMIT ?"
        params.append(limit)

    rows = conn.execute(query, params).fetchall()
    return [
        PendingPdfParseDocument(
            document_id=row[0],
            local_path=Path(row[1]),
        )
        for row in rows
    ]


def extract_pdf_pages(document_id: str, local_path: Path) -> list[ExtractedPage]:
    import pymupdf

    pages: list[ExtractedPage] = []
    with pymupdf.open(local_path.as_posix()) as pdf:
        for page_index in range(pdf.page_count):
            page_number = page_index + 1
            text = pdf.load_page(page_index).get_text("text") or ""
            char_count = len(text)
            pages.append(
                ExtractedPage(
                    page_id=page_id_for(document_id=document_id, page_number=page_number),
                    document_id=document_id,
                    page_number=page_number,
                    text=text,
                    char_count=char_count,
                    extraction_method="pymupdf",
                    extraction_quality=extraction_quality(char_count),
                )
            )
    return pages


def replace_document_pages(
    conn: duckdb.DuckDBPyConnection,
    document_id: str,
    pages: list[ExtractedPage],
) -> None:
    conn.execute("DELETE FROM pages WHERE document_id = ?", (document_id,))
    if not pages:
        return

    conn.executemany(
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
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                page.page_id,
                page.document_id,
                page.page_number,
                page.text,
                page.char_count,
                page.extraction_method,
                page.extraction_quality,
            )
            for page in pages
        ],
    )


def page_id_for(document_id: str, page_number: int) -> str:
    return f"page-{document_id}-{page_number:04d}"


def extraction_quality(char_count: int) -> str:
    if char_count >= 500:
        return "good"
    if char_count >= 100:
        return "medium"
    return "poor"
