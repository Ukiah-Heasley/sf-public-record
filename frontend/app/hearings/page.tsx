"use client";

import { useEffect, useState } from "react";
import { HearingTable } from "../../components/HearingTable";
import { listHearings } from "../../lib/api";
import type { HearingSummary } from "../../lib/types";

export default function HearingsPage() {
  const [hearings, setHearings] = useState<HearingSummary[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listHearings()
      .then(setHearings)
      .catch((err) => setError(err instanceof Error ? err.message : "Could not load hearings"));
  }, []);

  return (
    <main className="page">
      <header className="page-header">
        <div>
          <p className="eyebrow">Hearings</p>
          <h1>Planning Commission Archive</h1>
          <p className="muted">Recent hearings with source documents and extracted agenda items.</p>
        </div>
      </header>
      {error ? <div className="empty">{error}</div> : null}
      <section className="panel">
        <HearingTable hearings={hearings} />
      </section>
    </main>
  );
}
