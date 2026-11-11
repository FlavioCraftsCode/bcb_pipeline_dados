"""Previsão do IPCA mensal para os próximos 12 meses.

Metodologia
-----------
1. **Modelos candidatos** — dois *baselines* honestos e dois modelos de ML:
   ``ingenuo_sazonal`` (mesmo mês do ano anterior), ``media_sazonal``
   (nível dos últimos 12 meses + perfil sazonal de 5 anos), ``ridge_lags``
   e ``gbm_lags`` (regressões sobre defasagens e sazonalidade, previsão recursiva).
2. **Backtest walk-forward** — para cada uma das últimas ``n_origens`` datas,
   treina só com o passado e prevê 12 meses à frente. Nada de vazamento de
   dados do futuro: é exatamente o que o modelo teria feito em tempo real.
3. **Seleção** pelo menor MAE médio nos horizontes 1–12 e cálculo do
   *skill* contra o ingênuo sazonal (``1 - MAE_modelo / MAE_ingenuo``).
4. **Intervalos de previsão empíricos** — quantis dos erros do backtest por
   horizonte (abordagem conformal simples), sem supor normalidade.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from .analise import acumulado_12m

HORIZONTE = 12
N_LAGS = 12
INICIO_TREINO = pd.Timestamp("2004-01-01")  # pós-estabilização; evita a hiperinflação


Previsor = Callable[[pd.Series, int], np.ndarray]


# ------------------------------------------------------------------- baselines
def ingenuo_sazonal(hist: pd.Series, h: int) -> np.ndarray:
    ult12 = hist.iloc[-12:].to_numpy()
    return np.array([ult12[i % 12] for i in range(h)])


def media_sazonal(hist: pd.Series, h: int) -> np.ndarray:
    recente = hist.iloc[-60:]
    perfil = (recente - recente.rolling(12, min_periods=6).mean()).groupby(recente.index.month).mean()
    nivel = hist.iloc[-12:].mean()
    meses = pd.date_range(hist.index[-1] + pd.offsets.MonthBegin(1), periods=h, freq="MS").month
    return np.array([nivel + perfil.get(m, 0.0) for m in meses])


# ------------------------------------------------------------- modelos de ML
def _features(valores: np.ndarray, mes: int) -> np.ndarray:
    """Vetor de atributos para prever o próximo ponto a partir dos últimos 12."""
    lags = valores[-N_LAGS:][::-1]  # lag1 primeiro
    sazonal = np.zeros(12)
    sazonal[mes - 1] = 1
    return np.concatenate([lags, [valores[-12:].mean(), valores[-3:].mean()], sazonal])


def _matriz_treino(hist: pd.Series) -> tuple[np.ndarray, np.ndarray]:
    v = hist.to_numpy()
    meses = hist.index.month
    X, y = [], []
    for t in range(N_LAGS, len(v)):
        X.append(_features(v[:t], meses[t]))
        y.append(v[t])
    return np.asarray(X), np.asarray(y)


def _recursivo(modelo_fabrica: Callable[[], object]) -> Previsor:
    def prever(hist: pd.Series, h: int) -> np.ndarray:
        X, y = _matriz_treino(hist)
        modelo = modelo_fabrica()
        modelo.fit(X, y)
        valores = list(hist.to_numpy())
        mes = hist.index[-1].month
        saida = []
        for _ in range(h):
            mes = mes % 12 + 1
            pred = float(modelo.predict(_features(np.asarray(valores), mes).reshape(1, -1))[0])
            saida.append(pred)
            valores.append(pred)
        return np.array(saida)

    return prever


ridge_lags = _recursivo(lambda: make_pipeline(StandardScaler(), Ridge(alpha=10.0)))
gbm_lags = _recursivo(
    lambda: HistGradientBoostingRegressor(
        max_iter=200, learning_rate=0.05, max_depth=3, min_samples_leaf=10, random_state=42
    )
)

MODELOS: dict[str, Previsor] = {
    "ingenuo_sazonal": ingenuo_sazonal,
    "media_sazonal": media_sazonal,
    "ridge_lags": ridge_lags,
    "gbm_lags": gbm_lags,
}

DESCRICOES = {
    "ingenuo_sazonal": "Repete o mesmo mês do ano anterior (baseline)",
    "media_sazonal": "Nível dos últimos 12 meses + perfil sazonal (baseline)",
    "ridge_lags": "Regressão Ridge com 12 defasagens e sazonalidade",
    "gbm_lags": "Gradient boosting com 12 defasagens e sazonalidade",
}


# ------------------------------------------------------------------ backtest
@dataclass
class ResultadoPrevisao:
    modelo_escolhido: str
    metricas: pd.DataFrame  # modelo, mae, rmse, mae_12m, skill
    metricas_horizonte: pd.DataFrame  # modelo, horizonte, mae
    previsao: pd.DataFrame  # data, previsto, li, ls, previsto_12m, li_12m, ls_12m
    origens_backtest: int
    cobertura_intervalo: float


def backtest(serie: pd.Series, n_origens: int = 36, modelos: dict[str, Previsor] | None = None) -> pd.DataFrame:
    """Erros de previsão walk-forward. Uma linha por (modelo, origem, horizonte)."""
    modelos = modelos or MODELOS
    s = serie.loc[serie.index >= INICIO_TREINO].dropna()
    linhas = []
    n = len(s)
    primeira = n - n_origens - HORIZONTE + 1
    if primeira < 60:
        raise ValueError("Histórico insuficiente para o backtest")
    for o in range(primeira, n - 1):
        hist = s.iloc[:o]
        reais = s.iloc[o : o + HORIZONTE]
        for nome, f in modelos.items():
            prev = f(hist, len(reais))
            for k, (dt, real) in enumerate(reais.items(), start=1):
                linhas.append(
                    {
                        "modelo": nome,
                        "origem": hist.index[-1],
                        "data": dt,
                        "horizonte": k,
                        "real": float(real),
                        "previsto": float(prev[k - 1]),
                    }
                )
    df = pd.DataFrame(linhas)
    df["erro"] = df["real"] - df["previsto"]
    return df


def _mae_acumulado_12m(erros: pd.DataFrame) -> pd.Series:
    """MAE do acumulado de 12 meses previsto vs. realizado (só origens completas)."""
    completos = erros.groupby(["modelo", "origem"]).filter(lambda g: len(g) == HORIZONTE)

    def acum(x: pd.Series) -> float:
        return (np.prod(1 + x / 100) - 1) * 100

    g = completos.groupby(["modelo", "origem"])
    diff = (g["real"].apply(acum) - g["previsto"].apply(acum)).abs()
    return diff.groupby("modelo").mean()


def prever_ipca(serie_mensal: pd.Series, n_origens: int = 36, nivel: float = 0.8) -> ResultadoPrevisao:
    s = serie_mensal.sort_index().dropna()
    s.index = pd.DatetimeIndex(s.index)
    erros = backtest(s, n_origens)

    por_h = (
        erros.assign(abs=erros["erro"].abs()).groupby(["modelo", "horizonte"])["abs"].mean().rename("mae").reset_index()
    )
    metricas = erros.groupby("modelo").agg(
        mae=("erro", lambda e: float(np.mean(np.abs(e)))),
        rmse=("erro", lambda e: float(np.sqrt(np.mean(e**2)))),
    )
    metricas["mae_12m"] = _mae_acumulado_12m(erros)
    base = metricas.loc["ingenuo_sazonal", "mae"]
    metricas["skill"] = 1 - metricas["mae"] / base
    metricas = metricas.sort_values("mae")
    escolhido = metricas.index[0]

    # Intervalos empíricos por horizonte, a partir dos erros do modelo escolhido.
    e = erros[erros["modelo"] == escolhido]
    a = (1 - nivel) / 2
    q = e.groupby("horizonte")["erro"].quantile([a, 1 - a]).unstack()
    dentro = e.merge(q, left_on="horizonte", right_index=True)
    cobertura = float(((dentro["erro"] >= dentro[a]) & (dentro["erro"] <= dentro[1 - a])).mean())

    hist = s.loc[s.index >= INICIO_TREINO]
    pontos = MODELOS[escolhido](hist, HORIZONTE)
    datas = pd.date_range(s.index[-1] + pd.offsets.MonthBegin(1), periods=HORIZONTE, freq="MS")
    prev = pd.DataFrame(
        {
            "data": datas,
            "horizonte": range(1, HORIZONTE + 1),
            "previsto": pontos,
            "li": pontos + q[a].to_numpy(),
            "ls": pontos + q[1 - a].to_numpy(),
        }
    )

    # Trajetória do IPCA acumulado em 12 meses: realizado + previsto.
    combinado = pd.concat([s, pd.Series(pontos, index=datas)])
    prev["previsto_12m"] = acumulado_12m(combinado).loc[datas].to_numpy()
    # Banda do acumulado: erros acumulados observados no backtest para cada horizonte.
    bandas = _bandas_acumulado(e, s, a)
    prev["li_12m"] = prev["previsto_12m"] + bandas[a].reindex(prev["horizonte"]).to_numpy()
    prev["ls_12m"] = prev["previsto_12m"] + bandas[1 - a].reindex(prev["horizonte"]).to_numpy()

    metricas = metricas.reset_index()
    metricas["descricao"] = metricas["modelo"].map(DESCRICOES)
    return ResultadoPrevisao(
        modelo_escolhido=escolhido,
        metricas=metricas,
        metricas_horizonte=por_h,
        previsao=prev,
        origens_backtest=int(erros["origem"].nunique()),
        cobertura_intervalo=cobertura,
    )


def _bandas_acumulado(erros_modelo: pd.DataFrame, s: pd.Series, a: float) -> pd.DataFrame:
    """Quantis do erro do *acumulado 12m* por horizonte, a partir do backtest."""
    linhas = []
    for origem, g in erros_modelo.groupby("origem"):
        g = g.sort_values("horizonte")
        passado = s.loc[:origem]
        for _, linha in g.iterrows():
            k = int(linha["horizonte"])
            reais = pd.concat([passado, pd.Series(g["real"].iloc[:k].to_numpy(), index=g["data"].iloc[:k])])
            prevs = pd.concat([passado, pd.Series(g["previsto"].iloc[:k].to_numpy(), index=g["data"].iloc[:k])])
            r = (np.prod(1 + reais.iloc[-12:] / 100) - 1) * 100
            p = (np.prod(1 + prevs.iloc[-12:] / 100) - 1) * 100
            linhas.append({"horizonte": k, "erro": r - p})
    df = pd.DataFrame(linhas)
    return df.groupby("horizonte")["erro"].quantile([a, 1 - a]).unstack()
