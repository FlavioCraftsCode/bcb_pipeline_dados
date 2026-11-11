"""Camada de qualidade de dados.

Cada checagem devolve um :class:`ResultadoCheck` com severidade:

* ``ok``     — passou;
* ``alerta`` — anomalia registrada, mas a carga segue (ex.: outlier estatístico);
* ``falha``  — dado não confiável; a série **não** é carregada nesta execução
               (fica em quarentena e o histórico já carregado é preservado).

Os resultados são persistidos em ``dq_resultados`` e exibidos no painel.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date
from enum import Enum

import numpy as np
import pandas as pd

from .config import Periodicidade, Serie


class Status(str, Enum):
    OK = "ok"
    ALERTA = "alerta"
    FALHA = "falha"


@dataclass(frozen=True)
class ResultadoCheck:
    codigo_bcb: str
    checagem: str
    status: Status
    detalhe: str
    valor_observado: float | None = None

    def como_dict(self) -> dict:
        d = asdict(self)
        d["status"] = self.status.value
        return d


def _br(v: float, casas: int = 2) -> str:
    """Número no formato brasileiro (vírgula decimal, ponto de milhar)."""
    return f"{v:,.{casas}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _r(serie: Serie, nome: str, status: Status, detalhe: str, valor: float | None = None) -> ResultadoCheck:
    return ResultadoCheck(serie.codigo, nome, status, detalhe, None if valor is None else float(valor))


# --------------------------------------------------------------------- checks
def check_nao_vazio(df: pd.DataFrame, serie: Serie, incremental: bool) -> ResultadoCheck:
    n = len(df)
    if n > 0:
        return _r(serie, "nao_vazio", Status.OK, f"{n} linhas recebidas", n)
    # Em carga incremental, "nada novo" é normal (ex.: série mensal no meio do mês).
    status = Status.OK if incremental else Status.FALHA
    return _r(serie, "nao_vazio", status, "Nenhuma linha recebida da API", 0)


def check_nulos(df: pd.DataFrame, serie: Serie) -> ResultadoCheck:
    nulos = int(df["data"].isna().sum() + df["valor"].isna().sum())
    if nulos == 0:
        return _r(serie, "sem_nulos", Status.OK, "Nenhum valor ou data inválida", 0)
    return _r(serie, "sem_nulos", Status.FALHA, f"{nulos} datas/valores não convertidos", nulos)


def check_duplicados(df: pd.DataFrame, serie: Serie) -> ResultadoCheck:
    dup = int(df["data"].duplicated().sum())
    if dup == 0:
        return _r(serie, "sem_duplicados", Status.OK, "Uma observação por data", 0)
    return _r(serie, "sem_duplicados", Status.FALHA, f"{dup} datas repetidas", dup)


def check_faixa(df: pd.DataFrame, serie: Serie) -> ResultadoCheck:
    lo, hi = serie.faixa_valida
    fora = df[(df["valor"] < lo) | (df["valor"] > hi)]
    if fora.empty:
        return _r(serie, "faixa_valida", Status.OK, f"Todos os valores entre {_br(lo, 0)} e {_br(hi, 0)}", 0)
    exemplo = fora.iloc[0]
    return _r(
        serie,
        "faixa_valida",
        Status.FALHA,
        f"{len(fora)} valores fora de {_br(lo, 0)} a {_br(hi, 0)}"
        f" (ex.: {_br(exemplo['valor'])} em {exemplo['data']:%d/%m/%Y})",
        len(fora),
    )


def check_atualidade(ultima_data: date | None, serie: Serie, hoje: date) -> ResultadoCheck:
    if ultima_data is None:
        return _r(serie, "atualidade", Status.FALHA, "Série sem nenhuma observação")
    atraso = (hoje - ultima_data).days
    limite = serie.atraso_maximo_dias
    if atraso <= limite:
        return _r(serie, "atualidade", Status.OK, f"Último dado há {atraso} dias (limite {limite})", atraso)
    return _r(serie, "atualidade", Status.ALERTA, f"Último dado há {atraso} dias — acima do limite de {limite}", atraso)


def check_lacunas_mensais(df: pd.DataFrame, serie: Serie) -> ResultadoCheck:
    if serie.periodicidade is not Periodicidade.MENSAL or len(df) < 2:
        return _r(serie, "sem_lacunas", Status.OK, "Não se aplica")
    meses = pd.PeriodIndex(df["data"].dropna(), freq="M")
    esperado = pd.period_range(meses.min(), meses.max(), freq="M")
    faltando = esperado.difference(meses)
    if len(faltando) == 0:
        return _r(serie, "sem_lacunas", Status.OK, "Sequência mensal contínua", 0)
    return _r(
        serie,
        "sem_lacunas",
        Status.ALERTA,
        f"{len(faltando)} meses ausentes (ex.: {faltando[0].strftime('%m/%Y')})",
        len(faltando),
    )


def check_outliers(df: pd.DataFrame, serie: Serie, limiar: float = 8.0) -> ResultadoCheck:
    """Outliers nas variações via z-score robusto (mediana/MAD).

    MAD em vez de desvio-padrão porque o histórico brasileiro tem caudas
    pesadíssimas (planos econômicos); o desvio-padrão "esconderia" anomalias.
    Olha apenas as últimas 36 observações: o objetivo é flagrar dado novo estranho.
    """
    s = df.dropna(subset=["valor"]).sort_values("data")["valor"]
    if len(s) < 30:
        return _r(serie, "outliers", Status.OK, "Amostra insuficiente para teste")
    variacao = s.diff().dropna()
    base = variacao.iloc[:-36] if len(variacao) > 72 else variacao
    mediana = base.median()
    mad = (base - mediana).abs().median() * 1.4826
    if mad == 0 or np.isnan(mad):
        return _r(serie, "outliers", Status.OK, "Variação sem dispersão")
    z = ((variacao.iloc[-36:] - mediana) / mad).abs()
    n = int((z > limiar).sum())
    zmax = float(z.max())
    if n == 0:
        return _r(serie, "outliers", Status.OK, f"Nenhuma variação recente com |z| acima de {_br(limiar, 0)}", zmax)
    return _r(serie, "outliers", Status.ALERTA, f"{n} variações recentes com |z| acima de {_br(limiar, 0)}", zmax)


def check_reconciliacao_ipca(
    ipca_mensal: pd.DataFrame, ipca_12m_oficial: pd.DataFrame, serie_ref: Serie, tolerancia_pp: float = 0.05
) -> ResultadoCheck:
    """Recalcula o IPCA acumulado em 12 meses e compara com a série oficial 13522.

    Valida, de ponta a ponta, que a extração e a transformação do IPCA mensal
    estão corretas — se um mês vier errado, o acumulado diverge.
    """
    from .analise import acumulado_12m

    calc = acumulado_12m(ipca_mensal.set_index("data")["valor"]).dropna()
    ofi = ipca_12m_oficial.set_index("data")["valor"]
    comum = calc.index.intersection(ofi.index)
    comum = comum[comum >= pd.Timestamp("2000-01-01")]  # pós-Real: arredondamento estável
    if len(comum) == 0:
        return _r(serie_ref, "reconciliacao_ipca_12m", Status.ALERTA, "Sem períodos em comum para comparar")
    diff = (calc.loc[comum] - ofi.loc[comum]).abs()
    pior = float(diff.max())
    if pior <= tolerancia_pp:
        return _r(
            serie_ref,
            "reconciliacao_ipca_12m",
            Status.OK,
            f"{len(comum)} meses conferidos; maior diferença de {_br(pior, 3)} p.p.",
            pior,
        )
    data_pior = diff.idxmax()
    return _r(
        serie_ref,
        "reconciliacao_ipca_12m",
        Status.FALHA,
        f"Acumulado calculado diverge do oficial em {_br(pior, 3)} p.p. ({data_pior:%m/%Y})",
        pior,
    )


def validar_lote(
    df: pd.DataFrame,
    serie: Serie,
    *,
    incremental: bool,
    historico: pd.DataFrame | None = None,
    hoje: date | None = None,
) -> list[ResultadoCheck]:
    """Executa a bateria de checagens de uma série.

    ``df`` é o lote recém-extraído; ``historico`` é a série completa já
    combinada (banco + lote), usada nas checagens que precisam de contexto.
    """
    hoje = hoje or date.today()
    completo = historico if historico is not None else df
    ultima = completo["data"].max()
    ultima_data = None if pd.isna(ultima) else pd.Timestamp(ultima).date()
    return [
        check_nao_vazio(df, serie, incremental),
        check_nulos(df, serie),
        check_duplicados(df, serie),
        check_faixa(df.dropna(subset=["valor"]), serie),
        check_atualidade(ultima_data, serie, hoje),
        check_lacunas_mensais(completo, serie),
        check_outliers(completo, serie),
    ]


def lote_aprovado(resultados: list[ResultadoCheck]) -> bool:
    return not any(r.status is Status.FALHA for r in resultados)
