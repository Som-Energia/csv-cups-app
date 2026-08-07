-- Canonical CUPS storage is the first 20 characters.
--
-- A collision occurs when distinct historical CUPS values share those first 20
-- characters. For each table, keep the row with the greatest uploaded_at,
-- because every importer upsert writes uploaded_at at import time. If two rows
-- have the same timestamp, import provenance cannot distinguish them; id DESC
-- provides a stable deterministic final tie-breaker (it is not treated as an
-- import-recency signal). Delete collision losers before updating cups so no
-- transient unique-constraint violation is possible.

DELETE FROM records AS loser
USING records AS winner
WHERE LEFT(loser.cups, 20) = LEFT(winner.cups, 20)
  AND (loser.uploaded_at, loser.id) < (winner.uploaded_at, winner.id);

DELETE FROM record_consumptions AS loser
USING record_consumptions AS winner
WHERE LEFT(loser.cups, 20) = LEFT(winner.cups, 20)
  AND loser.fechainiciomesconsumo = winner.fechainiciomesconsumo
  AND loser.fechafinmesconsumo = winner.fechafinmesconsumo
  AND (loser.uploaded_at, loser.id) < (winner.uploaded_at, winner.id);

DELETE FROM record_autoconsumos AS loser
USING record_autoconsumos AS winner
WHERE loser.cau = winner.cau
  AND loser.fechainicioreparto = winner.fechainicioreparto
  AND LEFT(loser.cups, 20) = LEFT(winner.cups, 20)
  AND loser.horacoeficientevariablereparto = winner.horacoeficientevariablereparto
  AND (loser.uploaded_at, loser.id) < (winner.uploaded_at, winner.id);

UPDATE records SET cups = LEFT(cups, 20) WHERE LENGTH(cups) > 20;
UPDATE record_consumptions SET cups = LEFT(cups, 20) WHERE LENGTH(cups) > 20;
UPDATE record_autoconsumos SET cups = LEFT(cups, 20) WHERE LENGTH(cups) > 20;

-- Existing unique constraints and indexes remain attached to these columns.
ALTER TABLE records ALTER COLUMN cups TYPE VARCHAR(20);
ALTER TABLE record_consumptions ALTER COLUMN cups TYPE VARCHAR(20);
ALTER TABLE record_autoconsumos ALTER COLUMN cups TYPE VARCHAR(20);
