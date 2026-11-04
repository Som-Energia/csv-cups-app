import os
from pathlib import Path


class Settings:
    def __init__(self):
        self.base_dir = Path(__file__).resolve().parent.parent
        self.app_version = os.getenv("APP_VERSION", "1.0.1")
        self.upload_dir = Path(os.getenv("UPLOAD_DIR", self.base_dir / "storage" / "uploads"))
        self.upload_dir.mkdir(parents=True, exist_ok=True)
        self.database_url = os.getenv(
            "DATABASE_URL",
            "postgresql+psycopg2://csvapp:csvapp@localhost:5432/csvapp",
        )
        self.redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        self.chunk_size = int(os.getenv("IMPORT_CHUNK_SIZE", "5000"))
        self.import_split_rows = int(os.getenv("IMPORT_SPLIT_ROWS", "50000"))
        self.upload_chunk_size = int(os.getenv("UPLOAD_CHUNK_SIZE", str(8 * 1024 * 1024)))
        self.sips_api_url = os.getenv("SIPS_API_URL", "https://api.cnmc.gob.es").rstrip("/")
        self.sips_consumer_key = os.getenv("SIPS_CONSUMER_KEY", "")
        secret_file = os.getenv("SIPS_CONSUMER_SECRET_FILE", "")
        self.sips_consumer_secret = (
            Path(secret_file).read_text().strip() if secret_file
            else os.getenv("SIPS_CONSUMER_SECRET", "")
        )
        self.sips_nif_empresa = os.getenv("SIPS_NIF_EMPRESA", "")
        self.sips_procedure_id = os.getenv("SIPS_PROCEDURE_ID", "")
        self.sips_file_types = tuple(filter(None, (
            value.strip() for value in os.getenv("SIPS_FILE_TYPES", "").split(",")
        )))
        self.sips_poll_seconds = int(os.getenv("SIPS_POLL_SECONDS", "3600"))
        self.sips_start_after_month = os.getenv("SIPS_START_AFTER_MONTH", "").strip()
        self.sips_max_download_bytes = int(os.getenv("SIPS_MAX_DOWNLOAD_BYTES", str(50 * 1024**3)))
        self.sips_max_unpacked_bytes = int(os.getenv("SIPS_MAX_UNPACKED_BYTES", str(500 * 1024**3)))
        self.chunk_upload_dir = self.upload_dir / "chunks"
        self.chunk_upload_dir.mkdir(parents=True, exist_ok=True)


settings = Settings()
