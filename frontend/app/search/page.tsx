"use client";

import { Search, SlidersHorizontal } from "lucide-react";
import { FormEvent, useState } from "react";
import { searchEvidence } from "../../lib/api";
import type { SearchResultItem } from "../../lib/types";

const DOCUMENT_TYPES = [
  "staff_report",
  "correspondence_pre_hearing",
  "correspondence_at_hearing",
  "presentation",
  "agenda"
];

export default function SearchPage() {
  const [query, setQuery] = useState("parking opposition near transit");
  const [documentTypes, setDocumentTypes] = useState<string[]>(["staff_report"]);
  const [results, setResults] = useState<SearchResultItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLoading(true);
    setError(null);
    try {
      const response = await searchEvidence({
        query,
        limit: 10,
        document_types: documentTypes.length ? documentTypes : null,
        lexical_only: false
      });
      setResults(response.results);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Search failed");
    } finally {
      setLoading(false);
    }
  }

  function toggleDocumentType(sourceType: string) {
    setDocumentTypes((current) =>
      current.includes(sourceType)
        ? current.filter((item) => item !== sourceType)
        : [...current, sourceType]
    );
  }

  return (
    <main className="page">
      <header className="page-header">
        <div>
          <p className="eyebrow">Search</p>
          <h1>Cited Planning Evidence</h1>
          <p className="muted">Results return source URLs, page ranges, and retrieval scores.</p>
        </div>
      </header>

      <section className="panel">
        <form className="stack" onSubmit={submit}>
          <div className="search-form">
            <input
              className="search-input"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              aria-label="Search query"
            />
            <button className="button" type="submit" disabled={loading}>
              <Search size={18} />
              {loading ? "Searching" : "Search"}
            </button>
          </div>
          <div className="filters" aria-label="Document type filters">
            {DOCUMENT_TYPES.map((sourceType) => (
              <label className="checkbox-pill" key={sourceType}>
                <input
                  type="checkbox"
                  checked={documentTypes.includes(sourceType)}
                  onChange={() => toggleDocumentType(sourceType)}
                />
                {sourceType.replaceAll("_", " ")}
              </label>
            ))}
            <span className="badge amber">
              <SlidersHorizontal size={14} /> hybrid
            </span>
          </div>
        </form>
      </section>

      {error ? <div className="empty">{error}</div> : null}

      <section className="results" aria-live="polite">
        {results.length === 0 && !loading ? (
          <div className="empty">No evidence results loaded.</div>
        ) : null}
        {results.map((result) => (
          <article className="result-card" key={result.chunk_id}>
            <div className="result-meta">
              <span className="badge blue">{result.source_type.replaceAll("_", " ")}</span>
              <span className="badge">{result.citation_label ?? result.chunk_id}</span>
              <span className="badge">score {result.score.toFixed(4)}</span>
            </div>
            <h3>{result.title ?? "Untitled document"}</h3>
            <p className="result-text">{result.text}</p>
            <p className="muted">{result.url}</p>
          </article>
        ))}
      </section>
    </main>
  );
}
