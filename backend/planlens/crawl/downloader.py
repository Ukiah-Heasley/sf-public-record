from __future__ import annotations

import hashlib
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import duckdb
import httpx

from ..config import Settings
from ..db import connect


@dataclass(frozen=True)
class PendingPdfDocument:
    document_id: str
    url: str
    local_path: str | None
    sha256: str | None


@dataclass(frozen=True)
class DownloadFailure:
    document_id: str
    url: str
    error: str


@dataclass(frozen=True)
class DownloadPdfsResult:
    total_count: int
    downloaded_count: int
    skipped_count: int
    failed_count: int
    failures: tuple[DownloadFailure, ...]


def download_pdfs(
    db_path: Path | str,
    settings: Settings,
    limit: int | None = None,
    force: bool = False,
) -> DownloadPdfsResult:
    with connect(db_path) as conn:
        return download_pdf_documents(
            conn=conn,
            settings=settings,
            limit=limit,
            force=force,
        )


def download_pdf_documents(
    conn: duckdb.DuckDBPyConnection,
    settings: Settings,
    limit: int | None = None,
    force: bool = False,
    client: httpx.Client | None = None,
    sleep: Callable[[float], None] = time.sleep,
    max_retries: int = 3,
) -> DownloadPdfsResult:
    documents = list_pending_pdf_documents(conn, limit=limit)
    settings.pdf_dir.mkdir(parents=True, exist_ok=True)

    downloaded_count = 0
    skipped_count = 0
    failures: list[DownloadFailure] = []

    owns_client = client is None
    if client is None:
        client = httpx.Client(
            headers={"User-Agent": settings.user_agent},
            follow_redirects=True,
            timeout=60.0,
        )

    try:
        for index, document in enumerate(documents):
            target_path = pdf_path_for_document(settings.pdf_dir, document.document_id)
            existing_path = Path(document.local_path) if document.local_path else target_path

            if not force and existing_path.exists():
                file_sha = sha256_file(existing_path)
                if document.sha256 is None or file_sha == document.sha256:
                    update_download_metadata(
                        conn=conn,
                        document_id=document.document_id,
                        local_path=existing_path,
                        sha256=file_sha,
                        mime_type="application/pdf",
                        file_size_bytes=existing_path.stat().st_size,
                    )
                    skipped_count += 1
                    continue

            try:
                content, mime_type = fetch_pdf_content(
                    client=client,
                    url=document.url,
                    max_retries=max_retries,
                    sleep=sleep,
                )
            except Exception as exc:  # noqa: BLE001 - keep the batch moving.
                failures.append(
                    DownloadFailure(
                        document_id=document.document_id,
                        url=document.url,
                        error=str(exc),
                    )
                )
                continue

            content_sha = hashlib.sha256(content).hexdigest()
            target_path.write_bytes(content)
            update_download_metadata(
                conn=conn,
                document_id=document.document_id,
                local_path=target_path,
                sha256=content_sha,
                mime_type=mime_type,
                file_size_bytes=len(content),
            )
            downloaded_count += 1

            if settings.crawl_delay_seconds > 0 and index < len(documents) - 1:
                sleep(settings.crawl_delay_seconds)
    finally:
        if owns_client:
            client.close()

    return DownloadPdfsResult(
        total_count=len(documents),
        downloaded_count=downloaded_count,
        skipped_count=skipped_count,
        failed_count=len(failures),
        failures=tuple(failures),
    )


def list_pending_pdf_documents(
    conn: duckdb.DuckDBPyConnection,
    limit: int | None = None,
) -> list[PendingPdfDocument]:
    query = """
        SELECT document_id, url, local_path, sha256
        FROM source_documents
        WHERE lower(url) LIKE '%.pdf%'
        ORDER BY document_id
    """
    params: list[object] = []
    if limit is not None:
        query += " LIMIT ?"
        params.append(limit)

    rows = conn.execute(query, params).fetchall()
    return [
        PendingPdfDocument(
            document_id=row[0],
            url=row[1],
            local_path=row[2],
            sha256=row[3],
        )
        for row in rows
    ]


def fetch_pdf_content(
    client: httpx.Client,
    url: str,
    max_retries: int = 3,
    sleep: Callable[[float], None] = time.sleep,
) -> tuple[bytes, str]:
    last_error: Exception | None = None

    for attempt in range(max_retries):
        try:
            response = client.get(url)
            if response.status_code == 429 or response.status_code >= 500:
                response.raise_for_status()
            response.raise_for_status()

            content_type = response.headers.get("content-type", "").split(";", maxsplit=1)[0]
            mime_type = content_type.strip().lower() or "application/pdf"
            content = response.content

            if not is_pdf_response(url=url, mime_type=mime_type, content=content):
                raise ValueError(f"Response is not a PDF: {mime_type or 'unknown content type'}")

            if mime_type == "application/octet-stream":
                return content, "application/pdf"
            return content, mime_type
        except Exception as exc:  # noqa: BLE001 - retry HTTP and transport failures together.
            last_error = exc
            if attempt < max_retries - 1:
                sleep(2**attempt)

    assert last_error is not None
    raise last_error


def update_download_metadata(
    conn: duckdb.DuckDBPyConnection,
    document_id: str,
    local_path: Path,
    sha256: str,
    mime_type: str,
    file_size_bytes: int,
) -> None:
    conn.execute(
        """
        UPDATE source_documents
        SET
            local_path = ?,
            sha256 = ?,
            mime_type = ?,
            file_size_bytes = ?,
            downloaded_at = now()
        WHERE document_id = ?
        """,
        (
            local_path.as_posix(),
            sha256,
            mime_type,
            file_size_bytes,
            document_id,
        ),
    )


def is_pdf_response(url: str, mime_type: str, content: bytes) -> bool:
    if "pdf" in mime_type:
        return True
    if mime_type == "application/octet-stream" and content.startswith(b"%PDF"):
        return True
    return url.lower().split("?", maxsplit=1)[0].endswith(".pdf") and content.startswith(b"%PDF")


def pdf_path_for_document(pdf_dir: Path, document_id: str) -> Path:
    return pdf_dir / f"{document_id}.pdf"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
