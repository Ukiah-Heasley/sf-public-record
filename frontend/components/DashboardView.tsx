"use client";

import {
  BookOpenText,
  FileDown,
  FileText,
  Layers3,
  Link2,
  ListChecks,
  Search
} from "lucide-react";
import { useEffect, useState } from "react";
import { getDashboard } from "../lib/api";
import type { DashboardResponse } from "../lib/types";
import { Bars } from "./Bars";
import { HearingTable } from "./HearingTable";
import { MetricCard } from "./MetricCard";

const EMPTY_DASHBOARD: DashboardResponse = {
  summary: {
    hearings_indexed: 0,
    pdfs_downloaded: 0,
    pages_parsed: 0,
    agenda_items_extracted: 0,
    staff_reports_linked: 0,
    chunks_indexed: 0,
    embeddings_indexed: 0
  },
  recent_activity: [],
  document_types: [],
  extraction_health: [],
  opposition_themes: []
};

export function DashboardView() {
  const [dashboard, setDashboard] = useState<DashboardResponse>(EMPTY_DASHBOARD);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getDashboard()
      .then(setDashboard)
      .catch((err) => setError(err instanceof Error ? err.message : "Could not load dashboard"));
  }, []);

  const { summary } = dashboard;

  return (
    <main className="page">
      <header className="page-header">
        <div>
          <p className="eyebrow">Dashboard</p>
          <h1>Where Does SF Housing Get Delayed?</h1>
          <p className="muted">Planning Commission evidence indexed from hearings and PDFs.</p>
        </div>
      </header>

      {error ? <div className="empty">{error}</div> : null}

      <section className="grid-metrics">
        <MetricCard label="Hearings indexed" value={summary.hearings_indexed} icon={BookOpenText} />
        <MetricCard label="PDFs downloaded" value={summary.pdfs_downloaded} icon={FileDown} />
        <MetricCard label="Pages parsed" value={summary.pages_parsed} icon={FileText} />
        <MetricCard label="Agenda items" value={summary.agenda_items_extracted} icon={ListChecks} />
        <MetricCard label="Staff reports linked" value={summary.staff_reports_linked} icon={Link2} />
        <MetricCard label="Chunks indexed" value={summary.chunks_indexed} icon={Layers3} />
        <MetricCard label="Embeddings" value={summary.embeddings_indexed} icon={Search} />
      </section>

      <section className="dashboard-grid">
        <div className="stack">
          <section className="panel">
            <h2>Recent Hearings</h2>
            <HearingTable hearings={dashboard.recent_activity} />
          </section>
          <section className="panel">
            <h2>YIMBY Signals</h2>
            <Bars
              data={dashboard.opposition_themes.map((item) => ({
                label: item.theme,
                value: item.mention_count
              }))}
            />
          </section>
        </div>

        <aside className="stack">
          <section className="panel">
            <h2>Document Types</h2>
            <Bars
              data={dashboard.document_types.map((item) => ({
                label: item.source_type.replaceAll("_", " "),
                value: item.count
              }))}
            />
          </section>
          <section className="panel">
            <h2>Extraction Health</h2>
            <Bars
              data={dashboard.extraction_health.map((item) => ({
                label: item.extraction_quality,
                value: item.page_count
              }))}
            />
          </section>
        </aside>
      </section>
    </main>
  );
}
