from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from app.migrations import run_pending_migrations
from app.settings import settings

engine = create_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def init_db():
    # Register tables even when the worker starts before the HTTP application.
    from app import models  # noqa: F401

    run_pending_migrations(engine, metadata=Base.metadata)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
