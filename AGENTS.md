# AGENTS.md

Aquest fitxer documenta el context real del projecte per a futurs agents i contribucions automatitzades.

## Resum del projecte

`csv-cups-app` es una aplicacio FastAPI que importa fitxers CSV o ZIP amb dades de CUPS, desa els fitxers a disc, encola el processament a Redis i persisteix els resultats a PostgreSQL.

No es una app CRUD generica. El cor del projecte es el pipeline d'importacio i reprocessat.

## Stack i components

- Python 3.12
- FastAPI + Uvicorn
- SQLAlchemy 2
- PostgreSQL
- Redis + RQ
- Jinja2 per les pagines HTML server-side
- Docker Compose per desenvolupament local

Components operatius:

- `app`: HTTP server
- `worker`: consumidor de la cua
- `postgres`: dades persistides
- `redis`: backend de cua

## Regla d'or

Si toques el flux d'importacio, pensa SEMPRE en aquests quatre punts:

1. pujada a disc
2. encolat a Redis
3. processament al worker
4. consistencia entre `app`, `worker` i `UPLOAD_DIR`

Molta gent toca nomes l'API i s'oblida del worker. Aixo trenca produccio.

## Fitxers importants

- `app/main.py`: endpoints API, pagines HTML i creacio inicial dels jobs
- `app/services/importer.py`: logica d'importacio, validacio de capcaleres, splitting, retries i upserts
- `app/models.py`: `ImportJob`, `ImportJobChunk`, `Record`, `RecordConsumption`
- `app/schemas.py`: respostes de l'API
- `app/constants.py`: formats suportats, etiquetes UI i agrupacions de camps
- `app/settings.py`: variables d'entorn
- `app/jobs.py`: Redis i cua RQ
- `app/database.py`: engine SQLAlchemy i `init_db()`
- `worker.py`: entry point del worker
- `docker-compose.yml`: desenvolupament local amb un `worker` escalable
- `migrations/*.sql`: canvis manuals de schema/indexos

## Configuracio d'entorn

Variables suportades:

- `APP_VERSION`
- `DATABASE_URL`
- `REDIS_URL`
- `UPLOAD_DIR`
- `IMPORT_CHUNK_SIZE`
- `IMPORT_SPLIT_ROWS`
- `UPLOAD_CHUNK_SIZE`

Les tres critiques son:

- `DATABASE_URL`
- `REDIS_URL`
- `UPLOAD_DIR`

## Desplegament

Patro recomanat:

- una sola imatge Docker
- un proces `app`
- un proces `worker`
- mateix codi, diferent `command`

Comandes:

- `app`: `uvicorn app.main:app --host 0.0.0.0 --port 8000`
- `worker`: `python worker.py`

En `docker-compose`, els workers s'han d'escalar amb:

```bash
docker compose up --scale worker=3
```

NO creis `worker2`, `worker3`, etc. Es pitjor manteniment per no guanyar res.

## Formats de dades suportats

Hi ha dos formats d'importacio:

1. `ps`
2. `consumption`

La deteccio es fa comparant exactament les capcaleres del CSV.

Consequencies:

- no canviis noms de capcalera alegremente
- si afegeixes un nou format, has de tocar com a minim `constants.py` i `importer.py`
- valida sempre la compatibilitat amb els upserts existents

## Persistencia i model

Taules:

- `import_jobs`: estat global de cada importacio
- `import_job_chunks`: estat per chunk
- `records`: dades PS, unic per `cups`
- `record_consumptions`: consums, unic per `cups + periode`

El codi usa upserts PostgreSQL via `sqlalchemy.dialects.postgresql.insert`.

Si canvies claus uniques o indexos, NO et limitis al model Python: pensa en dades existents i SQL manual.

## Migrations

Gotcha IMPORTANT:

- hi ha SQLs a `migrations/`
- el runtime actual SI executa migracions automatiques a startup
- `init_db()` fa `Base.metadata.create_all(bind=engine)` i despres executa els SQL pendents de `migrations/`
- les migracions aplicades es registren a `schema_migrations`
- `app` i `worker` es coordinen amb `pg_advisory_lock` per evitar doble execucio concurrent

Aixo vol dir que:

- nous canvis de schema han d'anar a `migrations/*.sql` si no son simples creacions inicials
- els indexos especials i canvis incrementals continuen sense sortir de `create_all()` magicament
- no assumeixis que un canvi a `models.py` resol una migracio real: si canvia l'esquema, afegeix SQL versionat
- si desplegues amb Docker, assegura't que la imatge copia la carpeta top-level `migrations/` o el runtime no podra aplicar-les

## Flux funcional

Flux d'importacio:

1. `POST /api/uploads` accepta `.csv` o `.zip`
2. el fitxer es desa a `UPLOAD_DIR`
3. es crea un `ImportJob`
4. es fa `enqueue_import(job.id)`
5. el worker processa el job
6. si cal, divideix en chunks i encua subjobs
7. es fan upserts a `records` o `record_consumptions`

Flux de consulta:

- `/`: cerca i tauler principal
- `/records/{cups}`: detall PS + consums
- `/jobs/{job_id}`: detall de seguiment del job

## Endpoints que un agent ha de coneixer

- `GET /health`
- `POST /api/uploads`
- `GET /api/jobs`
- `GET /api/jobs/{job_id}`
- `GET /api/jobs/{job_id}/chunks`
- `POST /api/jobs/{job_id}/requeue`
- `POST /api/jobs/{job_id}/retry-failed-chunks`
- `GET /api/records`
- `GET /api/records/{cups}`
- `GET /api/records/{cups}/consumptions`

## Convencions per tocar codi

- fes canvis petits i locals
- no introdueixis abstraccions noves si no hi ha dolor real
- si toques importacio, revisa sempre impacte a `app/main.py`, `app/jobs.py`, `worker.py` i `app/services/importer.py`
- si canvies configuracio, reflecteix-ho a `README.md` i a aquest `AGENTS.md`
- no assumeixis que hi ha tests que et salvaran: avui no n'hi ha

## Verificacions utils

Despres de canvis de desplegament o documentacio:

```bash
docker compose config
```

Despres de canvis funcionals:

```bash
curl http://localhost:8000/health
```

Si el canvi afecta imports:

- comprova pujada de fitxer
- comprova que el job passa a `queued`
- comprova que un worker el consumeix
- comprova resultat a `/api/jobs/{id}`

## Errors habituals

- arrencar nomes `app` i oblidar el `worker`
- usar un `UPLOAD_DIR` no compartit entre processos
- assumir que qualsevol CSV es valid
- tocar nomes `models.py` i ignorar `migrations/`
- duplicar serveis `workerX` en lloc d'escalar `worker`

## Expectatives per futurs agents

Quan treballis aqui:

- verifica abans d'afirmar
- diferencia entre el que suporta el codi i el que desplega la configuracio actual
- documenta qualsevol canvi operatiu
- si descobreixes una limitacio de runtime, deixa-la escrita
