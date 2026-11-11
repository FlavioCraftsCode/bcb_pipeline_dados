"""Camada de leitura (serviço) usada pela API e pela exportação estática.

Todas as funções devolvem estruturas JSON-serializáveis. Mantê-las fora da API
garante que o painel servido pelo FastAPI e o snapshot estático publicado no
GitHub Pages mostrem exatamente os mesmos números.
"""

from __future__ import annotations

import math
import time
from datetime import date, datetime
from decimal import Decimal
from threading import Lock

import pandas as pd
from sqlalchemy import Engine, text

from .analise import matriz_correlacao, painel_mensal, para_mensal, resumo_indicador
from .config import SERIES, Periodicidade, serie

COLUNAS_PAINEL = {
    "selic": "Meta Selic (% a.a.)",
    "ipca_12m": "IPCA 12 meses (%)",
    "juro_real": "Juro real ex-post (% a.a.)",
    "dolar": "Dólar, média do mês (R$)",
    "dolar_var_12m": "Dólar, variação 12 meses (%)",
    "igpm_12m": "IGP-M 12 meses (%)",
    "ibcbr_var_12m": "IBC-Br, variação 12 meses (%)",
    "desemprego": "Desocupação (%)",
}


def _limpo(v):
    if v is None:
        return None
    if isinstance(v, (pd.Timestamp, datetime)):
        return v.isoformat()
    if isinstance(v, date):
        return v.isoformat()
    if isinstance(v, Decimal):
        v = float(v)
    if hasattr(v, "item"):
        v = v.item()
    if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
        return None
    return v


def _registros(df: pd.DataFrame) -> list[dict]:
    return [{k: _limpo(v) for k, v in linha.items()} for linha in df.to_dict("records")]


# ------------------------------------------------------------ cache de leitura
class _Cache:
    """Cache em memória das séries, invalidado quando a fato muda."""

    def __init__(self, ttl: float = 30.0) -> None:
        self.ttl = ttl
        self._lock = Lock()
        self._versao = None
        self._verificado = 0.0
        self._series: dict[str, pd.Series] = {}

    def series(self, engine: Engine) -> dict[str, pd.Series]:
        with self._lock:
            agora = time.monotonic()
            if agora - self._verificado < self.ttl and self._series:
                return self._series
            with engine.connect() as conn:
                versao = conn.execute(text("SELECT count(*), max(atualizado_em) FROM fato_indicadores")).one()
                versao = tuple(versao)
                if versao != self._versao or not self._series:
                    df = pd.read_sql(text("SELECT slug, data, valor FROM vw_observacoes ORDER BY slug, data"), conn)
                    df["data"] = pd.to_datetime(df["data"])
                    self._series = {slug: g.set_index("data")["valor"].astype(float) for slug, g in df.groupby("slug")}
                    self._versao = versao
            self._verificado = agora
            return self._series


CACHE = _Cache()


def carregar_series(engine: Engine) -> dict[str, pd.Series]:
    return CACHE.series(engine)


# ------------------------------------------------------------------ consultas
def indicadores(engine: Engine) -> list[dict]:
    dados = carregar_series(engine)
    saida = []
    for s in SERIES:
        hist = dados.get(s.slug)
        if hist is None or hist.empty:
            continue
        mensal = para_mensal(hist) if s.periodicidade is Periodicidade.DIARIA else hist
        faisca = mensal.iloc[-36:]
        saida.append(
            {
                "codigo": s.codigo,
                "slug": s.slug,
                "nome": s.nome,
                "unidade": s.unidade,
                "periodicidade": s.periodicidade.value,
                "fonte": s.fonte,
                "descricao": s.descricao,
                "casas_decimais": s.casas_decimais,
                "tags": list(s.tags),
                "resumo": {k: _limpo(v) for k, v in resumo_indicador(hist, s.periodicidade.value).items()},
                "faisca": [{"data": d.date().isoformat(), "valor": _limpo(v)} for d, v in faisca.items()],
            }
        )
    return saida


def serie_historica(engine: Engine, slug: str, frequencia: str = "mensal", desde: str | None = None) -> dict:
    s = serie(slug)
    hist = carregar_series(engine).get(s.slug, pd.Series(dtype=float))
    if frequencia == "mensal" and s.periodicidade is Periodicidade.DIARIA and not hist.empty:
        hist = para_mensal(hist, "ultimo")
    if desde:
        hist = hist.loc[hist.index >= pd.Timestamp(desde)]
    return {
        "slug": s.slug,
        "codigo": s.codigo,
        "nome": s.nome,
        "unidade": s.unidade,
        "frequencia": frequencia,
        "pontos": [{"data": d.date().isoformat(), "valor": _limpo(v)} for d, v in hist.items()],
    }


def painel(engine: Engine, desde: str = "2000-01-01") -> dict:
    p = painel_mensal(carregar_series(engine))
    p = p.loc[p.index >= pd.Timestamp(desde), [c for c in COLUNAS_PAINEL if c in p]]
    p = p.dropna(how="all")
    ultimo = {c: _ultimo_valido(p[c]) for c in p.columns}
    return {
        "colunas": {c: COLUNAS_PAINEL[c] for c in p.columns},
        "ultimo": ultimo,
        "linhas": _registros(p.reset_index(names="data").assign(data=lambda d: d["data"].dt.date)),
    }


def _ultimo_valido(s: pd.Series) -> dict | None:
    s = s.dropna()
    if s.empty:
        return None
    return {"data": s.index[-1].date().isoformat(), "valor": _limpo(s.iloc[-1])}


def correlacoes(engine: Engine, desde: str = "2012-01-01") -> dict:
    p = painel_mensal(carregar_series(engine))
    cols = ["selic", "ipca_12m", "juro_real", "dolar_var_12m", "ibcbr_var_12m", "desemprego", "igpm_12m"]
    m = matriz_correlacao(p, cols, desde)
    return {
        "metodo": "spearman",
        "desde": desde,
        "rotulos": {c: COLUNAS_PAINEL[c] for c in m.columns},
        "variaveis": list(m.columns),
        "matriz": [[_limpo(v) for v in linha] for linha in m.to_numpy()],
    }


def previsao(engine: Engine) -> dict:
    with engine.connect() as conn:
        ultimo = conn.execute(text("SELECT max(gerado_em) FROM previsoes WHERE codigo_bcb = '433'")).scalar()
        if ultimo is None:
            return {"disponivel": False}
        prev = pd.read_sql(
            text(
                "SELECT data_alvo AS data, horizonte, previsto, li, ls, previsto_12m, li_12m, ls_12m, "
                "modelo, data_base FROM previsoes WHERE codigo_bcb = '433' AND gerado_em = :g ORDER BY horizonte"
            ),
            conn,
            params={"g": ultimo},
        )
        met = pd.read_sql(
            text(
                "SELECT modelo, escolhido, mae, rmse, mae_12m, skill, origens, cobertura, descricao "
                "FROM previsao_metricas WHERE codigo_bcb = '433' AND gerado_em = :g ORDER BY mae"
            ),
            conn,
            params={"g": ultimo},
        )
    p = painel_mensal(carregar_series(engine))
    recente = p.loc[p.index >= p.index.max() - pd.DateOffset(years=4), ["ipca", "ipca_12m"]].dropna(how="all")
    return {
        "disponivel": True,
        "gerado_em": _limpo(ultimo),
        "modelo": prev["modelo"].iloc[0],
        "data_base": _limpo(prev["data_base"].iloc[0]),
        "nivel_intervalo": 0.8,
        "previsao": _registros(prev.drop(columns=["modelo", "data_base"])),
        "metricas": _registros(met),
        "historico": _registros(recente.reset_index(names="data").assign(data=lambda d: d["data"].dt.date)),
    }


def qualidade(engine: Engine) -> dict:
    with engine.connect() as conn:
        id_exec = conn.execute(text("SELECT max(id_execucao) FROM dq_resultados")).scalar()
        if id_exec is None:
            return {"id_execucao": None, "resultados": [], "frescor": []}
        res = pd.read_sql(
            text(
                "SELECT d.codigo_bcb, i.slug, i.nome_indicador, d.checagem, d.status, d.detalhe, "
                "d.valor_observado, d.verificado_em FROM dq_resultados d "
                "LEFT JOIN dim_indicador i ON i.codigo_bcb = d.codigo_bcb "
                "WHERE d.id_execucao = :e ORDER BY d.codigo_bcb, d.id_resultado"
            ),
            conn,
            params={"e": id_exec},
        )
        frescor = pd.read_sql(text("SELECT * FROM vw_frescor ORDER BY codigo_bcb"), conn)
        historico = pd.read_sql(
            text(
                "SELECT id_execucao, "
                "count(*) FILTER (WHERE status = 'ok') AS ok, "
                "count(*) FILTER (WHERE status = 'informativo') AS informativo, "
                "count(*) FILTER (WHERE status = 'bloqueante') AS bloqueante "
                "FROM dq_resultados GROUP BY id_execucao ORDER BY id_execucao DESC LIMIT 30"
            ),
            conn,
        )
    return {
        "id_execucao": int(id_exec),
        "resultados": _registros(res),
        "frescor": _registros(frescor),
        "historico": _registros(historico.iloc[::-1]),
    }


def execucoes(engine: Engine, limite: int = 20) -> dict:
    with engine.connect() as conn:
        ex = pd.read_sql(
            text(
                "SELECT id_execucao, iniciado_em, finalizado_em, status, modo, gatilho, linhas_extraidas, "
                "linhas_inseridas, linhas_revisadas, requisicoes_http, erro, "
                "extract(epoch FROM finalizado_em - iniciado_em)::float8 AS duracao_s "
                "FROM etl_execucoes ORDER BY id_execucao DESC LIMIT :n"
            ),
            conn,
            params={"n": limite},
        )
        series_ex = pd.read_sql(
            text(
                "SELECT s.*, i.slug FROM etl_execucoes_series s "
                "LEFT JOIN dim_indicador i ON i.codigo_bcb = s.codigo_bcb "
                "WHERE s.id_execucao = (SELECT max(id_execucao) FROM etl_execucoes_series) "
                "ORDER BY s.codigo_bcb"
            ),
            conn,
        )
    return {"execucoes": _registros(ex), "ultima_por_serie": _registros(series_ex)}


def saude(engine: Engine) -> dict:
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
        ultima = conn.execute(
            text("SELECT id_execucao, status, finalizado_em FROM etl_execucoes ORDER BY id_execucao DESC LIMIT 1")
        ).one_or_none()
    return {
        "status": "ok",
        "banco": "ok",
        "ultima_execucao": None
        if ultima is None
        else {"id": ultima.id_execucao, "status": ultima.status, "finalizado_em": _limpo(ultima.finalizado_em)},
    }
