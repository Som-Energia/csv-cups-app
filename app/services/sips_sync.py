"""Durable SIPS inbox -> existing ImportJob/RQ pipeline."""
import csv
import io
import json
import logging
import os
import shutil
from datetime import datetime
from pathlib import Path
from zipfile import ZipFile

from sqlalchemy import case, text

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
    if config.sips_poll_seconds < 10 or config.sips_max_download_bytes <= 0 or config.sips_max_unpacked_bytes <= 0:
        raise SipsError("Invalid SIPS polling interval or size limits")


def source_key(config):
    return json.dumps([config.sips_api_url, config.sips_procedure_id, config.sips_nif_empresa])


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
    for remote in remotes.values():
        receipt = db.query(SipsFile).filter_by(source=source, remote_id=remote.remote_id).first()
        if receipt is None:
            db.add(SipsFile(source=source, remote_id=remote.remote_id, filename=remote.filename,
                            md5=remote.md5, total_bytes=remote.size, available_at=remote.available_at))
        elif receipt.md5 != remote.md5 or receipt.total_bytes != remote.size:
            raise SipsError("CNMC changed immutable metadata for a known UUID")
    db.commit()
    # Finish any already-dispatched snapshot first, even if an older publication
    # appeared since the last poll. Otherwise its workers could overlap ours.
    has_jobs = db.query(ImportJob.id).filter(ImportJob.sips_file_id == SipsFile.id).exists()
    receipts = db.query(SipsFile).filter(
        SipsFile.source == source, SipsFile.status != "completed",
    ).order_by(case((has_jobs, 0), else_=1), SipsFile.available_at, SipsFile.remote_id).all()
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
            newer_completed = db.query(SipsFile).filter(
                SipsFile.source == source, SipsFile.status == "completed",
                SipsFile.available_at > receipt.available_at,
            ).first()
            if newer_completed is not None:
                raise SipsError("Late older SIPS snapshot: refusing to overwrite newer imported data; review required")
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
            receipt.status = "failed"
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
