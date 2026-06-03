from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Annotated

import typer

from .config import Settings
from .crawl.cpc_archive import ARCHIVE_URL, crawl_archive
from .crawl.downloader import download_pdfs
from .crawl.supporting_pages import crawl_supporting_pages
from .db import init_db
from .embed.embeddings import embed_chunks
from .parse.agenda_parser import parse_agendas
from .parse.chunker import chunk_documents
from .parse.pdf_text import parse_pdfs
from .search.hybrid import hybrid_search, lexical_search

app = typer.Typer(no_args_is_help=True, help="PlanLens SF local pipeline commands.")


def _parse_date(value: str | None) -> date | None:
    if value is None:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise typer.BadParameter("Use YYYY-MM-DD format.") from exc


def _parse_csv(value: str | None) -> list[str] | None:
    if not value:
        return None
    return [part.strip() for part in value.split(",") if part.strip()]


def _snippet(text: str, limit: int = 260) -> str:
    compact = " ".join(text.split())
    if len(compact) <= limit:
        return compact
    return f"{compact[: limit - 3].rstrip()}..."


@app.command("init-db")
def init_db_command(
    db_path: Annotated[Path | None, typer.Option(help="DuckDB database path.")] = None,
) -> None:
    """Create or migrate the local DuckDB database."""
    settings = Settings.from_env()
    target = db_path or settings.db_path
    init_db(target)
    typer.echo(f"Initialized DuckDB at {target}")


@app.command("crawl-archive")
def crawl_archive_command(
    since: Annotated[
        str | None,
        typer.Option(help="Inclusive lower bound, YYYY-MM-DD."),
    ] = None,
    limit: Annotated[int, typer.Option(min=1, help="Maximum hearing rows to insert.")] = 50,
    include_future: Annotated[
        bool,
        typer.Option(help="Include future dated archive rows."),
    ] = False,
    archive_url: Annotated[str, typer.Option(help="CPC archive URL.")] = ARCHIVE_URL,
    db_path: Annotated[Path | None, typer.Option(help="DuckDB database path.")] = None,
) -> None:
    """Fetch the CPC hearing archive and upsert hearing rows."""
    settings = Settings.from_env()
    target = db_path or settings.db_path
    init_db(target)

    result = crawl_archive(
        db_path=target,
        settings=settings,
        source_url=archive_url,
        since=_parse_date(since),
        limit=limit,
        include_future=include_future,
    )

    typer.echo(f"Saved archive snapshot: {result.snapshot_path}")
    typer.echo(f"Parsed hearing rows: {result.parsed_count}")
    typer.echo(f"Upserted hearing rows: {result.upserted_count}")


@app.command("crawl-supporting")
def crawl_supporting_command(
    limit: Annotated[int | None, typer.Option(min=1, help="Maximum hearings to scan.")] = 50,
    hearing_id: Annotated[
        str | None,
        typer.Option(help="Only scan one hearing ID."),
    ] = None,
    db_path: Annotated[Path | None, typer.Option(help="DuckDB database path.")] = None,
) -> None:
    """Fetch CPC supporting pages and upsert source document rows."""
    settings = Settings.from_env()
    target = db_path or settings.db_path
    init_db(target)

    result = crawl_supporting_pages(
        db_path=target,
        settings=settings,
        limit=limit,
        hearing_id=hearing_id,
    )

    typer.echo(f"Scanned hearings: {result.hearing_count}")
    typer.echo(f"Saved supporting snapshots: {len(result.snapshot_paths)}")
    typer.echo(f"Upserted source documents: {result.upserted_document_count}")


@app.command("download-pdfs")
def download_pdfs_command(
    limit: Annotated[
        int | None,
        typer.Option(min=1, help="Maximum source documents to download."),
    ] = None,
    force: Annotated[
        bool,
        typer.Option(help="Redownload PDFs even when local hash metadata matches."),
    ] = False,
    db_path: Annotated[Path | None, typer.Option(help="DuckDB database path.")] = None,
) -> None:
    """Download registered PDF source documents into the local raw PDF directory."""
    settings = Settings.from_env()
    target = db_path or settings.db_path
    init_db(target)

    result = download_pdfs(
        db_path=target,
        settings=settings,
        limit=limit,
        force=force,
    )

    typer.echo(f"PDF source documents: {result.total_count}")
    typer.echo(f"Downloaded PDFs: {result.downloaded_count}")
    typer.echo(f"Skipped PDFs: {result.skipped_count}")
    typer.echo(f"Failed PDFs: {result.failed_count}")
    for failure in result.failures:
        typer.echo(f"- {failure.document_id}: {failure.error}")


@app.command("parse-pdfs")
def parse_pdfs_command(
    limit: Annotated[
        int | None,
        typer.Option(min=1, help="Maximum downloaded PDF documents to parse."),
    ] = None,
    document_id: Annotated[
        str | None,
        typer.Option(help="Only parse one source document ID."),
    ] = None,
    db_path: Annotated[Path | None, typer.Option(help="DuckDB database path.")] = None,
) -> None:
    """Extract page text from downloaded PDF documents."""
    settings = Settings.from_env()
    target = db_path or settings.db_path
    init_db(target)

    result = parse_pdfs(
        db_path=target,
        limit=limit,
        document_id=document_id,
    )

    typer.echo(f"PDF documents considered: {result.document_count}")
    typer.echo(f"Parsed PDF documents: {result.parsed_document_count}")
    typer.echo(f"Extracted pages: {result.page_count}")
    typer.echo(f"Failed PDFs: {result.failed_count}")
    for failure in result.failures:
        typer.echo(f"- {failure.document_id}: {failure.error}")


@app.command("parse-agendas")
def parse_agendas_command(
    limit: Annotated[
        int | None,
        typer.Option(min=1, help="Maximum agenda documents to parse."),
    ] = None,
    hearing_id: Annotated[
        str | None,
        typer.Option(help="Only parse agendas for one hearing ID."),
    ] = None,
    document_id: Annotated[
        str | None,
        typer.Option(help="Only parse one agenda source document ID."),
    ] = None,
    link_documents: Annotated[
        bool,
        typer.Option(help="Link matching staff reports/supporting docs to agenda items."),
    ] = True,
    db_path: Annotated[Path | None, typer.Option(help="DuckDB database path.")] = None,
) -> None:
    """Parse agenda item rows from extracted agenda PDF pages."""
    settings = Settings.from_env()
    target = db_path or settings.db_path
    init_db(target)

    result = parse_agendas(
        db_path=target,
        limit=limit,
        hearing_id=hearing_id,
        document_id=document_id,
        link_documents=link_documents,
    )

    typer.echo(f"Agenda documents considered: {result.document_count}")
    typer.echo(f"Parsed agenda documents: {result.parsed_document_count}")
    typer.echo(f"Extracted agenda items: {result.agenda_item_count}")
    typer.echo(f"Linked supporting documents: {result.linked_document_count}")


@app.command("chunk")
def chunk_command(
    limit: Annotated[
        int | None,
        typer.Option(min=1, help="Maximum parsed documents to chunk."),
    ] = None,
    document_id: Annotated[
        str | None,
        typer.Option(help="Only chunk one source document ID."),
    ] = None,
    db_path: Annotated[Path | None, typer.Option(help="DuckDB database path.")] = None,
) -> None:
    """Create deterministic search chunks from extracted page text."""
    settings = Settings.from_env()
    target = db_path or settings.db_path
    init_db(target)

    result = chunk_documents(
        db_path=target,
        settings=settings,
        limit=limit,
        document_id=document_id,
    )

    typer.echo(f"Parsed documents considered: {result.document_count}")
    typer.echo(f"Chunks written: {result.chunk_count}")


@app.command("embed")
def embed_command(
    batch_size: Annotated[
        int,
        typer.Option(min=1, help="Embedding batch size."),
    ] = 32,
    limit: Annotated[
        int | None,
        typer.Option(min=1, help="Maximum chunks to embed."),
    ] = None,
    force: Annotated[
        bool,
        typer.Option(help="Recompute embeddings for the configured provider/model."),
    ] = False,
    db_path: Annotated[Path | None, typer.Option(help="DuckDB database path.")] = None,
) -> None:
    """Embed chunks with the configured embedding provider."""
    settings = Settings.from_env()
    target = db_path or settings.db_path
    init_db(target)

    result = embed_chunks(
        db_path=target,
        settings=settings,
        batch_size=batch_size,
        limit=limit,
        force=force,
    )

    typer.echo(f"Embedding provider: {result.embedding_provider}")
    typer.echo(f"Embedding model: {result.embedding_model}")
    typer.echo(f"Embedding dimensions: {result.embedding_dim}")
    typer.echo(f"Chunks available: {result.chunk_count}")
    typer.echo(f"Chunks embedded: {result.embedded_count}")
    typer.echo(f"Chunks skipped: {result.skipped_count}")


@app.command("search")
def search_command(
    query: Annotated[str, typer.Argument(help="Search query.")],
    limit: Annotated[int, typer.Option(min=1, help="Maximum results.")] = 10,
    date_start: Annotated[
        str | None,
        typer.Option(help="Inclusive lower hearing date bound, YYYY-MM-DD."),
    ] = None,
    date_end: Annotated[
        str | None,
        typer.Option(help="Inclusive upper hearing date bound, YYYY-MM-DD."),
    ] = None,
    document_types: Annotated[
        str | None,
        typer.Option(help="Comma-separated source document types to include."),
    ] = None,
    lexical_only: Annotated[
        bool,
        typer.Option(help="Use lexical ranking only, without embedding the query."),
    ] = False,
    db_path: Annotated[Path | None, typer.Option(help="DuckDB database path.")] = None,
) -> None:
    """Search chunks with hybrid lexical/vector ranking."""
    settings = Settings.from_env()
    target = db_path or settings.db_path
    init_db(target)

    if lexical_only:
        response = lexical_search(
            db_path=target,
            query=query,
            date_start=_parse_date(date_start),
            date_end=_parse_date(date_end),
            document_types=_parse_csv(document_types),
            limit=limit,
        )
    else:
        response = hybrid_search(
            db_path=target,
            settings=settings,
            query=query,
            date_start=_parse_date(date_start),
            date_end=_parse_date(date_end),
            document_types=_parse_csv(document_types),
            limit=limit,
        )

    typer.echo(f"Query: {response.query}")
    typer.echo(response.answer_stub)
    for index, result in enumerate(response.results, start=1):
        typer.echo("")
        typer.echo(
            f"{index}. score={result.score:.4f} "
            f"vector={result.vector_score:.4f} lexical={result.lexical_score:.4f}"
        )
        typer.echo(result.citation_label or result.chunk_id)
        typer.echo(f"{result.title or result.source_type} - {result.url}")
        typer.echo(_snippet(result.text))


if __name__ == "__main__":
    app()
