CREATE INDEX IF NOT EXISTS idx_hearings_date ON hearings(hearing_date);
CREATE INDEX IF NOT EXISTS idx_documents_hearing ON source_documents(hearing_id);
CREATE INDEX IF NOT EXISTS idx_pages_document ON pages(document_id);
CREATE INDEX IF NOT EXISTS idx_agenda_hearing ON agenda_items(hearing_id);
CREATE INDEX IF NOT EXISTS idx_agenda_case ON agenda_items(case_number);
