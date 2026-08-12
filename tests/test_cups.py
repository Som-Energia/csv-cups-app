import csv
import io
import unittest
from unittest.mock import Mock, patch

from fastapi import HTTPException

from app.constants import (
    CONSUMPTION_CSV_HEADERS,
    IMPORT_FORMAT_AUTOCONSUMO,
    IMPORT_FORMAT_CONSUMPTION,
    IMPORT_FORMAT_PS,
)
from app.main import (
    get_record,
    get_record_bono_social,
    get_record_consumptions,
    list_records,
)
from app.services.importer import (
    deduplicate_rows,
    detect_csv_format,
    get_headers_for_format,
    normalize_row,
    upsert_autoconsumo_chunk,
    upsert_consumption_chunk,
    upsert_ps_chunk,
)


class FakeRecordQuery:
    def __init__(self):
        self.cups_lookup = None

    def filter(self, criterion):
        self.cups_lookup = criterion.right.value
        return self

    def order_by(self, *args):
        return self

    def limit(self, *args):
        return self

    def all(self):
        return []


class FakeExcluded:
    def __getattr__(self, name):
        return name

    def __getitem__(self, name):
        return name


class FakeInsertStatement:
    def __init__(self, model):
        self.model = model
        self.rows = None
        self.excluded = FakeExcluded()

    def values(self, rows):
        self.rows = rows
        return self

    def on_conflict_do_update(self, **kwargs):
        return self


class FakeInsertRecorder:
    def __init__(self):
        self.statements = []

    def __call__(self, model):
        statement = FakeInsertStatement(model)
        self.statements.append(statement)
        return statement


class FakeUpsertQuery:
    def filter(self, *args):
        return self

    def all(self):
        return []


class FakeUpsertDatabase:
    def __init__(self):
        self.executed = []
        self.commits = 0

    def query(self, *args):
        return FakeUpsertQuery()

    def execute(self, statement):
        self.executed.append(statement)

    def commit(self):
        self.commits += 1


class CupsCanonicalizationTests(unittest.TestCase):
    canonical_cups = "ES123456789012345678"
    extended_cups = canonical_cups + "0F"

    def test_all_import_formats_canonicalize_cups(self):
        for import_format in (
            IMPORT_FORMAT_PS,
            IMPORT_FORMAT_CONSUMPTION,
            IMPORT_FORMAT_AUTOCONSUMO,
        ):
            row = {header: "value" for header in get_headers_for_format(import_format)}
            row["cups"] = self.extended_cups
            if import_format == IMPORT_FORMAT_AUTOCONSUMO:
                row["cau"] = "CAU"
                row["fechaInicioReparto"] = "2026-01-01"
            if import_format == IMPORT_FORMAT_CONSUMPTION:
                row["fechaInicioMesConsumo"] = "2026-01-01"
                row["fechaFinMesConsumo"] = "2026-01-31"

            self.assertEqual(normalize_row(import_format, row)["cups"], self.canonical_cups)

    def test_all_import_formats_reject_invalid_cups_lengths(self):
        for import_format in (
            IMPORT_FORMAT_PS,
            IMPORT_FORMAT_CONSUMPTION,
            IMPORT_FORMAT_AUTOCONSUMO,
        ):
            row = {header: "value" for header in get_headers_for_format(import_format)}
            if import_format == IMPORT_FORMAT_AUTOCONSUMO:
                row["cau"] = "CAU"
                row["fechaInicioReparto"] = "2026-01-01"
            if import_format == IMPORT_FORMAT_CONSUMPTION:
                row["fechaInicioMesConsumo"] = "2026-01-01"
                row["fechaFinMesConsumo"] = "2026-01-31"
            for length in (19, 21, 23):
                row["cups"] = "E" * length
                with self.subTest(import_format=import_format, length=length):
                    with self.assertRaisesRegex(ValueError, "exactly 20 or 22"):
                        normalize_row(import_format, row)

    def test_canonical_and_extended_import_values_deduplicate_to_one_logical_key(self):
        for import_format in (
            IMPORT_FORMAT_PS,
            IMPORT_FORMAT_CONSUMPTION,
            IMPORT_FORMAT_AUTOCONSUMO,
        ):
            base_row = {header: "value" for header in get_headers_for_format(import_format)}
            if import_format == IMPORT_FORMAT_AUTOCONSUMO:
                base_row["cau"] = "CAU"
                base_row["fechaInicioReparto"] = "2026-01-01"
            if import_format == IMPORT_FORMAT_CONSUMPTION:
                base_row["fechaInicioMesConsumo"] = "2026-01-01"
                base_row["fechaFinMesConsumo"] = "2026-01-31"

            canonical_row = {**base_row, "cups": self.canonical_cups}
            extended_row = {**base_row, "cups": self.extended_cups}
            rows = [
                normalize_row(import_format, canonical_row),
                normalize_row(import_format, extended_row),
            ]

            with self.subTest(import_format=import_format):
                self.assertEqual(len(deduplicate_rows(import_format, rows)), 1)

    def test_every_upsert_path_receives_canonical_cups_values(self):
        upsert_functions = {
            IMPORT_FORMAT_PS: upsert_ps_chunk,
            IMPORT_FORMAT_CONSUMPTION: upsert_consumption_chunk,
            IMPORT_FORMAT_AUTOCONSUMO: upsert_autoconsumo_chunk,
        }
        for import_format, upsert_function in upsert_functions.items():
            base_row = {header: "value" for header in get_headers_for_format(import_format)}
            if import_format == IMPORT_FORMAT_AUTOCONSUMO:
                base_row["cau"] = "CAU"
                base_row["fechaInicioReparto"] = "2026-01-01"
            if import_format == IMPORT_FORMAT_CONSUMPTION:
                base_row["fechaInicioMesConsumo"] = "2026-01-01"
                base_row["fechaFinMesConsumo"] = "2026-01-31"

            for raw_cups in (f" {self.canonical_cups} ", f" {self.extended_cups} "):
                normalized_row = normalize_row(import_format, {**base_row, "cups": raw_cups})
                database = FakeUpsertDatabase()
                insert_recorder = FakeInsertRecorder()

                with self.subTest(import_format=import_format, raw_cups=raw_cups):
                    with patch("app.services.importer.insert", insert_recorder):
                        upsert_function(database, [normalized_row])

                    self.assertEqual(len(insert_recorder.statements), 1)
                    self.assertEqual(insert_recorder.statements[0].rows[0]["cups"], self.canonical_cups)
                    self.assertEqual(len(insert_recorder.statements[0].rows[0]["cups"]), 20)
                    self.assertEqual(database.executed, insert_recorder.statements)
                    self.assertEqual(database.commits, 1)

    def test_api_records_query_canonicalizes_22_character_input(self):
        query = FakeRecordQuery()
        db = Mock()
        db.query.return_value = query

        self.assertEqual(list_records(cups=self.extended_cups, limit=100, db=db), [])
        self.assertEqual(query.cups_lookup, self.canonical_cups)

    def test_api_cups_routes_reject_invalid_input_before_database_access(self):
        for endpoint in (
            lambda: list_records(cups="ES123", limit=100, db=Mock()),
            lambda: get_record(cups="ES123", db=Mock()),
            lambda: get_record_bono_social(cups="ES123", db=Mock()),
            lambda: get_record_consumptions(cups="ES123", db=Mock()),
        ):
            with self.assertRaises(HTTPException) as raised:
                endpoint()
            self.assertEqual(raised.exception.status_code, 422)
            self.assertEqual(raised.exception.detail, "CUPS must contain exactly 20 or 22 characters.")


class ConsumptionFormatTests(unittest.TestCase):
    old_reactive_headers = [f"consumoEnergiaReactivaEnVArhP{period}" for period in range(1, 7)]
    inductive_headers = [
        f"consumoEnergiaReactivaInductivaEnVArhP{period}" for period in range(1, 7)
    ]
    capacitive_headers = [
        f"consumoEnergiaReactivaCapacitivaEnVArhP{period}" for period in range(1, 7)
    ]

    def test_new_consumption_headers_are_detected(self):
        self.assertEqual(detect_csv_format(CONSUMPTION_CSV_HEADERS), IMPORT_FORMAT_CONSUMPTION)

    def test_old_consumption_headers_are_rejected(self):
        old_headers = [
            *CONSUMPTION_CSV_HEADERS[:10],
            *self.old_reactive_headers,
            *CONSUMPTION_CSV_HEADERS[22:],
        ]

        with self.assertRaisesRegex(ValueError, "do not match any supported format"):
            detect_csv_format(old_headers)

    def test_new_reactive_values_are_normalized_and_upserted(self):
        values = {
            header: str(index)
            for index, header in enumerate(self.inductive_headers + self.capacitive_headers, start=1)
        }
        row = {header: "value" for header in CONSUMPTION_CSV_HEADERS}
        row.update(values)
        row.update(
            {
                "cups": "ES0705000100521001PH0F",
                "fechaInicioMesConsumo": "2024-10-31",
                "fechaFinMesConsumo": "2024-11-30",
                "codigoDHEquipoDeMedida": "",
                "codigoTipoLectura": " ",
            }
        )
        buffer = io.StringIO()
        writer = csv.DictWriter(buffer, fieldnames=CONSUMPTION_CSV_HEADERS)
        writer.writeheader()
        writer.writerow(row)
        parsed_row = next(csv.DictReader(io.StringIO(buffer.getvalue())))

        normalized = normalize_row(IMPORT_FORMAT_CONSUMPTION, parsed_row)
        database = FakeUpsertDatabase()
        insert_recorder = FakeInsertRecorder()
        with patch("app.services.importer.insert", insert_recorder):
            upsert_consumption_chunk(database, [normalized])

        payload = insert_recorder.statements[0].rows[0]
        self.assertEqual(payload["cups"], "ES0705000100521001PH")
        self.assertEqual(
            {header: payload[header] for header in values},
            values,
        )
        self.assertIsNone(payload["codigoDHEquipoDeMedida"])
        self.assertIsNone(payload["codigoTipoLectura"])


if __name__ == "__main__":
    unittest.main()
