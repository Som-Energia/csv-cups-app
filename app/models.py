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
    cups = Column(String, nullable=False, unique=True, index=True)
    nombreEmpresaDistribuidora = Column(String, nullable=True)
    codigoPostalPS = Column(String, nullable=True)
    municipioPS = Column(String, nullable=True)
    codigoProvinciaPS = Column(String, nullable=True)
    fechaAltaSuministro = Column(String, nullable=True)
    codigoTarifaATREnVigor = Column(String, nullable=True)
    codigoTensionV = Column(String, nullable=True)
    potenciaMaximaBIEW = Column(String, nullable=True)
    potenciaMaximaAPMW = Column(String, nullable=True)
    codigoClasificacionPS = Column(String, nullable=True)
    codigoDisponibilidadICP = Column(String, nullable=True)
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
    fechaLimiteDerechosReconocidos = Column(String, nullable=True)
    fechaUltimaLectura = Column(String, nullable=True)
    informacionImpagos = Column(String, nullable=True)
    importeDepositoGarantiaEuros = Column(String, nullable=True)
    tipoIdTitular = Column(String, nullable=True)
    esViviendaHabitual = Column(String, nullable=True)
    codigoComercializadora = Column(String, nullable=True)
    codigoTelegestion = Column(String, nullable=True)
    codigoFasesEquipoMedida = Column(String, nullable=True)
    codigoAutoconsumo = Column(String, nullable=True)
    codigoTipoContrato = Column(String, nullable=True)
    codigoPeriodicidadFacturacion = Column(String, nullable=True)
    codigoBIE = Column(String, nullable=True)
    fechaEmisionBIE = Column(String, nullable=True)
    fechaCaducidadBIE = Column(String, nullable=True)
    codigoAPM = Column(String, nullable=True)
    fechaEmisionAPM = Column(String, nullable=True)
    fechaCaducidadAPM = Column(String, nullable=True)
    relacionTransformacionIntensidad = Column(String, nullable=True)
    CNAE = Column(String, nullable=True)
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
    aplicacionBonoSocial = Column(String, nullable=True)


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
    cups = Column(String, nullable=False, index=True)
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
    consumoEnergiaReactivaEnVArhP1 = Column(
        "consumoenergiareactivaenvarhp1",
        String,
        key="consumoEnergiaReactivaEnVArhP1",
        nullable=True,
    )
    consumoEnergiaReactivaEnVArhP2 = Column(
        "consumoenergiareactivaenvarhp2",
        String,
        key="consumoEnergiaReactivaEnVArhP2",
        nullable=True,
    )
    consumoEnergiaReactivaEnVArhP3 = Column(
        "consumoenergiareactivaenvarhp3",
        String,
        key="consumoEnergiaReactivaEnVArhP3",
        nullable=True,
    )
    consumoEnergiaReactivaEnVArhP4 = Column(
        "consumoenergiareactivaenvarhp4",
        String,
        key="consumoEnergiaReactivaEnVArhP4",
        nullable=True,
    )
    consumoEnergiaReactivaEnVArhP5 = Column(
        "consumoenergiareactivaenvarhp5",
        String,
        key="consumoEnergiaReactivaEnVArhP5",
        nullable=True,
    )
    consumoEnergiaReactivaEnVArhP6 = Column(
        "consumoenergiareactivaenvarhp6",
        String,
        key="consumoEnergiaReactivaEnVArhP6",
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
