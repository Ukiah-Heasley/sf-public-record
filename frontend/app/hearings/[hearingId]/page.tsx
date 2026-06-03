"use client";

import { ExternalLink } from "lucide-react";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { getHearing } from "../../../lib/api";
import type { HearingDetail } from "../../../lib/types";

export default function HearingDetailPage() {
  const params = useParams<{ hearingId: string }>();
  const [hearing, setHearing] = useState<HearingDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!params.hearingId) {
      return;
    }
    getHearing(params.hearingId)
      .then(setHearing)
      .catch((err) => setError(err instanceof Error ? err.message : "Could not load hearing"));
  }, [params.hearingId]);

  if (error) {
    return (
      <main className="page">
        <div className="empty">{error}</div>
      </main>
    );
  }

  if (!hearing) {
    return (
      <main className="page">
        <div className="empty">Loading hearing.</div>
      </main>
    );
  }

  return (
    <main className="page">
      <header className="page-header">
        <div>
          <p className="eyebrow">{hearing.status ?? "hearing"}</p>
          <h1>{formatDate(hearing.hearing_date)}</h1>
          <p className="muted">{hearing.title ?? "Planning Commission"}</p>
        </div>
        <a className="button secondary" href={hearing.source_url} target="_blank">
          <ExternalLink size={17} />
          Source
        </a>
      </header>

      <section className="two-column">
        <div className="stack">
          <section className="panel">
            <h2>Agenda Items</h2>
            <div className="item-list">
              {hearing.agenda_items.length ? (
                hearing.agenda_items.map((item) => (
                  <article className="item-card" key={item.agenda_item_id}>
                    <div className="item-meta">
                      {item.item_number ? <span className="badge">Item {item.item_number}</span> : null}
                      {item.case_number ? <span className="badge blue">{item.case_number}</span> : null}
                      {item.district ? <span className="badge">District {item.district}</span> : null}
                    </div>
                    <h3>{item.address ?? item.section ?? "Agenda item"}</h3>
                    <p className="muted">{item.project_description ?? item.raw_text}</p>
                  </article>
                ))
              ) : (
                <div className="empty">No parsed agenda items.</div>
              )}
            </div>
          </section>
        </div>

        <aside className="panel">
          <h2>Source Documents</h2>
          <div className="doc-list">
            {hearing.documents.length ? (
              hearing.documents.map((document) => (
                <a
                  className="item-card"
                  href={document.url}
                  target="_blank"
                  key={document.document_id}
                >
                  <div className="item-meta">
                    <span className="badge blue">{document.source_type.replaceAll("_", " ")}</span>
                  </div>
                  <h3>{document.title ?? document.document_id}</h3>
                  <p className="muted">{document.file_size_bytes ?? 0} bytes</p>
                </a>
              ))
            ) : (
              <div className="empty">No registered documents.</div>
            )}
          </div>
        </aside>
      </section>
    </main>
  );
}

function formatDate(value: string) {
  return new Intl.DateTimeFormat("en-US", {
    month: "long",
    day: "numeric",
    year: "numeric"
  }).format(new Date(`${value}T00:00:00`));
}
