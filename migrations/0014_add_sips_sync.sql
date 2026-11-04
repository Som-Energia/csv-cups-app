CREATE TABLE IF NOT EXISTS sips_files (
    id SERIAL PRIMARY KEY,
    source VARCHAR NOT NULL,
    remote_id VARCHAR NOT NULL,
    filename VARCHAR NOT NULL,
    md5 VARCHAR(32) NOT NULL,
    total_bytes BIGINT NOT NULL,
    available_at TIMESTAMP NOT NULL,
    status VARCHAR NOT NULL DEFAULT 'pending',
    error_message TEXT,
    ignored_members TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMP,
    CONSTRAINT uq_sips_source_remote UNIQUE (source, remote_id)
);
ALTER TABLE import_jobs ADD COLUMN IF NOT EXISTS sips_file_id INTEGER REFERENCES sips_files(id);
ALTER TABLE import_jobs ADD COLUMN IF NOT EXISTS sips_member VARCHAR;
CREATE INDEX IF NOT EXISTS ix_import_jobs_sips_file_id ON import_jobs(sips_file_id);
CREATE UNIQUE INDEX IF NOT EXISTS uq_import_job_sips_member ON import_jobs(sips_file_id, sips_member);
