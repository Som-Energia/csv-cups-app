"""Opt-in: real HTTPS fixture -> PostgreSQL ledger -> Redis/RQ worker -> HTTP API."""
import base64
import csv
import hashlib
import io
import json
import os
import ssl
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit
from unittest.mock import patch
from zipfile import ZipFile

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.constants import AUTOCONSUMO_CSV_HEADERS, CONSUMPTION_CSV_HEADERS, PS_CSV_HEADERS
from app.database import SessionLocal, engine, init_db
from app.jobs import get_queue, get_redis_connection
from app.main import app
from app.models import ImportJob, SipsFile
from app.services.sips_client import SipsClient
from app.services.sips_sync import SYNC_LOCK_ID, sync_once
from app.settings import settings
from tests.test_sips_sync import config


CUPS = "ES000000000000000001"


def csv_body(headers, row):
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=headers)
    writer.writeheader()
    writer.writerow(row)
    return output.getvalue()


class SipsPipelineIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if os.getenv("SIPS_INTEGRATION_TEST") != "1":
            raise unittest.SkipTest("Set SIPS_INTEGRATION_TEST=1 with an isolated sips_sync_test database and Redis /15")
        parsed = urlsplit(settings.database_url)
        redis = urlsplit(settings.redis_url)
        if parsed.hostname not in ("localhost", "127.0.0.1") or parsed.path != "/sips_sync_test":
            raise RuntimeError("Refusing integration tests outside local sips_sync_test database")
        if redis.hostname not in ("localhost", "127.0.0.1") or redis.path != "/15":
            raise RuntimeError("Refusing integration tests outside local Redis database /15")

    def setUp(self):
        with engine.begin() as connection:
            connection.execute(text("DROP SCHEMA public CASCADE"))
            connection.execute(text("CREATE SCHEMA public"))
        get_redis_connection().flushdb()
        init_db()
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.cfg = config(self.temp.name)
        self.cfg.sips_max_download_bytes = 1000000
        self.cfg.sips_max_unpacked_bytes = 1000000

    def test_full_pipeline_updates_only_new_files_with_real_worker(self):
        fixture = SimpleNamespace(cfg=self.cfg, downloads=[], tokens=0, revision=1, bad_download_auth=False)
        archive = io.BytesIO()
        with ZipFile(archive, "w") as zipfile:
            zipfile.writestr("ps.csv", csv_body(PS_CSV_HEADERS, {
                "cups": CUPS, "nombreEmpresaDistribuidora": "Original",
            }))
            zipfile.writestr("consumption.csv", csv_body(CONSUMPTION_CSV_HEADERS, {
                "cups": CUPS, "fechaInicioMesConsumo": "2026-01-01", "fechaFinMesConsumo": "2026-01-31",
                "consumoEnergiaActivaEnWhP1": "1234",
            }))
            zipfile.writestr("autoconsumo.csv", csv_body(AUTOCONSUMO_CSV_HEADERS, {
                "cups": CUPS, "cau": "CAU-TEST", "fechaInicioReparto": "2026-01-01",
                "horaCoeficienteVariableReparto": "01", "coeficienteReparto": "0.5",
            }))
        months = {"historical": "202501", "first": "202601", "second": "202602", "third": "202603"}
        bodies = {"historical": archive.getvalue(), "first": archive.getvalue(), "second": csv_body(PS_CSV_HEADERS, {
            "cups": CUPS, "nombreEmpresaDistribuidora": "Updated",
        }).encode(), "third": csv_body(PS_CSV_HEADERS, {"cups": "INVALID"}).encode()}

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, format, *args):
                pass

            def send(self, status, body):
                self.send_response(status)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_POST(self):
                route = urlsplit(self.path)
                if route.path == "/oauth2/token":
                    auth = base64.b64encode(b"key:secret").decode()
                    if self.headers.get("Authorization") != "Basic " + auth:
                        return self.send(401, b"")
                    data = self.rfile.read(int(self.headers["Content-Length"])).decode()
                    if parse_qs(data) != {"grant_type": ["client_credentials"], "scope": ["read"]}:
                        return self.send(400, b"")
                    fixture.tokens += 1
                    return self.send(200, json.dumps({"access_token": "token", "expires_in": 299}).encode())
                params = parse_qs(route.query)
                if route.path != "/api-oauth2/ficheros/consultar" or self.headers.get("Authorization") != "Bearer token":
                    return self.send(403, b"")
                if params.get("idProcedimiento") != ["42"] or params.get("nifEmpresa") != ["A12345678"]:
                    return self.send(400, b"")
                files = []
                for key in ("historical", *("first", "second", "third")[:fixture.revision]):
                    state = "DESCARGADO" if key in fixture.downloads else "DISPONIBLE"
                    if params.get("estado") != [state]:
                        continue
                    files.append({
                        "uuid": key, "nombre": months[key] + "_" + key + (".zip" if key in ("first", "historical") else ".csv"),
                        "numeroBytes": len(bodies[key]), "hash": hashlib.md5(bodies[key]).hexdigest(),
                        # An old data month republished recently is still history.
                        "fechaDisponibilidad": "2026-12-01T00:00:00Z" if key == "historical" else f"{months[key][:4]}-{months[key][4:]}-01T00:00:00Z",
                        "uriDescarga": fixture.cfg.sips_api_url + "/download/" + key,
                        "idProcedimiento": "42", "nifEmpresa": "A12345678", "tipoFichero": "SIPS",
                    })
                self.send(200, json.dumps(files).encode())

            def do_GET(self):
                key = self.path.rsplit("/", 1)[-1]
                if self.headers.get("Authorization"):
                    fixture.bad_download_auth = True
                fixture.downloads.append(key)
                self.send(200, bodies[key])

        cert, key = Path(self.temp.name) / "cert.pem", Path(self.temp.name) / "key.pem"
        subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "1",
                        "-subj", "/CN=localhost", "-addext", "subjectAltName=DNS:localhost",
                        "-keyout", str(key), "-out", str(cert)], check=True, capture_output=True)
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        tls = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        tls.load_cert_chain(cert, key)
        server.socket = tls.wrap_socket(server.socket, server_side=True)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        self.cfg.sips_api_url = f"https://localhost:{server.server_port}"

        def trusted_client(cfg):
            client = SipsClient(cfg)
            client.http.verify = str(cert)
            return client

        def worker():
            code = "from app.database import init_db; from app.jobs import QUEUE_NAME,get_redis_connection; from rq import Worker; init_db(); Worker([QUEUE_NAME],connection=get_redis_connection()).work(burst=True)"
            result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=60)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

        with patch("app.services.sips_sync.SipsClient", side_effect=trusted_client):
            self.assertEqual(sync_once(self.cfg), "importing")
            self.assertEqual(get_queue().count, 3)
            # Simulate scheduler restart before worker picks up: no duplicate RQ deliveries.
            self.assertEqual(sync_once(self.cfg), "importing")
            self.assertEqual(get_queue().count, 3)
            worker()
            self.assertEqual(sync_once(self.cfg), "idle")
            with SessionLocal() as db:
                self.assertEqual(db.query(SipsFile).one().status, "completed")
                self.assertTrue(all(j.status == "completed" for j in db.query(ImportJob).all()))
            with TestClient(app) as api:
                self.assertEqual(api.get("/health").status_code, 200)
                self.assertEqual(api.get(f"/api/records/{CUPS}").json()["nombreEmpresaDistribuidora"], "Original")
                self.assertEqual(len(api.get(f"/api/records/{CUPS}/consumptions").json()), 1)
                self.assertEqual(api.get(f"/records/{CUPS}").status_code, 200)
            fixture.revision = 2
            self.assertEqual(sync_once(self.cfg), "importing")
            worker()
            self.assertEqual(sync_once(self.cfg), "idle")
            self.assertEqual(sync_once(self.cfg), "idle")
            with TestClient(app) as api:
                self.assertEqual(api.get(f"/api/records/{CUPS}").json()["nombreEmpresaDistribuidora"], "Updated")
                self.assertEqual(len(api.get("/api/jobs").json()), 4)
            self.assertEqual(fixture.downloads, ["first", "second"])
            self.assertFalse(fixture.bad_download_auth)
            self.assertEqual(list((self.cfg.upload_dir / "sips").iterdir()), [])
            # Rejected rows must retain a retryable source, not become completed
            # and have their artifacts removed by the existing worker cleanup.
            fixture.revision = 3
            self.assertEqual(sync_once(self.cfg), "importing")
            worker()
            self.assertEqual(sync_once(self.cfg), "failed")
            with SessionLocal() as db:
                bad = db.query(ImportJob).order_by(ImportJob.id.desc()).first()
                assert bad is not None
                self.assertEqual(bad.status, "failed")
                self.assertEqual(bad.error_rows, 1)
                self.assertTrue(Path(str(bad.stored_path)).exists())
            with TestClient(app) as api:
                self.assertTrue(api.get(f"/api/jobs/{bad.id}").json()["can_requeue"])

    def test_concurrent_clean_startup_registers_models_and_serializes_schema(self):
        with engine.begin() as connection:
            connection.execute(text("DROP SCHEMA public CASCADE"))
            connection.execute(text("CREATE SCHEMA public"))
        processes = [subprocess.Popen(
            [sys.executable, "-c", "from app.database import init_db; init_db()"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        ) for _ in range(3)]
        for process in processes:
            stdout, stderr = process.communicate(timeout=30)
            self.assertEqual(process.returncode, 0, stdout + stderr)
        with SessionLocal() as db:
            self.assertEqual(db.query(ImportJob).count(), 0)
            self.assertEqual(db.query(SipsFile).count(), 0)
        with engine.connect() as connection:
            self.assertEqual(connection.execute(text("SELECT count(*) FROM schema_migrations")).scalar(), 14)

    def test_advisory_lock_and_upgrade_existing_import_jobs(self):
        with engine.begin() as connection:
            connection.execute(text("INSERT INTO import_jobs (filename, stored_path, attempt_token, status, total_bytes, uploaded_bytes, processed_bytes, processed_rows, created_rows, updated_rows, error_rows, rows_per_second, created_at, total_chunks, queued_chunks, processing_chunks, completed_chunks, failed_chunks, split_processed_bytes, split_total_bytes, split_created_chunks) VALUES ('existing.csv', '/tmp/existing.csv', '', 'completed', 0,0,0,0,0,0,0,0,NOW(),0,0,0,0,0,0,0,0)"))
            connection.execute(text("ALTER TABLE import_jobs DROP COLUMN sips_file_id, DROP COLUMN sips_member"))
            connection.execute(text("DROP TABLE sips_files"))
            connection.execute(text("DELETE FROM schema_migrations WHERE filename='0014_add_sips_sync.sql'"))
        init_db()
        init_db()
        with SessionLocal() as db:
            self.assertEqual(db.query(ImportJob).one().filename, "existing.csv")
            self.assertEqual(db.query(SipsFile).count(), 0)
        with engine.connect() as connection:
            connection.execute(text("SELECT pg_advisory_lock(:id)"), {"id": SYNC_LOCK_ID})
            try:
                self.assertEqual(sync_once(self.cfg), "locked")
            finally:
                connection.execute(text("SELECT pg_advisory_unlock(:id)"), {"id": SYNC_LOCK_ID})


if __name__ == "__main__":
    unittest.main()
