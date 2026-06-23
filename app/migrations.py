from pathlib import Path


MIGRATIONS_LOCK_ID = 87342159
MIGRATIONS_TABLE_NAME = "schema_migrations"


def get_migrations_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "migrations"


def get_migration_files() -> list[Path]:
    migrations_dir = get_migrations_dir()
    if not migrations_dir.exists():
        return []
    return sorted(path for path in migrations_dir.glob("*.sql") if path.is_file())


def ensure_schema_migrations_table(cursor):
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            filename TEXT PRIMARY KEY,
            applied_at TIMESTAMP NOT NULL DEFAULT NOW()
        )
        """
    )


def get_applied_migrations(cursor) -> set[str]:
    cursor.execute("SELECT filename FROM schema_migrations ORDER BY filename ASC")
    return {row[0] for row in cursor.fetchall()}


def apply_migration(cursor, migration_path: Path):
    sql = migration_path.read_text(encoding="utf-8").strip()
    if not sql:
        return
    print("Applying migration {}".format(migration_path.name))
    cursor.execute(sql)
    cursor.execute(
        "INSERT INTO schema_migrations (filename) VALUES (%s)",
        (migration_path.name,),
    )


def run_pending_migrations(engine):
    migration_files = get_migration_files()
    if not migration_files:
        return

    connection = engine.raw_connection()
    try:
        cursor = connection.cursor()
        try:
            cursor.execute("SELECT pg_advisory_lock(%s)", (MIGRATIONS_LOCK_ID,))
            connection.commit()

            ensure_schema_migrations_table(cursor)
            connection.commit()

            applied_migrations = get_applied_migrations(cursor)
            for migration_path in migration_files:
                if migration_path.name in applied_migrations:
                    continue
                try:
                    apply_migration(cursor, migration_path)
                    connection.commit()
                    applied_migrations.add(migration_path.name)
                    print("Applied migration {}".format(migration_path.name))
                except Exception:
                    connection.rollback()
                    raise
        finally:
            try:
                cursor.execute("SELECT pg_advisory_unlock(%s)", (MIGRATIONS_LOCK_ID,))
                connection.commit()
            except Exception:
                connection.rollback()
                raise
            finally:
                cursor.close()
    finally:
        connection.close()
