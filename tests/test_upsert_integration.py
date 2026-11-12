import os
import unittest
from datetime import datetime, timedelta
from urllib.parse import urlparse

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.constants import (
    IMPORT_FORMAT_AUTOCONSUMO,
    IMPORT_FORMAT_CONSUMPTION,
    IMPORT_FORMAT_PS,
)
from app.models import Base, Record, RecordAutoconsumo, RecordConsumption
from app.services.importer import (
    get_headers_for_format,
    upsert_autoconsumo_chunk,
    upsert_consumption_chunk,
    upsert_ps_chunk,
)


TEST_DATABASE_ENV = "UPSERT_TEST_DATABASE_URL"
TEST_DATABASE_NAME = "cups_upsert_test"


def get_test_database_url():
    database_url = os.getenv(TEST_DATABASE_ENV)
    if not database_url:
        raise unittest.SkipTest(f"Set {TEST_DATABASE_ENV} to run PostgreSQL upsert tests.")

    parsed = urlparse(database_url)
    if parsed.hostname not in {
        "127.0.0.1",
        "localhost",
        "postgres",
        "cups-upsert-postgres-test",
    } or parsed.path != f"/{TEST_DATABASE_NAME}":
        raise RuntimeError(
            f"{TEST_DATABASE_ENV} must target a local {TEST_DATABASE_NAME} database; refusing to run elsewhere."
        )
    return database_url


class ConditionalUpsertIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine(get_test_database_url())
        cls.Session = sessionmaker(bind=cls.engine)

    @classmethod
    def tearDownClass(cls):
        cls.engine.dispose()

    def setUp(self):
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    "DROP TABLE IF EXISTS record_autoconsumos, record_consumptions, records CASCADE"
                )
            )
        Base.metadata.create_all(
            self.engine,
            tables=[Record.__table__, RecordConsumption.__table__, RecordAutoconsumo.__table__],
        )

    def tearDown(self):
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    "DROP TABLE IF EXISTS record_autoconsumos, record_consumptions, records CASCADE"
                )
            )

    def test_ps_skips_identical_rows_and_counts_real_changes(self):
        self.assert_conditional_upsert(
            import_format=IMPORT_FORMAT_PS,
            model=Record,
            upsert=upsert_ps_chunk,
            key_values={"cups": "ES000000000000000001"},
            changed_field="nombreEmpresaDistribuidora",
        )

    def test_consumption_skips_identical_rows_and_counts_real_changes(self):
        self.assert_conditional_upsert(
            import_format=IMPORT_FORMAT_CONSUMPTION,
            model=RecordConsumption,
            upsert=upsert_consumption_chunk,
            key_values={
                "cups": "ES000000000000000002",
                "fechaInicioMesConsumo": "2026-01-01",
                "fechaFinMesConsumo": "2026-01-31",
            },
            changed_field="codigoTarifaATR",
        )

    def test_new_consumption_schema_allocates_bigint_ids(self):
        with self.engine.begin() as connection:
            connection.execute(text(
                "SELECT setval(pg_get_serial_sequence('record_consumptions', 'id'), 2147483647, true)"
            ))
        row = {
            **{header: None for header in get_headers_for_format(IMPORT_FORMAT_CONSUMPTION)},
            "cups": "ES000000000000000002",
            "fechaInicioMesConsumo": "2026-01-01",
            "fechaFinMesConsumo": "2026-01-31",
            "uploaded_at": datetime(2026, 1, 1),
        }
        with self.Session() as db:
            self.assertEqual(upsert_consumption_chunk(db, [row]), (1, 0))
            self.assertEqual(db.query(RecordConsumption).one().id, 2147483648)

    def test_autoconsumo_skips_identical_rows_and_counts_real_changes(self):
        self.assert_conditional_upsert(
            import_format=IMPORT_FORMAT_AUTOCONSUMO,
            model=RecordAutoconsumo,
            upsert=upsert_autoconsumo_chunk,
            key_values={
                "cau": "CAU-1",
                "fechaInicioReparto": "2026-01-01",
                "cups": "ES000000000000000003",
                "horaCoeficienteVariableReparto": "01",
            },
            changed_field="coeficienteReparto",
        )

    def assert_conditional_upsert(self, import_format, model, upsert, key_values, changed_field):
        first_timestamp = datetime(2026, 1, 1)
        second_timestamp = first_timestamp + timedelta(days=1)
        third_timestamp = second_timestamp + timedelta(days=1)
        fourth_timestamp = third_timestamp + timedelta(days=1)

        base_row: dict[str, str | datetime | None] = {
            header: None for header in get_headers_for_format(import_format)
        }
        base_row.update(key_values)
        base_row["uploaded_at"] = first_timestamp

        with self.Session() as db:
            self.assertEqual(upsert(db, [base_row]), (1, 0))

            identical_row = {**base_row, "uploaded_at": second_timestamp}
            self.assertEqual(upsert(db, [identical_row]), (0, 0))
            persisted = db.query(model).one()
            self.assertEqual(persisted.uploaded_at, first_timestamp)

            changed_row = {
                **base_row,
                changed_field: "changed",
                "uploaded_at": third_timestamp,
            }
            self.assertEqual(upsert(db, [changed_row]), (0, 1))
            persisted = db.query(model).one()
            self.assertEqual(getattr(persisted, changed_field), "changed")
            self.assertEqual(persisted.uploaded_at, third_timestamp)

            null_row = {**base_row, "uploaded_at": fourth_timestamp}
            self.assertEqual(upsert(db, [null_row]), (0, 1))
            persisted = db.query(model).one()
            self.assertIsNone(getattr(persisted, changed_field))
            self.assertEqual(persisted.uploaded_at, fourth_timestamp)

            new_key_values = dict(key_values)
            if "cups" in new_key_values:
                new_key_values["cups"] = "ES000000000000000009"
            new_row = {**base_row, **new_key_values, "uploaded_at": fourth_timestamp}
            changed_again = {
                **base_row,
                changed_field: "changed-again",
                "uploaded_at": fourth_timestamp,
            }
            self.assertEqual(upsert(db, [identical_row, changed_again, new_row]), (1, 1))


if __name__ == "__main__":
    unittest.main()
