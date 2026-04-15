-- Schema: Indicadores de Violência Contra as Mulheres - RS (2012-2026)

CREATE TABLE IF NOT EXISTS ocorrencias (
    id          SERIAL PRIMARY KEY,
    municipio   VARCHAR(300) NOT NULL,
    tipo_crime  VARCHAR(30)  NOT NULL,  -- ver CHECK abaixo
    ano         SMALLINT     NOT NULL,
    mes         SMALLINT,               -- 1-12; NULL = dado anual agregado (2012-2017)
    quantidade  INTEGER      NOT NULL DEFAULT 0,

    CONSTRAINT chk_tipo_crime CHECK (tipo_crime IN (
        'feminicidio_tentado',
        'feminicidio_consumado',
        'ameaca',
        'estupro',
        'lesao_corporal',
        'geral'
    )),
    CONSTRAINT chk_ano  CHECK (ano  BETWEEN 2012 AND 2030),
    CONSTRAINT chk_mes  CHECK (mes  IS NULL OR mes BETWEEN 1 AND 12),
    CONSTRAINT uq_ocorrencia UNIQUE (municipio, tipo_crime, ano, mes)
);

CREATE INDEX idx_ocorrencias_municipio  ON ocorrencias (municipio);
CREATE INDEX idx_ocorrencias_tipo_crime ON ocorrencias (tipo_crime);
CREATE INDEX idx_ocorrencias_ano        ON ocorrencias (ano);
CREATE INDEX idx_ocorrencias_ano_mes    ON ocorrencias (ano, mes);
