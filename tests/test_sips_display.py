import unittest
from datetime import datetime
from types import SimpleNamespace

from app.constants import PS_CSV_HEADERS
from app.main import (
    build_field_items,
    build_record_groups,
    format_consumption_period,
    format_display_value,
    serialize_record,
    serialize_csv_row,
)
from app.models import Record
from app.sips_display import CNAE_LABELS


class SipsDisplayTests(unittest.TestCase):
    def test_requested_codes_include_code_and_official_description(self):
        cases = (
            ("F", "tipoPersona", "F - Física"),
            ("NI", "tipoIdTitular", "NI - NIF"),
            ("07", "codigoTipoContrato", "07 - Suministro de Obras"),
            ("4778", "cnae", "4778 - Comercio al por menor de otros productos nuevos"),
            ("04", "codigoTensionV", "04 - 3X380/220"),
            ("2", "tipoControDelPotencia", "2 - Maxímetro"),
            ("2", "codigoModoControlPotencia", "2 - Maxímetro"),
        )

        for value, field_name, expected in cases:
            with self.subTest(field_name=field_name, value=value):
                self.assertEqual(format_display_value(value, field_name), expected)

    def test_field_specific_mappings_do_not_conflate_similar_codes(self):
        self.assertEqual(
            format_display_value("3", "codigoModoControlPotencia"),
            "3 - Control de potencia en contador de telegestión",
        )
        self.assertEqual(format_display_value("3", "tipoControDelPotencia"), "3")
        self.assertEqual(
            format_display_value("01", "codigoLecturaRemota"),
            "01 - Lectura remota con telegestión",
        )
        self.assertEqual(format_display_value("1", "acogimientoAutoconsumo"), "1 - Sí")

    def test_numeric_excel_style_codes_are_recognized_without_changing_the_code(self):
        self.assertEqual(format_display_value("1.0", "esViviendaHabitual"), "1.0 - Sí")
        self.assertEqual(
            format_display_value("2.0", "codigoPropiedadEquipoMedida"),
            "2.0 - Cliente",
        )
        self.assertEqual(format_display_value("18.0", "codigoTarifaATR"), "18.0 - 2.0TD")
        self.assertEqual(
            format_display_value("111.0", "cnae"),
            "111.0 - Cultivo de cereales, distintos de arroz, leguminosas y oleaginosas",
        )

    def test_unknown_codes_and_empty_values_are_safe(self):
        self.assertEqual(format_display_value("ZZ", "codigoTipoSuministro"), "ZZ")
        self.assertEqual(format_display_value("", "codigoTipoSuministro"), "-")
        self.assertEqual(format_display_value(None, "codigoTipoSuministro"), "-")

    def test_tariffs_now_include_the_original_code(self):
        self.assertEqual(format_display_value("018", "codigoTarifaATREnVigor"), "018 - 2.0TD")

    def test_watts_are_rendered_as_kw_without_float_rounding(self):
        cases = (
            ("5000", "5 kW"),
            ("5750", "5,75 kW"),
            ("1", "0,001 kW"),
            ("0", "0 kW"),
            ("not-a-number", "not-a-number"),
            ("NaN", "NaN"),
            ("Infinity", "Infinity"),
        )
        for value, expected in cases:
            with self.subTest(value=value):
                self.assertEqual(format_display_value(value, "potenciaMaximaBIEW"), expected)

    def test_dates_are_localized_for_display(self):
        self.assertEqual(format_display_value("2026-04-27", "fechaAltaSuministro"), "27/04/2026")
        self.assertEqual(
            format_display_value(datetime(2026, 4, 27, 13, 45), "uploaded_at"),
            "27/04/2026 13:45",
        )
        self.assertEqual(format_display_value("invalid", "fechaAltaSuministro"), "invalid")

    def test_consumption_view_translates_measurement_codes_and_power(self):
        source = SimpleNamespace(codigoTipoLectura="60", potenciaDemandadaEnWP1="7250")

        items = build_field_items(source, ["codigoTipoLectura", "potenciaDemandadaEnWP1"])

        self.assertEqual(items[0]["value"], "60 - Telegestión")
        self.assertEqual(items[1]["value"], "7,25 kW")

    def test_consumption_period_uses_localized_dates(self):
        consumption = SimpleNamespace(
            fechaInicioMesConsumo="2026-01-01",
            fechaFinMesConsumo="2026-01-31",
        )

        self.assertEqual(format_consumption_period(consumption), "01/01/2026 - 31/01/2026")

    def test_record_codes_use_descriptions_already_supplied_by_sips(self):
        record = Record(
            cups="ES123456789012345678",
            codigoEmpresaDistribuidora="0001",
            nombreEmpresaDistribuidora="Distribuidora Ejemplo",
            codigoProvinciaPS="08",
            desProvinciaPS="Barcelona",
        )

        fields = {
            field["name"]: field["value"]
            for group in build_record_groups(record)
            for field in group["fields"]
        }

        self.assertEqual(fields["codigoEmpresaDistribuidora"], "0001 - Distribuidora Ejemplo")
        self.assertEqual(fields["codigoProvinciaPS"], "08 - Barcelona")

    def test_csv_serialization_keeps_raw_values(self):
        record = Record(
            cups="ES123456789012345678",
            tipoPersona="F",
            cnae="4778",
            potenciaMaximaBIEW="5750",
        )

        row = serialize_csv_row(record, PS_CSV_HEADERS)

        self.assertEqual(row["tipoPersona"], "F")
        self.assertEqual(row["cnae"], "4778")
        self.assertEqual(row["potenciaMaximaBIEW"], "5750")

    def test_api_serialization_keeps_raw_values(self):
        record = Record(
            id=1,
            uploaded_at=datetime(2026, 4, 27, 13, 45),
            cups="ES123456789012345678",
            tipoPersona="F",
            cnae="4778",
            potenciaMaximaBIEW="5750",
        )

        payload = serialize_record(record)

        self.assertEqual(payload["tipoPersona"], "F")
        self.assertEqual(payload["cnae"], "4778")
        self.assertEqual(payload["potenciaMaximaBIEW"], "5750")

    def test_cnae_catalogue_contains_official_classes_and_cnmc_extension(self):
        self.assertEqual(len(CNAE_LABELS), 665)
        self.assertEqual(CNAE_LABELS["4778"], "Comercio al por menor de otros productos nuevos")
        self.assertIn("viviendas no habituales", CNAE_LABELS["9821"])


if __name__ == "__main__":
    unittest.main()
