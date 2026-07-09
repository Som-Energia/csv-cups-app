CREATE TABLE IF NOT EXISTS record_autoconsumos (
    id SERIAL PRIMARY KEY,
    uploaded_at TIMESTAMP NOT NULL DEFAULT NOW(),
    cau VARCHAR NOT NULL,
    fechaInicioReparto VARCHAR NOT NULL,
    cups VARCHAR NOT NULL,
    horaCoeficienteVariableReparto VARCHAR NOT NULL DEFAULT '',
    coeficienteReparto VARCHAR NULL,
    CONSTRAINT uq_record_autoconsumos_logical_row UNIQUE (
        cau,
        fechaInicioReparto,
        cups,
        horaCoeficienteVariableReparto
    )
);

CREATE INDEX IF NOT EXISTS idx_record_autoconsumos_cups
ON record_autoconsumos(cups);

CREATE INDEX IF NOT EXISTS idx_record_autoconsumos_cau
ON record_autoconsumos(cau);

CREATE INDEX IF NOT EXISTS idx_record_autoconsumos_reparto
ON record_autoconsumos(fechaInicioReparto DESC, horaCoeficienteVariableReparto ASC);
