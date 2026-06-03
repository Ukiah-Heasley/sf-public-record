export type HearingSummary = {
  hearing_id: string;
  hearing_date: string;
  title: string | null;
  status: string | null;
  agenda_url: string | null;
  minutes_url: string | null;
  supporting_url: string | null;
  document_count: number;
  agenda_item_count: number;
};

export type SourceDocumentSummary = {
  document_id: string;
  hearing_id: string | null;
  source_type: string;
  title: string | null;
  url: string;
  local_path: string | null;
  file_size_bytes: number | null;
  downloaded_at: string | null;
};

export type AgendaItemSummary = {
  agenda_item_id: string;
  hearing_id: string;
  item_number: string | null;
  section: string | null;
  case_number: string | null;
  address: string | null;
  district: string | null;
  planner_name: string | null;
  planner_contact: string | null;
  project_description: string | null;
  entitlement_type: string | null;
  ceqa_status: string | null;
  preliminary_recommendation: string | null;
  raw_text: string | null;
  parser_confidence: number | null;
};

export type HearingDetail = HearingSummary & {
  source_url: string;
  documents: SourceDocumentSummary[];
  agenda_items: AgendaItemSummary[];
};

export type DashboardResponse = {
  summary: {
    hearings_indexed: number;
    pdfs_downloaded: number;
    pages_parsed: number;
    agenda_items_extracted: number;
    staff_reports_linked: number;
    chunks_indexed: number;
    embeddings_indexed: number;
  };
  recent_activity: Array<{
    hearing_id: string;
    hearing_date: string;
    title: string | null;
    status: string | null;
    document_count: number;
    page_count: number;
    agenda_item_count: number;
  }>;
  document_types: Array<{ source_type: string; count: number }>;
  extraction_health: Array<{ extraction_quality: string; page_count: number }>;
  opposition_themes: Array<{ theme: string; mention_count: number }>;
};

export type SearchRequest = {
  query: string;
  date_start?: string | null;
  date_end?: string | null;
  document_types?: string[] | null;
  limit?: number;
  lexical_only?: boolean;
};

export type SearchResultItem = {
  chunk_id: string;
  document_id: string;
  title: string | null;
  source_type: string;
  hearing_date: string | null;
  page_start: number | null;
  page_end: number | null;
  citation_label: string | null;
  text: string;
  score: number;
  url: string;
};

export type SearchResponse = {
  query: string;
  answer_stub: string;
  results: SearchResultItem[];
};
