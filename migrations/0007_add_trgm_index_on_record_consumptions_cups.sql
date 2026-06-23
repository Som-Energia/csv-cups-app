CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE INDEX IF NOT EXISTS idx_record_consumptions_cups_trgm
ON record_consumptions
USING gin (cups gin_trgm_ops);
