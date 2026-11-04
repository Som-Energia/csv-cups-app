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
Jinja2==3.1.6
python-multipart==0.0.32
psycopg2-binary==2.9.9
redis==5.0.8
rq==1.16.2
requests==2.32.5
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

L'aplicacio suporta PS, consums i autoconsum, detectats per les capcaleres exactes del CSV.

### Format PS

Registre principal per punt de subministrament. Fa upsert sobre la taula `records` amb clau unica `cups`.

Capcaleres exactes:

```text
codigoEmpresaDistribuidora,nombreEmpresaDistribuidora,cups,referenciaCatastralPS,XPS,YPS,HusoPS,BandaPS,PaisPS,codigoProvinciaPS,desProvinciaPS,codigoMunicipioPS,desMunicipioPS,PoblacionPS,desPoblacionPS,codigoPostalPS,tipoViaPS,viaPS,numFincaPS,duplicadorFincaPS,escaleraPS,pisoPS,puertaPS,tipoAclaradorFincaPS,aclaradorFincaPS,fechaAltaSuministro,codigoTarifaATREnVigor,codigoSegmentoCargoEnVigor,codigoTensionV,potenciaMaximaBIEW,potenciaMaximaAPMW,codigoClasificacionPS,tipoControDelPotencia,tipoPerfilConsumo,valorDerechosExtensionW,valorDerechosAccesoW,codigoPropiedadEquipoMedida,codigoPropiedadICP,potenciasContratadasEnWP1,potenciasContratadasEnWP2,potenciasContratadasEnWP3,potenciasContratadasEnWP4,potenciasContratadasEnWP5,potenciasContratadasEnWP6,fechaUltimoMovimientoContrato,fechaUltimoCambioComercializador,cambioComercializadorEnCurso,codigoComercializadorVigente,fechaUltimoCambioAgregadorIndependiente,cambioAgregadorIndependienteEnCurso,codigoAgregadorIndependienteVigente,fechaLimiteDerechosReconocidos,fechaUltimaLectura,suspensionSuminstroImpago,tipoPersona,tipoIdTitular,idTitular,nombreTitular,apellido1Titular,apellido2Titular,PaisTitular,codigoProvinciaTitular,desProvinciaTitular,codigoMunicipioTitular,desMunicipioTitular,PoblacionTitular,desPoblacionTitular,codigoPostalTitular,tipoViaTitular,viaTitular,numFincaTitular,duplicadorFincaTitular,escaleraTitular,pisoTitular,puertaTitular,tipoAclaradorFincaTitular,aclaradorFincaTitular,esViviendaHabitual,codigoLecturaRemota,codigoFasesEquipoMedida,acogimientoAutoconsumo,aplicacionBonoSocial,suministroEsencial,cnae,codigoTipoContrato,codigoPeriodicidadFacturacion,codigoBIE,fechaEmisionBIE,fechaCaducidadBIE,codigoAPM,fechaEmisionAPM,fechaCaducidadAPM,relacionTransformacionIntensidad,codigoModoControlPotencia,potenciaCGPW,codigoDHEquipoDeMedida,codigoAccesibilidadContador,codigoPSContratable,motivoEstadoNoContratable,codigoTensionMedida,codigoClaseExpediente,codigoMotivoExpediente,codigoTipoSuministro
```

### Format de consums

Registre periodic de consum. Fa upsert sobre `record_consumptions` amb clau unica `cups + fechaInicioMesConsumo + fechaFinMesConsumo`.

Els imports només actualitzen registres existents quan alguna dada funcional ha canviat. Les files idèntiques conserven `uploaded_at` i no incrementen el comptador d'actualitzacions.

Capcaleres exactes:

```text
cups,fechaInicioMesConsumo,fechaFinMesConsumo,codigoTarifaATR,consumoEnergiaActivaEnWhP1,consumoEnergiaActivaEnWhP2,consumoEnergiaActivaEnWhP3,consumoEnergiaActivaEnWhP4,consumoEnergiaActivaEnWhP5,consumoEnergiaActivaEnWhP6,consumoEnergiaReactivaInductivaEnVArhP1,consumoEnergiaReactivaInductivaEnVArhP2,consumoEnergiaReactivaInductivaEnVArhP3,consumoEnergiaReactivaInductivaEnVArhP4,consumoEnergiaReactivaInductivaEnVArhP5,consumoEnergiaReactivaInductivaEnVArhP6,consumoEnergiaReactivaCapacitivaEnVArhP1,consumoEnergiaReactivaCapacitivaEnVArhP2,consumoEnergiaReactivaCapacitivaEnVArhP3,consumoEnergiaReactivaCapacitivaEnVArhP4,consumoEnergiaReactivaCapacitivaEnVArhP5,consumoEnergiaReactivaCapacitivaEnVArhP6,potenciaDemandadaEnWP1,potenciaDemandadaEnWP2,potenciaDemandadaEnWP3,potenciaDemandadaEnWP4,potenciaDemandadaEnWP5,potenciaDemandadaEnWP6,codigoDHEquipoDeMedida,codigoTipoLectura
```

### Format d'autoconsum

Coeficients de repartiment, amb capçaleres `cau,fechaInicioReparto,cups,horaCoeficienteVariableReparto,coeficienteReparto`. Fa upsert a `record_autoconsumos` per `cau + fechaInicioReparto + cups + horaCoeficienteVariableReparto`.

## Configuracio

Variables d'entorn suportades:

| Variable | Default | Descripcio |
| --- | --- | --- |
| `DATABASE_URL` | `postgresql+psycopg2://csvapp:csvapp@localhost:5432/csvapp` | Connexio SQLAlchemy a PostgreSQL |
| `REDIS_URL` | `redis://localhost:6379/0` | Connexio Redis per a la cua |
| `APP_VERSION` | `0.13.3` | Versio mostrada al footer de la UI |
| `UPLOAD_DIR` | `storage/uploads` sota el projecte | Directori persistent de pujades |
| `IMPORT_CHUNK_SIZE` | `5000` | Files per lot d'upsert |
| `IMPORT_SPLIT_ROWS` | `50000` | Files per chunk quan es divideix un import gran |
| `UPLOAD_CHUNK_SIZE` | `8388608` | Mida de lectura en bytes durant la pujada |

Variables realment critiques en produccio:

- `DATABASE_URL`
- `REDIS_URL`
- `UPLOAD_DIR`

## Sincronització automàtica amb SIPS / CNMC

El servei opcional `sips-sync` consulta les publicacions, descarrega les noves i crea jobs al mateix pipeline Redis/RQ que les pujades manuals. No cal pujar els fitxers a mà.

### Alta i activació

Cal tenir l'alta SIPS aprovada per la CNMC i una **Consumer Key / Consumer Secret vigents amb permís de descàrrega**, el NIF de l'empresa i l'identificador del procediment autoritzat. No són dades públiques: el programa no tramita l'alta ni eludeix l'autorització.

1. Copia `.env.example` a `.env` i omple `SIPS_CONSUMER_KEY`, `SIPS_CONSUMER_SECRET`, `SIPS_NIF_EMPRESA` i `SIPS_PROCEDURE_ID`.
2. Si la credencial ofereix diversos tipus, configura `SIPS_FILE_TYPES` amb els valors exactes de `tipoFichero` que vulguis importar. El catàleg de CNMC els anomena `nombrecorto`.
3. Arrenca **també els workers**:

```bash
chmod 600 .env
docker compose --profile sips up -d --build
docker compose logs -f sips-sync
```

La consulta s'executa en arrencar i després de cada `SIPS_POLL_SECONDS` (una hora per defecte). El perfil és optatiu perquè una instal·lació sense credencials segueixi funcionant igual. `docker compose stop sips-sync` atura les consultes sense interrompre els imports encolats.

| Variable | Default | Ús |
| --- | --- | --- |
| `SIPS_API_URL` | `https://api.cnmc.gob.es` | Origen HTTPS; preproducció: `https://apipre.cnmc.gob.es` |
| `SIPS_CONSUMER_KEY` | buit | Clau OAuth2 autoritzada |
| `SIPS_CONSUMER_SECRET` | buit | Secret OAuth2; no guardar a Git |
| `SIPS_CONSUMER_SECRET_FILE` | buit | Fitxer de secret muntat dins del contenidor; té preferència sobre l'anterior |
| `SIPS_NIF_EMPRESA` | buit | NIF vinculat a la credencial |
| `SIPS_PROCEDURE_ID` | buit | Identificador del procediment SIPS autoritzat |
| `SIPS_FILE_TYPES` | buit | Llista separada per comes; buida consulta tots els CSV/ZIP del procediment |
| `SIPS_POLL_SECONDS` | `3600` | Espera entre passades (mínim 10 segons) |
| `SIPS_MAX_DOWNLOAD_BYTES` | `53687091200` | Límit per fitxer comprimit: 50 GiB |
| `SIPS_MAX_UNPACKED_BYTES` | `536870912000` | Límit descomprimit per fitxer: 500 GiB |

En producció, és preferible muntar el secret com a fitxer de només lectura (`SIPS_CONSUMER_SECRET_FILE=/run/secrets/cnmc_secret`) mitjançant Docker secrets o Kubernetes Secret; la configuració Compose base no munta aquest fitxer per tu. Només `sips-sync` necessita credencials CNMC. Comparteix **el mateix `DATABASE_URL`, `REDIS_URL` i `UPLOAD_DIR`** entre `app`, `worker` i `sips-sync`, amb permisos de lectura/escriptura adequats (fitxers nous 0600, directoris SIPS 0700; mateix UID o ACL explícita). No exposis l'aplicació sense control d'accés: tracta dades confidencials i l'API actual no incorpora autenticació.

Sense Docker, exporta les variables i executa `python sips_sync.py` com a servei supervisat. També es pot fer una passada des de cron amb `python sips_sync.py --once` (codi de sortida 1 si falla; `importing` vol dir que els workers encara treballen). No cal cap scheduler RQ addicional. En Kubernetes utilitza la mateixa imatge amb `python sips_sync.py`, o un CronJob amb `--once`, sempre amb el volum compartit.

### Fiabilitat i seguiment

- OAuth2 `client_credentials`, token reutilitzat fins a la caducitat i una renovació en rebre 401. OAuth 1.0 va ser retirat per la CNMC el 13/10/2026.
- Consulta tant `DISPONIBLE` com `DESCARGADO`: una descàrrega fallida o un altre client poden haver canviat l'estat remot. La primera passada importa tot l'històric encara accessible que coincideixi amb el filtre.
- Historial persistent `sips_files`, únic per origen/procediment/empresa/UUID. Els enllaços temporals de descàrrega i els tokens no es desen ni s'escriuen als logs.
- Descàrrega en streaming a `.part`, verificació de bytes i MD5 proporcionats per CNMC i canvi de nom atòmic. MD5 només és la suma de comprovació del protocol; la seguretat del transport és HTTPS amb verificació TLS. No s'envia el token als enllaços de descàrrega, ni se segueixen redireccions ni enllaços a altres orígens.
- ZIP amb múltiples CSV: un `ImportJob` per membre suportat, amb noms locals independents de les rutes del ZIP. No s'extreuen rutes remotes directament.
- Un bloqueig PostgreSQL evita sincronitzadors simultanis. La creació de jobs és transaccional; si Redis falla entre el commit i l'encolat, la passada següent recupera els jobs sense tornar a descarregar ni duplicar-los.
- Publicacions ordenades per disponibilitat. No es passa a la següent fins que tots els jobs de l'anterior acabin sense files rebutjades. Una publicació antiga apareguda tard es bloqueja per evitar sobreescriure dades més noves.
- Errors de xarxa/descàrrega/encolat es reintenten a la passada següent. Errors d'importació o formats desconeguts requereixen revisió; no es marquen com a èxit. El ZIP verificat es conserva fins a completar l'import; després s'eliminen els fitxers i es conserva l'historial.

```bash
docker compose --profile sips run --rm sips-sync python sips_sync.py --status
# Retorna receipt, estat, error, membres ignorats i job_ids.
curl http://localhost:8000/api/jobs/123
curl http://localhost:8000/api/jobs/123/chunks
# Després de resoldre la causa (vegeu també /jobs/123):
curl -X POST http://localhost:8000/api/jobs/123/retry-failed-chunks
curl -X POST http://localhost:8000/api/jobs/123/requeue
```

No esborris manualment fonts/chunks d'imports SIPS pendents. Els jobs encallats per una caiguda del worker segueixen utilitzant els mecanismes existents de reencolat; el sincronitzador no força un job que podria continuar executant-se. Si un fitxer pendent caduca a CNMC abans de poder descarregar-lo, cal que CNMC el torni a posar a disposició. Una entrada antiga bloquejada necessita revisió operativa; no es descarta silenciosament.

**Abast dels formats:** PS d'electricitat, consums i coeficients de repartiment d'autoconsum amb les capçaleres de `app/constants.py`. La descàrrega normalitza només les sis variants de majúscules documentades per CNMC 4.0 (`husoPS`, `bandaPS`, `paisPS`, `poblacionPS`, `paisTitular`, `poblacionTitular`). No s'han afegit models de gas, LOPD, vertits, multicomercialitzador o potències temporals. Els membres no compatibles d'un ZIP consten a `ignored_members`; un fitxer sense cap CSV compatible falla. Els canvis futurs de format es rebutgen, no s'importen amb columnes desplaçades. Manté els upserts actuals: no elimina registres absents d'una publicació ni aplica baixes/oposicions automàticament.

Fonts del contracte implementat:
- [Tràmit SIPS i requisits d'accés](https://sede.cnmc.gob.es/tramites/energia-electricidad-energia-gas/bases-de-datos-de-consumidores-y-puntos-de-suministro)
- [OAuth2 i equivalències de rutes](https://sede.cnmc.gob.es/documentacion/api-publico/metodo-de-autenticacion)
- [Consulta i descàrrega de fitxers](https://sede.cnmc.gob.es/documentacion/api-publico/descarga)

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

Important: la imatge Docker ha d'incloure la carpeta `migrations/`, o les migracions SQL pendents no s'aplicaran a l'arrencada. Compose espera que PostgreSQL i Redis estiguin saludables; la creació inicial de taules i les migracions comparteixen un bloqueig PostgreSQL entre app, worker i sincronitzador.

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
