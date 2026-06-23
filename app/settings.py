import os
from pathlib import Path


class Settings:
    def __init__(self):
        self.base_dir = Path(__file__).resolve().parent.parent
        self.app_version = os.getenv("APP_VERSION", "0.9")
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
        self.chunk_upload_dir = self.upload_dir / "chunks"
        self.chunk_upload_dir.mkdir(parents=True, exist_ok=True)


settings = Settings()
