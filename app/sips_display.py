import csv
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path


def _load_cnae_labels() -> dict[str, str]:
    path = Path(__file__).parent / "data" / "cnae_2025.csv"
    with path.open(encoding="utf-8", newline="") as source:
        reader = csv.DictReader(source)
        if reader.fieldnames != ["code", "description"]:
            raise ValueError(f"Invalid CNAE catalogue columns in {path}")
        labels = {}
        for line_number, row in enumerate(reader, start=2):
            code = row["code"].strip()
            description = row["description"].strip()
            if not code or not description:
                raise ValueError(f"Invalid CNAE catalogue row {line_number} in {path}")
            if code in labels:
                raise ValueError(f"Duplicate CNAE code {code} in {path}")
            labels[code] = description
        return labels


CNAE_LABELS = _load_cnae_labels()

TYPE_IDENTIFIER_LABELS = {
    "CI": "CIF",
    "CT": "Carta de Trabajo",
    "DN": "DNI",
    "NI": "NIF",
    "NV": "N.I.V.A.",
    "OT": "Otro",
    "PS": "Pasaporte",
    "NE": "NIE",
}

PERSON_TYPE_LABELS = {
    "F": "Física",
    "J": "Jurídica",
}

CONTRACT_TYPE_LABELS = {
    "01": "Anual",
    "02": "Eventual Medido",
    "03": "Temporada",
    "04": "Energía Adicional",
    "05": "Suministro a instalaciones RECORE",
    "06": "Interconexiones internacionales",
    "07": "Suministro de Obras",
    "08": "Suministro de Socorro",
    "09": "Eventual a tanto alzado",
    "10": "Pruebas",
    "11": "Duplicado",
    "12": "De reserva",
}

SUPPLY_TYPE_LABELS = {
    "AB": "Almacenamiento tipo bombeo",
    "AH": "Almacenamiento hibridado",
    "AL": "Almacén",
    "AN": "Almacenamiento tipo stand-alone",
    "AP": "Alumbrado público",
    "AS": "Ascensores",
    "AT": "Antena Telefonía Móvil",
    "BA": "Batería de acumuladores",
    "CM": "Centro de Maniobra y Control",
    "CP": "CPD (Centro de Proceso de Datos)",
    "DE": "Desaladora",
    "EA": "Escalera-Ascensor",
    "ES": "Escalera",
    "FT": "Fábrica y Talleres sin Riesgo Específico",
    "FV": "Instalación Fotovoltaica",
    "GA": "Garaje",
    "GB": "Grupo Bombeo, Riego por Goteo",
    "HP": "Locales Húmedos con Riesgo de Corrosión o Polvo",
    "HR": "Producción de Hidrógeno Renovable",
    "IC": "Infraestructuras para producción de combustibles",
    "IF": "Infraestructuras ferroviarias",
    "IH": "Instalaciones Productoras de Hidrógeno Renovable",
    "IN": "Nave industrial",
    "IT": "Instalación Temporal en Emplazamiento Abierto",
    "KC": "Kioscos / cabinas teléfono",
    "LB": "Locales a Baja Temperatura",
    "LC": "Local comercial",
    "OF": "Oficina",
    "PC": "Pública concurrencia",
    "PT": "Puerto",
    "RA": "Refugio o Albergue Agrícola",
    "RT": "Repetidor de Televisión",
    "SA": "Servicios Auxiliares",
    "SC": "Suministro complementario",
    "SE": "Suministro eventual",
    "SG": "Servicio general vivienda",
    "SM": "Semáforo",
    "SO": "Suministro obras",
    "TL": "Telecomunicaciones",
    "TR": "Trastero",
    "UF": "Uso finca",
    "UV": "Usos Varios",
    "VI": "Vivienda",
    "VE": "Recarga de vehículo eléctrico",
}

VOLTAGE_LABELS = {
    "01": "1X220",
    "02": "1X230",
    "03": "3X380",
    "04": "3X380/220",
    "05": "3X400",
    "06": "3X400/230",
    "07": "1X127",
    "08": "1X133",
    "09": "2X220",
    "10": "2X230",
    "11": "3X220",
    "12": "3X220/127",
    "13": "3X230",
    "14": "3X230/133",
    "15": "5.000",
    "16": "6.000",
    "17": "7.200",
    "18": "8.000",
    "19": "10.000",
    "20": "11.000",
    "21": "12.000",
    "22": "13.000",
    "23": "13.200",
    "24": "15.000",
    "25": "16.500",
    "26": "17.000",
    "27": "20.000",
    "28": "22.000",
    "29": "25.000",
    "30": "26.500",
    "31": "30.000",
    "32": "36.000",
    "33": "44.000",
    "34": "45.000",
    "35": "66.000",
    "36": "110.000",
    "37": "132.000",
    "38": "220.000",
    "39": "400.000",
    "40": "1.200",
    "41": "2.000",
    "42": "5.500",
    "43": "55.000",
    "44": "130.000",
    "45": "100",
    "46": "150",
    "47": "3X100",
    "48": "3X150/260",
    "49": "3X260",
    "99": "Otra tensión obsoleta",
}

MEASUREMENT_POINT_LABELS = {
    "01": "Punto de medida tipo 1",
    "02": "Punto de medida tipo 2",
    "03": "Punto de medida tipo 3",
    "04": "Punto de medida tipo 4",
    "05": "Punto de medida tipo 5",
}

POWER_CONTROL_TYPE_LABELS = {
    "0": "Sin ICP ni maxímetro",
    "1": "ICP",
    "2": "Maxímetro",
}

POWER_CONTROL_MODE_LABELS = {
    "1": "ICP",
    "2": "Maxímetro",
    "3": "Control de potencia en contador de telegestión",
    "4": "Sin control de potencia",
}

CONSUMPTION_PROFILE_LABELS = {
    "Pa": "Consumidores con peajes de acceso 2.0 A y 2.1 A",
    "Pb": "Consumidores con peajes de acceso 2.0 DHA y 2.1 DHA",
    "Pc": "Consumidores con peajes de acceso 3.0 A y 3.1 A con registro en 6 períodos",
    "Pd": "Consumidores con peaje de acceso 2.0 DHS y 2.1 DHS",
}

EQUIPMENT_OWNER_LABELS = {
    "1": "Distribuidor",
    "2": "Cliente",
    "3": "Comercializador",
    "4": "Otros",
}

REMOTE_READING_LABELS = {
    "01": "Lectura remota con telegestión",
    "02": "Lectura remota sin telegestión",
    "03": "Sin lectura remota",
}

EQUIPMENT_PHASE_LABELS = {
    "M": "Monofásico",
    "T": "Trifásico",
}

BILLING_FREQUENCY_LABELS = {
    "01": "Mensual",
    "02": "Bimestral",
}

TIME_DISCRIMINATION_LABELS = {
    "0": "Dos períodos (Tarifa Nocturna)",
    "1": "Sin Discriminación Horaria",
    "2": "Dos períodos",
    "3": "Tres períodos, sin discriminación de sábados y festivos",
    "4": "Tres períodos, con discriminación de sábados y festivos",
    "5": "Cinco períodos",
    "6": "Seis períodos",
    "7": "Siete períodos",
    "8": "DH Supervalle",
    "9": "Tres períodos",
    "A": "Seis períodos",
}

METER_ACCESS_LABELS = {
    "1": "Punto de suministro accesible",
    "2": "Contador no accesible (para acceder se necesita la colaboración del usuario)",
    "3": "Accesibilidad condicionada",
}

CASE_CLASS_LABELS = {
    "I": "Inspección",
    "N": "Nuevos suministros",
}

CASE_REASON_LABELS = {
    "01": "Aumento potencia",
    "02": "Cambio tensión",
    "03": "Cambio tarifa",
    "04": "Nuevo suministro",
    "05": "Colectivo nueva construcción",
    "06": "Colectivo electrificación rural",
    "07": "Informativo Plan urbanístico",
    "08": "Informativo Plan industrial",
    "09": "Informativo Productor de Régimen Especial",
    "10": "Colectivo reconstrucción vivienda",
    "11": "TCT No relacionado a NNSS",
    "12": "TCT Relacionado a NNSS",
    "13": "Colectivo renovación de Instalaciones de enlace varios suministros",
    "14": "Renovación de instalaciones de enlace",
}

READING_SOURCE_LABELS = {
    "10": "Telemedida",
    "11": "Telemedida corregida",
    "20": "TPL",
    "21": "TPL corregida",
    "30": "Visual",
    "31": "Visual corregida",
    "40": "Estimada",
    "50": "Autolectura",
    "60": "Telegestión",
    "70": "Calculada",
    "99": "Sin Lectura",
}

TYPE_VIA_LABELS = {
    "AC": "Acceso", "AD": "Aldea", "AF": "Afueras", "AG": "Agrupación",
    "AL": "Alameda", "AR": "Arrabal", "AU": "Autopista / Autovía", "AV": "Avenida",
    "BC": "Barranco", "BD": "Barriada", "BL": "Bloque", "BO": "Barrio",
    "CA": "Colonia", "CF": "Callejón", "CH": "Chalet", "CI": "Carril",
    "CJ": "Calleja", "CL": "Calle", "CM": "Complejo", "CN": "Camino",
    "CO": "Cooperativa", "CR": "Carretera", "CS": "Casa", "CT": "Cuesta",
    "DI": "Diseminado extrarradio", "ED": "Edificio", "EN": "Entrada", "FC": "Finca",
    "FI": "Ficticio", "GL": "Glorieta", "GR": "Grupo", "LG": "Lugar",
    "MA": "Masía", "MU": "Muelle", "MZ": "Manzana", "NU": "Núcleo",
    "OV": "Otros", "PA": "Parque", "PB": "Poblado", "PD": "Partida",
    "PE": "Paseo", "PI": "Polígono industrial", "PJ": "Paraje", "PL": "Pantalán",
    "PO": "Polígono", "PQ": "Parque", "PR": "Prolongación", "PS": "Pasaje",
    "PT": "Plazoleta", "PY": "Playa", "PZ": "Plaza", "RA": "Rambla",
    "RD": "Ronda", "RS": "Residencial", "SD": "Senda", "SU": "Subida",
    "TR": "Travesía", "UR": "Urbanización", "VI": "Vial", "ZN": "Zona",
}

STAIR_LABELS = {
    "CTR": "Centro", "DCH": "Derecha", "EST": "Este", "EXT": "Exterior",
    "INT": "Interior", "IZQ": "Izquierda", "NOR": "Norte", "OES": "Oeste",
    "SUR": "Sur", "001": "Una", "002": "Dos",
}

FLOOR_LABELS = {
    "AT": "Ático", "BA": "Bajo", "EP": "Entreplanta", "ES": "Entresuelo",
    "LO": "Local", "PA": "Patio", "PR": "Principal", "S1": "Sótano-1",
    "S2": "Sótano-2", "S3": "Sótano 3", "S4": "Sótano 4", "S5": "Sótano 5",
    "S6": "Sótano 6", "SA": "Sobre ático", "SS": "Semisótano", "001": "Primero",
    "002": "Segundo", "003": "Tercero", "004": "Cuarto", "005": "Quinto",
    "006": "Sexto", "007": "Séptimo", "008": "Octavo", "009": "Noveno",
    "010": "Décimo", "011": "Décimo primero",
}

DOOR_LABELS = {
    "ZA": "Izq-Izq", "ZB": "Izq-Ctr", "ZC": "Izq-Dch", "ZD": "Izq",
    "ZE": "Ext-Izq", "ZF": "Ext-Ctr", "ZG": "Ext-Dch", "ZH": "Ext",
    "ZI": "Ctr-Izq", "ZJ": "Ctr", "ZK": "Ctr-Dch", "ZL": "Int",
    "ZM": "Int-Izq", "ZN": "Int-Ctr", "ZO": "Int-Dch", "ZP": "Dch",
    "ZQ": "Dch-Izq", "ZR": "Dch-Ctr", "ZS": "Dch-Dch", "001": "Una",
}

PROPERTY_QUALIFIER_LABELS = {
    "BI": "BIS",
    "KM": "Punto Kilométrico",
    "NO": "Normal",
    "PC": "Parcela",
    "PR": "Próximo",
    "SN": "S/N",
}

CHANGE_STEP_LABELS = {
    "01": "Solicitud de cambio de comercializadora",
    "02": "Aceptación o rechazo de la solicitud de cambio de comercializadora",
    "03": "Comunicación de incidencias en la solicitud de cambio de comercializadora",
    "04": "Rechazo de la solicitud de cambio por incidencias",
    "05": "Activación del cambio de comercializadora",
    "06": "Anulación de la solicitud de cambio de comercializadora",
    "07": "Aceptación o rechazo de la anulación",
    "08": "Anulación del cambio",
    "09": "Aceptación o rechazo de la anulación del cambio",
    "10": "Anulación de la baja a la comercializadora saliente",
    "11": "Aceptación a comercializador saliente",
}

YES_NO_LABELS = {"0": "No", "1": "Sí"}

FIELD_CODE_LABELS = {
    "tipoPersona": PERSON_TYPE_LABELS,
    "tipoIdTitular": TYPE_IDENTIFIER_LABELS,
    "codigoTipoSuministro": SUPPLY_TYPE_LABELS,
    "codigoTensionV": VOLTAGE_LABELS,
    "codigoTensionMedida": VOLTAGE_LABELS,
    "codigoClasificacionPS": MEASUREMENT_POINT_LABELS,
    "tipoControDelPotencia": POWER_CONTROL_TYPE_LABELS,
    "tipoPerfilConsumo": CONSUMPTION_PROFILE_LABELS,
    "codigoPropiedadEquipoMedida": EQUIPMENT_OWNER_LABELS,
    "codigoPropiedadICP": EQUIPMENT_OWNER_LABELS,
    "cambioComercializadorEnCurso": CHANGE_STEP_LABELS,
    "codigoComercializadorVigente": {"0762": "Som Energia"},
    "suspensionSuminstroImpago": YES_NO_LABELS,
    "tipoViaPS": TYPE_VIA_LABELS,
    "escaleraPS": STAIR_LABELS,
    "pisoPS": FLOOR_LABELS,
    "puertaPS": DOOR_LABELS,
    "tipoAclaradorFincaPS": PROPERTY_QUALIFIER_LABELS,
    "tipoViaTitular": TYPE_VIA_LABELS,
    "escaleraTitular": STAIR_LABELS,
    "pisoTitular": FLOOR_LABELS,
    "puertaTitular": DOOR_LABELS,
    "tipoAclaradorFincaTitular": PROPERTY_QUALIFIER_LABELS,
    "esViviendaHabitual": YES_NO_LABELS,
    "codigoLecturaRemota": REMOTE_READING_LABELS,
    "codigoFasesEquipoMedida": EQUIPMENT_PHASE_LABELS,
    "acogimientoAutoconsumo": YES_NO_LABELS,
    "aplicacionBonoSocial": {**YES_NO_LABELS, "N": "No", "S": "Sí"},
    "suministroEsencial": YES_NO_LABELS,
    "cnae": CNAE_LABELS,
    "codigoTipoContrato": CONTRACT_TYPE_LABELS,
    "codigoPeriodicidadFacturacion": BILLING_FREQUENCY_LABELS,
    "codigoModoControlPotencia": POWER_CONTROL_MODE_LABELS,
    "codigoDHEquipoDeMedida": TIME_DISCRIMINATION_LABELS,
    "codigoAccesibilidadContador": METER_ACCESS_LABELS,
    "codigoPSContratable": YES_NO_LABELS,
    "codigoClaseExpediente": CASE_CLASS_LABELS,
    "codigoMotivoExpediente": CASE_REASON_LABELS,
    "codigoTipoLectura": READING_SOURCE_LABELS,
}

WATT_FIELDS = {
    "potenciaMaximaBIEW",
    "potenciaMaximaAPMW",
    "valorDerechosExtensionW",
    "valorDerechosAccesoW",
    "potenciasContratadasEnWP1",
    "potenciasContratadasEnWP2",
    "potenciasContratadasEnWP3",
    "potenciasContratadasEnWP4",
    "potenciasContratadasEnWP5",
    "potenciasContratadasEnWP6",
    "potenciaCGPW",
    "potenciaDemandadaEnWP1",
    "potenciaDemandadaEnWP2",
    "potenciaDemandadaEnWP3",
    "potenciaDemandadaEnWP4",
    "potenciaDemandadaEnWP5",
    "potenciaDemandadaEnWP6",
}

DATE_FIELDS = {
    "uploaded_at",
    "fechaAltaSuministro",
    "fechaUltimoMovimientoContrato",
    "fechaUltimoCambioComercializador",
    "fechaUltimoCambioAgregadorIndependiente",
    "fechaLimiteDerechosReconocidos",
    "fechaUltimaLectura",
    "fechaEmisionBIE",
    "fechaCaducidadBIE",
    "fechaEmisionAPM",
    "fechaCaducidadAPM",
    "fechaInicioMesConsumo",
    "fechaFinMesConsumo",
    "fechaInicioReparto",
}


def format_code_label(value, labels: dict[str, str]) -> str:
    code = str(value).strip()
    lookup_code = code[:-2] if code.endswith(".0") else code
    label = labels.get(lookup_code)
    if label is None and lookup_code.isdigit():
        numeric_widths = {len(key) for key in labels if key.isdigit()}
        for width in sorted(numeric_widths):
            label = labels.get(lookup_code.zfill(width))
            if label is not None:
                break
    return f"{code} - {label}" if label else code


def format_kw(value) -> str:
    raw_value = str(value).strip()
    try:
        kw_value = Decimal(raw_value.replace(",", ".")) / Decimal(1000)
    except InvalidOperation:
        return raw_value
    if not kw_value.is_finite():
        return raw_value
    formatted = format(kw_value.normalize(), "f")
    if "." in formatted:
        formatted = formatted.rstrip("0").rstrip(".")
    return f"{formatted.replace('.', ',')} kW"


def format_date(value) -> str:
    if isinstance(value, datetime):
        return value.strftime("%d/%m/%Y %H:%M")
    if isinstance(value, date):
        return value.strftime("%d/%m/%Y")
    raw_value = str(value).strip()
    try:
        return date.fromisoformat(raw_value).strftime("%d/%m/%Y")
    except ValueError:
        return raw_value


def format_sips_value(value, field_name: str | None = None):
    if value in (None, ""):
        return "-"
    if field_name in DATE_FIELDS:
        return format_date(value)
    if field_name in WATT_FIELDS:
        return format_kw(value)
    labels = FIELD_CODE_LABELS.get(field_name)
    if labels is not None:
        return format_code_label(value, labels)
    return value
