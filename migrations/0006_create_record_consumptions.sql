CREATE TABLE IF NOT EXISTS record_consumptions (
    id SERIAL PRIMARY KEY,
    uploaded_at TIMESTAMP NOT NULL DEFAULT NOW(),
    cups VARCHAR NOT NULL,
    fechaInicioMesConsumo VARCHAR NOT NULL,
    fechaFinMesConsumo VARCHAR NOT NULL,
    codigoTarifaATR VARCHAR NULL,
    consumoEnergiaActivaEnWhP1 VARCHAR NULL,
    consumoEnergiaActivaEnWhP2 VARCHAR NULL,
    consumoEnergiaActivaEnWhP3 VARCHAR NULL,
    consumoEnergiaActivaEnWhP4 VARCHAR NULL,
    consumoEnergiaActivaEnWhP5 VARCHAR NULL,
    consumoEnergiaActivaEnWhP6 VARCHAR NULL,
    consumoEnergiaReactivaEnVArhP1 VARCHAR NULL,
    consumoEnergiaReactivaEnVArhP2 VARCHAR NULL,
    consumoEnergiaReactivaEnVArhP3 VARCHAR NULL,
    consumoEnergiaReactivaEnVArhP4 VARCHAR NULL,
    consumoEnergiaReactivaEnVArhP5 VARCHAR NULL,
    consumoEnergiaReactivaEnVArhP6 VARCHAR NULL,
    potenciaDemandadaEnWP1 VARCHAR NULL,
    potenciaDemandadaEnWP2 VARCHAR NULL,
    potenciaDemandadaEnWP3 VARCHAR NULL,
    potenciaDemandadaEnWP4 VARCHAR NULL,
    potenciaDemandadaEnWP5 VARCHAR NULL,
    potenciaDemandadaEnWP6 VARCHAR NULL,
    codigoDHEquipoDeMedida VARCHAR NULL,
    codigoTipoLectura VARCHAR NULL,
    CONSTRAINT uq_record_consumptions_cups_period UNIQUE (
        cups,
        fechaInicioMesConsumo,
        fechaFinMesConsumo
    )
);

CREATE INDEX IF NOT EXISTS idx_record_consumptions_cups
ON record_consumptions(cups);

CREATE INDEX IF NOT EXISTS idx_record_consumptions_cups_period_desc
ON record_consumptions(cups, fechaInicioMesConsumo DESC);
