"""Pipeline de dados macroeconômicos do Banco Central do Brasil (SGS).

Camadas:
    extracao      -> cliente HTTP do SGS (janelas de 10 anos, retry, incremental)
    transformacao -> limpeza, tipagem e atributos de calendário
    qualidade     -> checagens de qualidade de dados com severidade
    carga         -> upsert idempotente no Data Warehouse (Star Schema)
    analise       -> métricas derivadas (acumulado 12m, juro real, correlações)
    previsao      -> modelos de previsão com backtest walk-forward
"""

__version__ = "2.0.0"
