from datetime import datetime

from sqlalchemy import BigInteger, Column, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint

from app.database import Base


class ImportJob(Base):
    __tablename__ = "import_jobs"

    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String, nullable=False)
    stored_path = Column(String, nullable=False)
    attempt_token = Column(String, nullable=False, default="")
    status = Column(String, nullable=False, default="queued", index=True)
    total_bytes = Column(BigInteger, nullable=False, default=0)
    uploaded_bytes = Column(BigInteger, nullable=False, default=0)
    processed_bytes = Column(BigInteger, nullable=False, default=0)
    processed_rows = Column(Integer, nullable=False, default=0)
    created_rows = Column(Integer, nullable=False, default=0)
    updated_rows = Column(Integer, nullable=False, default=0)
    error_rows = Column(Integer, nullable=False, default=0)
    rows_per_second = Column(Float, nullable=False, default=0.0)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    started_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)
    last_progress_at = Column(DateTime, nullable=True)
    total_chunks = Column(Integer, nullable=False, default=0)
    queued_chunks = Column(Integer, nullable=False, default=0)
    processing_chunks = Column(Integer, nullable=False, default=0)
    completed_chunks = Column(Integer, nullable=False, default=0)
    failed_chunks = Column(Integer, nullable=False, default=0)
    split_processed_bytes = Column(BigInteger, nullable=False, default=0)
    split_created_chunks = Column(Integer, nullable=False, default=0)


class ImportJobChunk(Base):
    __tablename__ = "import_job_chunks"
    __table_args__ = (
        UniqueConstraint("job_id", "chunk_index", name="uq_import_job_chunks_job_chunk"),
    )

    id = Column(Integer, primary_key=True, index=True)
    job_id = Column(Integer, ForeignKey("import_jobs.id"), nullable=False, index=True)
    chunk_index = Column(Integer, nullable=False, index=True)
    filename = Column(String, nullable=False)
    stored_path = Column(String, nullable=False)
    status = Column(String, nullable=False, default="queued", index=True)
    total_rows = Column(Integer, nullable=False, default=0)
    processed_rows = Column(Integer, nullable=False, default=0)
    created_rows = Column(Integer, nullable=False, default=0)
    updated_rows = Column(Integer, nullable=False, default=0)
    error_rows = Column(Integer, nullable=False, default=0)
    rows_per_second = Column(Float, nullable=False, default=0.0)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    started_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)
    last_progress_at = Column(DateTime, nullable=True)


class Record(Base):
    __tablename__ = "records"

    id = Column(Integer, primary_key=True, index=True)
    uploaded_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    codigoEmpresaDistribuidora = Column(String, nullable=True)
    nombreEmpresaDistribuidora = Column(String, nullable=True)
    cups = Column(String(20), nullable=False, unique=True, index=True)
    referenciaCatastralPS = Column(String, nullable=True)
    XPS = Column(String, nullable=True)
    YPS = Column(String, nullable=True)
    HusoPS = Column(String, nullable=True)
    BandaPS = Column(String, nullable=True)
    PaisPS = Column(String, nullable=True)
    codigoProvinciaPS = Column(String, nullable=True)
    desProvinciaPS = Column(String, nullable=True)
    codigoMunicipioPS = Column(String, nullable=True)
    desMunicipioPS = Column(String, nullable=True)
    PoblacionPS = Column(String, nullable=True)
    desPoblacionPS = Column(String, nullable=True)
    codigoPostalPS = Column(String, nullable=True)
    tipoViaPS = Column(String, nullable=True)
    viaPS = Column(String, nullable=True)
    numFincaPS = Column(String, nullable=True)
    duplicadorFincaPS = Column(String, nullable=True)
    escaleraPS = Column(String, nullable=True)
    pisoPS = Column(String, nullable=True)
    puertaPS = Column(String, nullable=True)
    tipoAclaradorFincaPS = Column(String, nullable=True)
    aclaradorFincaPS = Column(String, nullable=True)
    fechaAltaSuministro = Column(String, nullable=True)
    codigoTarifaATREnVigor = Column(String, nullable=True)
    codigoSegmentoCargoEnVigor = Column(String, nullable=True)
    codigoTensionV = Column(String, nullable=True)
    potenciaMaximaBIEW = Column(String, nullable=True)
    potenciaMaximaAPMW = Column(String, nullable=True)
    codigoClasificacionPS = Column(String, nullable=True)
    tipoControDelPotencia = Column(String, nullable=True)
    tipoPerfilConsumo = Column(String, nullable=True)
    valorDerechosExtensionW = Column(String, nullable=True)
    valorDerechosAccesoW = Column(String, nullable=True)
    codigoPropiedadEquipoMedida = Column(String, nullable=True)
    codigoPropiedadICP = Column(String, nullable=True)
    potenciasContratadasEnWP1 = Column(String, nullable=True)
    potenciasContratadasEnWP2 = Column(String, nullable=True)
    potenciasContratadasEnWP3 = Column(String, nullable=True)
    potenciasContratadasEnWP4 = Column(String, nullable=True)
    potenciasContratadasEnWP5 = Column(String, nullable=True)
    potenciasContratadasEnWP6 = Column(String, nullable=True)
    fechaUltimoMovimientoContrato = Column(String, nullable=True)
    fechaUltimoCambioComercializador = Column(String, nullable=True)
    cambioComercializadorEnCurso = Column(String, nullable=True)
    codigoComercializadorVigente = Column(String, nullable=True)
    fechaUltimoCambioAgregadorIndependiente = Column(String, nullable=True)
    cambioAgregadorIndependienteEnCurso = Column(String, nullable=True)
    codigoAgregadorIndependienteVigente = Column(String, nullable=True)
    fechaLimiteDerechosReconocidos = Column(String, nullable=True)
    fechaUltimaLectura = Column(String, nullable=True)
    suspensionSuminstroImpago = Column(String, nullable=True)
    tipoPersona = Column(String, nullable=True)
    tipoIdTitular = Column(String, nullable=True)
    idTitular = Column(String, nullable=True)
    nombreTitular = Column(String, nullable=True)
    apellido1Titular = Column(String, nullable=True)
    apellido2Titular = Column(String, nullable=True)
    PaisTitular = Column(String, nullable=True)
    codigoProvinciaTitular = Column(String, nullable=True)
    desProvinciaTitular = Column(String, nullable=True)
    codigoMunicipioTitular = Column(String, nullable=True)
    desMunicipioTitular = Column(String, nullable=True)
    PoblacionTitular = Column(String, nullable=True)
    desPoblacionTitular = Column(String, nullable=True)
    codigoPostalTitular = Column(String, nullable=True)
    tipoViaTitular = Column(String, nullable=True)
    viaTitular = Column(String, nullable=True)
    numFincaTitular = Column(String, nullable=True)
    duplicadorFincaTitular = Column(String, nullable=True)
    escaleraTitular = Column(String, nullable=True)
    pisoTitular = Column(String, nullable=True)
    puertaTitular = Column(String, nullable=True)
    tipoAclaradorFincaTitular = Column(String, nullable=True)
    aclaradorFincaTitular = Column(String, nullable=True)
    esViviendaHabitual = Column(String, nullable=True)
    codigoLecturaRemota = Column(String, nullable=True)
    codigoFasesEquipoMedida = Column(String, nullable=True)
    acogimientoAutoconsumo = Column(String, nullable=True)
    codigoTipoContrato = Column(String, nullable=True)
    codigoPeriodicidadFacturacion = Column(String, nullable=True)
    codigoBIE = Column(String, nullable=True)
    fechaEmisionBIE = Column(String, nullable=True)
    fechaCaducidadBIE = Column(String, nullable=True)
    codigoAPM = Column(String, nullable=True)
    fechaEmisionAPM = Column(String, nullable=True)
    fechaCaducidadAPM = Column(String, nullable=True)
    relacionTransformacionIntensidad = Column(String, nullable=True)
    aplicacionBonoSocial = Column(String, nullable=True)
    suministroEsencial = Column(String, nullable=True)
    cnae = Column(String, nullable=True)
    codigoModoControlPotencia = Column(String, nullable=True)
    potenciaCGPW = Column(String, nullable=True)
    codigoDHEquipoDeMedida = Column(String, nullable=True)
    codigoAccesibilidadContador = Column(String, nullable=True)
    codigoPSContratable = Column(String, nullable=True)
    motivoEstadoNoContratable = Column(String, nullable=True)
    codigoTensionMedida = Column(String, nullable=True)
    codigoClaseExpediente = Column(String, nullable=True)
    codigoMotivoExpediente = Column(String, nullable=True)
    codigoTipoSuministro = Column(String, nullable=True)

    legacy_municipioPS = Column("municipioPS", String, nullable=True)
    legacy_codigoComercializadora = Column("codigoComercializadora", String, nullable=True)
    legacy_codigoTelegestion = Column("codigoTelegestion", String, nullable=True)
    legacy_codigoAutoconsumo = Column("codigoAutoconsumo", String, nullable=True)
    legacy_CNAE = Column("CNAE", String, nullable=True)


class RecordConsumption(Base):
    __tablename__ = "record_consumptions"
    __table_args__ = (
        UniqueConstraint(
            "cups",
            "fechaInicioMesConsumo",
            "fechaFinMesConsumo",
            name="uq_record_consumptions_cups_period",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    uploaded_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    cups = Column(String(20), nullable=False, index=True)
    fechaInicioMesConsumo = Column(
        "fechainiciomesconsumo", String, key="fechaInicioMesConsumo", nullable=False
    )
    fechaFinMesConsumo = Column(
        "fechafinmesconsumo", String, key="fechaFinMesConsumo", nullable=False
    )
    codigoTarifaATR = Column("codigotarifaatr", String, key="codigoTarifaATR", nullable=True)
    consumoEnergiaActivaEnWhP1 = Column(
        "consumoenergiaactivaenwhp1", String, key="consumoEnergiaActivaEnWhP1", nullable=True
    )
    consumoEnergiaActivaEnWhP2 = Column(
        "consumoenergiaactivaenwhp2", String, key="consumoEnergiaActivaEnWhP2", nullable=True
    )
    consumoEnergiaActivaEnWhP3 = Column(
        "consumoenergiaactivaenwhp3", String, key="consumoEnergiaActivaEnWhP3", nullable=True
    )
    consumoEnergiaActivaEnWhP4 = Column(
        "consumoenergiaactivaenwhp4", String, key="consumoEnergiaActivaEnWhP4", nullable=True
    )
    consumoEnergiaActivaEnWhP5 = Column(
        "consumoenergiaactivaenwhp5", String, key="consumoEnergiaActivaEnWhP5", nullable=True
    )
    consumoEnergiaActivaEnWhP6 = Column(
        "consumoenergiaactivaenwhp6", String, key="consumoEnergiaActivaEnWhP6", nullable=True
    )
    consumoEnergiaReactivaInductivaEnVArhP1 = Column(
        "consumoenergiareactivainductivaenvarhp1",
        String,
        key="consumoEnergiaReactivaInductivaEnVArhP1",
        nullable=True,
    )
    consumoEnergiaReactivaInductivaEnVArhP2 = Column(
        "consumoenergiareactivainductivaenvarhp2",
        String,
        key="consumoEnergiaReactivaInductivaEnVArhP2",
        nullable=True,
    )
    consumoEnergiaReactivaInductivaEnVArhP3 = Column(
        "consumoenergiareactivainductivaenvarhp3",
        String,
        key="consumoEnergiaReactivaInductivaEnVArhP3",
        nullable=True,
    )
    consumoEnergiaReactivaInductivaEnVArhP4 = Column(
        "consumoenergiareactivainductivaenvarhp4",
        String,
        key="consumoEnergiaReactivaInductivaEnVArhP4",
        nullable=True,
    )
    consumoEnergiaReactivaInductivaEnVArhP5 = Column(
        "consumoenergiareactivainductivaenvarhp5",
        String,
        key="consumoEnergiaReactivaInductivaEnVArhP5",
        nullable=True,
    )
    consumoEnergiaReactivaInductivaEnVArhP6 = Column(
        "consumoenergiareactivainductivaenvarhp6",
        String,
        key="consumoEnergiaReactivaInductivaEnVArhP6",
        nullable=True,
    )
    consumoEnergiaReactivaCapacitivaEnVArhP1 = Column(
        "consumoenergiareactivacapacitivaenvarhp1",
        String,
        key="consumoEnergiaReactivaCapacitivaEnVArhP1",
        nullable=True,
    )
    consumoEnergiaReactivaCapacitivaEnVArhP2 = Column(
        "consumoenergiareactivacapacitivaenvarhp2",
        String,
        key="consumoEnergiaReactivaCapacitivaEnVArhP2",
        nullable=True,
    )
    consumoEnergiaReactivaCapacitivaEnVArhP3 = Column(
        "consumoenergiareactivacapacitivaenvarhp3",
        String,
        key="consumoEnergiaReactivaCapacitivaEnVArhP3",
        nullable=True,
    )
    consumoEnergiaReactivaCapacitivaEnVArhP4 = Column(
        "consumoenergiareactivacapacitivaenvarhp4",
        String,
        key="consumoEnergiaReactivaCapacitivaEnVArhP4",
        nullable=True,
    )
    consumoEnergiaReactivaCapacitivaEnVArhP5 = Column(
        "consumoenergiareactivacapacitivaenvarhp5",
        String,
        key="consumoEnergiaReactivaCapacitivaEnVArhP5",
        nullable=True,
    )
    consumoEnergiaReactivaCapacitivaEnVArhP6 = Column(
        "consumoenergiareactivacapacitivaenvarhp6",
        String,
        key="consumoEnergiaReactivaCapacitivaEnVArhP6",
        nullable=True,
    )
    potenciaDemandadaEnWP1 = Column(
        "potenciademandadaenwp1", String, key="potenciaDemandadaEnWP1", nullable=True
    )
    potenciaDemandadaEnWP2 = Column(
        "potenciademandadaenwp2", String, key="potenciaDemandadaEnWP2", nullable=True
    )
    potenciaDemandadaEnWP3 = Column(
        "potenciademandadaenwp3", String, key="potenciaDemandadaEnWP3", nullable=True
    )
    potenciaDemandadaEnWP4 = Column(
        "potenciademandadaenwp4", String, key="potenciaDemandadaEnWP4", nullable=True
    )
    potenciaDemandadaEnWP5 = Column(
        "potenciademandadaenwp5", String, key="potenciaDemandadaEnWP5", nullable=True
    )
    potenciaDemandadaEnWP6 = Column(
        "potenciademandadaenwp6", String, key="potenciaDemandadaEnWP6", nullable=True
    )
    codigoDHEquipoDeMedida = Column(
        "codigodhequipodemedida", String, key="codigoDHEquipoDeMedida", nullable=True
    )
    codigoTipoLectura = Column("codigotipolectura", String, key="codigoTipoLectura", nullable=True)


class RecordAutoconsumo(Base):
    __tablename__ = "record_autoconsumos"
    __table_args__ = (
        UniqueConstraint(
            "cau",
            "fechaInicioReparto",
            "cups",
            "horaCoeficienteVariableReparto",
            name="uq_record_autoconsumos_logical_row",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    uploaded_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    cau = Column(String, nullable=False, index=True)
    fechaInicioReparto = Column(
        "fechainicioreparto", String, key="fechaInicioReparto", nullable=False, index=True
    )
    cups = Column(String(20), nullable=False, index=True)
    horaCoeficienteVariableReparto = Column(
        "horacoeficientevariablereparto",
        String,
        key="horaCoeficienteVariableReparto",
        nullable=False,
        default="",
    )
    coeficienteReparto = Column(
        "coeficientereparto", String, key="coeficienteReparto", nullable=True
    )
