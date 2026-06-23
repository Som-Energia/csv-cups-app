ALTER TABLE import_jobs
ADD COLUMN IF NOT EXISTS total_chunks INTEGER NOT NULL DEFAULT 0,
ADD COLUMN IF NOT EXISTS queued_chunks INTEGER NOT NULL DEFAULT 0,
ADD COLUMN IF NOT EXISTS processing_chunks INTEGER NOT NULL DEFAULT 0,
ADD COLUMN IF NOT EXISTS completed_chunks INTEGER NOT NULL DEFAULT 0,
ADD COLUMN IF NOT EXISTS failed_chunks INTEGER NOT NULL DEFAULT 0;

CREATE TABLE IF NOT EXISTS import_job_chunks (
    id SERIAL PRIMARY KEY,
    job_id INTEGER NOT NULL REFERENCES import_jobs(id),
    chunk_index INTEGER NOT NULL,
    filename VARCHAR NOT NULL,
    stored_path VARCHAR NOT NULL,
    status VARCHAR NOT NULL DEFAULT 'queued',
    total_rows INTEGER NOT NULL DEFAULT 0,
    processed_rows INTEGER NOT NULL DEFAULT 0,
    created_rows INTEGER NOT NULL DEFAULT 0,
    updated_rows INTEGER NOT NULL DEFAULT 0,
    error_rows INTEGER NOT NULL DEFAULT 0,
    rows_per_second DOUBLE PRECISION NOT NULL DEFAULT 0,
    error_message TEXT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    started_at TIMESTAMP NULL,
    finished_at TIMESTAMP NULL,
    last_progress_at TIMESTAMP NULL,
    CONSTRAINT uq_import_job_chunks_job_chunk UNIQUE (job_id, chunk_index)
);

CREATE INDEX IF NOT EXISTS idx_import_job_chunks_job_id ON import_job_chunks(job_id);
CREATE INDEX IF NOT EXISTS idx_import_job_chunks_status ON import_job_chunks(status);
