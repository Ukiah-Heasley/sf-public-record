# PlanLens SF

PlanLens SF is a local-first civic document intelligence project for San Francisco Planning Commission materials.

The app is intentionally not a generic "chat with PDFs" wrapper. The core model is civic and source-first:

```text
hearing -> agenda item -> case/project -> supporting documents -> pages/chunks/evidence
```

Milestone 5 implements the local-first MVP: DuckDB initialization, CPC crawling, supporting-document discovery, idempotent PDF downloads, PDF text extraction, agenda item parsing, structure-aware chunking, embeddings, hybrid search, FastAPI routes, and a Next.js frontend.

## Setup

```bash
uv sync
uv run planlens init-db
```

## Milestone 5 CLI

Initialize the local database:

```bash
uv run planlens init-db
```

Crawl recent CPC archive rows:

```bash
uv run planlens crawl-archive --since 2025-01-01 --limit 25
```

By default, `crawl-archive` excludes future hearing dates. Add `--include-future` to keep scheduled future rows from the archive page.

Register agenda, minutes, staff report, presentation, correspondence, notice, and other supporting document links:

```bash
uv run planlens crawl-supporting --limit 25
```

Download registered PDF sources:

```bash
uv run planlens download-pdfs
```

Extract page text from downloaded PDFs:

```bash
uv run planlens parse-pdfs
```

Parse agenda items from extracted agenda pages and link supporting documents when case numbers match:

```bash
uv run planlens parse-agendas
```

Create deterministic, citation-preserving chunks:

```bash
uv run planlens chunk
```

Embed chunks with the configured provider:

```bash
uv run planlens embed
```

Search indexed evidence:

```bash
uv run planlens search "parking opposition near transit"
```

Use `--lexical-only` to debug keyword ranking without embedding the query.

Run the API:

```bash
uv run planlens serve-api
```

Run the frontend in another terminal:

```bash
cd frontend
npm install
npm run dev
```

Then open `http://localhost:3000`.

## Embeddings

The default provider is `local_hash`, an offline deterministic embedding baseline that keeps the MVP runnable without API keys. It is useful for development and hybrid lexical/vector ranking, but it is intentionally swappable.

```bash
PLANLENS_EMBEDDING_PROVIDER=local_hash
PLANLENS_EMBEDDING_MODEL=local-hash-v1
PLANLENS_EMBEDDING_DIMENSIONS=384
```

Future/higher-quality providers can be configured without changing the database shape:

```bash
PLANLENS_EMBEDDING_PROVIDER=openai
PLANLENS_EMBEDDING_MODEL=text-embedding-3-small
OPENAI_API_KEY=...

PLANLENS_EMBEDDING_PROVIDER=google
PLANLENS_EMBEDDING_MODEL=gemini-embedding-001
GOOGLE_API_KEY=...
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

Build the frontend:

```bash
cd frontend
npm run build
```

## Current Limitations

Milestone 5 is an MVP. It returns cited retrieval evidence, but LLM answer generation, hosted deployment, auth, historical backfill, OCR fallback, advanced maps, and polished production analytics are intentionally deferred.

## Roadmap

1. Repo, DB, and CPC archive crawler.
2. Supporting page parser and PDF downloader.
3. PDF text extraction and agenda item parser.
4. Chunking, embeddings, and hybrid search.
5. FastAPI and Next.js MVP.
