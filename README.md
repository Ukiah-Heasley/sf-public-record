# PlanLens SF

PlanLens SF is a local-first civic document intelligence project for San Francisco Planning Commission materials.

The app is intentionally not a generic "chat with PDFs" wrapper. The core model is civic and source-first:

```text
hearing -> agenda item -> case/project -> supporting documents -> pages/chunks/evidence
```

Milestone 2 implements the repository scaffold, DuckDB initialization, the official CPC hearing archive crawler, supporting-page document discovery, and idempotent PDF downloads.

## Setup

```bash
uv sync
uv run --no-editable planlens init-db
```

## Milestone 2 CLI

Initialize the local database:

```bash
uv run --no-editable planlens init-db
```

Crawl recent CPC archive rows:

```bash
uv run --no-editable planlens crawl-archive --since 2025-01-01 --limit 25
```

By default, `crawl-archive` excludes future hearing dates. Add `--include-future` to keep scheduled future rows from the archive page.

Register agenda, minutes, staff report, presentation, correspondence, notice, and other supporting document links:

```bash
uv run --no-editable planlens crawl-supporting --limit 25
```

Download registered PDF sources:

```bash
uv run --no-editable planlens download-pdfs
```

## Data Directory

```text
data/
  raw/
    html/       archived CPC HTML snapshots
    pdfs/       downloaded source PDFs
  processed/    future parsed artifacts
  exports/      future exports
  planlens.duckdb
```

Generated local data is ignored by git, while the directory structure is kept with `.gitkeep` files.

## Development

Run tests:

```bash
uv run pytest
```

Run linting:

```bash
uv run ruff check
```

## Current Limitations

Milestone 2 stores hearing metadata and source document PDF metadata. PDF text extraction, agenda item parsing, chunking, embeddings, search, API routes, and the frontend are intentionally left for later milestones.

## Roadmap

1. Repo, DB, and CPC archive crawler.
2. Supporting page parser and PDF downloader.
3. PDF text extraction and agenda item parser.
4. Chunking, embeddings, and hybrid search.
5. FastAPI and Next.js MVP.
