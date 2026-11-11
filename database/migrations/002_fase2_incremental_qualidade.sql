-- 002 — Fase 2: carga incremental idempotente, observabilidade e camada analítica.

-- ---------------------------------------------------------------- dimensões
ALTER TABLE dim_indicador
    ADD COLUMN IF NOT EXISTS slug          VARCHAR(40),
    ADD COLUMN IF NOT EXISTS unidade       VARCHAR(20),
    ADD COLUMN IF NOT EXISTS periodicidade VARCHAR(10),
    ADD COLUMN IF NOT EXISTS fonte         VARCHAR(60),
    ADD COLUMN IF NOT EXISTS descricao     TEXT,
    ADD COLUMN IF NOT EXISTS ativo         BOOLEAN NOT NULL DEFAULT TRUE;

-- Correção da fase 1: a série SGS 11 é a Selic *diária* (ao dia), não a meta
-- definida pelo Copom (série 432). Os registros antigos são descartados; a meta
-- correta é carregada pela pipeline.
DELETE FROM fato_indicadores
 WHERE id_indicador IN (SELECT id_indicador FROM dim_indicador WHERE codigo_bcb = '11');
DELETE FROM dim_indicador WHERE codigo_bcb = '11';

-- A chave natural do indicador passa a ser o código SGS.
CREATE UNIQUE INDEX IF NOT EXISTS uq_dim_indicador_codigo ON dim_indicador(codigo_bcb);
CREATE UNIQUE INDEX IF NOT EXISTS uq_dim_indicador_slug ON dim_indicador(slug);

ALTER TABLE dim_tempo ADD COLUMN IF NOT EXISTS fim_de_mes BOOLEAN NOT NULL DEFAULT FALSE;
UPDATE dim_tempo
   SET fim_de_mes = (data = (date_trunc('month', data) + INTERVAL '1 month - 1 day')::date);

-- -------------------------------------------------------------------- fato
-- Remove eventuais duplicatas antes de criar a chave única (mantém a mais recente).
DELETE FROM fato_indicadores f
 USING fato_indicadores g
 WHERE f.id_indicador = g.id_indicador
   AND f.id_tempo = g.id_tempo
   AND f.id_fato < g.id_fato;

ALTER TABLE fato_indicadores
    ADD COLUMN IF NOT EXISTS carregado_em  TIMESTAMPTZ NOT NULL DEFAULT now(),
    ADD COLUMN IF NOT EXISTS atualizado_em TIMESTAMPTZ NOT NULL DEFAULT now(),
    ADD COLUMN IF NOT EXISTS id_execucao   INT;

DELETE FROM fato_indicadores WHERE id_tempo IS NULL OR id_indicador IS NULL;
ALTER TABLE fato_indicadores ALTER COLUMN id_tempo SET NOT NULL;
ALTER TABLE fato_indicadores ALTER COLUMN id_indicador SET NOT NULL;

-- Base do upsert idempotente (ON CONFLICT) e da busca por série+período.
CREATE UNIQUE INDEX IF NOT EXISTS uq_fato_indicador_tempo
    ON fato_indicadores(id_indicador, id_tempo);

-- ----------------------------------------------------------- observabilidade
CREATE TABLE IF NOT EXISTS etl_execucoes (
    id_execucao      SERIAL PRIMARY KEY,
    iniciado_em      TIMESTAMPTZ NOT NULL DEFAULT now(),
    finalizado_em    TIMESTAMPTZ,
    status           VARCHAR(12) NOT NULL DEFAULT 'executando'
                     CHECK (status IN ('executando', 'sucesso', 'parcial', 'falha')),
    modo             VARCHAR(12) NOT NULL CHECK (modo IN ('completo', 'incremental')),
    gatilho          VARCHAR(20) NOT NULL DEFAULT 'manual',
    linhas_extraidas INT NOT NULL DEFAULT 0,
    linhas_inseridas INT NOT NULL DEFAULT 0,
    linhas_revisadas INT NOT NULL DEFAULT 0,
    requisicoes_http INT NOT NULL DEFAULT 0,
    erro             TEXT
);

CREATE TABLE IF NOT EXISTS etl_execucoes_series (
    id_execucao      INT NOT NULL REFERENCES etl_execucoes(id_execucao) ON DELETE CASCADE,
    codigo_bcb       VARCHAR(10) NOT NULL,
    status           VARCHAR(12) NOT NULL CHECK (status IN ('sucesso', 'quarentena', 'falha')),
    desde            DATE,
    linhas_extraidas INT NOT NULL DEFAULT 0,
    linhas_inseridas INT NOT NULL DEFAULT 0,
    linhas_revisadas INT NOT NULL DEFAULT 0,
    duracao_ms       INT NOT NULL DEFAULT 0,
    erro             TEXT,
    PRIMARY KEY (id_execucao, codigo_bcb)
);

CREATE TABLE IF NOT EXISTS dq_resultados (
    id_resultado    SERIAL PRIMARY KEY,
    id_execucao     INT NOT NULL REFERENCES etl_execucoes(id_execucao) ON DELETE CASCADE,
    codigo_bcb      VARCHAR(10) NOT NULL,
    checagem        VARCHAR(40) NOT NULL,
    status          VARCHAR(8) NOT NULL CHECK (status IN ('ok', 'alerta', 'falha')),
    detalhe         TEXT NOT NULL,
    valor_observado DOUBLE PRECISION,
    verificado_em   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_dq_execucao ON dq_resultados(id_execucao);

-- ----------------------------------------------------------------- previsões
CREATE TABLE IF NOT EXISTS previsoes (
    id_previsao   SERIAL PRIMARY KEY,
    gerado_em     TIMESTAMPTZ NOT NULL DEFAULT now(),
    codigo_bcb    VARCHAR(10) NOT NULL,
    modelo        VARCHAR(40) NOT NULL,
    data_base     DATE NOT NULL,          -- último dado observado usado no treino
    data_alvo     DATE NOT NULL,
    horizonte     INT NOT NULL,
    previsto      DOUBLE PRECISION NOT NULL,
    li            DOUBLE PRECISION NOT NULL,
    ls            DOUBLE PRECISION NOT NULL,
    previsto_12m  DOUBLE PRECISION,
    li_12m        DOUBLE PRECISION,
    ls_12m        DOUBLE PRECISION
);
CREATE INDEX IF NOT EXISTS idx_previsoes_codigo_gerado ON previsoes(codigo_bcb, gerado_em DESC);

CREATE TABLE IF NOT EXISTS previsao_metricas (
    gerado_em   TIMESTAMPTZ NOT NULL,
    codigo_bcb  VARCHAR(10) NOT NULL,
    modelo      VARCHAR(40) NOT NULL,
    escolhido   BOOLEAN NOT NULL,
    mae         DOUBLE PRECISION NOT NULL,
    rmse        DOUBLE PRECISION NOT NULL,
    mae_12m     DOUBLE PRECISION,
    skill       DOUBLE PRECISION,
    origens     INT NOT NULL,
    cobertura   DOUBLE PRECISION,
    descricao   TEXT,
    PRIMARY KEY (gerado_em, codigo_bcb, modelo)
);

-- ---------------------------------------------------------- camada analítica
-- Visão longa e legível: a forma como analistas consultam o DW.
CREATE OR REPLACE VIEW vw_observacoes AS
SELECT i.codigo_bcb,
       i.slug,
       i.nome_indicador,
       i.unidade,
       i.periodicidade,
       t.data,
       t.ano,
       t.mes,
       f.valor::DOUBLE PRECISION AS valor,
       f.atualizado_em
  FROM fato_indicadores f
  JOIN dim_tempo t     ON t.id_tempo = f.id_tempo
  JOIN dim_indicador i ON i.id_indicador = f.id_indicador;

-- Mart mensal: diárias agregadas (último valor do mês) + mensais como estão.
CREATE OR REPLACE VIEW mart_mensal AS
WITH base AS (
    SELECT slug, date_trunc('month', data)::date AS mes, data, valor,
           row_number() OVER (PARTITION BY slug, date_trunc('month', data) ORDER BY data DESC) AS rn,
           avg(valor) OVER (PARTITION BY slug, date_trunc('month', data)) AS media_mes
      FROM vw_observacoes
)
SELECT slug, mes, valor AS valor_fim_mes, media_mes
  FROM base
 WHERE rn = 1;

-- Juro real ex-post (Fisher): Selic no fim do mês vs. IPCA oficial em 12 meses.
CREATE OR REPLACE VIEW mart_juro_real AS
SELECT s.mes,
       s.valor_fim_mes                                            AS selic,
       p.valor_fim_mes                                            AS ipca_12m,
       ((1 + s.valor_fim_mes / 100) / (1 + p.valor_fim_mes / 100) - 1) * 100 AS juro_real
  FROM mart_mensal s
  JOIN mart_mensal p ON p.mes = s.mes AND p.slug = 'ipca_12m'
 WHERE s.slug = 'selic';

-- Última observação e frescor por indicador (usado por monitoramento e API).
CREATE OR REPLACE VIEW vw_frescor AS
SELECT i.codigo_bcb, i.slug, i.nome_indicador, i.periodicidade,
       max(t.data)                 AS ultima_data,
       count(*)                    AS observacoes,
       max(f.atualizado_em)        AS ultima_atualizacao,
       current_date - max(t.data)  AS dias_desde_ultima
  FROM dim_indicador i
  LEFT JOIN fato_indicadores f ON f.id_indicador = i.id_indicador
  LEFT JOIN dim_tempo t        ON t.id_tempo = f.id_tempo
 GROUP BY i.codigo_bcb, i.slug, i.nome_indicador, i.periodicidade;
