"""Carga no Data Warehouse: upsert idempotente no Star Schema + registros de execução."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

import pandas as pd
from sqlalchemy import Connection, Engine, text

from . import sql
from .config import SERIES, Serie
from .previsao import ResultadoPrevisao
from .qualidade import ResultadoCheck
from .transformacao import dimensao_tempo


@dataclass
class ResultadoCarga:
    inseridas: int = 0
    revisadas: int = 0


def _nativo(v):
    """Converte escalares numpy/pandas em tipos Python aceitos pelo driver."""
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    if hasattr(v, "item"):
        return v.item()
    return v


def sincronizar_indicadores(engine: Engine, series: tuple[Serie, ...] = SERIES) -> None:
    linhas = [
        {
            "codigo_bcb": s.codigo,
            "slug": s.slug,
            "nome_indicador": s.nome,
            "unidade": s.unidade,
            "periodicidade": s.periodicidade.value,
            "fonte": s.fonte,
            "descricao": s.descricao,
        }
        for s in series
    ]
    with engine.begin() as conn:
        conn.execute(text(sql.UPSERT_INDICADOR), linhas)


def ultima_data(engine: Engine, serie: Serie) -> date | None:
    with engine.connect() as conn:
        return conn.execute(text(sql.ULTIMA_DATA), {"codigo_bcb": serie.codigo}).scalar()


def ler_serie(engine: Engine, serie: Serie) -> pd.DataFrame:
    with engine.connect() as conn:
        df = pd.read_sql(text(sql.SERIE_COMPLETA), conn, params={"codigo_bcb": serie.codigo})
    df["data"] = pd.to_datetime(df["data"])
    df["valor"] = df["valor"].astype(float)
    return df


def gravar_observacoes(engine: Engine, df: pd.DataFrame, id_execucao: int) -> ResultadoCarga:
    """Upsert de um lote (já validado) numa única transação."""
    if df.empty:
        return ResultadoCarga()
    tempo = dimensao_tempo(df["data"])
    obs = [
        {"codigo_bcb": str(r.codigo_bcb), "data": r.data.date(), "valor": float(r.valor)}
        for r in df.itertuples(index=False)
    ]
    with engine.begin() as conn:
        conn.execute(text(sql.INSERIR_TEMPO), [{k: _nativo(v) for k, v in r.items()} for r in tempo.to_dict("records")])
        conn.execute(text(sql.CRIAR_STAGING))
        conn.execute(text(sql.INSERIR_STAGING), obs)
        linha = conn.execute(text(sql.MERGE_FATO), {"id_execucao": id_execucao}).one()
    return ResultadoCarga(inseridas=int(linha.inseridas), revisadas=int(linha.revisadas))


# --------------------------------------------------------------- observabilidade
def iniciar_execucao(engine: Engine, modo: str, gatilho: str) -> int:
    with engine.begin() as conn:
        return int(conn.execute(text(sql.INICIAR_EXECUCAO), {"modo": modo, "gatilho": gatilho}).scalar_one())


def finalizar_execucao(engine: Engine, id_execucao: int, **campos) -> None:
    with engine.begin() as conn:
        conn.execute(text(sql.FINALIZAR_EXECUCAO), {"id_execucao": id_execucao, **campos})


def registrar_serie(engine: Engine, **campos) -> None:
    with engine.begin() as conn:
        conn.execute(text(sql.REGISTRAR_SERIE), campos)


def registrar_qualidade(
    conn_ou_engine: Engine | Connection, id_execucao: int, resultados: list[ResultadoCheck]
) -> None:
    if not resultados:
        return
    linhas = [{"id_execucao": id_execucao, **r.como_dict()} for r in resultados]
    if isinstance(conn_ou_engine, Connection):
        conn_ou_engine.execute(text(sql.REGISTRAR_DQ), linhas)
        return
    with conn_ou_engine.begin() as conn:
        conn.execute(text(sql.REGISTRAR_DQ), linhas)


def gravar_previsao(engine: Engine, serie: Serie, r: ResultadoPrevisao, data_base: date) -> datetime:
    gerado_em = datetime.now().astimezone()
    prev = [
        {
            "gerado_em": gerado_em,
            "codigo_bcb": serie.codigo,
            "modelo": r.modelo_escolhido,
            "data_base": data_base,
            "data_alvo": linha["data"].date(),
            **{k: _nativo(linha[k]) for k in ("horizonte", "previsto", "li", "ls", "previsto_12m", "li_12m", "ls_12m")},
        }
        for _, linha in r.previsao.iterrows()
    ]
    met = [
        {
            "gerado_em": gerado_em,
            "codigo_bcb": serie.codigo,
            "modelo": m["modelo"],
            "escolhido": m["modelo"] == r.modelo_escolhido,
            "mae": float(m["mae"]),
            "rmse": float(m["rmse"]),
            "mae_12m": _nativo(m["mae_12m"]),
            "skill": _nativo(m["skill"]),
            "origens": r.origens_backtest,
            "cobertura": r.cobertura_intervalo if m["modelo"] == r.modelo_escolhido else None,
            "descricao": m["descricao"],
        }
        for _, m in r.metricas.iterrows()
    ]
    with engine.begin() as conn:
        conn.execute(text(sql.INSERIR_PREVISAO), prev)
        conn.execute(text(sql.INSERIR_METRICA), met)
    return gerado_em
