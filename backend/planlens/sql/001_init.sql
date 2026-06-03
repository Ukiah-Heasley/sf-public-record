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
