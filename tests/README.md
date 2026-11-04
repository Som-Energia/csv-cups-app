# CUPS and SIPS tests

## SIPS synchronization

Unit tests (no CNMC credentials, PostgreSQL or Redis required):

```bash
pip install -r requirements.txt -r tests/requirements.txt
python -m unittest tests.test_sips_sync tests.test_sips_months -v
```

End-to-end tests use a local HTTPS CNMC fixture with a temporary trusted certificate,
real PostgreSQL, Redis and an RQ worker subprocess. They verify OAuth2, anonymous
checksummed download, multi-member ZIP imports, HTTP record/job queries, subsequent
updates without duplicate downloads, exclusion of republished historical months,
rejected-row recovery, the synchronizer lock,
concurrent initialization on an empty database and upgrading existing import tables. `openssl` must be installed. No live CNMC data/credentials are used.

**Destructive, disposable services only:** the suite resets the `public` schema in
`sips_sync_test` and flushes local Redis DB 15. It refuses other database names or
non-local hosts. Keep these ports separate from development/production services.

```bash
docker run -d --rm --name csv-sips-test-pg \
  -p 127.0.0.1:55439:5432 \
  -e POSTGRES_USER=csvapp -e POSTGRES_PASSWORD=csvapp \
  -e POSTGRES_DB=sips_sync_test postgres:16-alpine
docker run -d --rm --name csv-sips-test-redis \
  -p 127.0.0.1:56389:6379 redis:7-alpine
# Wait for PostgreSQL to report ready before running the suite.
docker exec csv-sips-test-pg pg_isready -U csvapp -d sips_sync_test
SIPS_INTEGRATION_TEST=1 \
DATABASE_URL=postgresql+psycopg2://csvapp:csvapp@127.0.0.1:55439/sips_sync_test \
REDIS_URL=redis://127.0.0.1:56389/15 \
UPLOAD_DIR=/tmp/csv-sips-integration-uploads \
python -m unittest tests.test_sips_integration -v
docker stop csv-sips-test-pg csv-sips-test-redis
```

The authenticated production CNMC connection must be checked by the operator with
their authorized credentials (`python sips_sync.py --once`, then `--status`).
Never put real tokens, signed download links or personal records in test fixtures.

## Existing CUPS suites

Install the test-only HTTP client before running the HTTP suite:

```bash
pip install -r tests/requirements.txt
python -m unittest tests.test_cups tests.test_cups_helpers tests.test_cups_api_http
```

`test_cups_migration_integration.py` is opt-in and refuses any target other than
the local disposable database named `cups_migration_test`. Run it in a dedicated
Docker network with a disposable PostgreSQL container:

```bash
docker network create cups-migration-test-net
docker run -d --rm --name cups-migration-postgres-test \
  --network cups-migration-test-net \
  -e POSTGRES_DB=cups_migration_test \
  -e POSTGRES_USER=csvapp \
  -e POSTGRES_PASSWORD=csvapp \
  postgres:16-alpine
docker run --rm --network cups-migration-test-net \
  -e CUPS_MIGRATION_TEST_DATABASE_URL=postgresql://csvapp:csvapp@cups-migration-postgres-test/cups_migration_test \
  -v "$PWD/tests:/app/tests:ro" csv-cups-app-app \
  python -m unittest tests.test_cups_migration_integration
docker stop cups-migration-postgres-test
docker network rm cups-migration-test-net
```

Conditional upsert tests also require an isolated PostgreSQL database:

```bash
docker run -d --rm --name cups-upsert-postgres-test \
  -e POSTGRES_DB=cups_upsert_test \
  -e POSTGRES_USER=csvapp \
  -e POSTGRES_PASSWORD=csvapp \
  postgres:16-alpine
docker run --rm --network container:cups-upsert-postgres-test \
  -e UPSERT_TEST_DATABASE_URL=postgresql://csvapp:csvapp@localhost:5432/cups_upsert_test \
  -v "$PWD/tests:/app/tests:ro" csv-cups-app-app \
  python -m unittest tests.test_upsert_integration
docker stop cups-upsert-postgres-test
```
