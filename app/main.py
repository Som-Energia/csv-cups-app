import csv
from datetime import date, datetime, timedelta
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

from fastapi import Depends, FastAPI, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.constants import (
    AUTOCONSUMO_CSV_HEADERS,
    ATR_TARIFF_LABELS,
    CONSUMPTION_CSV_HEADERS,
    CSV_HEADERS,
    FIELD_GROUPS,
    FIELD_LABELS_CA,
    PS_CSV_HEADERS,
)
from app.database import get_db, init_db
from app.jobs import enqueue_import
from app.models import ImportJob, ImportJobChunk, Record, RecordAutoconsumo, RecordConsumption
from app.schemas import (
    JobChunkPageOut,
    JobChunkOut,
    JobOut,
    RecordBonoSocialOut,
    RecordConsumptionOut,
    RecordOut,
    RetryFailedChunksResponse,
    UploadResponse,
)
from app.services.importer import (
    JOB_STATUS_FAILED,
    JOB_STATUS_PROCESSING,
    JOB_STATUS_QUEUED,
    JOB_STATUS_SPLITTING,
    cleanup_job_artifacts,
    cleanup_job_chunks,
    retry_failed_chunks,
)
from app.settings import settings


app = FastAPI(title="CSV CUPS App")

STALL_THRESHOLD = timedelta(minutes=10)
STATUS_LABELS_CA = {
    "queued": "En cua",
    "processing": "Processant",
    "completed": "Completat",
    "failed": "Fallit",
    "splitting": "Dividint",
    "partial_failed": "Parcial amb errors",
}
MONTH_LABELS_CA = {
    "01": "Gener",
    "02": "Febrer",
    "03": "Marc",
    "04": "Abril",
    "05": "Maig",
    "06": "Juny",
    "07": "Juliol",
    "08": "Agost",
    "09": "Setembre",
    "10": "Octubre",
    "11": "Novembre",
    "12": "Desembre",
}
ACTIVE_ENERGY_FIELDS = [
    "consumoEnergiaActivaEnWhP1",
    "consumoEnergiaActivaEnWhP2",
    "consumoEnergiaActivaEnWhP3",
    "consumoEnergiaActivaEnWhP4",
    "consumoEnergiaActivaEnWhP5",
    "consumoEnergiaActivaEnWhP6",
]
REACTIVE_ENERGY_FIELDS = [
    "consumoEnergiaReactivaEnVArhP1",
    "consumoEnergiaReactivaEnVArhP2",
    "consumoEnergiaReactivaEnVArhP3",
    "consumoEnergiaReactivaEnVArhP4",
    "consumoEnergiaReactivaEnVArhP5",
    "consumoEnergiaReactivaEnVArhP6",
]
DEMANDED_POWER_FIELDS = [
    "potenciaDemandadaEnWP1",
    "potenciaDemandadaEnWP2",
    "potenciaDemandadaEnWP3",
    "potenciaDemandadaEnWP4",
    "potenciaDemandadaEnWP5",
    "potenciaDemandadaEnWP6",
]

app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")
templates.env.globals["app_version"] = settings.app_version


@app.on_event("startup")
def on_startup():
    init_db()


def utcnow():
    return datetime.utcnow()


def build_cups_lookup_candidates(cups: str) -> list[str]:
    normalized_cups = cups.strip()
    if not normalized_cups:
        return []

    alternate_cups = (
        normalized_cups[:-2] if normalized_cups.upper().endswith("0F") else f"{normalized_cups}0F"
    )
    candidates = [normalized_cups]
    if alternate_cups and alternate_cups not in candidates:
        candidates.append(alternate_cups)
    return candidates


def get_record_by_exact_cups(db: Session, cups: str) -> Record | None:
    return db.query(Record).filter(Record.cups == cups).first()


def resolve_existing_cups(db: Session, cups: str) -> str:
    normalized_cups = cups.strip()
    for candidate in build_cups_lookup_candidates(normalized_cups):
        has_record = db.query(Record.id).filter(Record.cups == candidate).limit(1).first() is not None
        has_consumptions_for_candidate = (
            db.query(RecordConsumption.id).filter(RecordConsumption.cups == candidate).limit(1).first() is not None
        )
        has_autoconsumos_for_candidate = (
            db.query(RecordAutoconsumo.id).filter(RecordAutoconsumo.cups == candidate).limit(1).first() is not None
        )
        if has_record or has_consumptions_for_candidate or has_autoconsumos_for_candidate:
            return candidate
    return normalized_cups


def is_job_stalled(job: ImportJob, now: datetime | None = None) -> bool:
    if job.status != "processing":
        return False
    reference_time = job.last_progress_at or job.started_at
    if reference_time is None:
        return False
    if now is None:
        now = utcnow()
    return now - reference_time > STALL_THRESHOLD


def job_source_exists(job: ImportJob) -> bool:
    return bool(job.stored_path) and Path(job.stored_path).exists()


def can_requeue_job(job: ImportJob, now: datetime | None = None) -> bool:
    return job_source_exists(job) and (job.status == JOB_STATUS_FAILED or is_job_stalled(job, now=now))


def serialize_job(job: ImportJob) -> JobOut:
    payload = JobOut.model_validate(job)
    payload.can_requeue = can_requeue_job(job)
    payload.can_retry_failed_chunks = (
        job_source_exists(job)
        and job.total_chunks > 0
        and job.failed_chunks > 0
        and job.status != "splitting"
        and job.queued_chunks == 0
        and job.processing_chunks == 0
    )
    if job.total_bytes > 0:
        payload.split_progress_percent = min(
            (float(job.split_processed_bytes) / float(job.total_bytes)) * 100,
            100.0,
        )
    else:
        payload.split_progress_percent = 0.0
    return payload


def get_field_label(field_name: str) -> str:
    return FIELD_LABELS_CA.get(field_name, field_name)


def format_tariff_label(value):
    normalized_value = str(value).strip() if value not in (None, "") else ""
    if not normalized_value:
        return "-"
    return ATR_TARIFF_LABELS.get(normalized_value, normalized_value)


def format_field_value(value):
    return value if value not in (None, "") else "-"


def format_display_value(value, field_name: str | None = None):
    if value in (None, ""):
        return "-"
    if field_name in ("codigoTarifaATREnVigor", "codigoTarifaATR"):
        return format_tariff_label(value)
    return value


def format_datetime_minute(value: datetime | None) -> str:
    if value is None:
        return "-"
    return value.strftime("%Y-%m-%d %H:%M")


def build_job_display_title(job: ImportJob) -> str:
    parts = ["Importació #{}".format(job.id)]
    filename_stem = Path(job.filename or "").stem
    tokens = [token for token in filename_stem.split("_") if token]

    period = None
    if tokens:
        first_token = tokens[0]
        if len(first_token) == 6 and first_token.isdigit():
            year = first_token[:4]
            month = MONTH_LABELS_CA.get(first_token[4:6])
            if month:
                period = "{} {}".format(month, year)

    info_parts = []
    import_type_labels = {
        "CAUREPARTO": "Autoconsum",
        "VERTIDOS": "Vertidos",
        "CAUCIL": "CauCil",
        "CONSUMOS": "Consums",
        "PS": "Informació PS",
    }
    for token, label in import_type_labels.items():
        if token in tokens:
            info_parts.append(label)
            break
    if "peninsular" in tokens:
        info_parts.append("Peninsular")
    elif "balear" in tokens or "baleares" in tokens:
        info_parts.append("Balears")

    if period:
        parts.append(period)
    if info_parts:
        parts.append(" ".join(info_parts))

    return " - ".join(parts)


def build_record_groups(record: Record):
    if record is None:
        return []
    grouped_fields = []
    for group_name, field_names in FIELD_GROUPS:
        fields = []
        for field_name in field_names:
            fields.append(
                {
                    "name": field_name,
                    "label": get_field_label(field_name),
                    "value": format_display_value(getattr(record, field_name, None), field_name),
                }
            )
        grouped_fields.append({"name": group_name, "fields": fields})
    return grouped_fields


def format_consumption_period(consumption: RecordConsumption) -> str:
    if consumption is None:
        return "-"
    return "{} - {}".format(
        format_field_value(consumption.fechaInicioMesConsumo),
        format_field_value(consumption.fechaFinMesConsumo),
    )


def build_field_items(source, field_names: list[str]):
    items = []
    for field_name in field_names:
        items.append(
            {
                "name": field_name,
                "label": get_field_label(field_name),
                "value": format_display_value(getattr(source, field_name, None), field_name),
            }
        )
    return items


def build_record_summary(
    record: Record | None,
    cups: str,
    has_consumption_data: bool,
    has_autoconsumo_data: bool,
):
    available_data = []
    if record is not None:
        available_data.append("PS")
    if has_consumption_data:
        available_data.append("consumptions")
    if has_autoconsumo_data:
        available_data.append("autoconsumo")
    summary = [
        {
            "label": "CUPS",
            "value": format_display_value(record.cups if record is not None else cups, "cups"),
            "field_name": "cups",
        },
        {
            "label": "Dades disponibles",
            "value": ", ".join(available_data) if available_data else "-",
            "field_name": "data_type",
        },
    ]
    if record is not None:
        summary.extend(
            [
                {
                    "label": "Distribuidora",
                    "value": format_display_value(record.nombreEmpresaDistribuidora, "nombreEmpresaDistribuidora"),
                    "field_name": "nombreEmpresaDistribuidora",
                },
                {
                    "label": "Municipi",
                    "value": format_display_value(record.municipioPS, "municipioPS"),
                    "field_name": "municipioPS",
                },
                {
                    "label": "Tarifa ATR",
                    "value": format_display_value(record.codigoTarifaATREnVigor, "codigoTarifaATREnVigor"),
                    "field_name": "codigoTarifaATREnVigor",
                },
                {
                    "label": "Actualitzat",
                    "value": format_display_value(record.uploaded_at, "uploaded_at"),
                    "field_name": "uploaded_at",
                },
            ]
        )
    return summary


def build_consumption_history(consumptions: list[RecordConsumption]):
    rows = []
    for index, consumption in enumerate(consumptions, start=1):
        rows.append(
            {
                "id": consumption.id,
                "is_open": index == 1,
                "period": format_consumption_period(consumption),
                "tariff": format_display_value(consumption.codigoTarifaATR, "codigoTarifaATR"),
                "reading_type": format_display_value(consumption.codigoTipoLectura, "codigoTipoLectura"),
                "updated_at": format_display_value(consumption.uploaded_at, "uploaded_at"),
                "groups": [
                    {
                        "title": "Energia activa",
                        "fields": build_field_items(
                            consumption,
                            [
                                "consumoEnergiaActivaEnWhP1",
                                "consumoEnergiaActivaEnWhP2",
                                "consumoEnergiaActivaEnWhP3",
                                "consumoEnergiaActivaEnWhP4",
                                "consumoEnergiaActivaEnWhP5",
                                "consumoEnergiaActivaEnWhP6",
                            ],
                        ),
                    },
                    {
                        "title": "Energia reactiva",
                        "fields": build_field_items(
                            consumption,
                            [
                                "consumoEnergiaReactivaEnVArhP1",
                                "consumoEnergiaReactivaEnVArhP2",
                                "consumoEnergiaReactivaEnVArhP3",
                                "consumoEnergiaReactivaEnVArhP4",
                                "consumoEnergiaReactivaEnVArhP5",
                                "consumoEnergiaReactivaEnVArhP6",
                            ],
                        ),
                    },
                    {
                        "title": "Potència demandada",
                        "fields": build_field_items(
                            consumption,
                            [
                                "potenciaDemandadaEnWP1",
                                "potenciaDemandadaEnWP2",
                                "potenciaDemandadaEnWP3",
                                "potenciaDemandadaEnWP4",
                                "potenciaDemandadaEnWP5",
                                "potenciaDemandadaEnWP6",
                            ],
                        ),
                    },
                    {
                        "title": "Dades de mesura",
                        "fields": build_field_items(
                            consumption,
                            [
                                "codigoTarifaATR",
                                "codigoTipoLectura",
                                "codigoDHEquipoDeMedida",
                                "uploaded_at",
                            ],
                        ),
                    },
                ],
            }
        )
    return rows


def build_consumption_summary(consumptions: list[RecordConsumption]):
    if not consumptions:
        return []
    latest = consumptions[0]
    oldest = consumptions[-1]
    return [
        {"label": "Períodes importats", "value": str(len(consumptions))},
        {"label": "Període més recent", "value": format_consumption_period(latest)},
        {"label": "Període més antic", "value": format_consumption_period(oldest)},
        {"label": "Última tarifa", "value": format_display_value(latest.codigoTarifaATR, "codigoTarifaATR")},
    ]


def has_autoconsumos(db: Session, cups: str) -> bool:
    return (
        db.query(RecordAutoconsumo.id)
        .filter(RecordAutoconsumo.cups == cups)
        .limit(1)
        .first()
        is not None
    )


def get_autoconsumos_for_cups(db: Session, cups: str) -> list[RecordAutoconsumo]:
    return (
        db.query(RecordAutoconsumo)
        .filter(RecordAutoconsumo.cups == cups)
        .order_by(
            RecordAutoconsumo.fechaInicioReparto.desc(),
            RecordAutoconsumo.horaCoeficienteVariableReparto.asc(),
            RecordAutoconsumo.id.desc(),
        )
        .all()
    )


def build_autoconsumo_summary(autoconsumos: list[RecordAutoconsumo]):
    if not autoconsumos:
        return []
    unique_caus = {row.cau for row in autoconsumos if row.cau}
    latest = autoconsumos[0]
    return [
        {"label": "Rows imported", "value": str(len(autoconsumos))},
        {"label": "CAUs", "value": str(len(unique_caus))},
        {
            "label": "Latest reparto start",
            "value": format_display_value(latest.fechaInicioReparto, "fechaInicioReparto"),
        },
        {
            "label": "Last updated",
            "value": format_display_value(latest.uploaded_at, "uploaded_at"),
        },
    ]


def build_autoconsumo_rows(autoconsumos: list[RecordAutoconsumo]):
    rows = []
    for row in autoconsumos:
        rows.append(
            {
                "id": row.id,
                "cau": format_display_value(row.cau, "cau"),
                "fechaInicioReparto": format_display_value(row.fechaInicioReparto, "fechaInicioReparto"),
                "horaCoeficienteVariableReparto": format_display_value(
                    row.horaCoeficienteVariableReparto,
                    "horaCoeficienteVariableReparto",
                ),
                "coeficienteReparto": format_display_value(row.coeficienteReparto, "coeficienteReparto"),
                "uploaded_at": format_display_value(row.uploaded_at, "uploaded_at"),
            }
        )
    return rows


def parse_numeric_value(value) -> float:
    if value in (None, ""):
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    normalized = str(value).strip()
    try:
        return float(normalized)
    except ValueError:
        pass
    if "," in normalized:
        normalized = normalized.replace(".", "").replace(",", ".")
        try:
            return float(normalized)
        except ValueError:
            return 0.0
    return 0.0


def parse_consumption_date(value) -> date | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value

    text = str(value).strip()
    if not text:
        return None

    if text.isdigit() and len(text) == 8:
        try:
            return datetime.strptime(text, "%Y%m%d").date()
        except ValueError:
            return None

    for parser in (date.fromisoformat, datetime.fromisoformat):
        try:
            parsed = parser(text)
            return parsed if isinstance(parsed, date) and not isinstance(parsed, datetime) else parsed.date()
        except ValueError:
            continue

    for date_format in ("%Y-%m-%d", "%Y/%m/%d", "%d/%m/%Y", "%d-%m-%Y", "%Y%m%d"):
        try:
            return datetime.strptime(text, date_format).date()
        except ValueError:
            continue

    try:
        numeric_value = float(text.replace(",", "."))
    except ValueError:
        return None
    if 1 <= numeric_value <= 60000:
        return (datetime(1899, 12, 30) + timedelta(days=numeric_value)).date()
    return None


def format_metric_value(value: float | int | None, decimals: int = 3) -> str:
    if value in (None, ""):
        return "-"
    numeric_value = float(value)
    if numeric_value.is_integer():
        return str(int(numeric_value))
    return ("{:.%df}" % decimals).format(numeric_value).rstrip("0").rstrip(".")


def build_metric_items(values: dict[str, float], suffix: str = ""):
    items = []
    for field_name, value in values.items():
        label = get_field_label(field_name)
        if suffix:
            label = "{} {}".format(label, suffix)
        items.append({"label": label, "value": format_metric_value(value), "field_name": field_name})
    return items


def build_annual_consumption_summary(consumptions: list[RecordConsumption]):
    parsed_rows = []
    for consumption in consumptions:
        start_date = parse_consumption_date(consumption.fechaInicioMesConsumo)
        end_date = parse_consumption_date(consumption.fechaFinMesConsumo)
        if start_date is None or end_date is None:
            continue
        parsed_rows.append(
            {
                "consumption": consumption,
                "start_date": start_date,
                "end_date": end_date,
            }
        )

    if not parsed_rows:
        return None

    parsed_rows.sort(key=lambda row: (row["end_date"], row["start_date"]), reverse=True)
    latest_end_date = parsed_rows[0]["end_date"]
    included_rows = []
    for row in parsed_rows:
        days_from_latest = (latest_end_date - row["start_date"]).days
        row["days_from_latest"] = days_from_latest
        if days_from_latest <= 365:
            included_rows.append(row)

    if not included_rows:
        return None

    active_totals = {
        field_name: sum(parse_numeric_value(getattr(row["consumption"], field_name, None)) for row in included_rows) / 1000
        for field_name in ACTIVE_ENERGY_FIELDS
    }
    reactive_totals = {
        field_name: sum(parse_numeric_value(getattr(row["consumption"], field_name, None)) for row in included_rows) / 1000
        for field_name in REACTIVE_ENERGY_FIELDS
    }
    max_powers = {
        field_name: max(parse_numeric_value(getattr(row["consumption"], field_name, None)) for row in included_rows) / 1000
        for field_name in DEMANDED_POWER_FIELDS
    }

    total_consumption = round(sum(active_totals.values()))
    earliest_start_date = included_rows[-1]["start_date"]
    days_in_period = (latest_end_date - earliest_start_date).days
    prorated_consumption = None if days_in_period == 0 else (float(total_consumption) / float(days_in_period)) * 365

    return {
        "summary": [
            {"label": "Períodes inclosos", "value": str(len(included_rows))},
            {"label": "Nombre de CUPS", "value": str(len({row['consumption'].cups for row in included_rows}))},
            {"label": "Període més recent", "value": format_consumption_period(included_rows[0]["consumption"])},
            {"label": "Inici de la finestra", "value": format_field_value(included_rows[-1]["consumption"].fechaInicioMesConsumo)},
            {"label": "Dies del període", "value": str(days_in_period)},
            {"label": "Consum últims 365 dies (kWh)", "value": format_metric_value(total_consumption)},
            {
                "label": "Consum prorratejat a 365 dies",
                "value": format_metric_value(prorated_consumption) if prorated_consumption is not None else "-",
            },
        ],
        "groups": [
            {
                "title": "Ús energètic últims 365 dies (kWh)",
                "items": build_metric_items(active_totals),
            },
            {
                "title": "Energia reactiva últims 365 dies (kVArh)",
                "items": build_metric_items(reactive_totals),
            },
            {
                "title": "Potència màxima (kW)",
                "items": build_metric_items(max_powers),
            },
        ],
    }


def has_consumptions(db: Session, cups: str) -> bool:
    return (
        db.query(RecordConsumption.id)
        .filter(RecordConsumption.cups == cups)
        .limit(1)
        .first()
        is not None
    )


def get_consumptions_for_cups(db: Session, cups: str) -> list[RecordConsumption]:
    return (
        db.query(RecordConsumption)
        .filter(RecordConsumption.cups == cups)
        .order_by(
            RecordConsumption.fechaInicioMesConsumo.desc(),
            RecordConsumption.fechaFinMesConsumo.desc(),
        )
        .all()
    )


def build_csv_response(rows: list[dict[str, str]], headers: list[str], filename: str) -> Response:
    output = StringIO()
    writer = csv.DictWriter(output, fieldnames=headers, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return Response(
        content=output.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def serialize_csv_row(source, headers: list[str]) -> dict[str, str]:
    return {header: getattr(source, header, "") or "" for header in headers}


def build_search_results(db: Session, normalized_cups: str):
    records = []
    for candidate in build_cups_lookup_candidates(normalized_cups):
        records = (
            db.query(Record)
            .filter(Record.cups.ilike(f"%{candidate}%"))
            .order_by(Record.uploaded_at.desc())
            .limit(100)
            .all()
        )
        if records:
            break
    return [
        {
            "cups": record.cups,
            "codigoEmpresaDistribuidora": record.codigoEmpresaDistribuidora,
            "nombreEmpresaDistribuidora": record.nombreEmpresaDistribuidora,
            "codigoPostalPS": record.codigoPostalPS,
            "municipioPS": record.municipioPS,
            "tarifa": format_display_value(record.codigoTarifaATREnVigor, "codigoTarifaATREnVigor"),
            "uploaded_at": record.uploaded_at,
        }
        for record in records
    ]


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/", response_class=HTMLResponse)
def home(
    request: Request,
    cups: str = Query(default=""),
    db: Session = Depends(get_db),
):
    normalized_cups = cups.strip()
    records = []
    if normalized_cups:
        records = build_search_results(db, normalized_cups)
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "records": records,
            "cups": normalized_cups,
            "headers": CSV_HEADERS,
            "show_records": bool(normalized_cups),
        },
    )


@app.get("/imports", response_class=HTMLResponse)
def imports_page(request: Request, db: Session = Depends(get_db)):
    jobs = db.query(ImportJob).order_by(ImportJob.created_at.desc()).limit(20).all()
    return templates.TemplateResponse(
        "imports.html",
        {
            "request": request,
            "jobs": jobs,
            "status_labels": STATUS_LABELS_CA,
            "build_job_display_title": build_job_display_title,
            "format_datetime_minute": format_datetime_minute,
        },
    )


@app.get("/records/{cups}", response_class=HTMLResponse)
def record_detail(request: Request, cups: str, db: Session = Depends(get_db)):
    resolved_cups = resolve_existing_cups(db, cups)
    record = get_record_by_exact_cups(db, resolved_cups)
    has_consumption_data = has_consumptions(db, resolved_cups)
    has_autoconsumo_data = has_autoconsumos(db, resolved_cups)
    if record is None and not has_consumption_data and not has_autoconsumo_data:
        raise HTTPException(status_code=404, detail="Record not found")
    active_tab = request.query_params.get("tab", "ps")
    if active_tab not in ("ps", "consumptions", "annual", "autoconsumo"):
        active_tab = "ps"
    if record is None and active_tab == "ps":
        if has_consumption_data:
            active_tab = "consumptions"
        elif has_autoconsumo_data:
            active_tab = "autoconsumo"
    subject = record if record is not None else SimpleNamespace(cups=resolved_cups)
    should_defer_consumptions = has_consumption_data and active_tab != "consumptions"
    should_defer_annual_consumptions = has_consumption_data and active_tab != "annual"
    should_defer_autoconsumos = has_autoconsumo_data and active_tab != "autoconsumo"
    consumptions = []
    autoconsumos = []
    annual_consumption_summary = None
    if has_consumption_data and not should_defer_consumptions:
        consumptions = get_consumptions_for_cups(db, resolved_cups)
    if has_consumption_data and not should_defer_annual_consumptions:
        annual_source = consumptions if consumptions else get_consumptions_for_cups(db, resolved_cups)
        annual_consumption_summary = build_annual_consumption_summary(annual_source)
    if has_autoconsumo_data and not should_defer_autoconsumos:
        autoconsumos = get_autoconsumos_for_cups(db, resolved_cups)
    return templates.TemplateResponse(
        "detail.html",
        {
            "request": request,
            "record": subject,
            "record_groups": build_record_groups(record),
            "record_summary": build_record_summary(
                record,
                resolved_cups,
                has_consumption_data,
                has_autoconsumo_data,
            ),
            "active_tab": active_tab,
            "has_ps_data": record is not None,
            "has_consumption_data": has_consumption_data,
            "has_autoconsumo_data": has_autoconsumo_data,
            "should_defer_consumptions": should_defer_consumptions,
            "should_defer_annual_consumptions": should_defer_annual_consumptions,
            "should_defer_autoconsumos": should_defer_autoconsumos,
            "consumption_history": build_consumption_history(consumptions),
            "consumption_summary": build_consumption_summary(consumptions),
            "annual_consumption_summary": annual_consumption_summary,
            "autoconsumo_rows": build_autoconsumo_rows(autoconsumos),
            "autoconsumo_summary": build_autoconsumo_summary(autoconsumos),
        },
    )


@app.get("/records/{cups}/consumptions/partial", response_class=HTMLResponse)
def record_consumptions_partial(request: Request, cups: str, db: Session = Depends(get_db)):
    resolved_cups = resolve_existing_cups(db, cups)
    consumptions = get_consumptions_for_cups(db, resolved_cups)
    if not consumptions:
        record_exists = db.query(Record.id).filter(Record.cups == resolved_cups).limit(1).first() is not None
        if not record_exists:
            raise HTTPException(status_code=404, detail="Record not found")
    return templates.TemplateResponse(
        "record_consumptions_partial.html",
        {
            "request": request,
            "has_consumption_data": bool(consumptions),
            "consumption_history": build_consumption_history(consumptions),
            "consumption_summary": build_consumption_summary(consumptions),
        },
    )


@app.get("/records/{cups}/annual-consumptions/partial", response_class=HTMLResponse)
def record_annual_consumptions_partial(request: Request, cups: str, db: Session = Depends(get_db)):
    resolved_cups = resolve_existing_cups(db, cups)
    consumptions = get_consumptions_for_cups(db, resolved_cups)
    if not consumptions:
        record_exists = db.query(Record.id).filter(Record.cups == resolved_cups).limit(1).first() is not None
        if not record_exists:
            raise HTTPException(status_code=404, detail="Record not found")
    return templates.TemplateResponse(
        "record_annual_consumptions_partial.html",
        {
            "request": request,
            "has_consumption_data": bool(consumptions),
            "annual_consumption_summary": build_annual_consumption_summary(consumptions),
        },
    )


@app.get("/records/{cups}/autoconsumos/partial", response_class=HTMLResponse)
def record_autoconsumos_partial(request: Request, cups: str, db: Session = Depends(get_db)):
    resolved_cups = resolve_existing_cups(db, cups)
    autoconsumos = get_autoconsumos_for_cups(db, resolved_cups)
    if not autoconsumos:
        record_exists = db.query(Record.id).filter(Record.cups == resolved_cups).limit(1).first() is not None
        consumption_exists = has_consumptions(db, resolved_cups)
        if not record_exists and not consumption_exists:
            raise HTTPException(status_code=404, detail="Record not found")
    return templates.TemplateResponse(
        "record_autoconsumos_partial.html",
        {
            "request": request,
            "has_autoconsumo_data": bool(autoconsumos),
            "autoconsumo_rows": build_autoconsumo_rows(autoconsumos),
            "autoconsumo_summary": build_autoconsumo_summary(autoconsumos),
        },
    )


@app.get("/records/{cups}/ps.csv")
def download_record_ps_csv(cups: str, db: Session = Depends(get_db)):
    resolved_cups = resolve_existing_cups(db, cups)
    record = get_record_by_exact_cups(db, resolved_cups)
    if record is None:
        raise HTTPException(status_code=404, detail="Record not found")
    return build_csv_response(
        rows=[serialize_csv_row(record, PS_CSV_HEADERS)],
        headers=PS_CSV_HEADERS,
        filename=f"{resolved_cups}_ps.csv",
    )


@app.get("/records/{cups}/consumptions.csv")
def download_record_consumptions_csv(cups: str, db: Session = Depends(get_db)):
    resolved_cups = resolve_existing_cups(db, cups)
    consumptions = get_consumptions_for_cups(db, resolved_cups)
    if not consumptions:
        record_exists = db.query(Record.id).filter(Record.cups == resolved_cups).limit(1).first() is not None
        if not record_exists:
            raise HTTPException(status_code=404, detail="Record not found")
        raise HTTPException(status_code=404, detail="Consumptions not found")
    return build_csv_response(
        rows=[serialize_csv_row(consumption, CONSUMPTION_CSV_HEADERS) for consumption in consumptions],
        headers=CONSUMPTION_CSV_HEADERS,
        filename=f"{resolved_cups}_consumptions.csv",
    )


@app.get("/records/{cups}/autoconsumos.csv")
def download_record_autoconsumos_csv(cups: str, db: Session = Depends(get_db)):
    resolved_cups = resolve_existing_cups(db, cups)
    autoconsumos = get_autoconsumos_for_cups(db, resolved_cups)
    if not autoconsumos:
        record_exists = db.query(Record.id).filter(Record.cups == resolved_cups).limit(1).first() is not None
        if not record_exists:
            raise HTTPException(status_code=404, detail="Record not found")
        raise HTTPException(status_code=404, detail="Autoconsumo rows not found")
    return build_csv_response(
        rows=[serialize_csv_row(autoconsumo, AUTOCONSUMO_CSV_HEADERS) for autoconsumo in autoconsumos],
        headers=AUTOCONSUMO_CSV_HEADERS,
        filename=f"{resolved_cups}_autoconsumos.csv",
    )


@app.get("/autoconsumos/{autoconsumo_id}", response_class=HTMLResponse)
def autoconsumo_detail(request: Request, autoconsumo_id: int, db: Session = Depends(get_db)):
    autoconsumo = db.query(RecordAutoconsumo).filter(RecordAutoconsumo.id == autoconsumo_id).first()
    if autoconsumo is None:
        raise HTTPException(status_code=404, detail="Autoconsumo row not found")
    linked_record = get_record_by_exact_cups(db, resolve_existing_cups(db, autoconsumo.cups))
    return templates.TemplateResponse(
        "autoconsumo_detail.html",
        {
            "request": request,
            "autoconsumo": autoconsumo,
            "linked_record": linked_record,
            "field_items": build_field_items(
                autoconsumo,
                [
                    "cau",
                    "fechaInicioReparto",
                    "cups",
                    "horaCoeficienteVariableReparto",
                    "coeficienteReparto",
                    "uploaded_at",
                ],
            ),
        },
    )


@app.get("/jobs/{job_id}", response_class=HTMLResponse)
def job_detail(request: Request, job_id: int, db: Session = Depends(get_db)):
    job = db.query(ImportJob).filter(ImportJob.id == job_id).first()
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return templates.TemplateResponse(
        "job.html",
        {
            "request": request,
            "job": job,
            "job_display_title": build_job_display_title(job),
            "status_labels": STATUS_LABELS_CA,
        },
    )


@app.post("/api/uploads", response_model=UploadResponse)
async def upload_from_api(file: UploadFile = File(...), db: Session = Depends(get_db)):
    if not file.filename:
        raise HTTPException(status_code=400, detail="Missing filename")

    suffix = Path(file.filename).suffix or ".csv"
    if suffix.lower() not in (".csv", ".zip"):
        raise HTTPException(status_code=400, detail="Only CSV or ZIP files are supported")
    stored_name = f"{uuid4().hex}{suffix}"
    stored_path = settings.upload_dir / stored_name
    uploaded_bytes = 0

    with stored_path.open("wb") as output_file:
        while True:
            chunk = await file.read(settings.upload_chunk_size)
            if not chunk:
                break
            output_file.write(chunk)
            uploaded_bytes += len(chunk)
    await file.close()

    job = ImportJob(
        filename=file.filename,
        stored_path=str(stored_path),
        status="queued",
        total_bytes=uploaded_bytes,
        uploaded_bytes=uploaded_bytes,
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    try:
        enqueue_import(job.id)
    except Exception as exc:
        job.status = JOB_STATUS_FAILED
        job.error_message = f"Could not enqueue background job: {exc}"
        db.commit()
        raise HTTPException(status_code=503, detail="Could not enqueue background job")
    return {"job_id": job.id, "status": job.status}


@app.get("/api/jobs", response_model=list[JobOut])
def list_jobs(limit: int = Query(default=20, ge=1, le=200), db: Session = Depends(get_db)):
    jobs = db.query(ImportJob).order_by(ImportJob.created_at.desc()).limit(limit).all()
    return [serialize_job(job) for job in jobs]


@app.get("/api/jobs/{job_id}", response_model=JobOut)
def get_job(job_id: int, db: Session = Depends(get_db)):
    job = db.query(ImportJob).filter(ImportJob.id == job_id).first()
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return serialize_job(job)


@app.get("/api/jobs/{job_id}/chunks", response_model=JobChunkPageOut)
def get_job_chunks(
    job_id: int,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    job = db.query(ImportJob).filter(ImportJob.id == job_id).first()
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    chunks_query = db.query(ImportJobChunk).filter(ImportJobChunk.job_id == job_id)
    total = chunks_query.count()
    total_pages = max((total + page_size - 1) // page_size, 1)
    current_page = min(page, total_pages)
    offset = (current_page - 1) * page_size
    items = (
        chunks_query
        .order_by(ImportJobChunk.chunk_index.asc())
        .offset(offset)
        .limit(page_size)
        .all()
    )
    return {
        "items": items,
        "page": current_page,
        "page_size": page_size,
        "total": total,
        "total_pages": total_pages,
    }


@app.post("/api/jobs/{job_id}/requeue", response_model=JobOut)
def requeue_job(
    job_id: int,
    force: bool = Query(default=False),
    db: Session = Depends(get_db),
):
    job = db.query(ImportJob).filter(ImportJob.id == job_id).first()
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    if force:
        if job.status == "completed":
            raise HTTPException(status_code=409, detail="Completed jobs cannot be requeued")
        cleanup_job_chunks(db, job)
    elif not can_requeue_job(job):
        raise HTTPException(status_code=409, detail="Job cannot be requeued")

    now = utcnow()
    job.attempt_token = uuid4().hex
    job.status = "queued"
    job.started_at = None
    job.finished_at = None
    job.processed_bytes = 0
    job.processed_rows = 0
    job.created_rows = 0
    job.updated_rows = 0
    job.error_rows = 0
    job.rows_per_second = 0
    job.error_message = None
    job.last_progress_at = now
    job.total_chunks = 0
    job.queued_chunks = 0
    job.processing_chunks = 0
    job.completed_chunks = 0
    job.failed_chunks = 0
    job.split_processed_bytes = 0
    job.split_created_chunks = 0
    db.commit()
    db.refresh(job)

    try:
        enqueue_import(job.id)
    except Exception as exc:
        job.status = JOB_STATUS_FAILED
        job.finished_at = now
        job.last_progress_at = now
        job.error_message = f"Could not enqueue background job: {exc}"
        db.commit()
        raise HTTPException(status_code=503, detail="Could not enqueue background job")

    db.refresh(job)
    return serialize_job(job)


@app.post("/api/jobs/{job_id}/retry-failed-chunks", response_model=RetryFailedChunksResponse)
def retry_job_failed_chunks(job_id: int, db: Session = Depends(get_db)):
    job = db.query(ImportJob).filter(ImportJob.id == job_id).first()
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status == "splitting":
        raise HTTPException(status_code=409, detail="Job is still splitting")
    if job.failed_chunks <= 0:
        raise HTTPException(status_code=409, detail="No failed chunks to retry")

    retried_chunks = retry_failed_chunks(job_id)
    if retried_chunks <= 0:
        raise HTTPException(status_code=409, detail="No failed chunks to retry")

    refreshed_job = db.query(ImportJob).filter(ImportJob.id == job_id).first()
    return {
        "job_id": job_id,
        "retried_chunks": retried_chunks,
        "status": refreshed_job.status if refreshed_job else "processing",
    }


@app.post("/api/jobs/{job_id}/cleanup-artifacts", response_model=JobOut)
def cleanup_job_files(job_id: int, db: Session = Depends(get_db)):
    job = db.query(ImportJob).filter(ImportJob.id == job_id).first()
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    if job.status in (JOB_STATUS_QUEUED, JOB_STATUS_SPLITTING, JOB_STATUS_PROCESSING):
        now = utcnow()
        job.status = JOB_STATUS_FAILED
        job.finished_at = now
        job.last_progress_at = now
        job.error_message = "Artifacts deleted manually before import completed."

    cleanup_job_artifacts(db, job, delete_source=True)
    db.refresh(job)
    return serialize_job(job)


@app.get("/api/records", response_model=list[RecordOut])
def list_records(
    cups: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=1000),
    db: Session = Depends(get_db),
):
    query = db.query(Record)
    if not cups:
        return query.order_by(Record.uploaded_at.desc()).limit(limit).all()

    records = []
    normalized_cups = cups.strip()
    for candidate in build_cups_lookup_candidates(normalized_cups):
        records = (
            db.query(Record)
            .filter(Record.cups.ilike(f"%{candidate}%"))
            .order_by(Record.uploaded_at.desc())
            .limit(limit)
            .all()
        )
        if records:
            break
    return records


@app.get("/api/records/{cups}", response_model=RecordOut)
def get_record(cups: str, db: Session = Depends(get_db)):
    record = get_record_by_exact_cups(db, resolve_existing_cups(db, cups))
    if record is None:
        raise HTTPException(status_code=404, detail="Record not found")
    return record


@app.get("/api/records/{cups}/bono-social", response_model=RecordBonoSocialOut)
def get_record_bono_social(cups: str, db: Session = Depends(get_db)):
    record = get_record_by_exact_cups(db, resolve_existing_cups(db, cups))
    if record is None:
        raise HTTPException(status_code=404, detail="Record not found")
    return {
        "cups": record.cups,
        "hasBonoSocial": str(record.aplicacionBonoSocial or "").strip() == "1",
    }


@app.get("/api/records/{cups}/consumptions", response_model=list[RecordConsumptionOut])
def get_record_consumptions(cups: str, db: Session = Depends(get_db)):
    resolved_cups = resolve_existing_cups(db, cups)
    return (
        db.query(RecordConsumption)
        .filter(RecordConsumption.cups == resolved_cups)
        .order_by(
            RecordConsumption.fechaInicioMesConsumo.desc(),
            RecordConsumption.fechaFinMesConsumo.desc(),
        )
        .all()
    )
