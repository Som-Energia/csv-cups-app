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
- `sips-sync`: consulta i descarrega SIPS (opcional, perfil Compose `sips`); mateix volum i BD/cua que app/worker

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
- `sips_sync.py`: servei periodic, `--once` per cron i `--status` per seguiment
- `app/services/sips_client.py`: OAuth2 CNMC, consulta DISPONIBLE/DESCARGADO i descarrega verificada
- `app/services/sips_sync.py`: inbox persistent, preparacio multi-CSV i lliurament a RQ
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
- `SIPS_API_URL` (HTTPS, default `https://api.cnmc.gob.es`)
- `SIPS_CONSUMER_KEY`, `SIPS_CONSUMER_SECRET` (credencials vigents; nomes al sincronitzador)
- `SIPS_CONSUMER_SECRET_FILE` (secret muntat, preferent sobre variable)
- `SIPS_NIF_EMPRESA`, `SIPS_PROCEDURE_ID` (obligatoris; cataleg public de produccio: `2` electricitat, `3` gas)
- `SIPS_FILE_TYPES` (llista de tipus CNMC exactes separats per comes; buit = tots els CSV/ZIP)
- `SIPS_POLL_SECONDS` (3600, minim 10)
- `SIPS_START_AFTER_MONTH` (buit; limit exclusiu YYYY-MM si cal indicar el mes existent)
- `SIPS_MAX_DOWNLOAD_BYTES` (53687091200), `SIPS_MAX_UNPACKED_BYTES` (536870912000)

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

Hi ha tres formats d'importacio:

1. `ps`
2. `consumption`
3. `autoconsumo`

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
- `sips_files`: historial unic per origen/procediment/empresa/UUID; migracio `0014`
- `import_jobs.sips_file_id` i `sips_member`: vinculacio opcional, unica per fitxer/membre

El codi usa upserts PostgreSQL via `sqlalchemy.dialects.postgresql.insert`.
Cada intent d'upsert consumeix seqüencia encara que la fila ja existeixi o no canviï.
`record_consumptions.id` i la seva seqüencia son `BIGINT` des de `0015`: cal ampliar
TOTS DOS i resoldre la seqüencia amb `pg_get_serial_sequence`, no assumir-ne el nom
(instal·lacions antigues poden conservar `records_consumptions_id_seq`). Mai reset/CYCLE.
La migracio reescriu la taula i reconstrueix indexos amb bloqueig exclusiu: en BD
grans cal copia, espai de disc/WAL i manteniment amb app/workers/sips-sync aturats.
Despres es poden reintentar nomes els chunks fallits, sense tornar a pujar la font.

Si canvies claus uniques o indexos, NO et limitis al model Python: pensa en dades existents i SQL manual.

## Migrations

Gotcha IMPORTANT:

- hi ha SQLs a `migrations/`
- el runtime actual SI executa migracions automatiques a startup
- `init_db()` registra els models i fa `Base.metadata.create_all(bind=engine)` i els SQL pendents dins del mateix bloqueig de migracions
- les migracions aplicades es registren a `schema_migrations`
- `app`, `worker` i `sips-sync` es coordinen amb `pg_advisory_lock` per evitar doble execucio concurrent, inclosa la creacio inicial
- Compose espera healthchecks de PostgreSQL i Redis abans d'arrencar els processos

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
- hi ha tests a `tests/`; els d'integracio necessiten serveis locals aillats (vegeu `tests/README.md`)

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

## Invariants del sincronitzador SIPS

- OAuth2 client_credentials; no OAuth1 (retirat 13/10/2026). Cal alta CNMC previa.
- User-Agent explicit csv-cups-app/<versio> (CNMC SIPS client) a tota la sessio: nginx CNMC retorna 403 HTML amb python-requests per defecte abans de validar OAuth2 (reproduit amb credencials ficticies; amb UA propi respon 401 invalid_client). No atribuir automaticament un 403 a permisos/credencials ni exposar el cos cru de les respostes.
- Descarrega anonima amb l'URL retornat, nomes HTTPS del mateix origen, sense redirects. Mai logs de secrets, tokens o URLs de descarrega.
- Streaming, MD5 CNMC + mida, `.part` i rename atomic. MD5 no es usa per autenticacio.
- Lock PostgreSQL de sessio, no lock Redis amb TTL que podria caducar a mitja descarrega.
- Persistir recepcio i jobs abans d'encolar; IDs RQ estables recuperen errors d'encolat.
- No marcar complet fins que TOTS els jobs acabin sense errors. Ordenar pel mes de dades del nom del fitxer, no per fechaDisponibilidad.
- Nomes mesos estrictament posteriors al maxim importat sense errors (manuals inclosos). Instal·lacio buida: nomes ultim mes disponible. Noms locals sense mes i sense altra referencia: exigir SIPS_START_AFTER_MONTH, mai descarregar tot l'historic.
- Admetre tot el lot mensual abans d'encolar. Estats selected/download_failed identifiquen fitxers ja admesos que han de completar-se encara que un altre fitxer del mes hagi acabat.
- Pendents antics de versions anteriors sense jobs: skipped si no son posteriors al tall. No cancel·lar automaticament jobs ja encolats. Fitxers remots sense mes recognoscible: ignorar amb avis, mai usar la data de publicacio com a mes de dades.
- No eliminar fonts pendents. Fitxers verificats es conserven fins a completar; l'historial persisteix despres de la neteja.
- SIPS prepara multiples CSV per ZIP i normalitza sis aliases de capcalera CNMC 4.0; les pujades manuals mantenen la validacio existent.
- Gas i altres formats no modelats no s'importen: membres ignorats visibles a `--status`; cap CSV compatible = error. No s'apliquen baixes/oposicions ni s'esborren registres absents d'un snapshot.
- Problemes de format/importacio requereixen revisio i reencolat existent; errors de transport/Redis es reintenten periodicament. Credencials i expiracio de fitxers remots requereixen actuacio del titular/CNMC.
- L'app no autentica usuaris: protegir-la externament i garantir confidencialitat. Nous fitxers 0600/directoris 0700: processos amb mateix UID o permisos explicits.

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
