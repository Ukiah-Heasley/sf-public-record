# PlanLens SF — MVP Implementation Plan for Codex

## Project Goal

Build a local-first civic document intelligence app for SF Planning Commission materials.

The MVP should crawl recent San Francisco Planning Commission hearing pages, download agendas and supporting PDFs, parse them into structured tables, create searchable chunks with citations, and expose a polished UI for:

1. Searching planning documents with citations.
2. Browsing hearings and agenda items.
3. Viewing a YIMBY-focused dashboard.
4. Inspecting source evidence from PDFs.

This is not a generic “chat with PDFs” app. The core data model should be:

```text
hearing → agenda item → case/project → supporting documents → pages/chunks/evidence
```

## MVP Scope

Implement for the most recent 6–12 months of Planning Commission hearings.

Include:

```text
- CPC archive crawler
- Supporting packet page crawler
- PDF downloader with content hashing
- PDF text extraction
- Agenda item parser
- Staff report / correspondence document registry
- DuckDB schema
- Basic chunking
- Embedding pipeline
- Hybrid search endpoint
- Frontend dashboard
- Frontend search page
- Frontend hearing / agenda item detail page
```

Defer:

```text
- Full historical backfill
- Perfect OCR
- Perfect table extraction
- Full public-comment deduplication
- Auth
- User accounts
- Cloud deployment
- Rust rewrite
- Parcel-level maps
```

## Recommended Stack

Backend:

```text
Python 3.12
uv
FastAPI
DuckDB
Pydantic
httpx
BeautifulSoup4
PyMuPDF
Docling optional/parser adapter
sentence-transformers
Typer CLI
pytest
ruff
```

Frontend:

```text
Next.js
TypeScript
Tailwind
shadcn/ui
Recharts
```

Storage:

```text
data/
  raw/
    pdfs/
    html/
  processed/
  planlens.duckdb
```

## Repo Structure

Create this structure:

```text
planlens-sf/
  README.md
  pyproject.toml
  .env.example
  .gitignore

  data/
    raw/
      html/
      pdfs/
    processed/
    exports/

  backend/
    planlens/
      __init__.py

      config.py
      db.py

      cli.py

      crawl/
        __init__.py
        cpc_archive.py
        supporting_pages.py
        downloader.py
        models.py

      parse/
        __init__.py
        pdf_text.py
        agenda_parser.py
        chunker.py
        normalizers.py

      embed/
        __init__.py
        embeddings.py

      search/
        __init__.py
        hybrid.py

      api/
        __init__.py
        main.py
        routes_search.py
        routes_hearings.py
        routes_dashboard.py

      sql/
        001_init.sql
        002_indexes.sql

      tests/
        test_agenda_parser.py
        test_chunker.py
        test_archive_crawler.py

  frontend/
    package.json
    next.config.js
    app/
      page.tsx
      search/page.tsx
      dashboard/page.tsx
      hearings/page.tsx
      hearings/[hearingId]/page.tsx
      projects/[caseNumber]/page.tsx
    components/
      AppShell.tsx
      SearchBox.tsx
      AnswerCard.tsx
      CitationChip.tsx
      SourcePreview.tsx
      MetricCard.tsx
      OppositionThemesChart.tsx
      HearingTable.tsx
      ProjectCard.tsx
    lib/
      api.ts
      types.ts
```

## Environment Variables

Create `.env.example`:

```bash
PLANLENS_DB_PATH=data/planlens.duckdb
PLANLENS_RAW_DIR=data/raw
PLANLENS_USER_AGENT="PlanLensSF/0.1 civic research crawler; contact: local-dev"
PLANLENS_CRAWL_DELAY_SECONDS=1.0
PLANLENS_EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2
PLANLENS_ENABLE_OPENAI=false
OPENAI_API_KEY=
```

## DuckDB Schema

Implement `backend/planlens/sql/001_init.sql`.

Use stable IDs based on hashes where possible.

```sql
CREATE TABLE IF NOT EXISTS hearings (
    hearing_id VARCHAR PRIMARY KEY,
    hearing_date DATE NOT NULL,
    title VARCHAR,
    status VARCHAR,
    agenda_url VARCHAR,
    minutes_url VARCHAR,
    supporting_url VARCHAR,
    source_url VARCHAR NOT NULL,
    crawled_at TIMESTAMP DEFAULT current_timestamp
);

CREATE TABLE IF NOT EXISTS source_documents (
    document_id VARCHAR PRIMARY KEY,
    hearing_id VARCHAR,
    source_type VARCHAR NOT NULL,
    title VARCHAR,
    url VARCHAR NOT NULL,
    local_path VARCHAR,
    sha256 VARCHAR,
    mime_type VARCHAR,
    file_size_bytes BIGINT,
    downloaded_at TIMESTAMP,
    FOREIGN KEY (hearing_id) REFERENCES hearings(hearing_id)
);

CREATE TABLE IF NOT EXISTS pages (
    page_id VARCHAR PRIMARY KEY,
    document_id VARCHAR NOT NULL,
    page_number INTEGER NOT NULL,
    text TEXT,
    char_count INTEGER,
    extraction_method VARCHAR,
    extraction_quality VARCHAR,
    FOREIGN KEY (document_id) REFERENCES source_documents(document_id)
);

CREATE TABLE IF NOT EXISTS chunks (
    chunk_id VARCHAR PRIMARY KEY,
    document_id VARCHAR NOT NULL,
    page_start INTEGER,
    page_end INTEGER,
    chunk_index INTEGER,
    text TEXT NOT NULL,
    token_estimate INTEGER,
    section_hint VARCHAR,
    citation_label VARCHAR,
    FOREIGN KEY (document_id) REFERENCES source_documents(document_id)
);

CREATE TABLE IF NOT EXISTS chunk_embeddings (
    chunk_id VARCHAR PRIMARY KEY,
    embedding_model VARCHAR NOT NULL,
    embedding FLOAT[384],
    embedded_at TIMESTAMP DEFAULT current_timestamp,
    FOREIGN KEY (chunk_id) REFERENCES chunks(chunk_id)
);

CREATE TABLE IF NOT EXISTS agenda_items (
    agenda_item_id VARCHAR PRIMARY KEY,
    hearing_id VARCHAR NOT NULL,
    item_number VARCHAR,
    section VARCHAR,
    case_number VARCHAR,
    case_suffix VARCHAR,
    address VARCHAR,
    district VARCHAR,
    planner_name VARCHAR,
    planner_contact VARCHAR,
    project_description TEXT,
    entitlement_type VARCHAR,
    ceqa_status VARCHAR,
    preliminary_recommendation VARCHAR,
    continued_from VARCHAR,
    proposed_continuance_date DATE,
    raw_text TEXT,
    parser_confidence DOUBLE,
    FOREIGN KEY (hearing_id) REFERENCES hearings(hearing_id)
);

CREATE TABLE IF NOT EXISTS document_links (
    link_id VARCHAR PRIMARY KEY,
    agenda_item_id VARCHAR,
    document_id VARCHAR,
    relationship VARCHAR,
    confidence DOUBLE,
    FOREIGN KEY (agenda_item_id) REFERENCES agenda_items(agenda_item_id),
    FOREIGN KEY (document_id) REFERENCES source_documents(document_id)
);

CREATE TABLE IF NOT EXISTS extraction_runs (
    run_id VARCHAR PRIMARY KEY,
    run_type VARCHAR NOT NULL,
    started_at TIMESTAMP DEFAULT current_timestamp,
    completed_at TIMESTAMP,
    status VARCHAR,
    metadata_json JSON
);
```

Implement `002_indexes.sql`:

```sql
CREATE INDEX IF NOT EXISTS idx_hearings_date ON hearings(hearing_date);
CREATE INDEX IF NOT EXISTS idx_documents_hearing ON source_documents(hearing_id);
CREATE INDEX IF NOT EXISTS idx_pages_document ON pages(document_id);
CREATE INDEX IF NOT EXISTS idx_chunks_document ON chunks(document_id);
CREATE INDEX IF NOT EXISTS idx_agenda_hearing ON agenda_items(hearing_id);
CREATE INDEX IF NOT EXISTS idx_agenda_case ON agenda_items(case_number);
```

Also initialize DuckDB FTS when chunks exist:

```sql
INSTALL fts;
LOAD fts;

PRAGMA create_fts_index(
  'chunks',
  'chunk_id',
  'text',
  overwrite = 1
);
```

For vector search, implement a feature flag because DuckDB VSS is experimental:

```sql
INSTALL vss;
LOAD vss;

CREATE INDEX IF NOT EXISTS hnsw_chunks
ON chunk_embeddings
USING HNSW (embedding);
```

If VSS fails, fall back to exact vector ordering.

## CLI Commands

Implement a Typer CLI at `backend/planlens/cli.py`.

Required commands:

```bash
planlens init-db
planlens crawl-archive --since 2025-01-01 --limit 50
planlens crawl-supporting
planlens download-pdfs
planlens parse-pdfs
planlens parse-agendas
planlens chunk
planlens embed
planlens search "parking opposition near transit"
planlens serve-api
```

Each command should be idempotent.

Do not redownload unchanged PDFs. Use URL + SHA256/content hash.

## Crawler Requirements

### `crawl/cpc_archive.py`

Implement a crawler that fetches the CPC hearing archive page and extracts rows with:

```text
hearing_date
status
agenda_url
minutes_url
supporting_url
source_url
```

Handle cancelled rows gracefully.

Do not assume every row has all links.

Store HTML snapshots in:

```text
data/raw/html/
```

Acceptance criteria:

```text
- Running crawl-archive creates hearing rows in DuckDB.
- Cancelled hearings are stored with status = cancelled.
- Missing links are null, not errors.
- The crawler is safe to rerun.
```

### `crawl/supporting_pages.py`

For each hearing with a supporting URL, fetch the page and extract links under:

```text
Staff Report
Presentation(s)
Correspondence
```

Store linked documents in `source_documents`.

Document source types:

```text
agenda
minutes
staff_report
presentation
correspondence_pre_hearing
correspondence_at_hearing
notice
other
```

Acceptance criteria:

```text
- Staff report links are classified as staff_report.
- Correspondence links are classified separately where possible.
- Existing document rows are upserted, not duplicated.
```

### `crawl/downloader.py`

Download all PDF URLs into:

```text
data/raw/pdfs/{document_id}.pdf
```

Implement:

```text
- polite delay
- retry with exponential backoff
- content-type check
- SHA256 hash
- file size
- skip if already downloaded and hash unchanged
```

Acceptance criteria:

```text
- Local PDF path, SHA256, file size, and timestamp are stored.
- Rerunning does not duplicate files.
```

## PDF Parsing

### `parse/pdf_text.py`

Implement parser adapter:

1. Try PyMuPDF text extraction first.
2. Store one row per page.
3. Compute simple extraction quality.

Quality heuristic:

```text
good: char_count >= 500
medium: 100 <= char_count < 500
poor: char_count < 100
```

Optional later:

```text
- Use Docling as a second parser.
- Add OCR fallback for poor pages.
```

Acceptance criteria:

```text
- Every parsed PDF creates pages.
- Each page has document_id, page_number, text, char_count, extraction_method.
- Empty pages do not crash the pipeline.
```

## Agenda Parser

### `parse/agenda_parser.py`

Parse agenda PDFs into agenda items.

Start with regex and line-based parsing. Good enough is fine.

Fields to extract:

```text
item_number
case_number
case_suffix
address
district
planner_name
planner_contact
project_description
entitlement_type
ceqa_status
preliminary_recommendation
continued_from
proposed_continuance_date
raw_text
parser_confidence
```

Useful regex patterns:

```python
CASE_RE = r"\b20\d{2}-\d{6}[A-Z0-9\-]*\b"
ITEM_RE = r"^\s*(\d+[a-zA-Z]?)\.\s+"
PHONE_RE = r"\(?\d{3}\)?[-.\s]\d{3}[-.\s]\d{4}"
EMAIL_RE = r"[\w\.-]+@sfgov\.org"
RECOMMENDATION_RE = r"Preliminary Recommendation:\s*(.+)"
DISTRICT_RE = r"District\s+(\d+)"
```

Implementation approach:

```text
1. Find agenda documents.
2. Concatenate page text with page markers.
3. Split by item number headings.
4. Extract fields from each block.
5. Store raw block text even when parsing is imperfect.
6. Assign parser_confidence based on extracted field count.
```

Acceptance criteria:

```text
- At least item_number, raw_text, and case_number are captured when present.
- Parser does not crash on non-standard agenda items.
- Parser confidence is stored.
```

## Linking Documents to Agenda Items

Implement simple linking first:

```text
- If source_documents.title contains a case number, link to matching agenda_items.case_number.
- If URL filename/title contains case number, link to matching agenda item.
- If no case number match, leave unlinked.
```

Acceptance criteria:

```text
- Staff reports with matching case numbers are linked to agenda items.
- Link confidence is 1.0 for exact case number matches.
```

## Chunking

### `parse/chunker.py`

Chunk page text by document.

Requirements:

```text
- Chunk size target: 800–1,200 tokens estimated.
- Overlap: 100–150 tokens estimated.
- Preserve page_start and page_end.
- Generate citation label like: "Oct 2, 2025 Staff Report · p. 12"
```

Use simple token estimate:

```python
token_estimate = len(text) // 4
```

Acceptance criteria:

```text
- Chunks preserve source document and page range.
- Chunks are deterministic/idempotent.
- Empty/poor pages do not create useless chunks.
```

## Embeddings

### `embed/embeddings.py`

Use `sentence-transformers/all-MiniLM-L6-v2` for MVP because it returns 384-dimensional vectors.

Requirements:

```text
- Batch embeddings.
- Skip chunks already embedded with same model.
- Store vectors in FLOAT[384].
- Provide a clean adapter so OpenAI embeddings can be added later.
```

Acceptance criteria:

```text
- Running planlens embed populates chunk_embeddings.
- Rerunning skips existing embeddings.
- Embedding dimension matches DuckDB schema.
```

## Search

### `search/hybrid.py`

Implement hybrid search.

Inputs:

```text
query: str
date_start: optional date
date_end: optional date
document_types: optional list
limit: default 10
```

Search strategy:

```text
1. FTS search against chunks.
2. Vector search against chunk_embeddings.
3. Normalize scores.
4. Merge results by chunk_id.
5. Return ranked chunks with document metadata and citation labels.
```

Initial score formula:

```text
hybrid_score = 0.55 * vector_score + 0.35 * fts_score + 0.10 * metadata_boost
```

Do not over-optimize ranking yet.

Acceptance criteria:

```text
- Search returns chunk text, citation label, document title, source URL, page range.
- Search works even if vector index is unavailable.
- Search works even if FTS index is unavailable, as long as embeddings exist.
```

## API

Implement FastAPI app.

Routes:

```text
GET /health

GET /hearings
GET /hearings/{hearing_id}
GET /hearings/{hearing_id}/agenda-items

GET /agenda-items/{agenda_item_id}

GET /dashboard/summary
GET /dashboard/opposition-themes
GET /dashboard/recent-activity

POST /search
```

`POST /search` request:

```json
{
  "query": "Which housing projects were delayed because of parking concerns?",
  "date_start": "2025-01-01",
  "date_end": null,
  "document_types": ["staff_report", "correspondence_pre_hearing"],
  "limit": 10
}
```

`POST /search` response:

```json
{
  "query": "...",
  "answer_stub": "Answer generation not implemented yet.",
  "results": [
    {
      "chunk_id": "...",
      "document_id": "...",
      "title": "...",
      "source_type": "staff_report",
      "hearing_date": "2025-10-02",
      "page_start": 12,
      "page_end": 13,
      "citation_label": "Oct 2, 2025 Staff Report · pp. 12–13",
      "text": "...",
      "score": 0.87,
      "url": "..."
    }
  ]
}
```

Do not implement LLM answer generation in the first pass. Return retrieved evidence first. Add answer generation later.

## Frontend Product Requirements

The UI is first-class. Do not make this look like a backend admin tool.

Build three pages first:

```text
/dashboard
/search
/hearings/[hearingId]
```

### Dashboard Page

Purpose: make the project feel compelling immediately.

Components:

```text
- Hero section: “Where does SF housing get delayed?”
- Metric cards:
  - hearings indexed
  - PDFs downloaded
  - pages parsed
  - agenda items extracted
  - staff reports linked
- Recent hearings table
- Top document types
- Extraction health card
- Placeholder “YIMBY signals” card
```

Use real data from API where possible.

### Search Page

Purpose: cited civic search experience.

Components:

```text
- Large search box
- Example query chips
- Search results list
- Citation chips
- Source preview panel
- Filters:
  - date range
  - document type
  - source type
```

Example queries:

```text
Which projects were delayed because of parking concerns?
Which staff reports mention Housing Element compliance?
Show housing projects near transit with public opposition.
What public comments mention neighborhood character?
```

### Hearing Detail Page

Purpose: turn a meeting into understandable civic units.

Components:

```text
- Hearing title/date/status
- Links to agenda/minutes/supporting page
- Agenda items list
- Source documents grouped by type
- Parser/extraction status
```

## UI Style Direction

Use a polished civic-intelligence aesthetic:

```text
- warm off-white background
- deep green / dark slate accents
- orange/gold highlights
- rounded cards
- dashboard metrics
- citation chips
- source preview side panel
```

The app should feel like:

```text
civic intelligence briefing + searchable evidence room
```

Not:

```text
generic chatbot
```

## First Implementation Milestones

### Milestone 1 — Repo + DB + Archive Crawler

Build:

```text
- repo structure
- pyproject.toml
- DuckDB init
- hearings table
- archive crawler
- CLI command: planlens crawl-archive
```

Acceptance:

```text
- Can crawl CPC archive and insert recent hearing rows.
- Tests pass.
```

### Milestone 2 — Supporting Pages + PDF Download

Build:

```text
- supporting page parser
- source_documents table population
- PDF downloader
- content hashing
```

Acceptance:

```text
- Can download agendas and staff report PDFs for recent hearings.
- Reruns are idempotent.
```

### Milestone 3 — PDF Text + Agenda Items

Build:

```text
- PDF page extraction
- agenda parser
- agenda_items table
```

Acceptance:

```text
- Agenda PDFs produce parsed agenda items.
- Case numbers and raw agenda text are stored.
```

### Milestone 4 — Chunking + Embeddings + Search

Build:

```text
- chunker
- local embeddings
- search endpoint
- CLI search
```

Acceptance:

```text
- User can search local corpus and receive cited chunks.
```

### Milestone 5 — API + Frontend MVP

Build:

```text
- FastAPI routes
- Next.js dashboard
- Next.js search page
- Next.js hearing detail page
```

Acceptance:

```text
- The app is demoable locally.
- Dashboard uses real backend metrics.
- Search returns real cited results.
```

## Testing Requirements

Add tests for:

```text
- archive row parsing
- supporting page link classification
- agenda item regex extraction
- chunk determinism
- search response shape
```

Use small HTML/PDF fixtures where practical.

## README Requirements

README should include:

```text
- Project purpose
- Why this is not generic RAG
- Setup instructions
- CLI usage
- Data directory explanation
- Current limitations
- Roadmap
```

Local run commands:

```bash
uv sync
uv run planlens init-db
uv run planlens crawl-archive --since 2025-01-01 --limit 25
uv run planlens crawl-supporting
uv run planlens download-pdfs
uv run planlens parse-pdfs
uv run planlens parse-agendas
uv run planlens chunk
uv run planlens embed
uv run planlens serve-api
cd frontend && npm install && npm run dev
```

## Development Philosophy

Prioritize:

```text
- clean schema
- idempotent pipeline
- source citations
- beautiful UI
- narrow but impressive demo
```

Avoid:

```text
- overbuilding infra
- parsing every historical edge case
- premature Rust rewrite
- generic chatbot UX
- uncited LLM answers
```

The first demo should answer:

> Can a normal person understand recent SF Planning Commission housing activity without reading hundreds of pages of PDFs?
