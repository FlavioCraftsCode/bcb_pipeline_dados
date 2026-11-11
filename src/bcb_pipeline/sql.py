"""SQL da camada de carga, centralizado e versionado junto ao código.

Parâmetros no estilo ``:nome`` (SQLAlchemy ``text()``).
"""

UPSERT_INDICADOR = """
INSERT INTO dim_indicador
    (codigo_bcb, slug, nome_indicador, unidade, periodicidade, fonte, descricao, ativo)
VALUES
    (:codigo_bcb, :slug, :nome_indicador, :unidade, :periodicidade, :fonte, :descricao, TRUE)
ON CONFLICT (codigo_bcb) DO UPDATE SET
    slug           = EXCLUDED.slug,
    nome_indicador = EXCLUDED.nome_indicador,
    unidade        = EXCLUDED.unidade,
    periodicidade  = EXCLUDED.periodicidade,
    fonte          = EXCLUDED.fonte,
    descricao      = EXCLUDED.descricao,
    ativo          = TRUE
"""

INSERIR_TEMPO = """
INSERT INTO dim_tempo (data, ano, mes, trimestre, dia_semana, fim_de_mes)
VALUES (:data, :ano, :mes, :trimestre, :dia_semana, :fim_de_mes)
ON CONFLICT (data) DO NOTHING
"""

CRIAR_STAGING = """
CREATE TEMP TABLE IF NOT EXISTS stg_observacoes (
    codigo_bcb VARCHAR(10) NOT NULL,
    data       DATE NOT NULL,
    valor      NUMERIC(15, 4) NOT NULL
) ON COMMIT DROP
"""

INSERIR_STAGING = """
INSERT INTO stg_observacoes (codigo_bcb, data, valor) VALUES (:codigo_bcb, :data, :valor)
"""

# Upsert da staging na fato. Só reescreve linhas cujo valor mudou (revisões da
# fonte); ``xmax = 0`` distingue linha nova de linha atualizada no PostgreSQL.
MERGE_FATO = """
WITH gravadas AS (
    INSERT INTO fato_indicadores (id_tempo, id_indicador, valor, id_execucao)
    SELECT t.id_tempo, i.id_indicador, s.valor, :id_execucao
      FROM stg_observacoes s
      JOIN dim_tempo t     ON t.data = s.data
      JOIN dim_indicador i ON i.codigo_bcb = s.codigo_bcb
    ON CONFLICT (id_indicador, id_tempo) DO UPDATE SET
        valor         = EXCLUDED.valor,
        atualizado_em = now(),
        id_execucao   = EXCLUDED.id_execucao
    WHERE fato_indicadores.valor IS DISTINCT FROM EXCLUDED.valor
    RETURNING (xmax = 0) AS inserida
)
SELECT count(*) FILTER (WHERE inserida)     AS inseridas,
       count(*) FILTER (WHERE NOT inserida) AS revisadas
  FROM gravadas
"""

ULTIMA_DATA = """
SELECT max(t.data)
  FROM fato_indicadores f
  JOIN dim_tempo t     ON t.id_tempo = f.id_tempo
  JOIN dim_indicador i ON i.id_indicador = f.id_indicador
 WHERE i.codigo_bcb = :codigo_bcb
"""

SERIE_COMPLETA = """
SELECT data, valor FROM vw_observacoes WHERE codigo_bcb = :codigo_bcb ORDER BY data
"""

INICIAR_EXECUCAO = """
INSERT INTO etl_execucoes (modo, gatilho) VALUES (:modo, :gatilho) RETURNING id_execucao
"""

FINALIZAR_EXECUCAO = """
UPDATE etl_execucoes SET
    finalizado_em    = now(),
    status           = :status,
    linhas_extraidas = :linhas_extraidas,
    linhas_inseridas = :linhas_inseridas,
    linhas_revisadas = :linhas_revisadas,
    requisicoes_http = :requisicoes_http,
    erro             = :erro
WHERE id_execucao = :id_execucao
"""

REGISTRAR_SERIE = """
INSERT INTO etl_execucoes_series
    (id_execucao, codigo_bcb, status, desde, linhas_extraidas, linhas_inseridas,
     linhas_revisadas, duracao_ms, erro)
VALUES
    (:id_execucao, :codigo_bcb, :status, :desde, :linhas_extraidas, :linhas_inseridas,
     :linhas_revisadas, :duracao_ms, :erro)
"""

REGISTRAR_DQ = """
INSERT INTO dq_resultados (id_execucao, codigo_bcb, checagem, status, detalhe, valor_observado)
VALUES (:id_execucao, :codigo_bcb, :checagem, :status, :detalhe, :valor_observado)
"""

INSERIR_PREVISAO = """
INSERT INTO previsoes
    (gerado_em, codigo_bcb, modelo, data_base, data_alvo, horizonte, previsto, li, ls,
     previsto_12m, li_12m, ls_12m)
VALUES
    (:gerado_em, :codigo_bcb, :modelo, :data_base, :data_alvo, :horizonte, :previsto, :li, :ls,
     :previsto_12m, :li_12m, :ls_12m)
"""

INSERIR_METRICA = """
INSERT INTO previsao_metricas
    (gerado_em, codigo_bcb, modelo, escolhido, mae, rmse, mae_12m, skill, origens, cobertura, descricao)
VALUES
    (:gerado_em, :codigo_bcb, :modelo, :escolhido, :mae, :rmse, :mae_12m, :skill, :origens, :cobertura,
     :descricao)
"""
