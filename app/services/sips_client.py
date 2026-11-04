"""CNMC OAuth2 download API. Never persist or log bearer download URLs."""
import hashlib
import os
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

import requests


class SipsError(RuntimeError):
    """Safe, credential-free operational error."""


@dataclass(frozen=True)
class RemoteFile:
    remote_id: str
    filename: str
    size: int
    md5: str
    available_at: datetime
    url: str


def parse_remote_file(item):
    try:
        remote_id = str(item["uuid"])
        filename = str(item["nombre"])
        size = int(item["numeroBytes"])
        digest = str(item["hash"]).lower()
        # CNMC prose uses uriDescargas; its JSON examples use uriDescarga.
        url = item.get("uriDescarga") or item["uriDescargas"]
        available = datetime.fromisoformat(item["fechaDisponibilidad"].replace("Z", "+00:00"))
        if available.tzinfo:
            available = available.astimezone(timezone.utc).replace(tzinfo=None)
        if not remote_id or not filename or size <= 0 or not re.fullmatch(r"[0-9a-f]{32}", digest):
            raise ValueError
        if not isinstance(url, str):
            raise ValueError
        return RemoteFile(remote_id, filename, size, digest, available, url)
    except (KeyError, TypeError, ValueError):
        raise SipsError("Invalid CNMC file metadata") from None


class SipsClient:
    def __init__(self, config):
        self.config = config
        self.base_url = config.sips_api_url
        base = urlsplit(self.base_url)
        if base.scheme != "https" or not base.hostname or base.username or base.password or base.path or base.query or base.fragment:
            raise SipsError("SIPS_API_URL must be an HTTPS origin")
        self.origin = (base.scheme, base.netloc)
        self.http = requests.Session()
        # Avoid implicit .netrc credentials on anonymous download requests.
        self.http.trust_env = False
        self.token = ""
        self.expires_at = 0.0

    def close(self):
        self.http.close()

    def request(self, method, url, **kwargs):
        try:
            response = self.http.request(method, url, timeout=(15, 120), allow_redirects=False, **kwargs)
        except requests.RequestException:
            raise SipsError("CNMC connection failed or timed out") from None
        return response

    @staticmethod
    def check_response(response):
        if response.status_code != 200:
            code = response.status_code
            response.close()
            raise SipsError(f"CNMC returned HTTP {code}")

    def authenticate(self):
        with self.request(
            "POST", self.base_url + "/oauth2/token",
            auth=(self.config.sips_consumer_key, self.config.sips_consumer_secret),
            data={"grant_type": "client_credentials", "scope": "read"},
        ) as response:
            self.check_response(response)
            try:
                payload = response.json()
                token = payload["access_token"]
                lifetime = int(payload["expires_in"])
                if not isinstance(token, str) or not token or lifetime <= 0:
                    raise ValueError
                self.token = token
                self.expires_at = time.monotonic() + max(0, lifetime - 30)
            except (ValueError, KeyError, TypeError):
                raise SipsError("Invalid CNMC OAuth2 token response") from None

    def consult(self, state):
        for attempt in range(2):
            if time.monotonic() >= self.expires_at:
                self.authenticate()
            with self.request(
                "POST", self.base_url + "/api-oauth2/ficheros/consultar",
                headers={"Authorization": f"Bearer {self.token}"},
                params={"idProcedimiento": self.config.sips_procedure_id,
                        "nifEmpresa": self.config.sips_nif_empresa, "estado": state},
            ) as response:
                if response.status_code == 401 and attempt == 0:
                    self.expires_at = 0
                    continue
                self.check_response(response)
                try:
                    payload = response.json()
                except ValueError:
                    raise SipsError("Invalid CNMC file list JSON") from None
                if not isinstance(payload, list) or not all(isinstance(item, dict) for item in payload):
                    raise SipsError("Invalid CNMC file list")
                return payload
        raise SipsError("CNMC authentication failed")

    def list_files(self):
        files = {}
        # Include DESCARGADO: a failed transfer or another client may have marked
        # the remote file downloaded. Only our persistent ledger proves import.
        for state in ("DISPONIBLE", "DESCARGADO"):
            for item in self.consult(state):
                if str(item.get("idProcedimiento")) != self.config.sips_procedure_id or str(item.get("nifEmpresa")) != self.config.sips_nif_empresa:
                    raise SipsError("CNMC returned a file for another procedure/company")
                if self.config.sips_file_types and item.get("tipoFichero") not in self.config.sips_file_types:
                    continue
                if Path(str(item.get("nombre", ""))).suffix.lower() not in (".csv", ".zip"):
                    continue
                remote = parse_remote_file(item)
                if remote.remote_id in files and files[remote.remote_id].md5 != remote.md5:
                    raise SipsError("Conflicting CNMC metadata for the same UUID")
                files[remote.remote_id] = remote
        return sorted(files.values(), key=lambda entry: (entry.available_at, entry.remote_id))

    def download(self, remote, destination):
        url = urlsplit(remote.url)
        if (url.scheme, url.netloc) != self.origin or url.username or url.password or url.fragment:
            raise SipsError("Refusing download outside the configured CNMC HTTPS origin")
        if remote.size > self.config.sips_max_download_bytes:
            raise SipsError("CNMC file exceeds SIPS_MAX_DOWNLOAD_BYTES")
        partial = destination.with_suffix(destination.suffix + ".part")
        partial.unlink(missing_ok=True)
        digest = hashlib.md5(usedforsecurity=False)  # CNMC transport checksum, not authentication
        size = 0
        try:
            with self.request("GET", remote.url, stream=True, headers={"Accept-Encoding": "identity"}) as response:
                self.check_response(response)
                with partial.open("wb") as output:
                    os.chmod(partial, 0o600)
                    for block in response.iter_content(chunk_size=1024 * 1024):
                        size += len(block)
                        if size > remote.size or size > self.config.sips_max_download_bytes:
                            raise SipsError("CNMC download exceeds declared size")
                        output.write(block)
                        digest.update(block)
                    output.flush()
                    os.fsync(output.fileno())
            if size != remote.size or digest.hexdigest() != remote.md5:
                raise SipsError("CNMC download size/MD5 mismatch")
            partial.replace(destination)
        except requests.RequestException:
            raise SipsError("CNMC download interrupted") from None
        finally:
            partial.unlink(missing_ok=True)
