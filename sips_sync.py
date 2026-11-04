"""Run the optional SIPS poller (or a single pass for cron)."""
import argparse
import json
import logging
import os
import signal
from threading import Event

from app.database import SessionLocal, init_db
from app.models import ImportJob, SipsFile
from app.services.sips_client import SipsError
from app.services.sips_sync import sync_once, validate_config
from app.settings import settings


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--once", action="store_true", help="One pass; exit nonzero on failure")
    parser.add_argument("--status", action="store_true", help="Show recent receipts and linked import job IDs")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    os.umask(0o077)
    init_db()
    if args.status:
        with SessionLocal() as db:
            rows = db.query(SipsFile).order_by(SipsFile.id.desc()).limit(100).all()
            print(json.dumps([{
                "id": row.id, "remote_id": row.remote_id, "filename": row.filename,
                "status": row.status, "error": row.error_message,
                "ignored_members": json.loads(row.ignored_members or "[]"),
                "job_ids": [job.id for job in db.query(ImportJob).filter_by(sips_file_id=row.id).all()],
            } for row in rows], ensure_ascii=False, indent=2))
        return 0
    try:
        validate_config(settings)
    except SipsError as exc:
        logging.error("%s", exc)
        return 1
    stop = Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    while not stop.is_set():
        try:
            result = sync_once()
            logging.info("SIPS sync: %s", result)
        except Exception as exc:
            message = str(exc) if isinstance(exc, SipsError) else type(exc).__name__
            logging.error("SIPS sync failed: %s", message)
            result = "failed"
        if args.once:
            return 1 if result == "failed" else 0
        stop.wait(settings.sips_poll_seconds)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
