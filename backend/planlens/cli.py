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

app = typer.Typer(no_args_is_help=True, help="PlanLens SF local pipeline commands.")


def _parse_date(value: str | None) -> date | None:
    if value is None:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise typer.BadParameter("Use YYYY-MM-DD format.") from exc


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


if __name__ == "__main__":
    app()
