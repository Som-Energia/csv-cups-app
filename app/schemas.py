from datetime import datetime

from pydantic import BaseModel, ConfigDict


class RecordOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    uploaded_at: datetime
    codigoEmpresaDistribuidora: str | None = None
    nombreEmpresaDistribuidora: str | None = None
    cups: str
    referenciaCatastralPS: str | None = None
    XPS: str | None = None
    YPS: str | None = None
    HusoPS: str | None = None
    BandaPS: str | None = None
    PaisPS: str | None = None
    codigoProvinciaPS: str | None = None
    desProvinciaPS: str | None = None
    codigoMunicipioPS: str | None = None
    desMunicipioPS: str | None = None
    PoblacionPS: str | None = None
    desPoblacionPS: str | None = None
    codigoPostalPS: str | None = None
    tipoViaPS: str | None = None
    viaPS: str | None = None
    numFincaPS: str | None = None
    duplicadorFincaPS: str | None = None
    escaleraPS: str | None = None
    pisoPS: str | None = None
    puertaPS: str | None = None
    tipoAclaradorFincaPS: str | None = None
    aclaradorFincaPS: str | None = None
    fechaAltaSuministro: str | None = None
    codigoTarifaATREnVigor: str | None = None
    codigoSegmentoCargoEnVigor: str | None = None
    codigoTensionV: str | None = None
    potenciaMaximaBIEW: str | None = None
    potenciaMaximaAPMW: str | None = None
    codigoClasificacionPS: str | None = None
    tipoControDelPotencia: str | None = None
    tipoPerfilConsumo: str | None = None
    valorDerechosExtensionW: str | None = None
    valorDerechosAccesoW: str | None = None
    codigoPropiedadEquipoMedida: str | None = None
    codigoPropiedadICP: str | None = None
    potenciasContratadasEnWP1: str | None = None
    potenciasContratadasEnWP2: str | None = None
    potenciasContratadasEnWP3: str | None = None
    potenciasContratadasEnWP4: str | None = None
    potenciasContratadasEnWP5: str | None = None
    potenciasContratadasEnWP6: str | None = None
    fechaUltimoMovimientoContrato: str | None = None
    fechaUltimoCambioComercializador: str | None = None
    cambioComercializadorEnCurso: str | None = None
    codigoComercializadorVigente: str | None = None
    fechaUltimoCambioAgregadorIndependiente: str | None = None
    cambioAgregadorIndependienteEnCurso: str | None = None
    codigoAgregadorIndependienteVigente: str | None = None
    fechaLimiteDerechosReconocidos: str | None = None
    fechaUltimaLectura: str | None = None
    suspensionSuminstroImpago: str | None = None
    tipoPersona: str | None = None
    tipoIdTitular: str | None = None
    idTitular: str | None = None
    nombreTitular: str | None = None
    apellido1Titular: str | None = None
    apellido2Titular: str | None = None
    PaisTitular: str | None = None
    codigoProvinciaTitular: str | None = None
    desProvinciaTitular: str | None = None
    codigoMunicipioTitular: str | None = None
    desMunicipioTitular: str | None = None
    PoblacionTitular: str | None = None
    desPoblacionTitular: str | None = None
    codigoPostalTitular: str | None = None
    tipoViaTitular: str | None = None
    viaTitular: str | None = None
    numFincaTitular: str | None = None
    duplicadorFincaTitular: str | None = None
    escaleraTitular: str | None = None
    pisoTitular: str | None = None
    puertaTitular: str | None = None
    tipoAclaradorFincaTitular: str | None = None
    aclaradorFincaTitular: str | None = None
    esViviendaHabitual: str | None = None
    codigoLecturaRemota: str | None = None
    codigoFasesEquipoMedida: str | None = None
    acogimientoAutoconsumo: str | None = None
    aplicacionBonoSocial: str | None = None
    suministroEsencial: str | None = None
    cnae: str | None = None
    codigoTipoContrato: str | None = None
    codigoPeriodicidadFacturacion: str | None = None
    codigoBIE: str | None = None
    fechaEmisionBIE: str | None = None
    fechaCaducidadBIE: str | None = None
    codigoAPM: str | None = None
    fechaEmisionAPM: str | None = None
    fechaCaducidadAPM: str | None = None
    relacionTransformacionIntensidad: str | None = None
    codigoModoControlPotencia: str | None = None
    potenciaCGPW: str | None = None
    codigoDHEquipoDeMedida: str | None = None
    codigoAccesibilidadContador: str | None = None
    codigoPSContratable: str | None = None
    motivoEstadoNoContratable: str | None = None
    codigoTensionMedida: str | None = None
    codigoClaseExpediente: str | None = None
    codigoMotivoExpediente: str | None = None
    codigoTipoSuministro: str | None = None


class RecordBonoSocialOut(BaseModel):
    cups: str
    hasBonoSocial: bool


class RecordConsumptionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    uploaded_at: datetime
    cups: str
    fechaInicioMesConsumo: str
    fechaFinMesConsumo: str
    codigoTarifaATR: str | None = None
    consumoEnergiaActivaEnWhP1: str | None = None
    consumoEnergiaActivaEnWhP2: str | None = None
    consumoEnergiaActivaEnWhP3: str | None = None
    consumoEnergiaActivaEnWhP4: str | None = None
    consumoEnergiaActivaEnWhP5: str | None = None
    consumoEnergiaActivaEnWhP6: str | None = None
    consumoEnergiaReactivaInductivaEnVArhP1: str | None = None
    consumoEnergiaReactivaInductivaEnVArhP2: str | None = None
    consumoEnergiaReactivaInductivaEnVArhP3: str | None = None
    consumoEnergiaReactivaInductivaEnVArhP4: str | None = None
    consumoEnergiaReactivaInductivaEnVArhP5: str | None = None
    consumoEnergiaReactivaInductivaEnVArhP6: str | None = None
    consumoEnergiaReactivaCapacitivaEnVArhP1: str | None = None
    consumoEnergiaReactivaCapacitivaEnVArhP2: str | None = None
    consumoEnergiaReactivaCapacitivaEnVArhP3: str | None = None
    consumoEnergiaReactivaCapacitivaEnVArhP4: str | None = None
    consumoEnergiaReactivaCapacitivaEnVArhP5: str | None = None
    consumoEnergiaReactivaCapacitivaEnVArhP6: str | None = None
    potenciaDemandadaEnWP1: str | None = None
    potenciaDemandadaEnWP2: str | None = None
    potenciaDemandadaEnWP3: str | None = None
    potenciaDemandadaEnWP4: str | None = None
    potenciaDemandadaEnWP5: str | None = None
    potenciaDemandadaEnWP6: str | None = None
    codigoDHEquipoDeMedida: str | None = None
    codigoTipoLectura: str | None = None


class ImportSummary(BaseModel):
    total: int
    created: int
    updated: int
    errors: list[dict[str, str]]


class JobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    filename: str
    status: str
    total_bytes: int
    uploaded_bytes: int
    processed_bytes: int
    processed_rows: int
    created_rows: int
    updated_rows: int
    error_rows: int
    rows_per_second: float
    error_message: str | None = None
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    last_progress_at: datetime | None = None
    can_requeue: bool = False
    can_retry_failed_chunks: bool = False
    total_chunks: int = 0
    queued_chunks: int = 0
    processing_chunks: int = 0
    completed_chunks: int = 0
    failed_chunks: int = 0
    split_processed_bytes: int = 0
    split_total_bytes: int = 0
    split_created_chunks: int = 0
    split_progress_percent: float = 0.0


class JobChunkOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    job_id: int
    chunk_index: int
    filename: str
    status: str
    total_rows: int
    processed_rows: int
    created_rows: int
    updated_rows: int
    error_rows: int
    rows_per_second: float
    error_message: str | None = None
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    last_progress_at: datetime | None = None


class JobChunkPageOut(BaseModel):
    items: list[JobChunkOut]
    page: int
    page_size: int
    total: int
    total_pages: int


class RetryFailedChunksResponse(BaseModel):
    job_id: int
    retried_chunks: int
    status: str


class UploadResponse(BaseModel):
    job_id: int
    status: str
