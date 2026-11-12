-- INTEGER -> BIGINT rewrites the table and rebuilds indexes under an exclusive
-- lock. Stop imports and allow maintenance time/disk space on large databases.
ALTER TABLE record_consumptions ALTER COLUMN id TYPE BIGINT;

-- Find the owned sequence rather than assuming its name: older installations
-- may retain records_consumptions_id_seq after a table rename. Preserve its
-- current value (including an exhausted INTEGER counter); never reset/cycle it.
DO $$
DECLARE
    sequence_name regclass;
BEGIN
    sequence_name := pg_get_serial_sequence('record_consumptions', 'id')::regclass;
    IF sequence_name IS NOT NULL THEN
        EXECUTE format('ALTER SEQUENCE %s AS BIGINT NO MAXVALUE', sequence_name);
    END IF;
END
$$;
