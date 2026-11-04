"""Durable SIPS inbox -> existing ImportJob/RQ pipeline."""
import csv
import io
import json
import logging
import os
import re
import shutil
from datetime import date, datetime
from pathlib import Path
from zipfile import ZipFile

from sqlalchemy import and_, or_, text

from app.database import SessionLocal, engine
from app.jobs import get_queue
from app.models import ImportJob, SipsFile
from app.services.importer import sanitize_headers, validate_headers
from app.services.sips_client import SipsClient, SipsError
from app.settings import settings

logger = logging.getLogger(__name__)
SYNC_LOCK_ID = 87342160
# CNMC 4.0 uses these spellings; keep legacy uploads and model names unchanged.
HEADER_ALIASES = {
    "husoPS": "HusoPS", "bandaPS": "BandaPS", "paisPS": "PaisPS",
    "poblacionPS": "PoblacionPS", "paisTitular": "PaisTitular",
    "poblacionTitular": "PoblacionTitular",
}


def validate_config(config):
    for name in ("sips_consumer_key", "sips_consumer_secret", "sips_nif_empresa", "sips_procedure_id"):
        if not getattr(config, name):
            raise SipsError(f"Missing {name.upper()}")
    if config.sips_start_after_month and (
        not re.fullmatch(r"\d{4}-\d{2}", config.sips_start_after_month)
        or filename_month(config.sips_start_after_month) is None
    ):
        raise SipsError("SIPS_START_AFTER_MONTH must be YYYY-MM")
    if config.sips_poll_seconds < 10 or config.sips_max_download_bytes <= 0 or config.sips_max_unpacked_bytes <= 0:
        raise SipsError("Invalid SIPS polling interval or size limits")


def source_key(config):
    return json.dumps([config.sips_api_url, config.sips_procedure_id, config.sips_nif_empresa])


def filename_month(filename):
    """Read the data month, never the date CNMC made an old file available."""
    name = Path(filename.replace("\\", "/")).name
    match = re.match(
        r"^(?:SIPS_\d+_)?((?:19|20)\d{2})([-_]?)(\d{2})(?:\2(\d{2}))?(?=$|[_.-])",
        name,
    )
    if match is None:
        return None
    try:
        period = date(int(match[1]), int(match[3]), int(match[4] or 1))
    except ValueError:
        return None
    return period.strftime("%Y-%m")


def latest_imported_month(db, source, configured_month):
    # Manual imports predate the SIPS ledger. Only successfully loaded data sets
    # a watermark; uploaded_at/created_at and failed imports do not prove a month.
    filenames = [row[0] for row in db.query(ImportJob.filename).filter(
        ImportJob.sips_file_id.is_(None), ImportJob.status == "completed", ImportJob.error_rows == 0,
    ).all()]
    has_jobs = db.query(ImportJob.id).filter(ImportJob.sips_file_id == SipsFile.id).exists()
    unfinished = db.query(ImportJob.id).filter(
        ImportJob.sips_file_id == SipsFile.id,
        or_(ImportJob.status != "completed", ImportJob.error_rows > 0),
    ).exists()
    filenames.extend(row[0] for row in db.query(SipsFile.filename).filter(
        SipsFile.source == source,
        or_(SipsFile.status == "completed", and_(has_jobs, ~unfinished)),
    ).all())
    months = [month for name in filenames if (month := filename_month(name)) is not None]
    if configured_month:
        months.append(configured_month)
    if filenames and not months:
        raise SipsError("Cannot determine the existing data month; set SIPS_START_AFTER_MONTH=YYYY-MM")
    return max(months, default=None)


def select_new_months(db, source, remotes, config):
    after_month = latest_imported_month(db, source, config.sips_start_after_month)
    remote_months = {key: filename_month(item.filename) for key, item in remotes.items()}
    newest = max((month for month in remote_months.values() if month), default=None)
    # Bootstrap an empty installation with only the newest month, not its history.
    logger.info("SIPS selection: after=%s; newest available=%s", after_month or "empty (latest only)", newest)
    for remote in remotes.values():
        month = remote_months[remote.remote_id]
        receipt = db.query(SipsFile).filter_by(source=source, remote_id=remote.remote_id).first()
        if receipt is not None:
            if receipt.md5 != remote.md5 or receipt.total_bytes != remote.size:
                raise SipsError("CNMC changed immutable metadata for a known UUID")
            continue
        if month is None:
            logger.warning("SIPS: ignoring a remote file without a recognizable data month")
            continue
        if (after_month and month <= after_month) or (not after_month and month != newest):
            continue
        # Admit the whole set before dispatch: all files in the same new month
        # must finish even after its first file advances the successful watermark.
        db.add(SipsFile(source=source, remote_id=remote.remote_id, filename=remote.filename,
                        md5=remote.md5, total_bytes=remote.size, available_at=remote.available_at,
                        status="selected"))
    db.commit()
    return after_month, newest


def prepare_csv(raw, destination, max_bytes):
    """Normalize only documented header aliases; copy the body in bounded chunks."""
    with io.TextIOWrapper(raw, encoding="utf-8-sig", newline="") as source:
        headers = [HEADER_ALIASES.get(name, name) for name in sanitize_headers(next(csv.reader(source), []))]
        try:
            validate_headers(headers)
        except ValueError:
            return False
        with destination.open("w", encoding="utf-8", newline="") as output:
            os.chmod(destination, 0o600)
            csv.writer(output).writerow(headers)
            size = 0
            while block := source.read(1024 * 1024):
                size += len(block.encode("utf-8"))
                if size > max_bytes:
                    raise SipsError("SIPS CSV exceeds unpacked size limit")
                output.write(block)
            output.flush()
            os.fsync(output.fileno())
    return True


def prepare_jobs(db, receipt, download_path, config):
    directory = download_path.parent / f"members-{receipt.id}"
    # No jobs exist yet: this directory can only contain abandoned staging files.
    if directory.exists():
        shutil.rmtree(directory)
    directory.mkdir(mode=0o700)
    prepared = []
    ignored = []
    try:
        if download_path.suffix.lower() == ".zip":
            with ZipFile(download_path) as archive:
                members = [m for m in archive.infolist() if not m.is_dir()]
                if sum(m.file_size for m in members) > config.sips_max_unpacked_bytes:
                    raise SipsError("SIPS ZIP exceeds SIPS_MAX_UNPACKED_BYTES")
                names = [m.filename for m in members]
                if len(names) != len(set(names)):
                    raise SipsError("SIPS ZIP contains duplicate member names")
                for index, member in enumerate(members):
                    # Never extract using remote paths (including ../ or symlinks).
                    target = directory / f"{index}.csv"
                    if Path(member.filename).suffix.lower() != ".csv":
                        ignored.append(member.filename)
                        continue
                    with archive.open(member) as raw:
                        supported = prepare_csv(raw, target, config.sips_max_unpacked_bytes)
                    if supported:
                        prepared.append((member.filename, target))
                    else:
                        ignored.append(member.filename)
        else:
            target = directory / "0.csv"
            with download_path.open("rb") as raw:
                if prepare_csv(raw, target, config.sips_max_unpacked_bytes):
                    prepared.append((receipt.filename, target))
        if not prepared:
            raise SipsError("SIPS file has no supported CSV headers (PS, consumption, autoconsumo)")
        for member, path in prepared:
            size = path.stat().st_size
            db.add(ImportJob(
                filename=f"SIPS_{receipt.id}_{Path(member).name}", stored_path=str(path),
                status="queued", total_bytes=size, uploaded_bytes=size,
                sips_file_id=receipt.id, sips_member=member,
            ))
        receipt.status = "importing"
        receipt.error_message = None
        receipt.ignored_members = json.dumps(ignored, ensure_ascii=False)
        db.commit()
    except Exception:
        db.rollback()
        # Staging is safely rebuilt on the next attempt; keep verified download.
        raise
    if ignored:
        logger.warning("SIPS file %s: %s unsupported members ignored; see status", receipt.id, len(ignored))


def dispatch_jobs(jobs):
    queue = get_queue()
    for job in jobs:
        if job.status != "queued" or job.attempt_token:
            # Manual requeues have their own attempt token and RQ delivery.
            # Reconcile only initial submissions, not the operator's retries.
            continue
        rq_id = f"sips-import-{job.id}"
        existing = queue.fetch_job(rq_id)
        if existing and existing.get_status() in ("queued", "started", "deferred", "scheduled"):
            continue
        # Stable RQ ID plus single synchronizer lock closes the commit/enqueue
        # crash window. The importer also refuses jobs no longer queued.
        queue.enqueue("app.services.importer.process_import_job", job.id,
                      job_id=rq_id, job_timeout="24h")


def sync_locked(db, client, config):
    source = source_key(config)
    remotes = {item.remote_id: item for item in client.list_files()}
    after_month, newest = select_new_months(db, source, remotes, config)
    # Finish any already-dispatched snapshot first, even if an older publication
    # appeared since the last poll. Otherwise its workers could overlap ours.
    receipts = db.query(SipsFile).filter(
        SipsFile.source == source, SipsFile.status.notin_(("completed", "skipped")),
    ).all()
    # Month order takes priority over publication order. Recently republished old
    # data must never run after a newer data month; dispatched work stays first.
    active_ids = {row[0] for row in db.query(ImportJob.sips_file_id).filter(
        ImportJob.sips_file_id.in_([receipt.id for receipt in receipts]),
    ).distinct().all()}
    receipts.sort(key=lambda receipt: (receipt.id not in active_ids,
                                      filename_month(receipt.filename) or "", receipt.available_at, receipt.remote_id))
    directory = config.upload_dir / "sips"
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    for receipt in receipts:
        receipt_id = receipt.id
        download = directory / f"{receipt.id}{Path(receipt.filename).suffix.lower()}"
        try:
            jobs = db.query(ImportJob).filter_by(sips_file_id=receipt.id).order_by(ImportJob.id).all()
            if jobs and all(job.status == "completed" and job.error_rows == 0 for job in jobs):
                receipt.status = "completed"
                receipt.completed_at = datetime.utcnow()
                receipt.error_message = None
                download.unlink(missing_ok=True)
                shutil.rmtree(directory / f"members-{receipt.id}", ignore_errors=True)
                db.commit()
                month = filename_month(receipt.filename)
                if month and (after_month is None or month > after_month):
                    after_month = month
                continue
            if jobs:
                if any(job.status in ("failed", "partial_failed") or job.error_rows for job in jobs):
                    receipt.status = "failed"
                    receipt.error_message = "Import failed or has rejected rows; inspect/retry the linked import jobs"
                else:
                    dispatch_jobs(jobs)
                    receipt.status = "importing"
                    receipt.error_message = None
                db.commit()
                return receipt.status
            month = filename_month(receipt.filename)
            admitted = receipt.status in ("selected", "download_failed")
            # Also discard the historical backlog created by older releases, but
            # never cancel work already dispatched to a worker.
            stale = month is None or (
                after_month is not None and (month < after_month or (month == after_month and not admitted))
            ) or (after_month is None and not admitted and month != newest)
            if stale:
                receipt.status = "skipped"
                receipt.error_message = "Not a newer data month; no import dispatched"
                db.commit()
                continue
            if not download.exists():
                remote = remotes.get(receipt.remote_id)
                if remote is None:
                    raise SipsError("Pending SIPS file is no longer available from CNMC")
                client.download(remote, download)
            prepare_jobs(db, receipt, download, config)
            dispatch_jobs(db.query(ImportJob).filter_by(sips_file_id=receipt.id).all())
            return "importing"
        except Exception as exc:
            db.rollback()
            receipt = db.get(SipsFile, receipt_id)
            # Never store raw HTTP/DB exceptions: they may contain URLs or secrets.
            message = str(exc) if isinstance(exc, SipsError) else f"SIPS operation failed ({type(exc).__name__})"
            receipt.status = "failed" if db.query(ImportJob.id).filter_by(sips_file_id=receipt_id).first() else "download_failed"
            receipt.error_message = message
            db.commit()
            logger.error("SIPS file %s: %s", receipt_id, message)
            return "failed"
    return "idle"


def sync_once(config=settings):
    validate_config(config)
    client = SipsClient(config)
    try:
        # Dedicated session-level PG lock: no TTL expiring during large downloads.
        with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
            if not connection.execute(text("SELECT pg_try_advisory_lock(:id)"), {"id": SYNC_LOCK_ID}).scalar():
                return "locked"
            try:
                with SessionLocal() as db:
                    return sync_locked(db, client, config)
            finally:
                connection.execute(text("SELECT pg_advisory_unlock(:id)"), {"id": SYNC_LOCK_ID})
    finally:
        client.close()
