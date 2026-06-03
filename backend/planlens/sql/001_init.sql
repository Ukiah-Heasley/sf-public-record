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
