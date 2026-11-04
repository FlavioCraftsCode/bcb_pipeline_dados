DROP TABLE IF EXISTS fato_indicadores CASCADE;
DROP TABLE IF EXISTS dim_tempo CASCADE;
DROP TABLE IF EXISTS dim_indicador CASCADE;


CREATE TABLE dim_tempo (
    id_tempo SERIAL PRIMARY KEY,
    data DATE UNIQUE NOT NULL,
    ano INT NOT NULL,
    mes INT NOT NULL,
    trimestre INT NOT NULL,
    dia_semana VARCHAR(20) NOT NULL
);

CREATE TABLE dim_indicador (
    id_indicador SERIAL PRIMARY KEY,
    nome_indicador VARCHAR(100) UNIQUE NOT NULL,
    codigo_bcb VARCHAR(10) NOT NULL
);

CREATE TABLE fato_indicadores (
    id_fato SERIAL PRIMARY KEY,
    id_tempo INT REFERENCES dim_tempo(id_tempo),
    id_indicador INT REFERENCES dim_indicador(id_indicador),
    valor NUMERIC(15, 4) NOT NULL
);


CREATE INDEX idx_fato_tempo ON fato_indicadores(id_tempo);
CREATE INDEX idx_fato_indicador ON fato_indicadores(id_indicador);