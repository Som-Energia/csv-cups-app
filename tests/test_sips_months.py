"""Month selection regressions: never bootstrap historical SIPS downloads."""
import tempfile
import unittest
from typing import Any
from unittest.mock import Mock, patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import ImportJob, SipsFile
from app.services.sips_client import SipsError, parse_remote_file
from app.services.sips_sync import filename_month, source_key, sync_locked, validate_config
from tests import test_sips_sync
from tests.test_sips_sync import config, metadata


class SipsMonthTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.cfg = config(self.temp.name)
        engine = create_engine("sqlite://")
        self.addCleanup(engine.dispose)
        Base.metadata.create_all(engine, tables=[SipsFile.__table__, ImportJob.__table__])
        self.db: Any = sessionmaker(bind=engine)()
        self.addCleanup(self.db.close)
        self.client = Mock()
        self.client.list_files.return_value = [parse_remote_file(metadata())]
        self.client.download.side_effect = test_sips_sync.SipsInboxTests.download
        dispatch = patch("app.services.sips_sync.dispatch_jobs")
        dispatch.start()
        self.addCleanup(dispatch.stop)

    def seed_manual(self, filename, status="completed", errors=0):
        self.db.add(ImportJob(filename=filename, stored_path="/not-needed.csv", status=status, error_rows=errors))
        self.db.commit()

    def finish_jobs(self):
        for job in self.db.query(ImportJob).filter(ImportJob.sips_file_id.isnot(None)).all():
            job.status = "completed"
        self.db.commit()

    def sync(self):
        return sync_locked(self.db, self.client, self.cfg)

    def test_supported_month_and_date_prefixes(self):
        for name in ("202610_PS.zip", "2026-10-01_PS.csv", "20261001_PS.csv", "2026_10_01_PS.zip", "2026-10_PS.zip"):
            self.assertEqual(filename_month(name), "2026-10", name)
        for name in ("202613_PS.zip", "2026-02-30_PS.zip", "opaque.zip", "20261099_PS.csv"):
            self.assertIsNone(filename_month(name), name)

    def test_bad_configured_month_is_rejected(self):
        for value in ("2026-13", "202610", "2026-10-01"):
            self.cfg.sips_start_after_month = value
            with self.assertRaisesRegex(SipsError, "YYYY-MM"):
                validate_config(self.cfg)

    def test_manual_month_excludes_older_and_same_month_even_if_republished(self):
        self.seed_manual("202609_SIPS2_PS_ELECTRICIDAD_peninsular.csv")
        self.client.list_files.return_value.extend([
            parse_remote_file(metadata(uuid="old", nombre="202608_PS.zip", fechaDisponibilidad="2026-12-01T00:00:00Z")),
            parse_remote_file(metadata(uuid="same", nombre="202609_CONSUMOS.zip")),
        ])
        self.assertEqual(self.sync(), "importing")
        self.assertEqual(self.client.download.call_args.args[0].remote_id, "file-1")
        self.assertEqual(self.db.query(SipsFile).count(), 1)

    def test_empty_database_only_bootstraps_latest_month(self):
        self.client.list_files.return_value.append(parse_remote_file(metadata(uuid="old", nombre="202601_PS.zip")))
        self.sync()
        self.assertEqual(self.db.query(SipsFile).count(), 1)
        self.assertEqual(self.client.download.call_args.args[0].remote_id, "file-1")

    def test_selected_files_in_same_new_month_all_finish_across_polls(self):
        self.seed_manual("202609_PS.csv")
        self.client.list_files.return_value.append(parse_remote_file(metadata(uuid="other-part", nombre="202610_CONSUMOS.zip")))
        self.sync()
        self.assertEqual(self.db.query(SipsFile).count(), 2)
        self.finish_jobs()
        self.assertEqual(self.sync(), "importing")
        self.finish_jobs()
        self.assertEqual(self.sync(), "idle")
        self.assertEqual(self.client.download.call_count, 2)

    def test_month_order_not_publication_order(self):
        self.seed_manual("202608_PS.csv")
        self.client.list_files.return_value.append(parse_remote_file(metadata(
            uuid="september", nombre="202609_PS.zip", fechaDisponibilidad="2026-12-01T00:00:00Z",
        )))
        self.sync()
        self.assertEqual(self.client.download.call_args.args[0].remote_id, "september")
        self.finish_jobs()
        self.assertEqual(self.sync(), "importing")
        self.assertEqual(self.client.download.call_args.args[0].remote_id, "file-1")

    def test_failed_manual_import_does_not_advance_watermark(self):
        self.seed_manual("202609_PS.csv")
        self.seed_manual("202612_PS.csv", "failed")
        self.seed_manual("202611_PS.csv", errors=1)
        self.assertEqual(self.sync(), "importing")
        self.client.download.assert_called_once()

    def test_unknown_existing_month_requires_explicit_lower_bound(self):
        self.seed_manual("renamed.csv")
        with self.assertRaisesRegex(SipsError, "SIPS_START_AFTER_MONTH"):
            self.sync()
        self.client.download.assert_not_called()
        self.cfg.sips_start_after_month = "2026-10"
        self.assertEqual(self.sync(), "idle")
        self.client.download.assert_not_called()

    def test_configured_lower_bound_never_lowers_known_month(self):
        self.seed_manual("202611_PS.csv")
        self.cfg.sips_start_after_month = "2026-01"
        self.assertEqual(self.sync(), "idle")
        self.client.download.assert_not_called()

    def test_unknown_remote_month_is_not_inferred_from_availability(self):
        self.client.list_files.return_value = [parse_remote_file(metadata(nombre="opaque.zip"))]
        self.assertEqual(self.sync(), "idle")
        self.client.download.assert_not_called()

    def test_legacy_historical_backlog_is_skipped_without_downloading(self):
        self.seed_manual("202609_PS.csv")
        old = parse_remote_file(metadata(uuid="legacy", nombre="202601_PS.zip"))
        self.db.add(SipsFile(source=source_key(self.cfg), remote_id=old.remote_id, filename=old.filename,
                            md5=old.md5, total_bytes=old.size, available_at=old.available_at, status="pending"))
        self.db.commit()
        self.assertEqual(self.sync(), "importing")
        self.assertEqual(self.db.query(SipsFile).filter_by(remote_id="legacy").one().status, "skipped")
        self.assertEqual(self.client.download.call_args.args[0].remote_id, "file-1")

    def test_download_retry_in_same_selected_month_is_preserved(self):
        self.seed_manual("202609_PS.csv")
        self.client.list_files.return_value.append(parse_remote_file(metadata(uuid="second", nombre="202610_PS_part2.zip")))
        self.sync()
        self.finish_jobs()
        self.client.download.side_effect = SipsError("offline")
        self.assertEqual(self.sync(), "failed")
        self.assertEqual(self.db.query(SipsFile).filter_by(remote_id="second").one().status, "download_failed")
        self.client.download.side_effect = test_sips_sync.SipsInboxTests.download
        self.assertEqual(self.sync(), "importing")

    def test_successful_worker_sets_watermark_before_ledger_reconciliation(self):
        self.sync()
        self.finish_jobs()
        self.client.list_files.return_value.append(parse_remote_file(metadata(uuid="same-month-new-uuid")))
        self.assertEqual(self.sync(), "idle")
        self.assertEqual(self.db.query(SipsFile).count(), 1)
        self.client.download.assert_called_once()


if __name__ == "__main__":
    unittest.main()
