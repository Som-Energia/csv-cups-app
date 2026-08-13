import errno
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
from zipfile import ZIP_DEFLATED, ZipFile

from app.constants import CONSUMPTION_CSV_HEADERS
from app.main import serialize_job
from app.services.importer import inspect_import_source, process_import_job


class FakeJobDatabase:
    def __init__(self, job):
        self.job = job
        self.commits = 0
        self.rollbacks = 0

    def query(self, *args):
        return self

    def filter(self, *args):
        return self

    def first(self):
        return self.job

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    def close(self):
        pass


def make_import_job():
    now = datetime.utcnow()
    return SimpleNamespace(
        id=1,
        filename="consumptions.zip",
        stored_path="/tmp/consumptions.zip",
        attempt_token="",
        status="queued",
        total_bytes=100,
        uploaded_bytes=100,
        processed_bytes=0,
        processed_rows=0,
        created_rows=0,
        updated_rows=0,
        error_rows=0,
        rows_per_second=0,
        error_message=None,
        created_at=now,
        started_at=None,
        finished_at=None,
        last_progress_at=None,
        total_chunks=0,
        queued_chunks=0,
        processing_chunks=0,
        completed_chunks=0,
        failed_chunks=0,
        split_processed_bytes=0,
        split_total_bytes=0,
        split_created_chunks=0,
    )


class ImportRetryTests(unittest.TestCase):
    def test_stale_file_handle_restarts_split_twice_before_succeeding(self):
        job = make_import_job()
        database = FakeJobDatabase(job)
        attempt_number = 0

        def start_attempt(db, current_job):
            nonlocal attempt_number
            attempt_number += 1
            current_job.status = "splitting"
            current_job.attempt_token = f"attempt-{attempt_number}"
            return datetime.utcnow(), current_job.attempt_token

        stale_error = OSError(errno.ESTALE, "Stale file handle")
        with (
            patch("app.services.importer.SessionLocal", return_value=database),
            patch("app.services.importer.start_split_attempt", side_effect=start_attempt),
            patch(
                "app.services.importer.split_csv_into_chunks",
                side_effect=[stale_error, stale_error, 1],
            ) as split,
            patch("app.services.importer.prepare_stale_handle_retry") as prepare_retry,
            patch("app.services.importer.sleep") as retry_sleep,
            patch("app.services.importer.refresh_import_job_status", return_value=job),
        ):
            process_import_job(job.id)

        self.assertEqual(split.call_count, 3)
        self.assertEqual([call.args[-1] for call in prepare_retry.call_args_list], [5, 30])
        self.assertEqual([call.args[0] for call in retry_sleep.call_args_list], [5, 30])
        self.assertEqual(job.status, "processing")

    def test_non_stale_os_error_is_not_retried(self):
        job = make_import_job()
        database = FakeJobDatabase(job)

        def start_attempt(db, current_job):
            current_job.status = "splitting"
            current_job.attempt_token = "attempt-1"
            return datetime.utcnow(), current_job.attempt_token

        with (
            patch("app.services.importer.SessionLocal", return_value=database),
            patch("app.services.importer.start_split_attempt", side_effect=start_attempt),
            patch(
                "app.services.importer.split_csv_into_chunks",
                side_effect=OSError(errno.ENOSPC, "No space left on device"),
            ) as split,
            patch("app.services.importer.prepare_stale_handle_retry") as prepare_retry,
        ):
            with self.assertRaises(OSError):
                process_import_job(job.id)

        self.assertEqual(split.call_count, 1)
        prepare_retry.assert_not_called()
        self.assertEqual(job.status, "failed")


class ImportProgressTests(unittest.TestCase):
    def test_zip_split_total_uses_uncompressed_csv_size(self):
        csv_content = ",".join(CONSUMPTION_CSV_HEADERS) + "\n" + ("x" * 10000)
        with tempfile.TemporaryDirectory() as directory:
            archive_path = Path(directory) / "consumptions.zip"
            with ZipFile(archive_path, "w", compression=ZIP_DEFLATED) as archive:
                archive.writestr("consumptions.csv", csv_content)

            source = inspect_import_source(archive_path)
            compressed_size = archive_path.stat().st_size

        self.assertEqual(source["split_total_bytes"], len(csv_content.encode("utf-8")))
        self.assertGreater(source["split_total_bytes"], compressed_size)

    def test_serialized_split_percent_uses_split_source_size(self):
        job = make_import_job()
        job.split_processed_bytes = 250
        job.split_total_bytes = 1000

        payload = serialize_job(job)

        self.assertEqual(payload.split_progress_percent, 25.0)


if __name__ == "__main__":
    unittest.main()
