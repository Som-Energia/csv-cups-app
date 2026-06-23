CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE INDEX IF NOT EXISTS idx_records_cups_trgm
ON records
USING gin (cups gin_trgm_ops);
