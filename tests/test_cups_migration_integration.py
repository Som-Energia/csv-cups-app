import os
import unittest
from pathlib import Path
from urllib.parse import urlparse

import psycopg2


TEST_DATABASE_ENV = "CUPS_MIGRATION_TEST_DATABASE_URL"
TEST_DATABASE_NAME = "cups_migration_test"


def get_test_database_url():
    database_url = os.getenv(TEST_DATABASE_ENV)
    if not database_url:
        raise unittest.SkipTest(f"Set {TEST_DATABASE_ENV} to run PostgreSQL migration integration tests.")

    parsed = urlparse(database_url)
    if parsed.hostname not in {
        "127.0.0.1",
        "localhost",
        "postgres",
        "cups-migration-postgres-test",
    } or parsed.path != f"/{TEST_DATABASE_NAME}":
        raise RuntimeError(
            f"{TEST_DATABASE_ENV} must target a local {TEST_DATABASE_NAME} database; refusing to run elsewhere."
        )
    return database_url


class CupsMigrationIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.database_url = get_test_database_url()

    def setUp(self):
        self.connection = psycopg2.connect(self.database_url)
        self.addCleanup(self.connection.close)
        self.drop_fixture_tables()
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                CREATE TABLE records (
                    id SERIAL PRIMARY KEY,
                    uploaded_at TIMESTAMP NOT NULL,
                    cups VARCHAR NOT NULL UNIQUE,
                    payload TEXT NOT NULL
                );
                CREATE TABLE record_consumptions (
                    id SERIAL PRIMARY KEY,
                    uploaded_at TIMESTAMP NOT NULL,
                    cups VARCHAR NOT NULL,
                    fechainiciomesconsumo VARCHAR NOT NULL,
                    fechafinmesconsumo VARCHAR NOT NULL,
                    payload TEXT NOT NULL,
                    CONSTRAINT uq_record_consumptions_cups_period
                        UNIQUE (cups, fechainiciomesconsumo, fechafinmesconsumo)
                );
                CREATE TABLE record_autoconsumos (
                    id SERIAL PRIMARY KEY,
                    uploaded_at TIMESTAMP NOT NULL,
                    cau VARCHAR NOT NULL,
                    fechainicioreparto VARCHAR NOT NULL,
                    cups VARCHAR NOT NULL,
                    horacoeficientevariablereparto VARCHAR NOT NULL DEFAULT '',
                    payload TEXT NOT NULL,
                    CONSTRAINT uq_record_autoconsumos_logical_row
                        UNIQUE (cau, fechainicioreparto, cups, horacoeficientevariablereparto)
                );
                """
            )
        self.connection.commit()

    def tearDown(self):
        self.drop_fixture_tables()

    def drop_fixture_tables(self):
        # A migration failure leaves PostgreSQL's transaction aborted. Roll it back
        # first so fixture cleanup can always run and the isolated database remains reusable.
        self.connection.rollback()
        with self.connection.cursor() as cursor:
            cursor.execute(
                "DROP TABLE IF EXISTS record_autoconsumos, record_consumptions, records CASCADE;"
            )
        self.connection.commit()

    def test_migration_deduplicates_all_unique_keys_before_truncating(self):
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO records (id, uploaded_at, cups, payload) VALUES
                    (10, '2026-01-01 00:00:00', 'ES000000000000000001AA', 'records-older'),
                    (11, '2026-02-01 00:00:00', 'ES000000000000000001BB', 'records-latest'),
                    (12, '2026-03-01 00:00:00', 'ES000000000000000004AA', 'records-tie-lower-id'),
                    (13, '2026-03-01 00:00:00', 'ES000000000000000004BB', 'records-tie-higher-id');
                INSERT INTO record_consumptions
                    (id, uploaded_at, cups, fechainiciomesconsumo, fechafinmesconsumo, payload) VALUES
                    (100, '2026-01-01 00:00:00', 'ES000000000000000002AA', '2026-01-01', '2026-01-31', 'consumption-older'),
                    (101, '2026-02-01 00:00:00', 'ES000000000000000002BB', '2026-01-01', '2026-01-31', 'consumption-latest'),
                    (102, '2026-03-01 00:00:00', 'ES000000000000000005AA', '2026-01-01', '2026-01-31', 'consumption-tie-lower-id'),
                    (103, '2026-03-01 00:00:00', 'ES000000000000000005BB', '2026-01-01', '2026-01-31', 'consumption-tie-higher-id');
                INSERT INTO record_autoconsumos
                    (id, uploaded_at, cau, fechainicioreparto, cups, horacoeficientevariablereparto, payload) VALUES
                    (200, '2026-01-01 00:00:00', 'CAU', '2026-01-01', 'ES000000000000000003AA', '01', 'autoconsumo-older'),
                    (201, '2026-02-01 00:00:00', 'CAU', '2026-01-01', 'ES000000000000000003BB', '01', 'autoconsumo-latest'),
                    (202, '2026-03-01 00:00:00', 'CAU', '2026-01-01', 'ES000000000000000006AA', '01', 'autoconsumo-tie-lower-id'),
                    (203, '2026-03-01 00:00:00', 'CAU', '2026-01-01', 'ES000000000000000006BB', '01', 'autoconsumo-tie-higher-id');
                """
            )
            migration_sql = (
                Path(__file__).resolve().parents[1] / "migrations" / "0011_canonicalize_cups.sql"
            ).read_text(encoding="utf-8")
            cursor.execute(migration_sql)
        self.connection.commit()

        with self.connection.cursor() as cursor:
            cursor.execute("SELECT id, cups, payload FROM records ORDER BY id")
            self.assertEqual(
                cursor.fetchall(),
                [
                    (11, "ES000000000000000001", "records-latest"),
                    (13, "ES000000000000000004", "records-tie-higher-id"),
                ],
            )
            cursor.execute("SELECT id, cups, payload FROM record_consumptions ORDER BY id")
            self.assertEqual(
                cursor.fetchall(),
                [
                    (101, "ES000000000000000002", "consumption-latest"),
                    (103, "ES000000000000000005", "consumption-tie-higher-id"),
                ],
            )
            cursor.execute("SELECT id, cups, payload FROM record_autoconsumos ORDER BY id")
            self.assertEqual(
                cursor.fetchall(),
                [
                    (201, "ES000000000000000003", "autoconsumo-latest"),
                    (203, "ES000000000000000006", "autoconsumo-tie-higher-id"),
                ],
            )
            cursor.execute(
                """
                SELECT table_name, character_maximum_length
                FROM information_schema.columns
                WHERE table_name IN ('records', 'record_consumptions', 'record_autoconsumos')
                  AND column_name = 'cups'
                ORDER BY table_name
                """
            )
            self.assertEqual(
                cursor.fetchall(),
                [
                    ("record_autoconsumos", 20),
                    ("record_consumptions", 20),
                    ("records", 20),
                ],
            )
