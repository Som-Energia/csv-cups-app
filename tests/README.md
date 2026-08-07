# CUPS focused tests

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
