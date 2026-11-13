"""Métricas analíticas derivadas das séries brutas.

Funções puras (pandas in, pandas out) — testáveis sem banco e reutilizadas pela
API, pela exportação estática e pelos modelos de previsão.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def acumulado_12m(variacao_mensal_pct: pd.Series) -> pd.Series:
    """Acumula variações mensais (%) em janelas móveis de 12 meses (composto)."""
    fator = 1 + variacao_mensal_pct.astype(float) / 100
    return (fator.rolling(12, min_periods=12).apply(np.prod, raw=True) - 1) * 100


def acumulado_no_ano(variacao_mensal_pct: pd.Series) -> pd.Series:
    s = variacao_mensal_pct.astype(float)
    fator = 1 + s / 100
    return (fator.groupby(s.index.year).cumprod() - 1) * 100


def para_mensal(serie_diaria: pd.Series, como: str = "ultimo") -> pd.Series:
    """Converte série diária em mensal (índice = 1º dia do mês)."""
    s = serie_diaria.sort_index()
    agrupado = s.groupby(s.index.to_period("M"))
    out = agrupado.last() if como == "ultimo" else agrupado.mean()
    out.index = out.index.to_timestamp()
    return out


def variacao_12m(serie_nivel: pd.Series) -> pd.Series:
    """Variação % contra o mesmo mês do ano anterior (série mensal)."""
    return (serie_nivel / serie_nivel.shift(12) - 1) * 100


def juro_real_ex_post(selic_aa_pct: pd.Series, ipca_12m_pct: pd.Series) -> pd.Series:
    """Juro real pela equação de Fisher: (1+i)/(1+π) - 1, em % a.a."""
    alinhado = pd.concat([selic_aa_pct, ipca_12m_pct], axis=1, join="inner").dropna()
    i, pi = alinhado.iloc[:, 0] / 100, alinhado.iloc[:, 1] / 100
    return ((1 + i) / (1 + pi) - 1) * 100


def painel_mensal(series: dict[str, pd.Series]) -> pd.DataFrame:
    """Monta o painel mensal analítico a partir das séries canônicas por slug.

    ``series`` mapeia slug -> pd.Series indexada por data.
    """
    out: dict[str, pd.Series] = {}
    if "selic" in series:
        out["selic"] = para_mensal(series["selic"], "ultimo")
    if "dolar" in series:
        out["dolar"] = para_mensal(series["dolar"], "media")
        out["dolar_var_12m"] = variacao_12m(out["dolar"])
    if "ipca" in series:
        ipca = series["ipca"].sort_index()
        out["ipca"] = ipca
        out["ipca_12m"] = acumulado_12m(ipca)
        out["ipca_ano"] = acumulado_no_ano(ipca)
    if "igpm" in series:
        out["igpm_12m"] = acumulado_12m(series["igpm"].sort_index())
    if "ibcbr" in series:
        out["ibcbr"] = series["ibcbr"].sort_index()
        out["ibcbr_var_12m"] = variacao_12m(out["ibcbr"])
    if "desemprego" in series:
        out["desemprego"] = series["desemprego"].sort_index()
    df = pd.DataFrame(out).sort_index()
    if {"selic", "ipca_12m"} <= set(df.columns):
        df["juro_real"] = juro_real_ex_post(df["selic"], df["ipca_12m"])
    return df


def matriz_correlacao(painel: pd.DataFrame, colunas: list[str], desde: str = "2012-01-01") -> pd.DataFrame:
    """Correlação de Spearman entre indicadores mensais (robusta a não linearidade)."""
    base = painel.loc[painel.index >= pd.Timestamp(desde), [c for c in colunas if c in painel]].dropna()
    return base.corr(method="spearman")


def resumo_indicador(s: pd.Series, periodicidade: str) -> dict:
    """Valores de destaque para o card de um indicador."""
    s = s.dropna().sort_index()
    if s.empty:
        return {}
    ultimo_dt = s.index[-1]
    ultimo = float(s.iloc[-1])
    alvo = ultimo_dt - pd.DateOffset(years=1)
    um_ano = s.loc[:alvo]
    anterior = s.iloc[-2] if len(s) > 1 else np.nan
    return {
        "data": ultimo_dt.date().isoformat(),
        "valor": ultimo,
        "anterior": None if pd.isna(anterior) else float(anterior),
        "valor_12m_atras": None if um_ano.empty else float(um_ano.iloc[-1]),
        "min_5a": float(s.loc[ultimo_dt - pd.DateOffset(years=5) :].min()),
        "max_5a": float(s.loc[ultimo_dt - pd.DateOffset(years=5) :].max()),
        "observacoes": int(len(s)),
        "periodicidade": periodicidade,
    }


# ------------------------------------------------------------------ destaques
# Regime de meta contínua (desde 2025): meta de 3,0% com tolerância de ±1,5 p.p.
META_INFLACAO_PCT = 3.0
TOLERANCIA_META_PP = 1.5
MESES_PARA_DESCUMPRIMENTO = 6


def decisoes_selic(selic: pd.Series, limite: int = 8) -> list[dict]:
    """Mudanças da meta Selic (das mais recentes para as mais antigas).

    A série do SGS é diária e só muda quando o Copom altera a meta, então cada
    variação do valor marca o início da vigência de uma nova meta.
    """
    s = selic.dropna().sort_index()
    if len(s) < 2:
        return []
    anterior = s.shift(1)
    mudou = (s - anterior).abs() > 1e-9
    mudancas = s[mudou]
    saida = [
        {
            "data": dt.date().isoformat(),
            "de": float(anterior.loc[dt]),
            "para": float(valor),
            "variacao_pp": round(float(valor - anterior.loc[dt]), 4),
        }
        for dt, valor in mudancas.items()
    ]
    return saida[::-1][:limite]


def situacao_meta_inflacao(
    ipca_12m: pd.Series,
    meta: float = META_INFLACAO_PCT,
    tolerancia: float = TOLERANCIA_META_PP,
) -> dict | None:
    """Posiciona o IPCA acumulado em 12 meses frente à banda da meta de inflação."""
    s = ipca_12m.dropna().sort_index()
    if s.empty:
        return None
    piso, teto = meta - tolerancia, meta + tolerancia
    valor = float(s.iloc[-1])
    if valor > teto:
        situacao = "acima"
    elif valor < piso:
        situacao = "abaixo"
    else:
        situacao = "dentro"
    fora = (s > teto) | (s < piso)
    consecutivos = 0
    for f in reversed(fora.tolist()):
        if not f:
            break
        consecutivos += 1
    return {
        "data": s.index[-1].date().isoformat(),
        "ipca_12m": valor,
        "meta": meta,
        "piso": piso,
        "teto": teto,
        "desvio_pp": round(valor - meta, 4),
        "situacao": situacao,
        "meses_consecutivos_fora": consecutivos,
        "meses_para_descumprimento": MESES_PARA_DESCUMPRIMENTO,
    }
