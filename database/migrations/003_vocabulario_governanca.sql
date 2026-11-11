-- 003 — Vocabulário de governança de dados para os status da plataforma.
--
--   Checagens (dq_resultados):          alerta -> informativo, falha -> bloqueante
--   Séries (etl_execucoes_series):      falha  -> interrompida
--   Execuções (etl_execucoes):          parcial -> concluido_com_isolamento
--                                       falha   -> concluido_com_isolamento, se todas as
--                                                  séries foram isoladas em quarentena;
--                                                  interrompida, nos demais casos
--
-- Migrações já aplicadas não são editadas: esta migração converte os dados
-- históricos e troca as restrições CHECK, preservando todo o histórico.

-- ------------------------------------------------------------- checagens
ALTER TABLE dq_resultados DROP CONSTRAINT IF EXISTS dq_resultados_status_check;
ALTER TABLE dq_resultados ALTER COLUMN status TYPE VARCHAR(16);
UPDATE dq_resultados SET status = 'bloqueante'  WHERE status = 'falha';
UPDATE dq_resultados SET status = 'informativo' WHERE status = 'alerta';
ALTER TABLE dq_resultados
    ADD CONSTRAINT dq_resultados_status_check
    CHECK (status IN ('ok', 'informativo', 'bloqueante'));

-- ----------------------------------------------------------------- séries
ALTER TABLE etl_execucoes_series DROP CONSTRAINT IF EXISTS etl_execucoes_series_status_check;
ALTER TABLE etl_execucoes_series ALTER COLUMN status TYPE VARCHAR(16);
UPDATE etl_execucoes_series SET status = 'interrompida' WHERE status = 'falha';
ALTER TABLE etl_execucoes_series
    ADD CONSTRAINT etl_execucoes_series_status_check
    CHECK (status IN ('sucesso', 'quarentena', 'interrompida'));

-- -------------------------------------------------------------- execuções
ALTER TABLE etl_execucoes DROP CONSTRAINT IF EXISTS etl_execucoes_status_check;
ALTER TABLE etl_execucoes ALTER COLUMN status TYPE VARCHAR(32);
UPDATE etl_execucoes SET status = 'concluido_com_isolamento' WHERE status = 'parcial';
UPDATE etl_execucoes e
   SET status = CASE
        WHEN EXISTS (SELECT 1 FROM etl_execucoes_series s WHERE s.id_execucao = e.id_execucao)
         AND NOT EXISTS (
                SELECT 1 FROM etl_execucoes_series s
                 WHERE s.id_execucao = e.id_execucao AND s.status <> 'quarentena')
        THEN 'concluido_com_isolamento'
        ELSE 'interrompida'
       END
 WHERE status = 'falha';
-- O resumo textual das séries isoladas acompanha o novo vocabulário.
UPDATE etl_execucoes SET erro = replace(erro, ': falha', ': interrompida')
 WHERE position(': falha' in erro) > 0;
ALTER TABLE etl_execucoes
    ADD CONSTRAINT etl_execucoes_status_check
    CHECK (status IN ('executando', 'sucesso', 'concluido_com_isolamento', 'interrompida'));
