ALTER TABLE import_jobs
ADD COLUMN IF NOT EXISTS last_progress_at TIMESTAMP NULL;

UPDATE import_jobs
SET last_progress_at = COALESCE(finished_at, started_at, created_at)
WHERE last_progress_at IS NULL;
