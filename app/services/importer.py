import csv
import io
from collections import OrderedDict
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from time import perf_counter
from uuid import uuid4
from zipfile import ZipFile

from sqlalchemy import tuple_
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.constants import (
    IMPORT_FORMAT_AUTOCONSUMO,
    IMPORT_FORMAT_CONSUMPTION,
    IMPORT_FORMAT_HEADERS,
    IMPORT_FORMAT_PS,
)
from app.database import SessionLocal
from app.jobs import enqueue_import_chunk
from app.models import ImportJob, ImportJobChunk, Record, RecordAutoconsumo, RecordConsumption
from app.settings import settings


JOB_STATUS_QUEUED = "queued"
JOB_STATUS_SPLITTING = "splitting"
JOB_STATUS_PROCESSING = "processing"
JOB_STATUS_PARTIAL_FAILED = "partial_failed"
JOB_STATUS_COMPLETED = "completed"
JOB_STATUS_FAILED = "failed"

CHUNK_STATUS_QUEUED = "queued"
CHUNK_STATUS_PROCESSING = "processing"
CHUNK_STATUS_COMPLETED = "completed"
CHUNK_STATUS_FAILED = "failed"
SPLIT_PROGRESS_COMMIT_BYTES = 100 * 1024 * 1024
TERMINAL_JOB_STATUSES = {JOB_STATUS_COMPLETED, JOB_STATUS_PARTIAL_FAILED, JOB_STATUS_FAILED}


def utcnow():
    return datetime.utcnow()


def new_attempt_token():
    return uuid4().hex


class JobSupersededError(RuntimeError):
    pass


def normalize_value(value):
    if value is None:
        return None
    value = value.replace("\x00", "").strip()
    return value or None


def sanitize_headers(headers):
    return [(header or "").replace("\x00", "").strip() for header in headers]


def sanitize_row(row):
    sanitized = {}
    for key, value in row.items():
        sanitized_key = (key or "").replace("\x00", "").strip()
        sanitized_value = value.replace("\x00", "") if value is not None else None
        sanitized[sanitized_key] = sanitized_value
    return sanitized


def detect_csv_format(headers):
    normalized_headers = sanitize_headers(headers)
    for import_format, expected_headers in IMPORT_FORMAT_HEADERS.items():
        if normalized_headers == expected_headers:
            return import_format
    raise ValueError("CSV headers do not match any supported format.")


def validate_headers(headers, import_format=None):
    detected_format = detect_csv_format(headers)
    if import_format is not None and detected_format != import_format:
        raise ValueError("CSV headers do not match the expected format.")
    return detected_format


def get_headers_for_format(import_format):
    return IMPORT_FORMAT_HEADERS[import_format]


def deduplicate_rows(import_format, rows):
    deduplicated = OrderedDict()
    for row in rows:
        if import_format == IMPORT_FORMAT_PS:
            key = row["cups"]
        elif import_format == IMPORT_FORMAT_AUTOCONSUMO:
            key = (
                row["cau"],
                row["fechaInicioReparto"],
                row["cups"],
                row["horaCoeficienteVariableReparto"],
            )
        else:
            key = (
                row["cups"],
                row["fechaInicioMesConsumo"],
                row["fechaFinMesConsumo"],
            )
        deduplicated[key] = row
    return list(deduplicated.values())


def is_same_attempt(timestamp_a, timestamp_b):
    if timestamp_a is None or timestamp_b is None:
        return False
    return abs((timestamp_a - timestamp_b).total_seconds()) < 1


def ensure_job_attempt_active(db: Session, job_id, started_at, attempt_token=None):
    current_job = db.query(ImportJob).filter(ImportJob.id == job_id).first()
    if current_job is None:
        raise JobSupersededError("Import job no longer exists.")
    if current_job.status not in (JOB_STATUS_PROCESSING, JOB_STATUS_SPLITTING):
        raise JobSupersededError("Import job is no longer active.")
    if attempt_token is not None and current_job.attempt_token != attempt_token:
        raise JobSupersededError("Import job attempt has been superseded.")
    if current_job.started_at and not is_same_attempt(current_job.started_at, started_at):
        raise JobSupersededError("Import job attempt has been superseded.")
    return current_job


def ensure_chunk_attempt_active(db: Session, chunk_id, attempt_token):
    chunk = db.query(ImportJobChunk).filter(ImportJobChunk.id == chunk_id).first()
    if chunk is None:
        raise JobSupersededError("Import chunk no longer exists.")
    if chunk.status != CHUNK_STATUS_PROCESSING:
        raise JobSupersededError("Import chunk is no longer active.")
    parent_job = db.query(ImportJob).filter(ImportJob.id == chunk.job_id).first()
    if parent_job is None:
        raise JobSupersededError("Import job no longer exists.")
    if parent_job.attempt_token != attempt_token:
        raise JobSupersededError("Import job attempt has been superseded.")
    if parent_job.status not in (JOB_STATUS_PROCESSING, JOB_STATUS_SPLITTING):
        raise JobSupersededError("Import job is no longer active.")
    return chunk


def normalize_row(import_format, row):
    headers = get_headers_for_format(import_format)
    normalized = {key: normalize_value(row.get(key)) for key in headers}
    cups = normalized.get("cups")
    if not cups:
        raise ValueError("missing cups value")
    if import_format == IMPORT_FORMAT_CONSUMPTION:
        if not normalized.get("fechaInicioMesConsumo") or not normalized.get("fechaFinMesConsumo"):
            raise ValueError("missing consumption period")
    if import_format == IMPORT_FORMAT_AUTOCONSUMO:
        if not normalized.get("cau"):
            raise ValueError("missing cau value")
        if not normalized.get("fechaInicioReparto"):
            raise ValueError("missing fechaInicioReparto value")
        normalized["horaCoeficienteVariableReparto"] = (
            normalized.get("horaCoeficienteVariableReparto") or ""
        )
    normalized["uploaded_at"] = utcnow()
    return normalized


def upsert_ps_chunk(db: Session, rows):
    if not rows:
        return 0, 0

    deduplicated_rows = deduplicate_rows(IMPORT_FORMAT_PS, rows)
    cups_values = [row["cups"] for row in deduplicated_rows]
    existing_cups = set(
        value[0] for value in db.query(Record.cups).filter(Record.cups.in_(cups_values)).all()
    )
    created = len(deduplicated_rows) - len(existing_cups)
    updated = len(existing_cups)

    insert_stmt = insert(Record).values(deduplicated_rows)
    update_columns = {
        header: insert_stmt.excluded[header]
        for header in get_headers_for_format(IMPORT_FORMAT_PS)
        if header != "cups"
    }
    update_columns["uploaded_at"] = insert_stmt.excluded.uploaded_at
    db.execute(
        insert_stmt.on_conflict_do_update(
            index_elements=[Record.cups],
            set_=update_columns,
        )
    )
    db.commit()
    return created, updated


def upsert_consumption_chunk(db: Session, rows):
    if not rows:
        return 0, 0

    deduplicated_rows = deduplicate_rows(IMPORT_FORMAT_CONSUMPTION, rows)
    keys = [
        (row["cups"], row["fechaInicioMesConsumo"], row["fechaFinMesConsumo"])
        for row in deduplicated_rows
    ]
    existing_keys = set(
        db.query(
            RecordConsumption.cups,
            RecordConsumption.fechaInicioMesConsumo,
            RecordConsumption.fechaFinMesConsumo,
        )
        .filter(
            tuple_(
                RecordConsumption.cups,
                RecordConsumption.fechaInicioMesConsumo,
                RecordConsumption.fechaFinMesConsumo,
            ).in_(keys)
        )
        .all()
    )
    created = len(deduplicated_rows) - len(existing_keys)
    updated = len(existing_keys)

    insert_stmt = insert(RecordConsumption).values(deduplicated_rows)
    update_columns = {
        header: insert_stmt.excluded[header]
        for header in get_headers_for_format(IMPORT_FORMAT_CONSUMPTION)
        if header not in ("cups", "fechaInicioMesConsumo", "fechaFinMesConsumo")
    }
    update_columns["uploaded_at"] = insert_stmt.excluded.uploaded_at
    db.execute(
        insert_stmt.on_conflict_do_update(
            index_elements=[
                RecordConsumption.cups,
                RecordConsumption.fechaInicioMesConsumo,
                RecordConsumption.fechaFinMesConsumo,
            ],
            set_=update_columns,
        )
    )
    db.commit()
    return created, updated


def upsert_autoconsumo_chunk(db: Session, rows):
    if not rows:
        return 0, 0

    deduplicated_rows = deduplicate_rows(IMPORT_FORMAT_AUTOCONSUMO, rows)
    keys = [
        (
            row["cau"],
            row["fechaInicioReparto"],
            row["cups"],
            row["horaCoeficienteVariableReparto"],
        )
        for row in deduplicated_rows
    ]
    existing_keys = set(
        db.query(
            RecordAutoconsumo.cau,
            RecordAutoconsumo.fechaInicioReparto,
            RecordAutoconsumo.cups,
            RecordAutoconsumo.horaCoeficienteVariableReparto,
        )
        .filter(
            tuple_(
                RecordAutoconsumo.cau,
                RecordAutoconsumo.fechaInicioReparto,
                RecordAutoconsumo.cups,
                RecordAutoconsumo.horaCoeficienteVariableReparto,
            ).in_(keys)
        )
        .all()
    )
    created = len(deduplicated_rows) - len(existing_keys)
    updated = len(existing_keys)

    insert_stmt = insert(RecordAutoconsumo).values(deduplicated_rows)
    update_columns = {
        header: insert_stmt.excluded[header]
        for header in get_headers_for_format(IMPORT_FORMAT_AUTOCONSUMO)
        if header not in ("cau", "fechaInicioReparto", "cups", "horaCoeficienteVariableReparto")
    }
    update_columns["uploaded_at"] = insert_stmt.excluded.uploaded_at
    db.execute(
        insert_stmt.on_conflict_do_update(
            index_elements=[
                RecordAutoconsumo.cau,
                RecordAutoconsumo.fechaInicioReparto,
                RecordAutoconsumo.cups,
                RecordAutoconsumo.horaCoeficienteVariableReparto,
            ],
            set_=update_columns,
        )
    )
    db.commit()
    return created, updated


def upsert_chunk(db: Session, import_format, rows):
    if import_format == IMPORT_FORMAT_PS:
        return upsert_ps_chunk(db, rows)
    if import_format == IMPORT_FORMAT_CONSUMPTION:
        return upsert_consumption_chunk(db, rows)
    if import_format == IMPORT_FORMAT_AUTOCONSUMO:
        return upsert_autoconsumo_chunk(db, rows)
    raise ValueError("Unsupported import format.")


def chunk_file_path(job_id, chunk_index, attempt_token):
    return settings.chunk_upload_dir / "job_{:06d}_{}_chunk_{:05d}.csv".format(
        job_id,
        attempt_token[:8],
        chunk_index,
    )


def delete_path_if_exists(path_value):
    if not path_value:
        return False
    try:
        Path(path_value).unlink()
        return True
    except OSError:
        return False


def cleanup_job_chunks(db: Session, job: ImportJob, commit=True):
    chunk_records = db.query(ImportJobChunk).filter(ImportJobChunk.job_id == job.id).all()
    for chunk in chunk_records:
        delete_path_if_exists(chunk.stored_path)
        db.delete(chunk)
    if commit:
        db.commit()


def cleanup_job_artifacts(db: Session, job: ImportJob, delete_source=False):
    cleanup_job_chunks(db, job, commit=False)
    source_deleted = delete_path_if_exists(job.stored_path) if delete_source else False
    db.commit()
    return {"source_deleted": source_deleted}


def build_chunk_record(job_id, chunk_index, path, total_rows):
    return ImportJobChunk(
        job_id=job_id,
        chunk_index=chunk_index,
        filename=path.name,
        stored_path=str(path),
        status=CHUNK_STATUS_QUEUED,
        total_rows=total_rows,
    )


def persist_chunk_record(
    db: Session,
    job: ImportJob,
    chunk_record: ImportJobChunk,
    started_at,
    attempt_token,
    processed_bytes,
    created_chunks,
):
    ensure_job_attempt_active(db, job.id, started_at, attempt_token=attempt_token)
    db.add(chunk_record)
    db.commit()
    update_split_progress(
        db,
        job,
        started_at,
        attempt_token,
        processed_bytes,
        created_chunks,
        force=True,
    )
    try:
        enqueue_import_chunk(chunk_record.id)
    except Exception as exc:
        chunk = db.query(ImportJobChunk).filter(ImportJobChunk.id == chunk_record.id).first()
        if chunk is not None:
            chunk.status = CHUNK_STATUS_FAILED
            chunk.error_message = "Could not enqueue chunk: {}".format(exc)
            chunk.finished_at = utcnow()
            chunk.last_progress_at = chunk.finished_at
            db.commit()
        refresh_import_job_status(db, job.id)


def update_split_progress(
    db: Session,
    job: ImportJob,
    started_at,
    attempt_token,
    processed_bytes,
    created_chunks,
    force=False,
):
    processed_bytes = min(processed_bytes, job.total_bytes or processed_bytes)
    bytes_delta = processed_bytes - (job.split_processed_bytes or 0)
    chunks_delta = created_chunks - (job.split_created_chunks or 0)
    if not force and bytes_delta < SPLIT_PROGRESS_COMMIT_BYTES and chunks_delta <= 0:
        return

    job = ensure_job_attempt_active(db, job.id, started_at, attempt_token=attempt_token)
    job.split_processed_bytes = processed_bytes
    job.split_created_chunks = created_chunks
    job.last_progress_at = utcnow()
    db.commit()


def inspect_zip_import_source(path: Path):
    matched_sources = []
    with ZipFile(path) as archive:
        for member in archive.infolist():
            if member.is_dir() or Path(member.filename).suffix.lower() != ".csv":
                continue
            with archive.open(member) as raw_member:
                text_wrapper = io.TextIOWrapper(raw_member, encoding="utf-8-sig", newline="")
                reader = csv.DictReader(text_wrapper)
                headers = sanitize_headers(reader.fieldnames or [])
                try:
                    import_format = validate_headers(headers)
                except ValueError:
                    continue
                matched_sources.append(
                    {
                        "import_format": import_format,
                        "headers": headers,
                        "archive_member": member.filename,
                    }
                )
        if not matched_sources:
            raise ValueError("ZIP file does not contain a supported CSV.")
        if len(matched_sources) > 1:
            raise ValueError("ZIP file contains multiple supported CSV files.")
    return matched_sources[0]


def inspect_import_source(stored_path):
    path = Path(stored_path)
    if path.suffix.lower() == ".zip":
        source = inspect_zip_import_source(path)
        source["path"] = path
        source["is_zip"] = True
        return source

    with path.open("rb") as raw_file:
        text_wrapper = io.TextIOWrapper(raw_file, encoding="utf-8-sig", newline="")
        reader = csv.DictReader(text_wrapper)
        headers = sanitize_headers(reader.fieldnames or [])
        import_format = validate_headers(headers)
    return {
        "path": path,
        "is_zip": False,
        "import_format": import_format,
        "headers": headers,
        "archive_member": None,
    }


@contextmanager
def open_import_source(source):
    if source["is_zip"]:
        with ZipFile(source["path"]) as archive:
            with archive.open(source["archive_member"]) as raw_file:
                text_wrapper = io.TextIOWrapper(raw_file, encoding="utf-8-sig", newline="")
                try:
                    yield raw_file, text_wrapper
                finally:
                    text_wrapper.detach()
        return

    with source["path"].open("rb") as raw_file:
        text_wrapper = io.TextIOWrapper(raw_file, encoding="utf-8-sig", newline="")
        try:
            yield raw_file, text_wrapper
        finally:
            text_wrapper.detach()


def split_csv_into_chunks(db: Session, job: ImportJob, started_at, attempt_token):
    current_writer = None
    current_file = None
    current_path = None
    current_rows = 0
    chunk_index = 0
    created_chunks = 0
    rows_since_last_check = 0
    source = inspect_import_source(job.stored_path)
    import_format = source["import_format"]
    headers = get_headers_for_format(import_format)

    with open_import_source(source) as (raw_file, text_wrapper):
        reader = csv.DictReader(text_wrapper)
        validate_headers(sanitize_headers(reader.fieldnames or []), import_format=import_format)

        def flush_current_chunk():
            if current_file is None or current_rows == 0:
                return None
            current_file.close()
            return build_chunk_record(job.id, chunk_index - 1, current_path, current_rows)

        for row in reader:
            sanitized_row = sanitize_row(row)
            rows_since_last_check += 1
            if rows_since_last_check >= 1000:
                ensure_job_attempt_active(db, job.id, started_at, attempt_token=attempt_token)
                rows_since_last_check = 0
            if current_writer is None:
                ensure_job_attempt_active(db, job.id, started_at, attempt_token=attempt_token)
                current_path = chunk_file_path(job.id, chunk_index, attempt_token)
                current_file = current_path.open("w", encoding="utf-8", newline="")
                current_writer = csv.DictWriter(current_file, fieldnames=headers)
                current_writer.writeheader()
                current_rows = 0
                chunk_index += 1

            current_writer.writerow({header: sanitized_row.get(header) for header in headers})
            current_rows += 1
            update_split_progress(
                db,
                job,
                started_at,
                attempt_token,
                raw_file.tell(),
                created_chunks,
            )

            if current_rows >= settings.import_split_rows:
                ensure_job_attempt_active(db, job.id, started_at, attempt_token=attempt_token)
                chunk_record = flush_current_chunk()
                if chunk_record is not None:
                    created_chunks += 1
                    persist_chunk_record(
                        db,
                        job,
                        chunk_record,
                        started_at,
                        attempt_token,
                        raw_file.tell(),
                        created_chunks,
                    )
                current_writer = None
                current_file = None
                current_path = None
                current_rows = 0

        if current_file is not None and current_rows > 0:
            ensure_job_attempt_active(db, job.id, started_at, attempt_token=attempt_token)
            chunk_record = flush_current_chunk()
            if chunk_record is not None:
                created_chunks += 1
                persist_chunk_record(
                    db,
                    job,
                    chunk_record,
                    started_at,
                    attempt_token,
                    raw_file.tell(),
                    created_chunks,
                )

        update_split_progress(
            db,
            job,
            started_at,
            attempt_token,
            job.total_bytes,
            created_chunks,
            force=True,
        )

    return created_chunks


def refresh_import_job_status(db: Session, job_id):
    job = db.query(ImportJob).filter(ImportJob.id == job_id).first()
    if job is None:
        return None

    chunks = (
        db.query(ImportJobChunk)
        .filter(ImportJobChunk.job_id == job_id)
        .order_by(ImportJobChunk.chunk_index.asc())
        .all()
    )

    if chunks:
        job.total_chunks = len(chunks)
        job.queued_chunks = sum(1 for chunk in chunks if chunk.status == CHUNK_STATUS_QUEUED)
        job.processing_chunks = sum(1 for chunk in chunks if chunk.status == CHUNK_STATUS_PROCESSING)
        job.completed_chunks = sum(1 for chunk in chunks if chunk.status == CHUNK_STATUS_COMPLETED)
        job.failed_chunks = sum(1 for chunk in chunks if chunk.status == CHUNK_STATUS_FAILED)

        job.processed_rows = sum(chunk.processed_rows for chunk in chunks)
        job.created_rows = sum(chunk.created_rows for chunk in chunks)
        job.updated_rows = sum(chunk.updated_rows for chunk in chunks)
        job.error_rows = sum(chunk.error_rows for chunk in chunks)
        job.rows_per_second = round(sum(chunk.rows_per_second for chunk in chunks), 2)

        total_rows = sum(chunk.total_rows for chunk in chunks)
        if total_rows > 0 and job.total_bytes:
            ratio = min(float(job.processed_rows) / float(total_rows), 1.0)
            job.processed_bytes = int(job.total_bytes * ratio)
        elif job.status == JOB_STATUS_COMPLETED:
            job.processed_bytes = job.total_bytes
        else:
            job.processed_bytes = 0

        progress_timestamps = [chunk.last_progress_at for chunk in chunks if chunk.last_progress_at]
        if progress_timestamps:
            job.last_progress_at = max(progress_timestamps)

    split_in_progress = job.status == JOB_STATUS_SPLITTING and job.split_processed_bytes < job.total_bytes

    if split_in_progress:
        job.status = JOB_STATUS_SPLITTING
        job.finished_at = None
        if job.failed_chunks > 0:
            job.error_message = "Alguns chunks han fallat mentre la divisio continua."
        else:
            job.error_message = None
    elif not chunks and job.status in TERMINAL_JOB_STATUSES:
        now = utcnow()
        if job.finished_at is None:
            job.finished_at = now
        if job.last_progress_at is None:
            job.last_progress_at = job.finished_at
        if job.status == JOB_STATUS_COMPLETED:
            job.processed_bytes = job.total_bytes
            job.error_message = None
    elif not chunks:
        job.total_chunks = 0
        job.queued_chunks = 0
        job.processing_chunks = 0
        job.completed_chunks = 0
        job.failed_chunks = 0
        job.processed_rows = 0
        job.created_rows = 0
        job.updated_rows = 0
        job.error_rows = 0
        job.rows_per_second = 0
        job.processed_bytes = 0
        now = utcnow()
        job.status = JOB_STATUS_COMPLETED
        job.finished_at = now
        job.last_progress_at = now
        job.error_message = None
    elif job.queued_chunks > 0 or job.processing_chunks > 0:
        job.status = JOB_STATUS_PROCESSING
        job.finished_at = None
        job.error_message = None if job.failed_chunks == 0 else "Some chunks failed while others are still running."
    elif job.failed_chunks > 0:
        job.status = JOB_STATUS_PARTIAL_FAILED
        now = utcnow()
        job.finished_at = now
        job.last_progress_at = now
        job.error_message = "{} chunk(s) failed. Retry failed chunks to continue.".format(
            job.failed_chunks
        )
    else:
        job.status = JOB_STATUS_COMPLETED
        now = utcnow()
        job.finished_at = now
        job.last_progress_at = now
        job.processed_bytes = job.total_bytes
        job.error_message = None

    db.commit()
    return job


def process_import_job(job_id):
    db = SessionLocal()
    try:
        job = db.query(ImportJob).filter(ImportJob.id == job_id).first()
        if job is None:
            return
        if job.status != JOB_STATUS_QUEUED:
            return

        cleanup_job_chunks(db, job)

        now = utcnow()
        job.status = JOB_STATUS_SPLITTING
        job.started_at = now
        job.attempt_token = new_attempt_token()
        job.finished_at = None
        job.last_progress_at = now
        job.processed_bytes = 0
        job.processed_rows = 0
        job.created_rows = 0
        job.updated_rows = 0
        job.error_rows = 0
        job.rows_per_second = 0
        job.error_message = None
        job.total_chunks = 0
        job.queued_chunks = 0
        job.processing_chunks = 0
        job.completed_chunks = 0
        job.failed_chunks = 0
        job.split_processed_bytes = 0
        job.split_created_chunks = 0
        db.commit()
        active_attempt_token = job.attempt_token

        created_chunks = split_csv_into_chunks(db, job, now, active_attempt_token)

        job.total_chunks = created_chunks
        job.queued_chunks = created_chunks
        job.split_processed_bytes = job.total_bytes
        job.split_created_chunks = created_chunks
        job.status = JOB_STATUS_PROCESSING if created_chunks else JOB_STATUS_COMPLETED
        if not created_chunks:
            job.finished_at = utcnow()
            job.processed_bytes = job.total_bytes
            job.last_progress_at = job.finished_at
        db.commit()

        job = refresh_import_job_status(db, job.id)
        if job is not None and job.status == JOB_STATUS_SPLITTING:
            job.status = JOB_STATUS_PROCESSING if created_chunks else JOB_STATUS_COMPLETED
            if not created_chunks:
                job.finished_at = utcnow()
                job.processed_bytes = job.total_bytes
                job.last_progress_at = job.finished_at
            db.commit()
            job = refresh_import_job_status(db, job.id)
        if job is not None and job.status == JOB_STATUS_COMPLETED:
            cleanup_job_artifacts(db, job, delete_source=True)
    except Exception as exc:
        db.rollback()
        failed_job = db.query(ImportJob).filter(ImportJob.id == job_id).first()
        if failed_job is not None:
            now = utcnow()
            failed_job.status = JOB_STATUS_FAILED
            failed_job.finished_at = now
            failed_job.last_progress_at = now
            failed_job.error_message = str(exc)
            db.commit()
        raise
    finally:
        db.close()


def update_chunk_progress(
    db,
    chunk,
    attempt_token,
    processed_rows,
    created_rows,
    updated_rows,
    error_rows,
    started,
):
    chunk = ensure_chunk_attempt_active(db, chunk.id, attempt_token)
    elapsed = max(perf_counter() - started, 0.001)
    chunk.processed_rows = min(processed_rows, chunk.total_rows)
    chunk.created_rows = created_rows
    chunk.updated_rows = updated_rows
    chunk.error_rows = error_rows
    chunk.rows_per_second = round(processed_rows / elapsed, 2)
    chunk.last_progress_at = utcnow()
    db.commit()


def process_import_job_chunk(chunk_id):
    db = SessionLocal()
    try:
        chunk = db.query(ImportJobChunk).filter(ImportJobChunk.id == chunk_id).first()
        if chunk is None:
            return
        if chunk.status != CHUNK_STATUS_QUEUED:
            return

        parent_job = db.query(ImportJob).filter(ImportJob.id == chunk.job_id).first()
        if parent_job is None:
            return
        attempt_token = parent_job.attempt_token

        now = utcnow()
        chunk.status = CHUNK_STATUS_PROCESSING
        chunk.started_at = now
        chunk.finished_at = None
        chunk.last_progress_at = now
        chunk.error_message = None
        db.commit()
        refresh_import_job_status(db, chunk.job_id)

        processed_rows = 0
        created_rows = 0
        updated_rows = 0
        error_rows = 0
        chunk_rows = []
        started = perf_counter()

        with open(chunk.stored_path, "rb") as raw_file:
            text_wrapper = io.TextIOWrapper(raw_file, encoding="utf-8-sig", newline="")
            reader = csv.DictReader(text_wrapper)
            import_format = validate_headers(sanitize_headers(reader.fieldnames or []))

            for index, row in enumerate(reader, start=2):
                processed_rows += 1
                try:
                    normalized = normalize_row(import_format, sanitize_row(row))
                except ValueError as exc:
                    error_rows += 1
                    if error_rows <= 100:
                        chunk.error_message = "Last row error at line {}: {}.".format(index, exc)
                        db.commit()
                    update_chunk_progress(
                        db,
                        chunk,
                        attempt_token,
                        processed_rows,
                        created_rows,
                        updated_rows,
                        error_rows,
                        started,
                    )
                    refresh_import_job_status(db, chunk.job_id)
                    continue

                chunk_rows.append(normalized)

                if len(chunk_rows) >= settings.chunk_size:
                    ensure_chunk_attempt_active(db, chunk_id, attempt_token)
                    created, updated = upsert_chunk(db, import_format, chunk_rows)
                    created_rows += created
                    updated_rows += updated
                    chunk_rows = []
                    chunk = db.query(ImportJobChunk).filter(ImportJobChunk.id == chunk_id).first()
                    update_chunk_progress(
                        db,
                        chunk,
                        attempt_token,
                        processed_rows,
                        created_rows,
                        updated_rows,
                        error_rows,
                        started,
                    )
                    refresh_import_job_status(db, chunk.job_id)

            if chunk_rows:
                ensure_chunk_attempt_active(db, chunk_id, attempt_token)
                created, updated = upsert_chunk(db, import_format, chunk_rows)
                created_rows += created
                updated_rows += updated
                chunk = db.query(ImportJobChunk).filter(ImportJobChunk.id == chunk_id).first()
                update_chunk_progress(
                    db,
                    chunk,
                    attempt_token,
                    processed_rows,
                    created_rows,
                    updated_rows,
                    error_rows,
                    started,
                )

        chunk = ensure_chunk_attempt_active(db, chunk_id, attempt_token)
        chunk.status = CHUNK_STATUS_COMPLETED
        now = utcnow()
        chunk.finished_at = now
        chunk.last_progress_at = now
        chunk.processed_rows = processed_rows
        chunk.created_rows = created_rows
        chunk.updated_rows = updated_rows
        chunk.error_rows = error_rows
        elapsed = max(perf_counter() - started, 0.001)
        chunk.rows_per_second = round(processed_rows / elapsed, 2)
        db.commit()
        job = refresh_import_job_status(db, chunk.job_id)
        if job is not None and job.status == JOB_STATUS_COMPLETED:
            cleanup_job_artifacts(db, job, delete_source=True)
    except Exception as exc:
        db.rollback()
        failed_chunk = db.query(ImportJobChunk).filter(ImportJobChunk.id == chunk_id).first()
        if failed_chunk is not None:
            now = utcnow()
            failed_chunk.status = CHUNK_STATUS_FAILED
            failed_chunk.finished_at = now
            failed_chunk.last_progress_at = now
            failed_chunk.error_message = str(exc)
            db.commit()
            refresh_import_job_status(db, failed_chunk.job_id)
        raise
    finally:
        db.close()


def retry_failed_chunks(job_id):
    db = SessionLocal()
    try:
        failed_chunks = (
            db.query(ImportJobChunk)
            .filter(
                ImportJobChunk.job_id == job_id,
                ImportJobChunk.status == CHUNK_STATUS_FAILED,
            )
            .order_by(ImportJobChunk.chunk_index.asc())
            .all()
        )
        if not failed_chunks:
            return 0

        now = utcnow()
        for chunk in failed_chunks:
            chunk.status = CHUNK_STATUS_QUEUED
            chunk.processed_rows = 0
            chunk.created_rows = 0
            chunk.updated_rows = 0
            chunk.error_rows = 0
            chunk.rows_per_second = 0
            chunk.error_message = None
            chunk.started_at = None
            chunk.finished_at = None
            chunk.last_progress_at = now
        db.commit()

        job = db.query(ImportJob).filter(ImportJob.id == job_id).first()
        if job is not None:
            job.status = JOB_STATUS_PROCESSING
            job.finished_at = None
            job.last_progress_at = now
            job.error_message = None
            db.commit()

        retried_chunks = 0
        for chunk in failed_chunks:
            try:
                enqueue_import_chunk(chunk.id)
                retried_chunks += 1
            except Exception as exc:
                chunk.status = CHUNK_STATUS_FAILED
                chunk.finished_at = utcnow()
                chunk.last_progress_at = chunk.finished_at
                chunk.error_message = "Could not enqueue chunk: {}".format(exc)
                db.commit()

        refresh_import_job_status(db, job_id)
        return retried_chunks
    finally:
        db.close()
