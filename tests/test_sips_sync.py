import hashlib
import io
import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from copy import copy
from typing import Any
from unittest.mock import Mock, patch
from zipfile import ZipFile

import requests
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.constants import CONSUMPTION_CSV_HEADERS, PS_CSV_HEADERS
from app.database import Base
from app.settings import settings
from app.models import ImportJob, SipsFile
from app.services.sips_client import SipsClient, SipsError, parse_remote_file
from app.services.sips_sync import prepare_jobs, source_key, sync_locked, validate_config


def config(directory):
    cfg = copy(settings)
    cfg.sips_api_url = "https://api.cnmc.gob.es"
    cfg.sips_consumer_key = "key"
    cfg.sips_consumer_secret = "secret"
    cfg.sips_nif_empresa = "A12345678"
    cfg.sips_procedure_id = "42"
    cfg.sips_file_types = ()
    cfg.sips_poll_seconds = 3600
    cfg.sips_max_download_bytes = 100000
    cfg.sips_max_unpacked_bytes = 100000
    cfg.upload_dir = Path(directory)
    return cfg


def metadata(**overrides):
    item = dict(uuid="file-1", nombre="2026-10-01_electricidad_ps.zip", numeroBytes="3",
                hash=hashlib.md5(b"abc").hexdigest(), fechaDisponibilidad="2026-10-01T00:00:00Z",
                uriDescarga="https://api.cnmc.gob.es/ficheros/v1/descarga/secret-url",
                idProcedimiento="42", nifEmpresa="A12345678", tipoFichero="SIPS-PS")
    return dict(item, **overrides)


def response(status=200, payload=None, body=b"abc"):
    result = Mock()
    result.status_code = status
    result.json.return_value = payload
    result.iter_content.return_value = [body]
    result.__enter__ = Mock(return_value=result)
    result.__exit__ = Mock(return_value=False)
    return result


class SipsClientTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.cfg = config(self.temp.name)
        self.client: Any = SipsClient(self.cfg)
        self.addCleanup(self.client.close)
        self.client.http = Mock()

    def test_metadata_accepts_both_documented_uri_spellings(self):
        item = metadata()
        item["uriDescargas"] = item.pop("uriDescarga")
        self.assertEqual(parse_remote_file(item).available_at, datetime(2026, 10, 1))
        for changes in ({"hash": "wrong"}, {"numeroBytes": -1}, {"fechaDisponibilidad": "bad"}):
            with self.assertRaises(SipsError):
                parse_remote_file(metadata(**changes))

    def test_oauth2_refresh_query_both_states_and_deduplicate(self):
        self.client.http.request.side_effect = [
            response(payload={"access_token": "first", "expires_in": 299}), response(401),
            response(payload={"access_token": "second", "expires_in": 299}),
            response(payload=[metadata()]), response(payload=[metadata()]),
        ]
        self.assertEqual(len(self.client.list_files()), 1)
        calls = self.client.http.request.call_args_list
        self.assertEqual(calls[0].kwargs["auth"], ("key", "secret"))
        self.assertEqual(calls[0].kwargs["data"], {"grant_type": "client_credentials", "scope": "read"})
        self.assertNotIn("secret", calls[0].kwargs["data"])
        self.assertEqual(calls[-1].kwargs["params"]["estado"], "DESCARGADO")
        self.assertEqual(calls[-1].kwargs["headers"]["Authorization"], "Bearer second")
        self.assertTrue(all(not call.kwargs["allow_redirects"] for call in calls))

    def test_filters_types_and_rejects_wrong_company(self):
        self.cfg.sips_file_types = ("SIPS-CONSUMPTION",)
        with patch.object(self.client, "consult", return_value=[metadata()]):
            self.assertEqual(self.client.list_files(), [])
        with patch.object(self.client, "consult", return_value=[metadata(nifEmpresa="other")]):
            with self.assertRaises(SipsError):
                self.client.list_files()

    def test_download_atomic_verified_and_anonymous(self):
        self.client.http.request.return_value = response()
        path = Path(self.temp.name) / "file.zip"
        self.client.download(parse_remote_file(metadata()), path)
        self.assertEqual(path.read_bytes(), b"abc")
        kwargs = self.client.http.request.call_args.kwargs
        self.assertNotIn("Authorization", kwargs["headers"])
        self.assertNotIn("auth", kwargs)
        self.assertFalse(path.with_suffix(".zip.part").exists())

    def test_corrupt_truncated_oversize_redirect_and_interrupted_download(self):
        for reply in (response(body=b"abd"), response(body=b"ab"), response(body=b"abcd"), response(302)):
            with self.subTest(reply=reply):
                self.client.http.request.return_value = reply
                path = Path(self.temp.name) / "file.zip"
                with self.assertRaises(SipsError):
                    self.client.download(parse_remote_file(metadata()), path)
                self.assertFalse(path.exists())
                self.assertFalse(path.with_suffix(".zip.part").exists())
        reply = response()
        reply.iter_content.side_effect = requests.ConnectionError("secret-url")
        self.client.http.request.return_value = reply
        with self.assertRaisesRegex(SipsError, "interrupted") as caught:
            self.client.download(parse_remote_file(metadata()), Path(self.temp.name) / "file.zip")
        self.assertNotIn("secret-url", str(caught.exception))

    def test_rejects_cross_origin_and_insecure_urls_before_request(self):
        for url in ("http://api.cnmc.gob.es/a", "https://evil.example/a", "https://user@api.cnmc.gob.es/a"):
            with self.assertRaises(SipsError):
                self.client.download(parse_remote_file(metadata(uriDescarga=url)), Path(self.temp.name) / "f")
        self.client.http.request.assert_not_called()
        self.cfg.sips_api_url = "http://localhost"
        with self.assertRaises(SipsError):
            SipsClient(self.cfg)

    def test_auth_errors_do_not_expose_secrets(self):
        self.client.http.request.return_value = response(403, {"secret": "sensitive"})
        with self.assertRaisesRegex(SipsError, "HTTP 403") as caught:
            self.client.authenticate()
        self.assertNotIn("sensitive", str(caught.exception))
        self.cfg.sips_consumer_key = ""
        with self.assertRaisesRegex(SipsError, "SIPS_CONSUMER_KEY"):
            validate_config(self.cfg)


class SipsInboxTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.cfg = config(self.temp.name)
        engine = create_engine("sqlite://")
        self.addCleanup(engine.dispose)
        Base.metadata.create_all(engine, tables=[SipsFile.__table__, ImportJob.__table__])
        self.db: Any = sessionmaker(bind=engine)()  # Legacy Column-based ORM is dynamically typed.
        self.addCleanup(self.db.close)
        self.client = Mock()
        self.client.list_files.return_value = [parse_remote_file(metadata())]
        self.dispatch = patch("app.services.sips_sync.dispatch_jobs")
        self.enqueue = self.dispatch.start()
        self.addCleanup(self.dispatch.stop)
        self.client.download.side_effect = self.download

    @staticmethod
    def download(remote, path):
        with ZipFile(path, "w") as archive:
            archive.writestr("../../ps.csv", ",".join(PS_CSV_HEADERS) + "\n")
            archive.writestr("consumption.csv", ",".join(CONSUMPTION_CSV_HEADERS) + "\n")
            archive.writestr("readme.txt", "not imported")

    def test_multimember_import_dedup_and_completion_survive_restarts(self):
        self.assertEqual(sync_locked(self.db, self.client, self.cfg), "importing")
        jobs = self.db.query(ImportJob).all()
        self.assertEqual(len(jobs), 2)
        for job in jobs:
            self.assertTrue(Path(job.stored_path).is_relative_to(self.cfg.upload_dir / "sips"))
        self.assertEqual(sync_locked(self.db, self.client, self.cfg), "importing")
        self.assertEqual(self.db.query(ImportJob).count(), 2)
        self.client.download.assert_called_once()
        for job in jobs:
            job.status = "completed"
        self.db.commit()
        self.assertEqual(sync_locked(self.db, self.client, self.cfg), "idle")
        receipt = self.db.query(SipsFile).one()
        self.assertEqual(receipt.status, "completed")
        self.assertEqual(json.loads(receipt.ignored_members), ["readme.txt"])
        self.db.close()
        self.assertEqual(sync_locked(self.db, self.client, self.cfg), "idle")
        self.assertEqual(self.db.query(ImportJob).count(), 2)
        self.client.download.assert_called_once()

    def test_download_error_retries_even_if_remote_marked_downloaded(self):
        self.client.download.side_effect = SipsError("CNMC download interrupted")
        self.assertEqual(sync_locked(self.db, self.client, self.cfg), "failed")
        self.assertEqual(self.db.query(ImportJob).count(), 0)
        self.client.download.side_effect = self.download
        self.assertEqual(sync_locked(self.db, self.client, self.cfg), "importing")
        self.assertEqual(self.db.query(SipsFile).count(), 1)

    def test_enqueue_failure_recovers_without_duplicate_jobs_or_download(self):
        self.enqueue.side_effect = RuntimeError("redis://secret")
        self.assertEqual(sync_locked(self.db, self.client, self.cfg), "failed")
        self.assertNotIn("secret", self.db.query(SipsFile).one().error_message)
        self.enqueue.side_effect = None
        self.assertEqual(sync_locked(self.db, self.client, self.cfg), "importing")
        self.assertEqual(self.db.query(ImportJob).count(), 2)
        self.client.download.assert_called_once()

    def test_failed_import_blocks_newer_snapshot_until_retried(self):
        later = parse_remote_file(metadata(uuid="new", fechaDisponibilidad="2026-11-01T00:00:00Z"))
        self.client.list_files.return_value.append(later)
        sync_locked(self.db, self.client, self.cfg)
        jobs = self.db.query(ImportJob).all()
        jobs[0].status = "failed"
        self.db.commit()
        self.assertEqual(sync_locked(self.db, self.client, self.cfg), "failed")
        self.client.download.assert_called_once()
        for job in jobs:
            job.status = "completed"
        self.db.commit()
        self.assertEqual(sync_locked(self.db, self.client, self.cfg), "importing")
        self.assertEqual(self.client.download.call_count, 2)

    def test_partial_chunk_failure_is_visible(self):
        sync_locked(self.db, self.client, self.cfg)
        job = self.db.query(ImportJob).first()
        job.status = "partial_failed"
        self.db.commit()
        self.assertEqual(sync_locked(self.db, self.client, self.cfg), "failed")

    def test_late_older_publication_cannot_overwrite_newer_data(self):
        sync_locked(self.db, self.client, self.cfg)
        for job in self.db.query(ImportJob).all():
            job.status = "completed"
        self.db.commit()
        sync_locked(self.db, self.client, self.cfg)
        self.client.list_files.return_value.append(parse_remote_file(metadata(
            uuid="late", fechaDisponibilidad="2025-01-01T00:00:00Z",
        )))
        self.assertEqual(sync_locked(self.db, self.client, self.cfg), "failed")
        self.client.download.assert_called_once()
        self.assertIn("older", self.db.query(SipsFile).filter_by(remote_id="late").one().error_message)

    def test_late_publication_does_not_overlap_active_workers(self):
        sync_locked(self.db, self.client, self.cfg)
        self.client.list_files.return_value.append(parse_remote_file(metadata(
            uuid="late-active", fechaDisponibilidad="2025-01-01T00:00:00Z",
        )))
        self.assertEqual(sync_locked(self.db, self.client, self.cfg), "importing")
        self.client.download.assert_called_once()
        for job in self.db.query(ImportJob).all():
            job.status = "completed"
        self.db.commit()
        self.assertEqual(sync_locked(self.db, self.client, self.cfg), "failed")
        self.client.download.assert_called_once()

    def test_rejected_rows_are_not_success(self):
        sync_locked(self.db, self.client, self.cfg)
        for job in self.db.query(ImportJob).all():
            job.status = "completed"
            job.error_rows = 1
        self.db.commit()
        self.assertEqual(sync_locked(self.db, self.client, self.cfg), "failed")

    def test_zip_limit_duplicate_names_and_unsupported_headers(self):
        for kind in ("large", "duplicate", "unsupported"):
            with self.subTest(kind=kind):
                remote = parse_remote_file(metadata(uuid=kind))
                receipt = SipsFile(source=source_key(self.cfg), remote_id=kind, filename="f.zip",
                                   md5=remote.md5, total_bytes=3, available_at=remote.available_at)
                self.db.add(receipt)
                self.db.commit()
                path = self.cfg.upload_dir / f"{kind}.zip"
                with ZipFile(path, "w") as archive:
                    archive.writestr("x.csv", "wrong\n")
                    if kind == "duplicate":
                        archive.writestr("x.csv", "wrong\n")
                self.cfg.sips_max_unpacked_bytes = 1 if kind == "large" else 100000
                with self.assertRaises(SipsError):
                    prepare_jobs(self.db, receipt, path, self.cfg)
        self.assertEqual(self.db.query(ImportJob).count(), 0)

    def test_cnmc_header_aliases(self):
        from app.services.sips_sync import prepare_csv, HEADER_ALIASES
        aliases = {value: key for key, value in HEADER_ALIASES.items()}
        raw = io.BytesIO((",".join(aliases.get(h, h) for h in PS_CSV_HEADERS) + "\n").encode())
        path = self.cfg.upload_dir / "ps.csv"
        self.assertTrue(prepare_csv(raw, path, 100000))
        self.assertEqual(path.read_text().strip().split(","), PS_CSV_HEADERS)


class SipsSchedulerTests(unittest.TestCase):
    def test_polling_continues_after_failure_and_waits_between_cycles(self):
        import sips_sync
        stop = Mock()
        stop.is_set.side_effect = [False, False, True]
        with patch("sys.argv", ["sips_sync.py"]), patch.object(sips_sync, "init_db"), \
                patch.object(sips_sync, "validate_config"), patch.object(sips_sync, "Event", return_value=stop), \
                patch.object(sips_sync.signal, "signal"), patch.object(sips_sync.os, "umask"), \
                patch.object(sips_sync, "sync_once", side_effect=[SipsError("offline"), "idle"]) as sync:
            self.assertEqual(sips_sync.main(), 0)
            self.assertEqual(sync.call_count, 2)
            self.assertEqual(stop.wait.call_count, 2)
            stop.wait.assert_called_with(settings.sips_poll_seconds)

    def test_once_reports_failure_without_waiting(self):
        import sips_sync
        stop = Mock()
        stop.is_set.return_value = False
        with patch("sys.argv", ["sips_sync.py", "--once"]), patch.object(sips_sync, "init_db"), \
                patch.object(sips_sync, "validate_config"), patch.object(sips_sync, "Event", return_value=stop), \
                patch.object(sips_sync.signal, "signal"), patch.object(sips_sync.os, "umask"), \
                patch.object(sips_sync, "sync_once", return_value="failed"):
            self.assertEqual(sips_sync.main(), 1)
            stop.wait.assert_not_called()

    def test_manual_retry_is_not_dispatched_again(self):
        from app.services.sips_sync import dispatch_jobs
        with patch("app.services.sips_sync.get_queue") as queue:
            dispatch_jobs([Mock(status="queued", attempt_token="operator-retry")])
            queue.return_value.enqueue.assert_not_called()


if __name__ == "__main__":
    unittest.main()
