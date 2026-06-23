# CSV CUPS App

Aplicacio web amb FastAPI per pujar fitxers CSV o ZIP molt grans, processar-los en segon pla i consultar dades per `cups`.

## Que fa

- pujada de fitxers a disc per streaming
- processament asyncron amb `RQ` i `Redis`
- persistencia a `PostgreSQL`
- upsert de dades PS per `cups`
- upsert de consums per `cups + periode`
- UI web per cercar CUPS, veure imports i inspeccionar registres
- API HTTP per pujar fitxers i consultar l'estat dels jobs

## Stack

- Python 3.12
- FastAPI
- Uvicorn
- SQLAlchemy 2
- PostgreSQL
- Redis
- RQ
- Jinja2
- Docker Compose

Dependencias Python actuals:

```text
fastapi==0.115.0
uvicorn[standard]==0.30.6
SQLAlchemy==2.0.35
Jinja2==3.1.4
python-multipart==0.0.9
psycopg2-binary==2.9.9
redis==5.0.8
rq==1.16.2
```

## Estructura del projecte

```text
.
├── app/
│   ├── main.py                # API i pagines HTML
│   ├── models.py              # Models SQLAlchemy
│   ├── schemas.py             # Schemas Pydantic
│   ├── database.py            # Engine, sessions i init DB
│   ├── settings.py            # Config per variables d'entorn
│   ├── constants.py           # Capcaleres CSV i etiquetes UI
│   ├── jobs.py                # Cua RQ i connexio Redis
│   ├── services/importer.py   # Logica d'importacio, splitting i upsert
│   ├── templates/             # HTML server-side
│   └── static/                # CSS i JS
├── migrations/                # SQL manual per evolucionar esquema/indexos
├── storage/uploads/           # Fitxers pujats i chunks temporals
├── Dockerfile
├── docker-compose.yml
├── worker.py                  # Entry point del worker
└── README.md
```

## Arquitectura

Flux principal:

1. L'usuari puja un CSV o ZIP a `POST /api/uploads`.
2. L'app desa el fitxer a `UPLOAD_DIR`.
3. L'app crea un `import_job` i l'encola a Redis.
4. El `worker` consumeix el job.
5. Si el fitxer es gran, es divideix en chunks.
6. Cada chunk es processa i fa upsert a PostgreSQL.
7. La UI i l'API consulten l'estat del job i les dades persistides.

Components:

- `app`: servidor web i API
- `worker`: processament en segon pla
- `postgres`: persistencia de `import_jobs`, `import_job_chunks`, `records` i `record_consumptions`
- `redis`: backend de cua

## Formats d'importacio suportats

L'aplicacio suporta dos formats diferents, detectats per les capcaleres exactes del CSV.

### Format PS

Registre principal per punt de subministrament. Fa upsert sobre la taula `records` amb clau unica `cups`.

Capcaleres exactes:

```text
codigoEmpresaDistribuidora,cups,nombreEmpresaDistribuidora,codigoPostalPS,municipioPS,codigoProvinciaPS,fechaAltaSuministro,codigoTarifaATREnVigor,codigoTensionV,potenciaMaximaBIEW,potenciaMaximaAPMW,codigoClasificacionPS,codigoDisponibilidadICP,tipoPerfilConsumo,valorDerechosExtensionW,valorDerechosAccesoW,codigoPropiedadEquipoMedida,codigoPropiedadICP,potenciasContratadasEnWP1,potenciasContratadasEnWP2,potenciasContratadasEnWP3,potenciasContratadasEnWP4,potenciasContratadasEnWP5,potenciasContratadasEnWP6,fechaUltimoMovimientoContrato,fechaUltimoCambioComercializador,fechaLimiteDerechosReconocidos,fechaUltimaLectura,informacionImpagos,importeDepositoGarantiaEuros,tipoIdTitular,esViviendaHabitual,codigoComercializadora,codigoTelegestion,codigoFasesEquipoMedida,codigoAutoconsumo,codigoTipoContrato,codigoPeriodicidadFacturacion,codigoBIE,fechaEmisionBIE,fechaCaducidadBIE,codigoAPM,fechaEmisionAPM,fechaCaducidadAPM,relacionTransformacionIntensidad,CNAE,codigoModoControlPotencia,potenciaCGPW,codigoDHEquipoDeMedida,codigoAccesibilidadContador,codigoPSContratable,motivoEstadoNoContratable,codigoTensionMedida,codigoClaseExpediente,codigoMotivoExpediente,codigoTipoSuministro,aplicacionBonoSocial
```

### Format de consums

Registre periodic de consum. Fa upsert sobre `record_consumptions` amb clau unica `cups + fechaInicioMesConsumo + fechaFinMesConsumo`.

Capcaleres exactes:

```text
cups,fechaInicioMesConsumo,fechaFinMesConsumo,codigoTarifaATR,consumoEnergiaActivaEnWhP1,consumoEnergiaActivaEnWhP2,consumoEnergiaActivaEnWhP3,consumoEnergiaActivaEnWhP4,consumoEnergiaActivaEnWhP5,consumoEnergiaActivaEnWhP6,consumoEnergiaReactivaEnVArhP1,consumoEnergiaReactivaEnVArhP2,consumoEnergiaReactivaEnVArhP3,consumoEnergiaReactivaEnVArhP4,consumoEnergiaReactivaEnVArhP5,consumoEnergiaReactivaEnVArhP6,potenciaDemandadaEnWP1,potenciaDemandadaEnWP2,potenciaDemandadaEnWP3,potenciaDemandadaEnWP4,potenciaDemandadaEnWP5,potenciaDemandadaEnWP6,codigoDHEquipoDeMedida,codigoTipoLectura
```

## Configuracio

Variables d'entorn suportades:

| Variable | Default | Descripcio |
| --- | --- | --- |
| `DATABASE_URL` | `postgresql+psycopg2://csvapp:csvapp@localhost:5432/csvapp` | Connexio SQLAlchemy a PostgreSQL |
| `REDIS_URL` | `redis://localhost:6379/0` | Connexio Redis per a la cua |
| `APP_VERSION` | `0.9` | Versio mostrada al footer de la UI |
| `UPLOAD_DIR` | `storage/uploads` sota el projecte | Directori persistent de pujades |
| `IMPORT_CHUNK_SIZE` | `5000` | Files per lot d'upsert |
| `IMPORT_SPLIT_ROWS` | `50000` | Files per chunk quan es divideix un import gran |
| `UPLOAD_CHUNK_SIZE` | `8388608` | Mida de lectura en bytes durant la pujada |

Variables realment critiques en produccio:

- `DATABASE_URL`
- `REDIS_URL`
- `UPLOAD_DIR`

## Executar amb Docker Compose

Arrencada basica:

```bash
docker compose up --build
```

Obre:

```text
http://localhost:8000
```

L'stack local inclou:

- `app`
- `worker`
- `postgres`
- `redis`

El `docker-compose.yml` utilitza una sola imatge per `app` i `worker`, amb comandes diferents:

- `app`: `uvicorn app.main:app --host 0.0.0.0 --port 8000`
- `worker`: `python worker.py`

Important: la imatge Docker ha d'incloure la carpeta `migrations/`, o les migracions SQL pendents no s'aplicaran a l'arrencada.

Escalar workers:

```bash
docker compose up --build --scale worker=3
```

## Executar sense Docker

Necessites PostgreSQL i Redis accessibles.

Servidor web:

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Worker:

```bash
python worker.py
```

## Desplegament a Harbor / Kubernetes

La imatge actual ja serveix tant per `app` com per `worker`.

Patro recomanat:

- una sola imatge a Harbor
- un deployment `app`
- un deployment `worker`
- mateix `DATABASE_URL`
- mateix `REDIS_URL`
- mateix volum compartit a `UPLOAD_DIR`

Exemple de variables:

```env
DATABASE_URL=postgresql+psycopg2://usuari:password@postgres.exemple:5432/csvapp
REDIS_URL=redis://redis.exemple:6379/0
UPLOAD_DIR=/app/storage/uploads
```

Important:

- si arranques nomes `app` i no `worker`, els fitxers es pujaran pero no es processaran
- `app` i `worker` han de veure el mateix `UPLOAD_DIR`

## Endpoints

### Salut

```bash
curl http://localhost:8000/health
```

Resposta:

```json
{"status": "ok"}
```

### Pujar un fitxer

Accepta `.csv` i `.zip`.

```bash
curl -X POST http://localhost:8000/api/uploads \
  -F "file=@fitxer.csv"
```

Resposta:

```json
{
  "job_id": 1,
  "status": "queued"
}
```

### Llistar jobs

```bash
curl "http://localhost:8000/api/jobs"
curl "http://localhost:8000/api/jobs?limit=50"
```

### Consultar un job

```bash
curl "http://localhost:8000/api/jobs/1"
```

### Consultar chunks d'un job

```bash
curl "http://localhost:8000/api/jobs/1/chunks"
```

### Reencolar un job

```bash
curl -X POST "http://localhost:8000/api/jobs/1/requeue"
curl -X POST "http://localhost:8000/api/jobs/1/requeue?force=true"
```

### Reintentar chunks fallits

```bash
curl -X POST "http://localhost:8000/api/jobs/1/retry-failed-chunks"
```

### Llistar registres PS

```bash
curl "http://localhost:8000/api/records"
curl "http://localhost:8000/api/records?cups=ES123"
```

### Obtenir un registre PS per CUPS

```bash
curl "http://localhost:8000/api/records/ES123456789"
```

### Obtenir consums d'un CUPS

```bash
curl "http://localhost:8000/api/records/ES123456789/consumptions"
```

## Pagines HTML

- `/`: cercador principal, pujades i llista de jobs recents
- `/records/{cups}`: detall del CUPS amb dades PS i historial de consums
- `/jobs/{job_id}`: detall i seguiment del job

## Model de dades

Taules principals:

- `import_jobs`: seguiment de cada pujada
- `import_job_chunks`: seguiment dels chunks quan un job es divideix
- `records`: dades PS per `cups`
- `record_consumptions`: historial de consum per `cups` i periode

Estats de job:

- `queued`
- `splitting`
- `processing`
- `partial_failed`
- `completed`
- `failed`

## Migrations i esquema

El projecte manté els canvis incrementals de BD a `migrations/*.sql` i ara els executa automaticament a startup.

El flux actual de `init_db()` es:

```python
Base.metadata.create_all(bind=engine)
run_pending_migrations(engine)
```

Aixo vol dir:

- `create_all()` crea taules si no existeixen
- les migracions SQL pendents s'apliquen automaticament en ordre pel nom del fitxer
- cada migracio aplicada es registra a la taula `schema_migrations`
- en reinicis posteriors no es tornen a executar les migracions ja registrades
- `app` i `worker` es coordinen amb `pg_advisory_lock` per evitar carreres quan arrenquen alhora

Si desplegues sobre una base ja existent, vigila especialment que els SQLs de `migrations/` segueixin sent idempotents o versionats correctament.

## Operacio i verificacio

Validar el `compose`:

```bash
docker compose config
```

Comprovar salut:

```bash
curl http://localhost:8000/health
```

## Limitacions i gotchas

- no hi ha suite de tests automatitzada al repo avui
- hi ha fitxers `.pyc` i dades sota `storage/` dins del workspace
- sense `worker` no hi ha processament en segon pla
- sense volum compartit entre `app` i `worker`, els chunks poden fallar
- els CSV s'han de correspondre exactament amb una de les dues capcaleres suportades

## Fitxers clau

- `app/main.py`: API, UI i flux de pujada
- `app/services/importer.py`: splitting, deteccio de format i upserts
- `app/models.py`: model relacional
- `app/constants.py`: formats d'importacio i etiquetes
- `app/settings.py`: configuracio d'entorn
- `app/jobs.py`: cua Redis/RQ
- `worker.py`: processador de fons
- `docker-compose.yml`: stack local i escalat de workers
